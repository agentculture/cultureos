"""release-step.sh's board steps after the PR #7 review (findings 2 and 4).

- `publish` prints the published OSTree commit: the release's target.
- `trigger` only starts the board's update unit (`cultureos-update now --no-wait`).
- `status <target> <trigger json> <wait>` polls the board until the target is booted AND
  the default (success), or a terminal outcome for it (failure), within the budget.

The board is an ssh stub that answers `cultureos os status --json` and
`cultureos-update status --json` from a script of replies (the last reply repeats).
"""

import json
from pathlib import Path

import pytest

from .test_release_workflow import _calls, _step, env  # noqa: F401  (fixture)

TARGET = "b" * 64
OLD = "a" * 64
OTHER = "c" * 64
STARTED = json.dumps({"result": "started", "exit_code": 0, "run_id": "s", "previous_run_id": "p0"})

SSH_STUB = r"""
import json, os, sys
args = " ".join(sys.argv[1:])
key = "os" if "cultureos os status" in args else "upd" if "cultureos-update status" in args \
    else "now"
path = os.environ["BOARD_SCRIPT"]
w = json.load(open(path))
replies = w[key]
out, rc = replies.pop(0) if len(replies) > 1 else replies[0]
json.dump(w, open(path, "w"))
print(out)
sys.exit(rc)
"""


def _board(env, os_replies, upd_replies, now=(STARTED, 0)):  # noqa: F811
    script = env["tmp"] / "board.json"
    script.write_text(json.dumps({"os": os_replies, "upd": upd_replies, "now": [list(now)]}))
    stub = env["tmp"] / "board_ssh.py"
    stub.write_text(SSH_STUB)
    ssh = env["tmp"] / "stubs" / "ssh"
    calls = env["calls"]
    ssh.write_text(f'#!/usr/bin/env bash\necho "ssh $*" >> "{calls}"\nexec python3 "{stub}" "$@"\n')
    ssh.chmod(0o755)
    return {"BOARD_SCRIPT": script}


def _os(booted, default, outcome="applied", deployed=None, reason=None, rc=None):
    doc = {
        "healthy": outcome in ("applied", "none"),
        "booted": {"commit": booted},
        "deployments": [{"commit": default}, *([{"commit": booted}] if booted != default else [])],
        "outcome": outcome,
        "last_update": {"deployed_commit": deployed, "reason": reason},
    }
    return [json.dumps(doc), rc if rc is not None else (0 if doc["healthy"] else 1)]


def _upd(result, commit=TARGET, run_id="r1", reason=None):
    return [json.dumps({"result": result, "commit": commit, "run_id": run_id, "reason": reason}), 0]


NONE = _upd("none", commit=None, run_id="fresh-every-time")
STALE_HELD = _upd("held", commit=OTHER, run_id="p0", reason="old")


def _status(env, board, wait=600):  # noqa: F811
    return _step(env, "status", TARGET, STARTED, str(wait), **board)


# -- success: booted and default ---------------------------------------------------------


def test_applied_after_staging_trial_and_promotion(env):  # noqa: F811
    board = _board(
        env,
        [
            _os(OLD, OLD),  # pulling
            _os(OLD, OLD),  # staged, rebooting
            _os(TARGET, OLD, outcome="none"),  # trial boot: booted, NOT yet the default
            _os(TARGET, TARGET, deployed=TARGET),  # promoted
        ],
        [STALE_HELD, _upd("staged"), NONE, NONE],
    )
    proc = _status(env, board)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["booted"]["commit"] == TARGET
    polls = [c for c in _calls(env) if "cultureos os status" in c]
    assert len(polls) == 4  # the trial boot itself was not taken for success


def test_board_already_running_the_target_succeeds(env):  # noqa: F811
    board = _board(env, [_os(TARGET, TARGET)], [_upd("up-to-date")])
    assert _status(env, board).returncode == 0


def test_a_stale_result_from_before_the_trigger_is_ignored(env):  # noqa: F811
    board = _board(env, [_os(OLD, OLD), _os(TARGET, TARGET)], [STALE_HELD])
    assert _status(env, board).returncode == 0


# -- failure: nothing applied is never success ------------------------------------------


@pytest.mark.parametrize(
    ("reply", "code", "text"),
    [
        (_upd("held", reason="rolled back here before"), 1, "rolled back here before"),
        (_upd("failed", reason="Can't verify commit"), 1, "verify"),
        (_upd("failed", commit=None, reason="cannot stage updates: not blessed"), 1, "blessed"),
        (_upd("error", reason="metadata pull failed"), 2, "metadata"),
        (_upd("unreachable", reason="cannot reach spark"), 3, "cannot reach"),
        (_upd("up-to-date", commit=OTHER), 1, "not the release target"),
        (_upd("staged", commit=OTHER), 1, "not the release target"),
    ],
)
def test_terminal_board_results_fail_the_step(env, reply, code, text):  # noqa: F811
    board = _board(env, [_os(OLD, OLD)], [reply])
    proc = _status(env, board)
    assert proc.returncode == code, proc.stderr
    assert proc.stderr.startswith(f"status failed (exit {code}): ")
    assert text in proc.stderr
    assert proc.stdout == ""


def test_rollback_of_the_target_fails(env):  # noqa: F811
    board = _board(
        env,
        [_os(OLD, OLD, outcome="rolled-back", deployed=TARGET, reason="20-tailscale exited 1")],
        [NONE],
    )
    proc = _status(env, board)
    assert proc.returncode == 1
    assert "rolled-back" in proc.stderr
    assert "20-tailscale" in proc.stderr


def test_pending_and_staged_keep_polling_until_the_budget(env):  # noqa: F811
    board = _board(env, [_os(OLD, OLD)], [_upd("pending")])
    proc = _status(env, board, wait=0)
    assert proc.returncode == 3
    assert "no final outcome" in proc.stderr
    assert "pending" in proc.stderr


def test_unreachable_board_times_out(env):  # noqa: F811
    board = _board(env, [["ssh: no route", 255]], [["ssh: no route", 255]])
    proc = _status(env, board, wait=0)
    assert proc.returncode == 3
    assert "no final outcome" in proc.stderr


@pytest.mark.parametrize("target", ["", "abc", "B" * 64, "-x"])
def test_status_refuses_a_bad_target(env, target):  # noqa: F811
    proc = _step(env, "status", target, STARTED, "60", **_board(env, [_os(OLD, OLD)], [NONE]))
    assert proc.returncode != 0
    assert "target" in proc.stderr


# -- trigger and publish ------------------------------------------------------------------


def test_trigger_does_not_wait_for_the_update(env):  # noqa: F811
    board = _board(env, [_os(OLD, OLD)], [NONE])
    proc = _step(env, "trigger", **board)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["result"] == "started"
    assert "cultureos-update now --no-wait --json" in _calls(env)[0]


def test_publish_prints_the_published_commit(env):  # noqa: F811
    ostree = Path(env["env"]["PUBLISH_SH"]).with_name("ostree")
    ostree.write_text(f'#!/usr/bin/env bash\necho "ostree $*" >> "{env["calls"]}"\necho {TARGET}\n')
    ostree.chmod(0o755)
    proc = _step(env, "publish", OSTREE=ostree, CULTUREOS_RELEASE_REPO="/srv/repo")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == TARGET
    assert "ostree rev-parse --repo=/srv/repo ventuno-q" in _calls(env)


def test_publish_fails_without_a_commit(env):  # noqa: F811
    ostree = Path(env["env"]["PUBLISH_SH"]).with_name("ostree")
    ostree.write_text("#!/usr/bin/env bash\necho 'error: Refspec not found' >&2\nexit 1\n")
    ostree.chmod(0o755)
    proc = _step(env, "publish", OSTREE=ostree)
    assert proc.returncode != 0
    assert proc.stdout == ""
