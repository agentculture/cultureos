"""cultureos-update fixes from the PR #7 review, run like tests/os/test_update_agent.py.

- Downgrade/replay: every pull carries --timestamp-check and
  --timestamp-check-from-rev=<booted>; an older, validly signed commit is refused and
  recorded as failed.
- Unclassified metadata errors are `error` (exit 2) and never touch update-state.json;
  signature failures are still recorded.
- Persistent trial-boot refusals are found by `cultureos-trialboot preflight` before the
  content pull and recorded as failed (once); transient ones stay `deferred`.
- `now --no-wait` starts the unit without blocking and returns `started`.
"""

import json
import subprocess
import sys

import pytest

from .test_trialboot_helper import NEW, OLD
from .test_update_agent import NEW2, Board

TS = {OLD: 1000, NEW: 2000, NEW2: 3000}
UNIT = "cultureos-update.service"


@pytest.fixture
def b(tmp_path):
    board = Board(tmp_path)
    w = board.load()
    w["timestamps"] = dict(TS)
    board.save()
    yield board
    board.close()


# -- finding 3: downgrade / replay ------------------------------------------------------


def test_every_pull_checks_timestamps_against_the_booted_commit(b):
    b.publish(NEW)
    assert b.agent_json("run")[1]["result"] == "staged"
    pulls = b.pulls()
    assert len(pulls) == 2
    for call in pulls:
        assert "--timestamp-check" in call
        assert f"--timestamp-check-from-rev={OLD}" in call


def test_older_signed_commit_is_refused_as_downgrade(b):
    w = b.load()
    w["timestamps"][NEW] = 500  # validly signed, but older than the booted OLD (1000)
    b.save()
    b.publish(NEW)
    rc, res = b.agent_json("run")
    assert rc == 1
    assert res["result"] == "failed"
    assert res["reason"].startswith("refused: older than booted commit (downgrade)")
    out = b.outcome()
    assert out["outcome"] == "failed"
    assert out["deployed_commit"] == NEW
    assert out["previous_commit"] == OLD
    assert b.pulls(metadata_only=False) == []  # refused before any content
    assert b.deploys() == []
    snap = b.state_snapshot()
    rc, res = b.agent_json("run")
    assert rc == 1
    assert b.state_snapshot() == snap  # same refusal, not rewritten


def test_replay_of_an_older_commit_than_the_last_fetched_is_refused(b):
    # The board already fetched NEW2 (newer); the remote is rolled back to NEW, which is
    # newer than the booted commit but older than what the local ref holds.
    w = b.load()
    w["refs"]["cultureos:ventuno-q"] = NEW2
    b.save()
    b.publish(NEW)
    rc, res = b.agent_json("run")
    assert rc == 1
    assert res["result"] == "failed"
    assert "(downgrade)" in res["reason"]
    assert b.deploys() == []


def test_newer_commit_passes_the_timestamp_check(b):
    b.publish(NEW2)
    rc, res = b.agent_json("run")
    assert rc == 0, res
    assert res["result"] == "staged"


# -- finding 6: unclassified metadata errors --------------------------------------------


def test_unclassified_metadata_error_is_error_and_keeps_the_last_outcome(b):
    b.add_check("10-ok", "exit 0")
    b.publish(NEW)
    b.agent_json("run")
    b.reboot()
    b.run("check")
    b.bless_booted()
    b.run("promote")
    assert b.outcome()["outcome"] == "applied"
    snap = b.state_snapshot()
    b.set_remote(pull_error="Corrupted metadata object; checksum expected='x' actual='y'")
    b.publish(NEW2)
    rc, res = b.agent_json("run")
    assert rc == 2
    assert res["result"] == "error"
    assert "Corrupted metadata object" in res["reason"]
    assert b.state_snapshot() == snap  # the real last outcome (applied) is kept


def test_signature_failure_is_still_recorded_with_the_commit(b):
    b.publish(NEW)
    b.set_remote(bad_signature=[NEW])
    rc, res = b.agent_json("run")
    assert rc == 1
    assert res["result"] == "failed"
    out = b.outcome()
    assert out["outcome"] == "failed"
    assert "Can't verify commit" in out["reason"]
    assert out["deployed_commit"] == NEW  # taken from ostree's message


# -- finding 5: persistent vs transient trial-boot refusals ----------------------------


def test_persistent_refusal_is_failed_before_any_content_pull(b):
    w = b.load()
    w["deployments"][0]["blessed"] = False  # bless never happened: not clearing by itself
    b.save()
    b.publish(NEW)
    rc, res = b.agent_json("run")
    assert rc == 1
    assert res["result"] == "failed"
    assert "not blessed" in res["reason"]
    assert b.pulls(metadata_only=False) == []  # no hourly re-download
    out = b.outcome()
    assert out["outcome"] == "failed"
    assert "not blessed" in out["reason"]
    assert out["deployed_commit"] is None  # a board condition, not this commit's fault
    snap = b.state_snapshot()
    for _ in range(2):
        rc, res = b.agent_json("run")
        assert rc == 1
    assert b.state_snapshot() == snap  # identical failure not rewritten each interval
    assert b.pulls(metadata_only=False) == []
    # cultureos os status reports it as degraded
    st = subprocess.run(
        [sys.executable, "-m", "cultureos", "os", "status", "--json"],
        env=b.env(CULTUREOS_OSTREE_STATUS_CMD=f"{b.tmp / 'bin' / 'ostree'} admin status --json"),
        capture_output=True,
        text=True,
    )
    assert st.returncode == 1
    # once the condition clears, the same commit is staged (not held)
    b.bless_booted()
    rc, res = b.agent_json("run")
    assert rc == 0
    assert res["result"] == "staged"


def test_booted_not_default_is_persistent(b):
    w = b.load()
    w["deployments"].append(dict(w["deployments"][0], checksum="d" * 64))
    w["booted"] = {"checksum": "d" * 64, "serial": 0}  # older entry picked by hand
    w["versions"]["d" * 64] = "0.9"
    b.save()
    b.publish(NEW)
    rc, res = b.agent_json("run")
    assert rc == 1
    assert res["result"] == "failed"
    assert "not the default" in res["reason"]
    assert b.pulls(metadata_only=False) == []


def _wrap_trialboot(b, stage_reply: dict | None) -> str:
    """A cultureos-trialboot that refuses `stage` with @stage_reply, else the real one."""
    real = b.tmp / "bin" / "cultureos-trialboot"
    p = b.tmp / "bin" / "tb-wrap"
    reply = json.dumps(stage_reply)
    p.write_text(
        "#!/bin/sh\n"
        f"if [ \"$1\" = stage ]; then echo '{reply}'; exit 1; fi\n"
        f'exec "{real}" "$@"\n'
    )
    p.chmod(0o755)
    return str(p)


def test_transient_stage_refusal_is_deferred_and_not_recorded(b):
    b.publish(NEW)
    tb = _wrap_trialboot(
        b, {"status": "refused", "kind": "transient", "reason": "a trial is already staged"}
    )
    rc, res = b.agent_json("run", CULTUREOS_UPDATE_TRIALBOOT=tb)
    assert rc == 3
    assert res["result"] == "deferred"
    assert not b.update_state.exists()


def test_persistent_stage_refusal_is_failed(b):
    b.publish(NEW)
    tb = _wrap_trialboot(
        b, {"status": "refused", "kind": "persistent", "reason": "default entry mismatch"}
    )
    rc, res = b.agent_json("run", CULTUREOS_UPDATE_TRIALBOOT=tb)
    assert rc == 1
    assert res["result"] == "failed"
    assert "default entry mismatch" in b.outcome()["reason"]


# -- finding 4: now --no-wait -----------------------------------------------------------


def test_now_no_wait_starts_the_unit_without_blocking(b):
    b.agent_json("run")  # an earlier result on file
    before = json.loads(b.result.read_text())["run_id"]
    b.publish(NEW)
    rc, res = b.agent_json("now", "--no-wait")
    assert rc == 0
    assert res["result"] == "started"
    assert res["previous_run_id"] == before
    assert res["run_id"]
    assert res["at"]
    calls = [c for c in b.load()["calls"] if c[0] == "systemctl" and "start" in c]
    assert calls == [["systemctl", "--no-ask-password", "--no-block", "start", UNIT]]
    # the run it started is visible through `status`
    rc, st = b.agent_json("status")
    assert st["result"] == "staged"
    assert st["run_id"] != before


def test_now_no_wait_reports_a_refused_start(b):
    p = b.tmp / "bin" / "deny-systemctl"
    p.write_text("#!/bin/sh\necho 'Access denied' >&2\nexit 1\n")
    p.chmod(0o755)
    rc, res = b.agent_json("now", "--no-wait", CULTUREOS_UPDATE_SYSTEMCTL=str(p))
    assert rc == 2
    assert res["result"] == "error"
    assert "Access denied" in res["reason"]


def test_now_blocking_still_works(b):
    b.publish(NEW)
    rc, res = b.agent_json("now")
    assert rc == 0
    assert res["result"] == "staged"
