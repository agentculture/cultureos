"""Offline tests for os/scripts/bb.sh, the shared, flock-serialized build wrapper.

kas-container is replaced by a stub on PATH; nothing here runs a container,
bitbake, or touches the network.
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "os" / "scripts" / "bb.sh"

STUB = r"""#!/usr/bin/env bash
# Stub kas-container: record argv + relevant env as one JSON line, hold for
# $STUB_SLEEP seconds so overlapping runs would be visible.
start=$(date +%s.%N)
sleep "${STUB_SLEEP:-0}"
end=$(date +%s.%N)
python3 - "$start" "$end" "$@" >> "$STUB_LOG" <<'PY'
import json, os, sys
keys = ("KAS_WORK_DIR", "KAS_BUILD_DIR", "DL_DIR", "SSTATE_DIR")
print(json.dumps({"start": float(sys.argv[1]), "end": float(sys.argv[2]),
                  "argv": sys.argv[3:], "env": {k: os.environ.get(k) for k in keys}}))
PY
exit "${STUB_RC:-0}"
"""


def _worktree(tmp_path: Path, name: str) -> Path:
    wt = tmp_path / name
    (wt / "os" / "kas").mkdir(parents=True)
    (wt / "os" / "kas" / "cultureos.yml").write_text("header:\n  version: 14\n")
    (wt / "os" / "meta-cultureos" / "conf").mkdir(parents=True)
    (wt / "os" / "meta-cultureos" / "conf" / "layer.conf").write_text("")
    return wt


@pytest.fixture
def env(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "kas-container"
    stub.write_text(STUB)
    stub.chmod(0o755)
    log = tmp_path / "stub.log"
    return {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "STUB_LOG": str(log),
        "CULTUREOS_BUILD_ROOT": str(tmp_path / "build-root"),
        "CULTUREOS_CACHE_DIR": str(tmp_path / "cache"),
    }


def _calls(env) -> list[dict]:
    path = Path(env["STUB_LOG"])
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _run(env, *args, **extra):
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        env={**env, **extra},
        capture_output=True,
        text=True,
        check=False,
    )


def test_script_is_static_safe():
    text = SCRIPT.read_text()
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text
    assert "flock" in text
    assert "sudo " not in text


def test_no_args_is_usage_error(env):
    proc = _run(env)
    assert proc.returncode == 1
    assert "usage" in proc.stderr.lower()
    assert _calls(env) == []


def test_help_exits_zero(env):
    proc = _run(env, "--help")
    assert proc.returncode == 0
    assert "usage" in proc.stdout.lower()


def test_rejects_non_worktree(env, tmp_path):
    proc = _run(env, str(tmp_path / "nope"), "cultureos-image")
    assert proc.returncode == 1
    assert "os/kas/cultureos.yml" in proc.stderr
    assert _calls(env) == []


def test_missing_kas_container_is_env_error(env, tmp_path):
    wt = _worktree(tmp_path, "wt")
    proc = _run(env, str(wt), CULTUREOS_KAS_CONTAINER=str(tmp_path / "missing"))
    assert proc.returncode == 2
    assert "kas-container" in proc.stderr


def test_default_runs_kas_build_with_shared_dirs(env, tmp_path):
    wt = _worktree(tmp_path, "wt")
    proc = _run(env, str(wt))
    assert proc.returncode == 0, proc.stderr
    (call,) = _calls(env)
    assert call["argv"][0] == "build"
    assert call["argv"][-1] == str(wt / "os" / "kas" / "cultureos.yml")
    root = tmp_path / "build-root"
    assert call["env"] == {
        "KAS_WORK_DIR": str(root),
        "KAS_BUILD_DIR": str(root / "build"),
        "DL_DIR": str(tmp_path / "cache" / "downloads"),
        "SSTATE_DIR": str(tmp_path / "cache" / "sstate-cache"),
    }
    for d in ("downloads", "sstate-cache"):
        assert (tmp_path / "cache" / d).is_dir()


def test_bitbake_args_pass_through_quoted(env, tmp_path):
    wt = _worktree(tmp_path, "wt")
    proc = _run(env, str(wt), "-c", "compile", "my recipe")
    assert proc.returncode == 0, proc.stderr
    (call,) = _calls(env)
    argv = call["argv"]
    # the caller's worktree is mounted read-only into the build container
    assert argv[:2] == ["--repo-ro", "shell"]
    cmd = argv[argv.index("-c") + 1]
    assert cmd == "bitbake -c compile my\\ recipe"
    assert argv[-1] == str(wt / "os" / "kas" / "cultureos.yml")


def test_kas_subcommand_mode(env, tmp_path):
    wt = _worktree(tmp_path, "wt")
    proc = _run(env, str(wt), "--kas", "dump", "--lock")
    assert proc.returncode == 0, proc.stderr
    (call,) = _calls(env)
    assert call["argv"] == ["dump", "--lock", str(wt / "os" / "kas" / "cultureos.yml")]


def test_extra_kas_configs_are_appended(env, tmp_path):
    wt = _worktree(tmp_path, "wt")
    (wt / "os" / "kas" / "mirror.yml").write_text("header:\n  version: 14\n")
    proc = _run(env, str(wt), CULTUREOS_KAS_CONFIG="os/kas/cultureos.yml:os/kas/mirror.yml")
    assert proc.returncode == 0, proc.stderr
    (call,) = _calls(env)
    kas = wt / "os" / "kas"
    assert call["argv"][-1] == f"{kas / 'cultureos.yml'}:{kas / 'mirror.yml'}"


def test_exit_code_propagates(env, tmp_path):
    wt = _worktree(tmp_path, "wt")
    proc = _run(env, str(wt), "cultureos-image", STUB_RC="3")
    assert proc.returncode == 3


def test_concurrent_runs_are_serialized(env, tmp_path):
    """Two worktrees build at once: the second waits for the lock, neither fails."""
    a, b = _worktree(tmp_path, "wt-a"), _worktree(tmp_path, "wt-b")
    run_env = {**env, "STUB_SLEEP": "1.5"}
    procs = [
        subprocess.Popen(
            ["bash", str(SCRIPT), str(wt), "cultureos-image"],
            env=run_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for wt in (a, b)
    ]
    outs = [p.communicate(timeout=30) for p in procs]
    assert [p.returncode for p in procs] == [0, 0], outs
    calls = sorted(_calls(env), key=lambda c: c["start"])
    assert len(calls) == 2
    assert calls[0]["end"] <= calls[1]["start"], "runs overlapped"
    # each run used its own worktree's manifest (and so its own layer)
    used = {c["argv"][-1] for c in calls}
    assert used == {str(w / "os" / "kas" / "cultureos.yml") for w in (a, b)}
    # the waiter said so
    assert any("waiting" in err for _, err in outs)


@pytest.mark.skipif(shutil.which("flock") is None, reason="flock(1) not installed")
def test_lock_is_released_after_failure(env, tmp_path):
    wt = _worktree(tmp_path, "wt")
    assert _run(env, str(wt), STUB_RC="1").returncode == 1
    t0 = time.monotonic()
    assert _run(env, str(wt)).returncode == 0
    assert time.monotonic() - t0 < 10
