"""Offline tests for os/scripts/build-reference.sh (kas-container/docker stubbed)."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "os" / "scripts" / "build-reference.sh"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _setup(tmp_path: Path, kas_rc: int) -> tuple[dict, Path]:
    stub = tmp_path / "bin"
    stub.mkdir()
    for name, body in {
        "kas-container": f"#!/bin/sh\nexit {kas_rc}\n",
        "kas": "#!/bin/sh\necho 'kas 0.0 stub'\n",
        "docker": "#!/bin/sh\nexit 0\n",
    }.items():
        (stub / name).write_text(body)
        (stub / name).chmod(0o755)
    ref = tmp_path / "ref"
    repo = ref / "meta-qcom-arduino"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(
        repo,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "a",
    )
    _git(repo, "branch", "other")
    _git(repo, "checkout", "-q", "other")
    _git(
        repo,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "b",
    )
    _git(repo, "checkout", "-q", "main")
    env = {
        **os.environ,
        "PATH": f"{stub}:{os.environ['PATH']}",
        "CULTUREOS_REF_DIR": str(ref),
    }
    return env, ref


def _run(env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )


def test_failed_build_without_deploy_dir_still_reports_real_rc(tmp_path):
    env, ref = _setup(tmp_path, kas_rc=3)
    proc = _run(env)
    assert proc.returncode == 3, proc.stderr
    report = (ref / "build-report.txt").read_text()
    assert "exit_code: 3" in report
    assert "qcomflash_dirs:" in report


def test_reused_clone_is_switched_to_requested_branch(tmp_path):
    env, ref = _setup(tmp_path, kas_rc=0)
    env["CULTUREOS_REF_BRANCH"] = "other"
    proc = _run(env)
    assert proc.returncode == 0, proc.stderr
    want = _git(ref / "meta-qcom-arduino", "rev-parse", "other")
    assert f"meta-qcom-arduino: other {want}" in (ref / "build-report.txt").read_text()
    assert f"commit: {want}" in (ref / "reference.yml").read_text()
