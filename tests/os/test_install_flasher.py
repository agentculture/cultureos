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


def _fake_tarball(tmp_path: Path, version: str, body: bytes | None = None) -> Path:
    # Like the real CLI: `--version` is an unknown flag, `version` is the subcommand.
    if body is None:
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
    assert "0.5.4" in text
    assert "linux-arm64" in text
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


def _with_existing(tmp_path: Path) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    old = bindir / "arduino-flasher-cli"
    old.write_text("#!/bin/sh\necho 'Arduino Flasher CLI version 0.5.4'\n")
    old.chmod(0o755)
    return old


def test_unparseable_version_reports_and_installs_nothing(tmp_path):
    tarball = _fake_tarball(tmp_path, "", body=b"#!/bin/sh\necho garbage\n")
    sha = hashlib.sha256(tarball.read_bytes()).hexdigest()
    proc, bindir = _run(tmp_path, tarball, sha)
    assert proc.returncode != 0
    assert "version" in proc.stderr
    assert not (bindir / "arduino-flasher-cli").exists()


@pytest.mark.parametrize(
    "body",
    [b"#!/bin/sh\nexit 126\n", b"#!/bin/sh\necho 'Arduino Flasher CLI version 0.5.3'\n"],
    ids=["not-runnable", "too-old"],
)
def test_failed_verification_keeps_previous_install(tmp_path, body):
    old = _with_existing(tmp_path)
    before = old.read_bytes()
    tarball = _fake_tarball(tmp_path, "", body=body)
    sha = hashlib.sha256(tarball.read_bytes()).hexdigest()
    proc, _ = _run(tmp_path, tarball, sha)
    assert proc.returncode != 0
    assert old.read_bytes() == before


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
