"""Offline tests for os/scripts/capture-baseline.sh (ssh is stubbed on PATH)."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "os" / "scripts" / "capture-baseline.sh"


def _run(tmp_path: Path, ssh_body: str) -> subprocess.CompletedProcess:
    stub = tmp_path / "bin"
    stub.mkdir()
    ssh = stub / "ssh"
    ssh.write_text("#!/bin/sh\n" + ssh_body)
    ssh.chmod(0o755)
    env = {**os.environ, "PATH": f"{stub}:{os.environ['PATH']}"}
    return subprocess.run(
        ["bash", str(SCRIPT), "fakehost"], env=env, capture_output=True, text=True, check=False
    )


def test_failing_remote_command_does_not_abort_capture(tmp_path):
    # Last arg is the remote command; fail the one with `systemctl is-active` (exit 3).
    body = 'for a; do last="$a"; done\necho out\ncase "$last" in *is-active*) exit 3;; esac\n'
    proc = _run(tmp_path, body)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.count("```") % 2 == 0
    assert "(exit 3)" in proc.stdout
    assert proc.stdout.count("### ") == 11


def test_unreachable_host_fails_with_closed_fence(tmp_path):
    proc = _run(tmp_path, "echo 'ssh: connect refused' >&2\nexit 255\n")
    assert proc.returncode == 255
    assert proc.stdout.count("```") % 2 == 0
