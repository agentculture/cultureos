"""Offline tests for os/scripts/install-flasher.sh (never touches the network)."""

import hashlib
import io
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "os" / "scripts" / "install-flasher.sh"
DOC = ROOT / "docs" / "os" / "recovery.md"


def _fake_tarball(tmp_path: Path, version: str) -> Path:
    # Like the real CLI: `--version` is an unknown flag, `version` is the subcommand.
    body = (
        f'#!/bin/sh\n[ "$1" = version ] || exit 1\n'
        f"echo 'Arduino Flasher CLI version {version}'\n"
    ).encode()
    path = tmp_path / "fake.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo("arduino-flasher-cli")
        info.size = len(body)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(body))
    return path


def _run(tmp_path, tarball, sha, minimum="0.5.4"):
    bindir = tmp_path / "bin"
    env = {
        **os.environ,
        "FLASHER_URL": tarball.as_uri(),
        "FLASHER_SHA256": sha,
        "FLASHER_MIN_VERSION": minimum,
        "INSTALL_DIR": str(bindir),
    }
    proc = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )
    return proc, bindir


def test_script_is_static_safe():
    text = SCRIPT.read_text()
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text
    assert "0.5.4" in text and "linux-arm64" in text
    # acceptance 3: nothing here may flash the board
    assert "flasher-cli flash" not in text
    assert '" flash' not in text
    assert "sudo " not in text.replace("#", "")


def test_installs_and_verifies_version(tmp_path):
    tarball = _fake_tarball(tmp_path, "0.5.4")
    sha = hashlib.sha256(tarball.read_bytes()).hexdigest()
    proc, bindir = _run(tmp_path, tarball, sha)
    assert proc.returncode == 0, proc.stderr
    assert (bindir / "arduino-flasher-cli").exists()
    assert "0.5.4" in proc.stdout


def test_rejects_bad_checksum(tmp_path):
    tarball = _fake_tarball(tmp_path, "0.5.4")
    proc, bindir = _run(tmp_path, tarball, "0" * 64)
    assert proc.returncode != 0
    assert not (bindir / "arduino-flasher-cli").exists()


def test_rejects_too_old_version(tmp_path):
    tarball = _fake_tarball(tmp_path, "0.5.3")
    sha = hashlib.sha256(tarball.read_bytes()).hexdigest()
    proc, _ = _run(tmp_path, tarball, sha)
    assert proc.returncode != 0


DOC_REQUIRED = [
    "pin1",
    "pin2",
    "FORCED_USB_BOOT_N",
    "05c6:9008",
    "dialout",
    "SUBSYSTEM",
    "erase",
    "eMMC",
    "barrel",
    "USB-C",
]


@pytest.mark.parametrize("needle", DOC_REQUIRED)
def test_recovery_doc_covers(needle):
    assert needle.lower() in DOC.read_text().lower()
