"""Offline tests for the culture-rules release rule/workflow (plan task t18).

Three layers: the exported JSON (structure, no secrets), the step wrapper
os/scripts/release-step.sh (stubs for bb.sh, bundle, publish and ssh), and, when a
culture-rules checkout is available, culture-rules' own validator and in-memory engine
(release_sim.py) to show a failed step stops the run before the board step.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXPORT = ROOT / "os" / "release" / "culture-rules"
SCRIPT = ROOT / "os" / "scripts" / "release-step.sh"
ORDER = ["sync", "build", "bundle", "publish", "notify", "status"]


def _load(rel: str) -> dict:
    return json.loads((EXPORT / rel).read_text())


WORKFLOW = _load("workflows/cultureos-release.json")
ACTOR = _load("actors/spark-cultureos-release.json")
RULE = _load("rules/cultureos-release.json")


# ---------------------------------------------------------------- the exported files


def test_export_layout_and_ids_match_file_names():
    for kind, doc in (("actors", ACTOR), ("workflows", WORKFLOW), ("rules", RULE)):
        assert (EXPORT / kind / f"{doc['id']}.json").is_file()
        assert doc["schema_version"] == "1.0"


def test_steps_are_in_pipeline_order_and_placed_on_spark():
    assert [s["id"] for s in WORKFLOW["steps"]] == ORDER
    for s in WORKFLOW["steps"]:
        assert s["kind"] == "code"
        assert s["placement"] == {"machine": "spark"}
        assert s["config"]["builtin"] == "action"
        assert s["config"]["action"]["kind"] == "machine.command"
        assert s["config"]["action"]["params"]["actor"] == ACTOR["id"]
    assert ACTOR["machine"] == "spark"
    assert ACTOR["kind"] == "runner"
    assert RULE["placement"]["machine"] == "spark"


def test_every_step_runs_a_registered_command_and_none_is_skippable():
    commands = ACTOR["params"]["commands"]
    for s in WORKFLOW["steps"]:
        cfg = s["config"]
        assert cfg["action"]["params"]["command"] in commands
        assert "on_error" not in cfg  # on_error "skip" would let the run continue past a failure
        assert "when" not in cfg
        assert s["retry"] is None
        assert s["enabled"] is True


def test_each_step_waits_for_the_previous_one_through_an_edge():
    edges = {(e["source"], e["target"], e["target_port"]) for e in WORKFLOW["edges"]}
    for prev, nxt in zip(ORDER[:3], ORDER[1:4]):
        assert (prev, nxt, "after") in edges
    assert ("publish", "notify", "after") in edges
    # the outcome step reads the board trigger's JSON, so it cannot run before it
    assert ("notify", "status", "update_json") in edges
    ports = {s["id"]: {p["name"] for p in s["inputs"]} for s in WORKFLOW["steps"]}
    for e in WORKFLOW["edges"]:
        if e["target"] != "outputs":
            assert e["target_port"] in ports[e["target"]]


def test_board_steps_call_the_documented_commands_and_outputs_record_them():
    cmds = ACTOR["params"]["commands"]
    assert cmds["release_trigger"]["argv"][1:] == ["trigger"]
    assert cmds["release_status"]["params"] == {"update_json": "string", "wait_s": "int"}
    sources = {o["name"]: o["source"] for o in WORKFLOW["outputs"]}
    assert sources["update"] == "steps.notify.outputs.stdout"
    assert sources["board_status"] == "steps.status.outputs.stdout"
    assert sources["commit"] == "steps.sync.outputs.stdout"
    assert sources["bundle"] == "steps.bundle.outputs.stdout"


def test_rule_ships_disabled_and_maps_event_data_to_inputs():
    assert RULE["enabled"] is False
    assert RULE["trigger"] == {"kind": "event", "params": {"type": "cultureos.release.requested"}}
    assert RULE["workflow"]["id"] == WORKFLOW["id"]
    assert RULE["workflow"]["inputs"] == {
        "ref": "trigger.data.ref",
        "version": "trigger.data.version",
    }
    assert RULE["concurrency_key"]  # one release at a time


def test_no_secrets_or_user_paths_in_the_export():
    text = "".join(p.read_text() for p in EXPORT.rglob("*.json"))
    assert not re.search(r"BEGIN [A-Z ]*PRIVATE KEY|ghp_|tskey-|\.secret\b|/home/", text)
    assert ACTOR["params"]["commands"]["release_sync"]["argv"][0].startswith("/REPLACE-WITH-")


# ---------------------------------------------------------------- culture-rules itself


def _culture_rules_src() -> Path | None:
    for cand in (os.environ.get("CULTURE_RULES_SRC"), str(Path.home() / "git" / "culture-rules")):
        if cand and (Path(cand) / "culture_rules" / "io" / "exchange.py").is_file():
            return Path(cand)
    return None


needs_cr = pytest.mark.skipif(_culture_rules_src() is None, reason="no culture-rules checkout")


def _cr(args: list[str]) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(_culture_rules_src())}
    return subprocess.run(
        [sys.executable, "-P", *args], capture_output=True, text=True, check=False, env=env
    )


@needs_cr
def test_culture_rules_validator_accepts_the_export():
    code = (
        "import sys; from culture_rules.io.exchange import read_bundle; "
        "r = read_bundle(sys.argv[1]); "
        "print(len(r.bundle.actors), len(r.bundle.workflows), len(r.bundle.rules)); "
        "[print(e) for e in r.errors]; sys.exit(1 if r.errors else 0)"
    )
    proc = _cr(["-c", code, str(EXPORT)])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.split() == ["1", "1", "1"]


@needs_cr
def test_a_failed_step_stops_the_run_before_the_board_trigger():
    proc = _cr([str(ROOT / "tests" / "os" / "release_sim.py"), str(EXPORT)])
    assert proc.returncode == 0, proc.stderr
    sims = json.loads(proc.stdout)
    ok = sims["ok"]
    assert ok["status"] == "succeeded"
    assert ok["ran"] == ORDER
    assert set(ok["hosts"]) == {"spark"}
    assert ok["args"][0] == {"ref": "origin/main"}
    assert ok["args"][2] == {"version": "0.12.0"}
    # the board's JSON is handed to the outcome step and recorded in the run outputs
    assert ok["args"][5] == {"update_json": "out:release_trigger", "wait_s": 1200}
    assert ok["outputs"]["update"] == "out:release_trigger"
    assert ok["outputs"]["board_status"] == "out:release_status"
    for failing in ORDER:
        run = sims[failing]
        assert run["status"] == "failed"
        assert run["ran"] == ORDER[: ORDER.index(failing) + 1]
    for failing in ("sync", "build", "bundle", "publish"):
        assert "notify" not in sims[failing]["ran"]
        assert "status" not in sims[failing]["ran"]


# ---------------------------------------------------------------- the step wrapper


@pytest.fixture
def env(tmp_path):
    """A git clone with the wrapper inside, plus stub programs and a log of their calls."""
    origin = tmp_path / "origin"
    clone = tmp_path / "clone"
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run([*git, "init", "-q", "-b", "main", str(origin)], check=True)
    (origin / "f").write_text("1")
    subprocess.run([*git, "-C", str(origin), "add", "f"], check=True)
    subprocess.run([*git, "-C", str(origin), "commit", "-q", "-m", "one"], check=True)
    subprocess.run([*git, "clone", "-q", str(origin), str(clone)], check=True)
    (clone / "os" / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, clone / "os" / "scripts" / "release-step.sh")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    calls = tmp_path / "calls"

    def stub(name: str, body: str) -> str:
        p = stubs / name
        p.write_text(f'#!/usr/bin/env bash\necho "{name} $*" >> "{calls}"\n{body}\n')
        p.chmod(0o755)
        return str(p)

    e = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path / "home"),
        "CULTUREOS_RELEASE_CONF": str(tmp_path / "none.env"),
        "BB_SH": stub("bb", "echo building; exit ${BB_RC:-0}"),
        "BUNDLE_SH": stub("bundle", "echo bundling; exit ${BUNDLE_RC:-0}"),
        "PUBLISH_SH": stub("publish", "echo signing; exit ${PUBLISH_RC:-0}"),
        "SSH": stub("ssh", 'cat "$SSH_SCRIPT"; exit "$(cat "$SSH_SCRIPT.rc")"'),
        "SLEEP": stub("sleep", "true"),
    }
    return {"clone": clone, "env": e, "calls": calls, "tmp": tmp_path, "git": git, "origin": origin}


def _step(env, *args, **extra):
    e = {**env["env"], **{k: str(v) for k, v in extra.items()}}
    script = env["clone"] / "os" / "scripts" / "release-step.sh"
    return subprocess.run(["bash", str(script), *args], capture_output=True, text=True, env=e)


def _board(env, out: str, rc: int = 0):
    p = env["tmp"] / "board.out"
    p.write_text(out)
    Path(f"{p}.rc").write_text(str(rc))
    return {"SSH_SCRIPT": p}


def _calls(env) -> list[str]:
    return env["calls"].read_text().splitlines() if env["calls"].exists() else []


def test_sync_checks_out_the_ref_and_prints_the_sha(env):
    proc = _step(env, "sync", "origin/main")
    assert proc.returncode == 0, proc.stderr
    sha = subprocess.run(
        ["git", "-C", str(env["clone"]), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    assert proc.stdout.strip() == sha


@pytest.mark.parametrize("ref", ["--upload-pack=x", "a b", "nope-not-a-ref"])
def test_sync_refuses_bad_or_unknown_refs(env, ref):
    proc = _step(env, "sync", ref)
    assert proc.returncode != 0


def test_sync_refuses_a_dirty_checkout(env):
    (env["clone"] / "f").write_text("dirty")
    proc = _step(env, "sync", "origin/main")
    assert proc.returncode != 0
    assert "local changes" in proc.stderr


def test_build_bundle_publish_pass_through_and_log(env):
    assert _step(env, "build").returncode == 0
    proc = _step(env, "bundle", "0.12.0")
    assert proc.returncode == 0
    assert proc.stdout.strip().endswith("cultureos-release-0.12.0.tar")
    assert _step(env, "publish").stdout.strip() == "published"
    calls = _calls(env)
    assert calls[0] == f"bb {env['clone']}"
    assert re.fullmatch(r"bundle \S+/build/tmp/deploy \S+/cultureos-release 0\.12\.0", calls[1])
    assert calls[2] == "publish "
    assert list((env["tmp"] / "home" / "cultureos-release" / "logs").glob("build-*.log"))


@pytest.mark.parametrize(
    ("step", "args", "rc_var"),
    [("build", [], "BB_RC"), ("bundle", ["1"], "BUNDLE_RC"), ("publish", [], "PUBLISH_RC")],
)
def test_a_failing_tool_fails_the_step_with_its_code_and_log(env, step, args, rc_var):
    proc = _step(env, step, *args, **{rc_var: 7})
    assert proc.returncode == 7
    assert proc.stderr.startswith(f"{step} failed (exit 7); log: ")
    assert proc.stdout == ""


def test_bundle_refuses_a_bad_version(env):
    assert _step(env, "bundle", "../x").returncode != 0
    assert _calls(env) == []


JSON_STAGED = (
    '{"result":"staged","exit_code":0,"commit":"abc","version":"1","reboot_in":30,"run_id":"r"}'
)


def test_trigger_prints_the_boards_json_and_targets_the_tailnet_name(env):
    proc = _step(env, "trigger", **_board(env, JSON_STAGED + "\n"))
    assert proc.returncode == 0
    assert proc.stdout.strip() == JSON_STAGED
    assert "arduino@cultureos cultureos-update now --json" in _calls(env)[0]


def test_trigger_failure_keeps_the_boards_json_in_stderr(env):
    failed = '{"result":"failed","exit_code":1,"commit":"abc","reason":"verify"}'
    proc = _step(env, "trigger", **_board(env, failed + "\n", 1))
    assert proc.returncode == 1
    assert proc.stderr.startswith("trigger failed (exit 1): ")
    assert failed in proc.stderr


def test_trigger_board_is_configurable(env):
    _step(env, "trigger", CULTUREOS_BOARD="me@board", **_board(env, "{}"))
    assert "me@board cultureos-update now --json" in _calls(env)[0]


def _status_json(commit: str, outcome: str, deployed: str) -> str:
    return json.dumps(
        {
            "healthy": outcome in ("applied", "none"),
            "booted": {"commit": commit},
            "outcome": outcome,
            "last_update": {"deployed_commit": deployed},
        }
    )


def test_status_after_staged_update_waits_and_reports_applied(env):
    out = _status_json("abc", "applied", "abc")
    proc = _step(env, "status", JSON_STAGED, "60", **_board(env, out))
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["outcome"] == "applied"
    assert "arduino@cultureos cultureos os status --json" in _calls(env)[-1]


def test_status_reports_a_rollback_as_a_failed_step(env):
    out = _status_json("old", "rolled-back", "abc")
    proc = _step(env, "status", JSON_STAGED, "60", **_board(env, out, 1))
    assert proc.returncode == 1
    assert "rolled back abc" in proc.stderr
    assert "rolled-back" in proc.stderr


def test_status_times_out_when_the_board_never_answers(env):
    proc = _step(env, "status", JSON_STAGED, "0", **_board(env, "ssh: no route", 255))
    assert proc.returncode == 3
    assert "no final outcome" in proc.stderr


def test_status_without_a_staged_update_reads_the_board_once(env):
    up_to_date = '{"result":"up-to-date","exit_code":0,"commit":"abc"}'
    out = _status_json("abc", "applied", "abc")
    proc = _step(env, "status", up_to_date, "60", **_board(env, out))
    assert proc.returncode == 0
    assert len(_calls(env)) == 1
