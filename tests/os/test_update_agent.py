"""Offline proof for the cultureos-update agent (t16).

The agent runs as a real subprocess against fake ``ostree`` / ``systemctl`` /
``systemd-run`` (tests/os/update_fake.py) and the REAL cultureos-trialboot helper (t15),
which itself runs against t15's fake ``bootctl``. The reachability probe connects to a
listening (or closed) socket on loopback, so nothing leaves the machine.

- Acceptance 1: ``now`` is the push path (it starts the unit, which runs ``run``);
  repeated checks with no new commit are no-ops (exit 0, no download, no state change).
- Acceptance 2: a new commit is pulled and handed to ``cultureos-trialboot stage``; the
  agent writes ``failed`` to update-state.json for verify / download / stage errors,
  the helper writes ``applied`` / ``rolled-back``.
- Acceptance 3: with the push path never used, the timer alone stages a new commit
  within one interval of the shipped timer, on a simulated clock.
"""

import configparser
import importlib.util
import json
import os
import random
import re
import socket
import subprocess
import sys
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from .test_trialboot_helper import HELPER, NEW, OLD, Machine

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / "os" / "meta-cultureos" / "recipes-core" / "cultureos-update-agent" / "files"
AGENT = FILES / "cultureos-update"
TIMER = FILES / "cultureos-update.timer"
FAKE = Path(__file__).with_name("update_fake.py")

NEW2 = "c" * 64
URL = "http://spark.tail0be7e0.ts.net:8650/"
REF = "cultureos:ventuno-q"


def _load_agent():
    loader = SourceFileLoader("cultureos_update_agent", str(AGENT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


class Board(Machine):
    """t15's simulated machine plus the release remote and the update agent."""

    def __init__(self, tmp: Path):
        super().__init__(tmp)
        bindir = tmp / "bin"
        for name, tool in (
            ("ostree", "ostree"),
            ("systemd-run", "systemd-run"),
            ("upd-systemctl", "systemctl"),
        ):
            p = bindir / name
            p.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" {tool} "$@"\n')
            p.chmod(0o755)
        p = bindir / "cultureos-trialboot"
        p.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{HELPER}" "$@"\n')
        p.chmod(0o755)
        w = self.load()
        w["refs"] = {"cultureos:old": OLD}  # nothing pulled from the remote yet
        w["versions"][NEW2] = "1.2"
        w["remote"] = {
            "url": URL,
            "branches": {"ventuno-q": OLD},
            "bad_signature": [],
            "pull_error": None,
            "content_error": None,
            "pull_sleep": 0,
        }
        self.save()
        self.result = tmp / "run" / "cultureos-update" / "result.json"
        self.lock = tmp / "run" / "cultureos-update.lock"
        self._server = socket.socket()
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(64)
        self.up_addr = "127.0.0.1:%d" % self._server.getsockname()[1]
        closed = socket.socket()
        closed.bind(("127.0.0.1", 0))
        self.down_addr = "127.0.0.1:%d" % closed.getsockname()[1]
        closed.close()
        self.network_up = True

    def close(self) -> None:
        self._server.close()

    def publish(self, commit: str) -> None:
        w = self.load()
        w["remote"]["branches"]["ventuno-q"] = commit
        self.save()

    def set_remote(self, **kv) -> None:
        w = self.load()
        w["remote"].update(kv)
        self.save()

    def env(self, **extra: str) -> dict:
        bindir = self.tmp / "bin"
        e = dict(os.environ)
        e.update(
            {
                "TB_WORLD": str(self.world_path),
                "CULTUREOS_TRIALBOOT_OSTREE": str(bindir / "ostree"),
                "CULTUREOS_TRIALBOOT_BOOTCTL": str(bindir / "bootctl"),
                "CULTUREOS_TRIALBOOT_SYSTEMCTL": str(bindir / "systemctl"),
                "CULTUREOS_TRIALBOOT_STATE": str(self.state),
                "CULTUREOS_UPDATE_STATE": str(self.update_state),
                "CULTUREOS_TRIALBOOT_BOOT_ID_FILE": str(self.boot_id),
                "CULTUREOS_TRIALBOOT_HEALTH_DIRS": f"{self.usr_checks}:{self.etc_checks}",
                "CULTUREOS_UPDATE_OSTREE": str(bindir / "ostree"),
                "CULTUREOS_UPDATE_TRIALBOOT": str(bindir / "cultureos-trialboot"),
                "CULTUREOS_UPDATE_SYSTEMCTL": str(bindir / "upd-systemctl"),
                "CULTUREOS_UPDATE_SYSTEMD_RUN": str(bindir / "systemd-run"),
                "CULTUREOS_UPDATE_RESULT": str(self.result),
                "CULTUREOS_UPDATE_LOCK": str(self.lock),
                "CULTUREOS_UPDATE_PROBE_ADDR": self.up_addr if self.network_up else self.down_addr,
                "CULTUREOS_UPDATE_PROBE_TIMEOUT": "2",
                "CULTUREOS_UPDATE_TAILNET_CIDRS": "100.64.0.0/10,fd7a:115c:a1e0::/48,127.0.0.0/8",
                "UPD_AGENT_CMD": json.dumps([sys.executable, str(AGENT)]),
            }
        )
        e.update(extra)
        return e

    def agent(self, *args: str, clock: float | None = None, **extra: str):
        if clock is not None:
            extra["CULTUREOS_UPDATE_NOW"] = repr(clock)
        return subprocess.run(
            [sys.executable, str(AGENT), *args],
            env=self.env(**extra),
            capture_output=True,
            text=True,
        )

    def agent_json(self, *args: str, **kw) -> tuple[int, dict]:
        r = self.agent(*args, "--json", **kw)
        lines = r.stdout.splitlines()
        assert len(lines) == 1, (r.stdout, r.stderr)  # one machine-readable line
        return r.returncode, json.loads(lines[0])

    def deploys(self) -> list:
        return self.calls("ostree", "admin", "deploy")

    def pulls(self, metadata_only: bool | None = None) -> list:
        out = self.calls("ostree", "pull")
        if metadata_only is None:
            return out
        return [c for c in out if ("--commit-metadata-only" in c) == metadata_only]

    def state_snapshot(self):
        p = self.update_state
        return (p.read_bytes(), p.stat().st_mtime_ns) if p.exists() else None


@pytest.fixture
def b(tmp_path):
    board = Board(tmp_path)
    yield board
    board.close()


# -- acceptance 1: push entrypoint, idempotent ------------------------------------


def test_now_with_no_new_commit_is_a_noop_every_time(b):
    for _ in range(3):
        rc, res = b.agent_json("now")
        assert rc == 0
        assert res["result"] == "up-to-date"
        assert res["commit"] == OLD
        assert res["booted_commit"] == OLD
    w = b.load()
    assert w.get("unit_starts") == ["cultureos-update.service"] * 3  # through the unit
    assert b.pulls(metadata_only=False) == []  # never downloaded content
    assert b.deploys() == []
    assert not b.update_state.exists()  # no state change
    assert w.get("scheduled") is None


def test_now_stages_a_new_commit_then_repeats_are_noops(b):
    b.publish(NEW)
    rc, res = b.agent_json("now")
    assert rc == 0, res
    assert res["result"] == "staged"
    assert res["commit"] == NEW
    assert res["version"] == "1.1"
    assert res["booted_commit"] == OLD
    assert res["reboot_in"] == 30
    w = b.load()
    assert [d["checksum"] for d in w["deployments"]] == [OLD, NEW]  # default unchanged
    assert w["oneshot"] == "ostree-1.conf"
    assert w["partial"] == []  # content pulled in full before the deploy
    assert len(b.pulls(metadata_only=True)) == 1
    assert len(b.pulls(metadata_only=False)) == 1
    (sched,) = w["scheduled"]
    assert "--on-active=30s" in sched
    assert sched[-2:] == ["systemctl", "reboot"]
    assert b.trial_state()["status"] == "pending"
    assert not b.update_state.exists()  # stage itself is not an outcome

    for _ in range(2):
        rc, res = b.agent_json("now")
        assert rc == 0
        assert res["result"] == "pending"
        assert res["commit"] == NEW
    assert len(b.deploys()) == 1
    assert len(b.load()["scheduled"]) == 1
    assert len(b.pulls()) == 2  # a pending trial is checked before any network access


def test_now_text_output_is_one_line(b):
    b.publish(NEW)
    r = b.agent("now")
    assert r.returncode == 0, r.stderr
    (line,) = r.stdout.splitlines()
    assert line.startswith("staged: " + NEW[:12] + " (1.1): reboot in 30 s")


def test_reboot_can_be_disabled(b):
    b.publish(NEW)
    rc, res = b.agent_json("run", CULTUREOS_UPDATE_REBOOT="no")
    assert rc == 0
    assert res["result"] == "staged"
    assert res["reboot_in"] is None
    assert "reboot disabled" in res["reason"]
    assert b.load().get("scheduled") is None


def test_now_reports_the_service_not_running_as_environment_error(b):
    rc, res = b.agent_json("now", UPD_AGENT_CMD=json.dumps(["true"]))
    assert rc == 2
    assert res["result"] == "error"
    assert "did not run" in res["reason"]


def test_status_prints_the_last_result(b):
    rc, res = b.agent_json("status")
    assert rc == 0
    assert res["result"] == "none"
    b.agent_json("now")
    rc, res = b.agent_json("status")
    assert rc == 0
    assert res["result"] == "up-to-date"


def test_concurrent_checks_serialize_on_the_lock(b):
    b.publish(NEW)
    b.set_remote(pull_sleep=0.5)
    procs = [
        subprocess.Popen(
            [sys.executable, str(AGENT), "run", "--json"],
            env=b.env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    outs = [p.communicate(timeout=120) for p in procs]
    results = sorted(json.loads(o[0])["result"] for o in outs)
    assert [p.returncode for p in procs] == [0, 0], outs
    assert results == ["pending", "staged"]
    assert len(b.deploys()) == 1


# -- acceptance 2: handoff to the trial-boot helper, update-state.json ------------


def test_full_cycle_applied_then_up_to_date(b):
    b.publish(NEW)
    assert b.agent_json("run")[1]["result"] == "staged"
    b.reboot()  # the scheduled reboot: one-shot trial boot
    assert b.agent_json("run")[1]["result"] == "pending"  # trial running, not promoted yet
    assert b.run("check").returncode == 0
    b.bless_booted()
    assert b.run("promote").returncode == 0
    out = b.outcome()
    assert out["outcome"] == "applied"
    assert out["deployed_commit"] == NEW
    snap = b.state_snapshot()
    rc, res = b.agent_json("run")
    assert rc == 0
    assert res["result"] == "up-to-date"
    assert res["booted_commit"] == NEW
    assert b.state_snapshot() == snap


def test_rolled_back_commit_is_held_not_retried(b):
    b.publish(NEW)
    assert b.agent_json("run")[1]["result"] == "staged"
    b.reboot(honour_oneshot=False)  # the trial never came up
    assert b.run("check").returncode == 0  # reconciles: rolled back
    assert b.outcome()["outcome"] == "rolled-back"
    snap = b.state_snapshot()
    for _ in range(2):
        rc, res = b.agent_json("run")
        assert rc == 0
        assert res["result"] == "held"
        assert res["commit"] == NEW
    assert len(b.deploys()) == 1  # no failure loop
    assert b.state_snapshot() == snap
    # a newer release is staged as usual
    b.publish(NEW2)
    rc, res = b.agent_json("run")
    assert rc == 0
    assert res["result"] == "staged"
    assert res["commit"] == NEW2


def test_retry_overrides_hold(b):
    b.publish(NEW)
    b.agent_json("run")
    b.reboot(honour_oneshot=False)
    b.run("check")
    rc, res = b.agent_json("run", "--retry")
    assert rc == 0
    assert res["result"] == "staged"


def test_bad_signature_records_failed_once(b):
    b.publish(NEW)
    b.set_remote(bad_signature=[NEW])
    rc, res = b.agent_json("run")
    assert rc == 1
    assert res["result"] == "failed"
    assert "Can't verify commit" in res["reason"]
    assert "ed25519" in res["reason"]
    out = b.outcome()
    assert out["outcome"] == "failed"
    assert out["reason"] == res["reason"]
    assert out["previous_commit"] == OLD
    assert out["schema_version"] == 1
    assert out["timestamp"]
    assert b.deploys() == []
    snap = b.state_snapshot()
    rc, res = b.agent_json("run")
    assert rc == 1
    assert res["result"] == "failed"
    assert b.state_snapshot() == snap  # the same failure is not rewritten
    # `cultureos os status` reports it: degraded, exit 1
    st = subprocess.run(
        [sys.executable, "-m", "cultureos", "os", "status", "--json"],
        env=b.env(CULTUREOS_OSTREE_STATUS_CMD=f"{b.tmp / 'bin' / 'ostree'} admin status --json"),
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert st.returncode == 1, st.stderr
    assert json.loads(st.stdout)["outcome"] == "failed"


def test_stage_error_records_failed_then_holds(b):
    b.publish(NEW)
    w = b.load()
    w["efivars_writable"] = False
    b.save()
    rc, res = b.agent_json("run")
    assert rc == 1
    assert res["result"] == "failed"
    assert "LoaderEntryOneShot" in res["reason"]
    out = b.outcome()
    assert out["outcome"] == "failed"
    assert out["deployed_commit"] == NEW
    assert out["deployed_version"] == "1.1"
    assert out["previous_commit"] == OLD
    snap = b.state_snapshot()
    rc, res = b.agent_json("run")
    assert rc == 0
    assert res["result"] == "held"
    assert len(b.deploys()) == 1
    assert b.state_snapshot() == snap


def test_content_pull_error_records_failed_with_commit(b):
    b.publish(NEW)
    b.set_remote(content_error="Writing content object: No space left on device")
    rc, res = b.agent_json("run")
    assert rc == 1
    assert res["result"] == "failed"
    out = b.outcome()
    assert out["deployed_commit"] == NEW
    assert "No space left" in out["reason"]
    assert b.deploys() == []


def test_helper_refusal_is_deferred_not_failed(b):
    w = b.load()
    w["deployments"][0]["blessed"] = False  # default not blessed yet
    b.save()
    b.publish(NEW)
    rc, res = b.agent_json("run")
    assert rc == 3
    assert res["result"] == "deferred"
    assert "not blessed" in res["reason"]
    assert not b.update_state.exists()
    b.bless_booted()
    rc, res = b.agent_json("run")
    assert rc == 0
    assert res["result"] == "staged"


# -- network / Tailscale down: retry next interval, never `failed` ----------------


def test_unreachable_remote_is_deferred_without_pulling(b):
    b.publish(NEW)
    b.network_up = False
    rc, res = b.agent_json("run")
    assert rc == 3
    assert res["result"] == "unreachable"
    assert "cannot reach" in res["reason"]
    assert b.pulls() == []
    assert not b.update_state.exists()
    # through the push path the unit does not fail (SuccessExitStatus=3)
    rc, res = b.agent_json("now")
    assert rc == 3
    assert res["result"] == "unreachable"
    b.network_up = True
    rc, res = b.agent_json("run")
    assert rc == 0
    assert res["result"] == "staged"


@pytest.mark.parametrize(
    "error, where",
    [
        (
            "While fetching http://spark.tail0be7e0.ts.net:8650/config: [6] Could not resolve "
            "hostname",
            "pull_error",
        ),
        (
            "While fetching http://spark.tail0be7e0.ts.net:8650/config: [7] Couldn't connect "
            "to server",
            "pull_error",
        ),
        (
            "While fetching http://spark.tail0be7e0.ts.net:8650/objects/ab/cd.filez: [28] "
            "Timeout was reached",
            "content_error",
        ),
        (
            "While fetching http://spark.tail0be7e0.ts.net:8650/summary: Server returned "
            "HTTP 502",
            "pull_error",
        ),
    ],
)
def test_network_errors_during_pull_are_deferred(b, error, where):
    b.publish(NEW)
    b.set_remote(**{where: error})
    rc, res = b.agent_json("run")
    assert rc == 3 and res["result"] == "unreachable", res
    assert not b.update_state.exists()
    assert b.deploys() == []
    b.set_remote(**{where: None})
    rc, res = b.agent_json("run")
    assert rc == 0
    assert res["result"] == "staged"


def test_probe_peer_off_the_tailnet_counts_as_unreachable(b):
    b.publish(NEW)
    rc, res = b.agent_json("run", CULTUREOS_UPDATE_TAILNET_CIDRS="100.64.0.0/10")
    assert rc == 3
    assert res["result"] == "unreachable"
    assert "not a tailnet address" in res["reason"]
    assert b.pulls() == []


@pytest.mark.parametrize(
    "url", ["https://example.com/repo/", "http://203.0.113.5:8650/", "file:///srv/repo"]
)
def test_remote_off_the_tailnet_is_refused(b, url):
    b.set_remote(url=url)
    b.publish(NEW)
    rc, res = b.agent_json("run")
    assert rc == 2
    assert res["result"] == "error"
    assert b.pulls() == []


def test_only_the_cultureos_remote_and_branch_are_pulled(b):
    b.publish(NEW)
    b.agent_json("run")
    for call in b.pulls():
        assert [a for a in call if not a.startswith("--")] == ["pull", "cultureos", "ventuno-q"]
    assert b.calls("ostree", "remote", "show-url") == [["remote", "show-url", "cultureos"]]


def test_run_without_a_usable_lock_is_an_environment_error(b):
    rc, res = b.agent_json("run", CULTUREOS_UPDATE_LOCK="/proc/no-such-dir/x.lock")
    assert rc == 2
    assert "now" in res["reason"]


# -- pure functions -----------------------------------------------------------------


def test_classify_pull_error():
    agent = _load_agent()
    assert agent.classify_pull_error("error: While fetching u: [6] Couldn't resolve") == "network"
    assert agent.classify_pull_error("error: While fetching u: [22] HTTP 404") == "other"
    assert agent.classify_pull_error("Server returned HTTP 404") == "other"
    assert agent.classify_pull_error("Server returned HTTP 503") == "network"
    assert agent.classify_pull_error("Commit x: No signatures found") == "verify"
    assert agent.classify_pull_error("Can't verify commit without detached metadata") == ("verify")
    assert agent.classify_pull_error("Corrupted file object") == "other"


def test_tailnet_address_ranges(monkeypatch):
    agent = _load_agent()
    monkeypatch.delenv("CULTUREOS_UPDATE_TAILNET_CIDRS", raising=False)
    assert agent._on_tailnet("100.101.102.103")
    assert agent._on_tailnet("fd7a:115c:a1e0::1")
    assert not agent._on_tailnet("192.168.1.10")
    assert not agent._on_tailnet("8.8.8.8")
    assert not agent._on_tailnet("spark.tail0be7e0.ts.net")


def test_remote_and_branch_are_the_recipe_substitution_points():
    text = AGENT.read_text()
    assert re.search(r'^REMOTE = "cultureos"$', text, re.M)
    assert re.search(r'^BRANCH = "ventuno-q"$', text, re.M)
    assert "CULTUREOS_UPDATE_REMOTE" not in text
    assert "CULTUREOS_UPDATE_BRANCH" not in text


# -- acceptance 3: the timer path alone, on a simulated clock ----------------------


def _timer() -> tuple[int, int]:
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read_string(TIMER.read_text())
    t = cp["Timer"]
    interval = {"minutely": 60, "hourly": 3600, "daily": 86400}[t["OnCalendar"]]
    m = re.fullmatch(r"(\d+)\s*(s|min)", t["RandomizedDelaySec"])
    delay = int(m.group(1)) * (60 if m.group(2) == "min" else 1)
    # With FixedRandomDelay the per-board offset is the same every time, so
    # consecutive runs are exactly one OnCalendar interval apart.
    assert t["FixedRandomDelay"] == "true"
    assert t["AccuracySec"] == "1s"
    assert t["Persistent"] == "true"
    assert delay < interval
    return interval, delay


def _simulate(b: Board, interval: int, offset: float, t_pub: float, down_until: float = -1):
    """Fire the timer at k * interval + offset, starting at the last run before the
    commit is published; the remote gets NEW at t_pub. Returns the stage time."""
    k = int((t_pub - offset) // interval)
    for step in range(k, k + 4):
        t = step * interval + offset
        if t >= t_pub:
            b.publish(NEW)
        b.network_up = t >= down_until
        rc, res = b.agent_json("run", clock=t)
        assert res["at"] == _iso(t)  # the injected clock
        if res["result"] == "staged":
            return t
        assert res["result"] in ("up-to-date", "unreachable"), res
        assert rc in (0, 3)
    raise AssertionError("never staged")


@pytest.mark.parametrize("seed", range(4))
def test_timer_alone_stages_within_one_interval(b, seed):
    interval, delay = _timer()
    rng = random.Random(seed)
    offset = rng.uniform(0, delay)
    t_pub = rng.uniform(10 * interval, 20 * interval)
    staged_at = _simulate(b, interval, offset, t_pub)
    assert 0 <= staged_at - t_pub <= interval
    assert b.load().get("unit_starts") is None  # the push path was never used
    assert b.trial_state()["status"] == "pending"


def test_timer_worst_case_publish_just_after_a_run(b):
    interval, delay = _timer()
    offset = delay  # latest possible per-board offset
    t_pub = 7 * interval + offset + 0.001
    staged_at = _simulate(b, interval, offset, t_pub)
    assert staged_at == 8 * interval + offset
    assert staged_at - t_pub <= interval


def test_timer_retries_next_interval_when_network_was_down(b):
    interval, delay = _timer()
    offset = delay / 2
    t_pub = 3 * interval + offset - 10
    first_run_after = 3 * interval + offset
    staged_at = _simulate(b, interval, offset, t_pub, down_until=first_run_after + 1)
    assert staged_at == first_run_after + interval  # one interval later, not never
    assert not b.update_state.exists()  # unreachability is never recorded as failed
