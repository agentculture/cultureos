"""Offline proof for t15 acceptance 3: cultureos-trialboot never changes the default
deployment before a passing health check.

The helper runs as a real subprocess against fake ``ostree`` / ``bootctl`` /
``systemctl`` (tests/os/trialboot_fake.py) that simulate the OSTree sysroot, the
systemd-boot entries and the EFI one-shot variable. ``Machine.reboot()`` plays the
firmware and systemd-boot: it boots the LoaderEntryOneShot entry once (and clears
the variable), otherwise the default entry (index 0).

Cases: pass, health fail, health timeout, unit timeout, crash before the check,
panic before user space / one-shot ignored, deadline, stale pass record, and the
stage preconditions. Every test also checks the invariant through the fake's
``set_default_audit``: each ``ostree admin set-default`` happened while the state
held a passing health record for the current boot.
"""

import json
import os
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = (
    ROOT
    / "os"
    / "meta-cultureos"
    / "recipes-core"
    / "cultureos-trialboot"
    / "files"
    / "cultureos-trialboot"
)
FAKE = Path(__file__).with_name("trialboot_fake.py")

OLD = "a" * 64
NEW = "b" * 64
REF = "cultureos:ventuno-q"


class Machine:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.world_path = tmp / "world.json"
        self.state = tmp / "var" / "trialboot.json"
        self.update_state = tmp / "var" / "update-state.json"
        self.boot_id = tmp / "boot_id"
        self.usr_checks = tmp / "usr-health.d"
        self.etc_checks = tmp / "etc-health.d"
        for d in (self.usr_checks, self.etc_checks, tmp / "bin"):
            d.mkdir(parents=True)
        for tool in ("ostree", "bootctl", "systemctl"):
            p = tmp / "bin" / tool
            p.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" {tool} "$@"\n')
            p.chmod(0o755)
        self.world = {
            "deployments": [
                {
                    "checksum": OLD,
                    "serial": 0,
                    "stateroot": "cultureos",
                    "version": "1.0",
                    "blessed": True,
                    "kargs": "console=ttyMSM0,115200 root=LABEL=otaroot panic=5",
                }
            ],
            "booted": {"checksum": OLD, "serial": 0},
            "refs": {REF: NEW, "cultureos:old": OLD},
            "versions": {NEW: "1.1", OLD: "1.0"},
            "oneshot": None,
            "efivars_writable": True,
            "default_override": None,
            "calls": [],
            "reboots": 0,
            "set_default_audit": [],
        }
        self.save()
        self.new_boot_id()

    # -- world ---------------------------------------------------------------
    def load(self) -> dict:
        self.world = json.loads(self.world_path.read_text())
        return self.world

    def save(self) -> None:
        self.world_path.write_text(json.dumps(self.world, indent=2))

    def new_boot_id(self) -> None:
        self.boot_id.write_text(str(uuid.uuid4()) + "\n")

    def default(self) -> dict:
        return self.load()["deployments"][0]

    def calls(self, tool: str, *prefix: str) -> list[list[str]]:
        n = len(prefix)
        return [
            c[1:] for c in self.load()["calls"] if c[0] == tool and tuple(c[1 : 1 + n]) == prefix
        ]

    def reboot(self, *, honour_oneshot: bool = True, bless: bool = False) -> None:
        """Firmware + systemd-boot: boot the one-shot entry once, else the default."""
        w = self.load()
        deps = w["deployments"]
        target = deps[0]
        if w["oneshot"] and honour_oneshot:
            for i, d in enumerate(deps):
                if f"ostree-{len(deps) - i}.conf" == w["oneshot"]:
                    target = d
        w["oneshot"] = None  # systemd-boot deletes the variable when it reads it
        w["booted"] = {"checksum": target["checksum"], "serial": target["serial"]}
        if bless:
            target["blessed"] = True
        self.save()
        self.new_boot_id()

    def bless_booted(self) -> None:
        """systemd-bless-boot.service after boot-complete.target."""
        w = self.load()
        for d in w["deployments"]:
            if d["checksum"] == w["booted"]["checksum"] and d["serial"] == w["booted"]["serial"]:
                d["blessed"] = True
        self.save()

    # -- health checks -------------------------------------------------------
    def add_check(self, name: str, body: str, where: str = "usr") -> Path:
        d = self.usr_checks if where == "usr" else self.etc_checks
        p = d / name
        p.write_text("#!/bin/sh\n" + body + "\n")
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
        return p

    # -- the helper ----------------------------------------------------------
    def run(self, *args: str, **env: str) -> subprocess.CompletedProcess:
        e = dict(os.environ)
        e.update(
            {
                "TB_WORLD": str(self.world_path),
                "CULTUREOS_TRIALBOOT_OSTREE": str(self.tmp / "bin" / "ostree"),
                "CULTUREOS_TRIALBOOT_BOOTCTL": str(self.tmp / "bin" / "bootctl"),
                "CULTUREOS_TRIALBOOT_SYSTEMCTL": str(self.tmp / "bin" / "systemctl"),
                "CULTUREOS_TRIALBOOT_STATE": str(self.state),
                "CULTUREOS_UPDATE_STATE": str(self.update_state),
                "CULTUREOS_TRIALBOOT_BOOT_ID_FILE": str(self.boot_id),
                "CULTUREOS_TRIALBOOT_HEALTH_DIRS": f"{self.usr_checks}:{self.etc_checks}",
            }
        )
        e.update(env)
        return subprocess.run(
            [sys.executable, str(HELPER), *args], env=e, capture_output=True, text=True
        )

    def trial_state(self) -> dict:
        return json.loads(self.state.read_text())

    def outcome(self) -> dict:
        return json.loads(self.update_state.read_text())


@pytest.fixture
def m(tmp_path):
    machine = Machine(tmp_path)
    yield machine
    # The invariant, checked after every scenario: a set-default only ever ran
    # while a passing health record for the then-current boot existed.
    w = machine.load()
    for audit in w["set_default_audit"]:
        assert audit["health"] is not None, "set-default without any health record"
        assert audit["health"]["result"] == "pass", audit
        assert audit["health"]["boot_id"] == audit["boot_id"], audit


def _stage(m: Machine) -> None:
    r = m.run("stage", REF)
    assert r.returncode == 0, r.stderr
    assert m.default()["checksum"] == OLD


# -- stage -------------------------------------------------------------------


def test_stage_deploys_non_default_and_sets_oneshot(m):
    r = m.run("stage", REF)
    assert r.returncode == 0, r.stderr
    w = m.load()
    assert [d["checksum"] for d in w["deployments"]] == [OLD, NEW]
    assert w["deployments"][0]["checksum"] == OLD  # default unchanged
    deploy = m.calls("ostree", "admin", "deploy")
    assert len(deploy) == 1
    assert "--not-as-default" in deploy[0]
    assert "--karg=panic=5" in deploy[0]
    assert "--os=cultureos" in deploy[0]
    assert w["oneshot"] == "ostree-1.conf"  # the trial entry, not the default
    assert m.calls("ostree", "admin", "set-default") == []
    st = m.trial_state()
    assert st["status"] == "pending"
    assert st["commit"] == NEW
    assert st["previous_commit"] == OLD
    assert st["entry_id"] == "ostree-1.conf"
    assert "panic=5" in w["deployments"][1]["kargs"]
    assert json.loads(r.stdout)["entry_id"] == "ostree-1.conf"


def test_stage_reboot_flag_requests_reboot(m):
    assert m.run("stage", REF, "--reboot").returncode == 0
    assert m.load()["reboots"] == 1


def test_stage_refuses_when_booted_is_not_default(m):
    _stage(m)
    m.reboot()  # into the trial
    r = m.run("stage", "cultureos:old")
    assert r.returncode == 1
    assert "not the default" in r.stderr
    assert m.default()["checksum"] == OLD


def test_stage_refuses_unblessed_default(m):
    m.world["deployments"][0]["blessed"] = False
    m.save()
    r = m.run("stage", REF)
    assert r.returncode == 1
    assert "not blessed" in r.stderr
    assert m.calls("ostree", "admin", "deploy") == []


def test_stage_refuses_when_loader_default_differs_from_ostree(m):
    """LoaderEntryDefault (or anything else) makes systemd-boot disagree with OSTree."""
    other = dict(m.world["deployments"][0], checksum="c" * 64)
    m.world["deployments"].append(other)
    m.world["default_override"] = 1
    m.save()
    r = m.run("stage", REF)
    assert r.returncode == 1
    assert "does not match" in r.stderr
    assert m.calls("ostree", "admin", "deploy") == []


def test_stage_refuses_the_running_commit(m):
    r = m.run("stage", "cultureos:old")
    assert r.returncode == 1
    assert "already" in r.stderr
    assert m.calls("ostree", "admin", "deploy") == []


def test_stage_unknown_ref_is_an_error(m):
    r = m.run("stage", "cultureos:nope")
    assert r.returncode == 2
    assert m.calls("ostree", "admin", "deploy") == []


def test_stage_oneshot_write_failure_leaves_default(m):
    m.world["efivars_writable"] = False
    m.save()
    r = m.run("stage", REF)
    assert r.returncode == 2
    assert "LoaderEntryOneShot" in r.stderr
    assert m.default()["checksum"] == OLD
    assert m.trial_state()["status"] == "failed"
    m.reboot()
    assert m.default()["checksum"] == OLD
    assert m.load()["booted"]["checksum"] == OLD


# -- the four outcomes -------------------------------------------------------


def test_pass_promotes_after_health_check(m):
    m.add_check("10-ok", "exit 0")
    _stage(m)
    m.reboot()
    assert m.load()["booted"]["checksum"] == NEW
    assert m.default()["checksum"] == OLD  # booted once, still not default

    # promote before the health check ran: refused, default unchanged
    r = m.run("promote")
    assert r.returncode == 1
    assert m.default()["checksum"] == OLD

    r = m.run("check")
    assert r.returncode == 0, r.stderr
    assert m.default()["checksum"] == OLD  # the check itself never promotes
    m.bless_booted()
    r = m.run("promote")
    assert r.returncode == 0, r.stderr
    assert m.default()["checksum"] == NEW
    assert m.trial_state()["status"] == "applied"
    out = m.outcome()
    assert out["outcome"] == "applied"
    assert out["deployed_commit"] == NEW
    assert out["previous_commit"] == OLD
    assert out["deployed_version"] == "1.1"
    assert m.load()["reboots"] == 0

    # next boot lands on the promoted deployment, nothing left to do
    m.reboot()
    assert m.load()["booted"]["checksum"] == NEW
    assert m.run("check").returncode == 0
    assert m.run("promote").returncode == 0
    assert len(m.calls("ostree", "admin", "set-default")) == 1


def test_health_fail_reboots_and_rolls_back(m):
    m.add_check("10-ok", "exit 0")
    m.add_check("20-culture", "echo 'culture daemon not running' >&2; exit 3")
    _stage(m)
    m.reboot()
    r = m.run("check")
    assert r.returncode == 1
    assert m.load()["reboots"] == 1
    assert m.run("promote").returncode == 1
    assert m.default()["checksum"] == OLD

    m.reboot()  # one-shot already consumed: the old default boots
    assert m.load()["booted"]["checksum"] == OLD
    r = m.run("check")  # normal boot: reconciles, never fails the unit
    assert r.returncode == 0, r.stderr
    st = m.trial_state()
    assert st["status"] == "rolled-back"
    assert "20-culture" in st["reason"]
    assert "culture daemon not running" in st["reason"]
    assert [d["checksum"] for d in m.load()["deployments"]] == [OLD]  # trial undeployed
    out = m.outcome()
    assert out["outcome"] == "rolled-back"
    assert out["deployed_commit"] == NEW
    assert out["previous_commit"] == OLD
    assert m.calls("ostree", "admin", "set-default") == []


def test_health_timeout_reboots_and_rolls_back(m):
    m.add_check("10-hangs", "sleep 30")
    _stage(m)
    m.reboot()
    r = m.run("check", CULTUREOS_TRIALBOOT_CHECK_TIMEOUT="1")
    assert r.returncode == 1
    assert m.load()["reboots"] == 1
    assert "timed out" in m.trial_state()["health"]["reason"]
    assert m.run("promote").returncode == 1
    m.reboot()
    assert m.run("check").returncode == 0
    assert m.trial_state()["status"] == "rolled-back"
    assert m.default()["checksum"] == OLD
    assert m.calls("ostree", "admin", "set-default") == []


def test_overall_health_budget(m):
    m.add_check("10-slow", "sleep 2")
    m.add_check("20-slow", "sleep 2")
    _stage(m)
    m.reboot()
    r = m.run("check", CULTUREOS_TRIALBOOT_TIMEOUT="1")
    assert r.returncode == 1
    assert "timed out" in m.trial_state()["health"]["reason"]
    assert m.default()["checksum"] == OLD


def test_crash_before_check_rolls_back(m):
    """Panic or hang on the trial after user space started but before the check
    finished: the watchdog or panic=N resets the board; nothing ran promote."""
    m.add_check("10-ok", "exit 0")
    _stage(m)
    m.reboot()
    assert m.load()["booted"]["checksum"] == NEW
    # (crash here: no check, no promote)
    m.reboot()
    assert m.load()["booted"]["checksum"] == OLD
    assert m.run("check").returncode == 0
    st = m.trial_state()
    assert st["status"] == "rolled-back"
    assert "never reached" in st["reason"] or "did not finish" in st["reason"]
    assert m.default()["checksum"] == OLD
    assert m.calls("ostree", "admin", "set-default") == []


def test_check_records_trial_reached_user_space(m):
    m.add_check("10-hangs", "sleep 30")
    _stage(m)
    m.reboot()
    # the check started (trial reached user space), then the board hung and reset
    m.run("check", CULTUREOS_TRIALBOOT_CHECK_TIMEOUT="1")
    w = m.load()
    w["reboots"] = 0
    m.save()
    m.reboot()
    m.run("check")
    st = m.trial_state()
    assert st["status"] == "rolled-back"
    assert "timed out" in st["reason"]


def test_crash_in_trial_before_user_space(m):
    """Kernel panic on the trial before systemd: panic=N reboots, the one-shot is
    gone, the old default boots, and the helper reports it."""
    _stage(m)
    m.reboot()  # trial kernel starts, panics: no helper command runs
    m.reboot()
    assert m.load()["booted"]["checksum"] == OLD
    assert m.run("check").returncode == 0
    st = m.trial_state()
    assert st["status"] == "rolled-back"
    assert "never reached" in st["reason"]
    assert "LoaderEntryOneShot" in st["reason"]
    assert m.default()["checksum"] == OLD


def test_oneshot_ignored_by_firmware(m):
    _stage(m)
    m.reboot(honour_oneshot=False)
    assert m.load()["booted"]["checksum"] == OLD
    assert m.run("check").returncode == 0
    assert m.run("promote").returncode == 0
    st = m.trial_state()
    assert st["status"] == "rolled-back"
    assert "LoaderEntryOneShot" in st["reason"]
    assert m.default()["checksum"] == OLD
    assert m.calls("ostree", "admin", "set-default") == []


# -- backstops ----------------------------------------------------------------


def test_health_unit_timeout_backstop(m):
    """systemd killed the check (TimeoutStartSec) before it wrote a result."""
    _stage(m)
    m.reboot()
    r = m.run("health-exit", SERVICE_RESULT="timeout", EXIT_CODE="killed", EXIT_STATUS="TERM")
    assert r.returncode == 0
    assert m.load()["reboots"] == 1
    h = m.trial_state()["health"]
    assert h["result"] == "fail"
    assert "timeout" in h["reason"]
    assert m.run("promote").returncode == 1
    assert m.default()["checksum"] == OLD


def test_health_exit_noop_after_pass_and_on_normal_boot(m):
    assert m.run("health-exit", SERVICE_RESULT="success").returncode == 0
    m.add_check("10-ok", "exit 0")
    _stage(m)
    m.reboot()
    assert m.run("check").returncode == 0
    assert m.run("health-exit", SERVICE_RESULT="success").returncode == 0
    assert m.load()["reboots"] == 0


def test_deadline_reboots_unpromoted_trial(m):
    _stage(m)
    m.reboot()
    assert m.run("deadline").returncode == 0
    assert m.load()["reboots"] == 1
    assert m.trial_state()["health"]["result"] == "fail"
    assert m.run("promote").returncode == 1
    assert m.default()["checksum"] == OLD


def test_deadline_noop_on_normal_and_promoted_boots(m):
    assert m.run("deadline").returncode == 0
    m.add_check("10-ok", "exit 0")
    _stage(m)
    m.reboot()
    m.run("check")
    m.run("promote")
    assert m.run("deadline").returncode == 0
    assert m.load()["reboots"] == 0


def test_stale_pass_from_another_boot_does_not_promote(m):
    m.add_check("10-ok", "exit 0")
    _stage(m)
    m.reboot()
    assert m.run("check").returncode == 0
    m.new_boot_id()  # same deployment, new boot: the old pass does not count
    r = m.run("promote")
    assert r.returncode == 1
    assert m.default()["checksum"] == OLD


def test_pass_for_another_commit_does_not_promote(m):
    m.add_check("10-ok", "exit 0")
    _stage(m)
    m.reboot()
    assert m.run("check").returncode == 0
    st = m.trial_state()
    st["health"]["commit"] = OLD
    m.state.write_text(json.dumps(st))
    assert m.run("promote").returncode == 1
    assert m.default()["checksum"] == OLD


def test_manual_boot_of_non_default_is_not_a_trial(m):
    """Choosing the older entry in the boot menu must not promote it."""
    m.add_check("10-ok", "exit 0")
    _stage(m)
    m.reboot()
    m.run("check")
    m.run("promote")
    assert m.default()["checksum"] == NEW
    w = m.load()
    w["booted"] = {"checksum": OLD, "serial": 0}  # picked from the menu
    m.save()
    m.new_boot_id()
    assert m.run("check").returncode == 0
    assert m.run("promote").returncode == 0
    assert m.run("deadline").returncode == 0
    assert m.default()["checksum"] == NEW
    assert m.load()["reboots"] == 0


# -- normal boots and check directories --------------------------------------


def test_check_on_normal_boot_runs_no_checks(m):
    marker = m.tmp / "ran"
    m.add_check("10-fail", f"touch {marker}; exit 1")
    r = m.run("check")
    assert r.returncode == 0
    assert not marker.exists()


def test_reconcile_waits_for_the_reboot(m):
    """Right after stage (same boot) a re-run of check must not call it a rollback."""
    _stage(m)
    assert m.run("check").returncode == 0
    assert m.trial_state()["status"] == "pending"
    assert len(m.load()["deployments"]) == 2


def test_etc_overrides_and_masks_usr_checks(m):
    m.add_check("10-net", "exit 1", where="usr")
    m.add_check("10-net", "exit 0", where="etc")  # override
    m.add_check("20-bad", "exit 1", where="usr")
    (m.etc_checks / "20-bad").symlink_to("/dev/null")  # mask
    (m.usr_checks / "30-not-executable").write_text("exit 1\n")
    _stage(m)
    m.reboot()
    r = m.run("check")
    assert r.returncode == 0, r.stderr
    m.bless_booted()
    assert m.run("promote").returncode == 0
    assert m.default()["checksum"] == NEW


def test_no_checks_installed_fails(m):
    """An image without health checks must not promote silently (PR #7 review)."""
    _stage(m)
    m.reboot()
    assert m.run("check").returncode == 1
    assert "no health checks installed" in m.trial_state()["health"]["reason"]
    assert m.run("promote").returncode == 1
    assert m.default()["checksum"] == OLD


def test_status_prints_state(m):
    r = m.run("status")
    assert r.returncode == 0
    assert json.loads(r.stdout)["status"] == "none"
    _stage(m)
    assert json.loads(m.run("status").stdout)["status"] == "pending"


def test_usage_errors(m):
    assert m.run().returncode == 1
    assert m.run("bogus").returncode == 1
    assert m.run("stage").returncode == 1


def test_missing_ostree_is_environment_error(m):
    r = m.run("stage", REF, CULTUREOS_TRIALBOOT_OSTREE=str(m.tmp / "nope"))
    assert r.returncode == 2
