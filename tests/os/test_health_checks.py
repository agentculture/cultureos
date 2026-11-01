"""The shipped trial-boot health checks and the gate's refusal contract (PR #7 review).

- Each check in cultureos-trialboot's ``health.d`` runs against stub ``systemctl``,
  ``tailscale`` and ``sleep`` on PATH (driven by a JSON file), so polling is instant.
- The real helper refuses to pass a trial when no check is installed.
- ``stage`` / ``preflight`` refusals carry a machine-readable kind (transient/persistent).
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from .test_trialboot_helper import NEW, OLD, REF, Machine

ROOT = Path(__file__).resolve().parents[2]
RECIPE_DIR = ROOT / "os" / "meta-cultureos" / "recipes-core" / "cultureos-trialboot"
HEALTH_D = RECIPE_DIR / "files" / "health.d"
CHECKS = ("10-sshd", "20-tailscale", "30-culture-node")

STUB = r"""
import json, os, sys
path = os.environ["HC_WORLD"]
w = json.load(open(path))
tool, args = sys.argv[1], sys.argv[2:]
w.setdefault("calls", []).append([tool, *args])

def pop(seq):
    return seq.pop(0) if len(seq) > 1 else seq[0]

rc = 0
if tool == "systemctl":
    verb = args[0]
    unit = [a for a in args[1:] if not a.startswith("-")][0]
    if verb == "is-active":
        state = pop(w["active"].setdefault(unit, ["inactive"]))
        if "--quiet" not in args:
            print(state)
        rc = 0 if state == "active" else 3
    elif verb == "is-enabled":
        state = w.get("enabled", {}).get(unit, "enabled")
        print(state)
        rc = 0 if state == "enabled" else 1
elif tool == "tailscale":
    ip = pop(w.setdefault("ip4", [""]))
    if ip:
        print(ip)
    else:
        print("no current Tailscale IPs; state: NeedsLogin", file=sys.stderr)
        rc = 1
json.dump(w, open(path, "w"))
sys.exit(rc)
"""


class Stubs:
    def __init__(self, tmp: Path):
        self.world = tmp / "hc.json"
        self.bin = tmp / "hcbin"
        self.bin.mkdir(parents=True)
        stub = tmp / "hc_stub.py"
        stub.write_text(STUB)
        for tool in ("systemctl", "tailscale"):
            p = self.bin / tool
            p.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{stub}" {tool} "$@"\n')
            p.chmod(0o755)
        sleep = self.bin / "sleep"
        sleep.write_text("#!/bin/sh\nexit 0\n")
        sleep.chmod(0o755)
        self.set(active={}, ip4=[""])

    def set(self, **w) -> None:
        self.world.write_text(json.dumps(w))

    def calls(self) -> list:
        return json.loads(self.world.read_text()).get("calls", [])

    def env(self) -> dict:
        return {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "HC_WORLD": str(self.world),
            "CULTUREOS_HEALTH_WAIT": "10",
            "CULTUREOS_HEALTH_POLL": "2",
        }

    def run(self, check: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(HEALTH_D / check)], env=self.env(), capture_output=True, text=True, timeout=30
        )


@pytest.fixture
def s(tmp_path):
    return Stubs(tmp_path)


# -- the stubs ---------------------------------------------------------------------


def test_stub_reports_tool_names(s):
    s.set(active={"x.service": ["active"]})
    r = subprocess.run(
        ["systemctl", "is-active", "x.service"], env=s.env(), capture_output=True, text=True
    )
    assert r.stdout.strip() == "active"


# -- 10-sshd ---------------------------------------------------------------------------


@pytest.mark.parametrize("unit", ["sshd.socket", "sshd.service"])
def test_sshd_passes_when_socket_or_service_active(s, unit):
    s.set(active={unit: ["active"]})
    r = s.run("10-sshd")
    assert r.returncode == 0, r.stderr


def test_sshd_waits_for_the_socket(s):
    s.set(active={"sshd.socket": ["inactive", "inactive", "active"]})
    assert s.run("10-sshd").returncode == 0


def test_sshd_fails_after_the_wait(s):
    s.set(active={})
    r = s.run("10-sshd")
    assert r.returncode == 1
    assert "sshd.socket" in r.stderr
    polls = [c for c in s.calls() if c[:2] == ["systemctl", "is-active"]]
    assert len(polls) >= 2  # it polled, it did not give up at once


# -- 20-tailscale ----------------------------------------------------------------------


def test_tailscale_passes_with_daemon_and_tailnet_address(s):
    s.set(active={"tailscaled.service": ["active"]}, ip4=["100.101.102.103"])
    r = s.run("20-tailscale")
    assert r.returncode == 0, r.stderr
    assert "100.101.102.103" in r.stdout


def test_tailscale_fails_when_logged_out(s):
    s.set(active={"tailscaled.service": ["active"]}, ip4=[""])
    r = s.run("20-tailscale")
    assert r.returncode == 1
    assert "no tailnet IPv4" in r.stderr


def test_tailscale_fails_when_daemon_down(s):
    s.set(active={"tailscaled.service": ["failed"]}, ip4=["100.101.102.103"])
    r = s.run("20-tailscale")
    assert r.returncode == 1
    assert "tailscaled.service is failed" in r.stderr


def test_tailscale_waits_for_the_address(s):
    s.set(active={"tailscaled.service": ["activating", "active"]}, ip4=["", "", "100.64.0.9"])
    assert s.run("20-tailscale").returncode == 0


# -- 30-culture-node -------------------------------------------------------------------


def test_culture_node_passes_when_active_and_stays_active(s):
    s.set(active={"culture-node.service": ["active"]})
    r = s.run("30-culture-node")
    assert r.returncode == 0, r.stderr


def test_culture_node_failed_fails_at_once(s):
    s.set(active={"culture-node.service": ["failed"]})
    r = s.run("30-culture-node")
    assert r.returncode == 1
    assert "failed" in r.stderr
    polls = [c for c in s.calls() if c[:2] == ["systemctl", "is-active"]]
    assert len(polls) == 1


def test_culture_node_crash_after_start_is_not_a_pass(s):
    # active, then gone by the settle re-check, then stuck restarting
    s.set(active={"culture-node.service": ["active", "activating"]})
    r = s.run("30-culture-node")
    assert r.returncode == 1
    assert "activating" in r.stderr


def test_culture_node_waits_through_startup(s):
    s.set(active={"culture-node.service": ["activating", "activating", "active"]})
    assert s.run("30-culture-node").returncode == 0


@pytest.mark.parametrize("state", ["disabled", "masked"])
def test_culture_node_disabled_by_operator_is_skipped(s, state):
    s.set(active={"culture-node.service": ["inactive"]}, enabled={"culture-node.service": state})
    r = s.run("30-culture-node")
    assert r.returncode == 0
    assert "not checked" in r.stdout


# -- the contract: budgets, no multi-user.target, packaged ------------------------------


def test_check_waits_fit_the_helpers_budgets():
    per_check, total = 120, 300  # cultureos-trialboot defaults (docs/os/rollback.md)
    waits = []
    for name in CHECKS:
        text = (HEALTH_D / name).read_text()
        assert text.startswith("#!/bin/sh\n")
        assert os.access(HEALTH_D / name, os.X_OK)
        wait = int(re.search(r"CULTUREOS_HEALTH_WAIT:-(\d+)", text).group(1))
        settle = re.search(r"CULTUREOS_HEALTH_SETTLE:-(\d+)", text)
        wait += int(settle.group(1)) if settle else 0
        assert wait < per_check, name
        code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
        assert "multi-user.target" not in code  # never wait for it: cycle with promote
        assert "is-system-running" not in code
        waits.append(wait)
    assert sum(waits) < total


def test_recipe_installs_the_checks():
    text = (RECIPE_DIR / "cultureos-trialboot.bb").read_text()
    for name in CHECKS:
        assert f"file://health.d/{name}" in text
    assert "${nonarch_libdir}/cultureos/health.d/" in text
    assert re.search(r"install -m 0755 \$\{S\}/health\.d/\$\{?check\}? ", text)


def test_shipped_checks_gate_a_real_trial(tmp_path):
    """The real helper with the shipped health.d: a trial that lost the tailnet is not
    promoted; the same trial with everything up is."""
    stubs = Stubs(tmp_path / "s")
    m = Machine(tmp_path / "m")
    env = {
        "PATH": stubs.env()["PATH"],
        "HC_WORLD": str(stubs.world),
        "CULTUREOS_HEALTH_WAIT": "4",
        "CULTUREOS_TRIALBOOT_HEALTH_DIRS": f"{HEALTH_D}:{m.etc_checks}",
    }
    up = {"sshd.socket": ["active"], "tailscaled.service": ["active"]}
    up["culture-node.service"] = ["active"]
    stubs.set(active=up, ip4=[""])  # logged out of the tailnet
    assert m.run("stage", REF).returncode == 0
    m.reboot()
    r = m.run("check", **env)
    assert r.returncode == 1
    assert "20-tailscale" in m.trial_state()["health"]["reason"]
    assert m.run("promote", **env).returncode == 1
    assert m.default()["checksum"] == OLD

    m.reboot()
    m.run("check", **env)  # reconcile the rollback
    assert m.trial_state()["status"] == "rolled-back"
    stubs.set(active=up, ip4=["100.64.0.7"])
    assert m.run("stage", REF).returncode == 0
    m.reboot()
    r = m.run("check", **env)
    assert r.returncode == 0, r.stderr
    m.bless_booted()
    assert m.run("promote", **env).returncode == 0
    assert m.default()["checksum"] == NEW


# -- the helper: no checks is a fail; refusal kinds --------------------------------------


@pytest.fixture
def m(tmp_path):
    return Machine(tmp_path)


def test_no_checks_installed_fails_the_trial(m):
    assert m.run("stage", REF).returncode == 0
    m.reboot()
    r = m.run("check")
    assert r.returncode == 1
    reason = m.trial_state()["health"]["reason"]
    assert "no health checks installed" in reason
    assert m.load()["reboots"] == 1
    assert m.run("promote").returncode == 1
    assert m.default()["checksum"] == OLD


def _refusal(r: subprocess.CompletedProcess) -> dict:
    assert r.returncode == 1, r.stderr
    (line,) = r.stdout.splitlines()
    out = json.loads(line)
    assert out["status"] == "refused"
    return out


def test_preflight_ok(m):
    r = m.run("preflight")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {"status": "ok"}
    assert m.calls("ostree", "admin", "deploy") == []


def test_already_staged_is_transient(m):
    assert m.run("stage", REF).returncode == 0
    for cmd in (["preflight"], ["stage", REF]):
        out = _refusal(m.run(*cmd))
        assert out["kind"] == "transient"
        assert "already staged" in out["reason"]


def test_unblessed_default_is_persistent(m):
    m.world["deployments"][0]["blessed"] = False
    m.save()
    for cmd in (["preflight"], ["stage", REF]):
        out = _refusal(m.run(*cmd))
        assert out["kind"] == "persistent"
        assert "not blessed" in out["reason"]
    assert m.calls("ostree", "admin", "deploy") == []


def test_loader_default_mismatch_is_persistent(m):
    other = dict(m.world["deployments"][0], checksum="c" * 64)
    m.world["deployments"].append(other)
    m.world["default_override"] = 1
    m.save()
    out = _refusal(m.run("preflight"))
    assert out["kind"] == "persistent"
    assert "does not match" in out["reason"]


def test_booted_not_default_is_persistent(m):
    m.world["deployments"].append(dict(m.world["deployments"][0], checksum="c" * 64))
    m.world["booted"] = {"checksum": "c" * 64, "serial": 0}  # older entry picked by hand
    m.save()
    out = _refusal(m.run("preflight"))
    assert out["kind"] == "persistent"
    assert "not the default" in out["reason"]
