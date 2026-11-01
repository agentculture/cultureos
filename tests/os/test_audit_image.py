"""os/scripts/audit-image.sh (t19 acceptance 2): no mutable app data outside /var and the
secrets scan, run against fixture rootfs trees (no image build needed)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "os" / "scripts" / "audit-image.sh"

# Markers assembled at runtime so the repo's own scan-secrets never sees a literal
# key block; the body is random base64, not a real key.
_B, _E, _PK = "-----BEGIN ", "-----END ", "PRIVATE KEY-----"
PEM = (
    _B
    + _PK
    + "\n"
    + "MC4CAQAwBQYDK2VwBCIEIJ+DYvh6SEqVTm50DFtMDoQikTmiCqirVv9mWG9qfSnF\n"
    + _E
    + _PK
    + "\n"
)

UNIT = """[Service]
ExecStart=/usr/bin/culture-node-start
Environment=HOME=/var/lib/culture
StateDirectory=culture
"""


def make_rootfs(tmp_path: Path) -> Path:
    r = tmp_path / "rootfs"
    for d in (
        "var/lib",
        "var/local",
        "usr/bin",
        "usr/sbin",
        "usr/etc/ssh",
        "usr/lib/systemd/system",
        "home",
    ):
        (r / d).mkdir(parents=True, exist_ok=True)
    (r / "var/log").symlink_to("volatile/log")
    (r / "usr/etc/shadow").write_text("root:!:19000::::::\narduino-router:!:19000::::::\n")
    (r / "usr/etc/passwd").write_text("root:x:0:0:root:/home/root:/bin/sh\n")
    (r / "usr/etc/wpa.conf").write_text("# psk=example only, commented\n")
    (r / "usr/lib/systemd/system/culture-node.service").write_text(UNIT)
    elf = r / "usr/bin/wpa_cli"
    elf.write_bytes(b"\x7fELF" + b"\0" * 12 + b"psk=%s\0")
    return r


def run(root: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "LC_ALL": "C"}
    return subprocess.run(
        ["bash", str(SCRIPT), str(root)], capture_output=True, text=True, env=env, check=False
    )


def test_clean_rootfs_passes(tmp_path):
    r = run(make_rootfs(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "audit: OK" in r.stdout


@pytest.mark.parametrize(
    "rel,content,needle",
    [
        ("var/lib/app/state.db", "data", "var/lib/app/state.db"),
        ("home/arduino/.profile", "x", "home/arduino/.profile"),
        ("usr/etc/NetworkManager/system-connections/w.nmconnection", "psk=hunter2\n", "psk="),
        ("usr/etc/notes.txt", "key tskey-auth-kAbc123CNTRL-0123456789abcdefABCDEF\n", "tskey-"),
        ("usr/share/k.pem", PEM, "PRIVATE KEY"),
        ("usr/etc/ssh/ssh_host_ed25519_key", "x", "ssh_host_ed25519_key"),
    ],
)
def test_findings_fail_the_audit(tmp_path, rel, content, needle):
    root = make_rootfs(tmp_path)
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    r = run(root)
    assert r.returncode == 1, r.stdout + r.stderr
    assert needle in r.stdout


def test_tskey_inside_a_binary_still_fails(tmp_path):
    root = make_rootfs(tmp_path)
    key = b"tskey-auth-kAbc123CNTRL-0123456789abcdefABCDEF"
    (root / "usr/bin/evil").write_bytes(b"\x7fELF" + b"\0" * 12 + key + b"\0")
    r = run(root)
    assert r.returncode == 1
    assert "tskey-" in r.stdout


def test_tailscale_constants_in_binaries_are_not_keys(tmp_path):
    # tailscaled itself contains "tskey-wrap"; programs embed the PEM markers.
    root = make_rootfs(tmp_path)
    (root / "usr/sbin/tailscaled").write_bytes(b"\x7fELF" + b"\0" * 12 + b"tskey-wrap\0tskey-\0")
    markers = (_B + "RSA " + _PK + "\0" + _E + "RSA " + _PK + "\0").encode()
    (root / "usr/sbin/sshd").write_bytes(b"\x7fELF" + b"\0" * 12 + markers)
    (root / "usr/share").mkdir(exist_ok=True)
    (root / "usr/share/magic").write_text("0 string -----BEGIN\\ PRIVATE\\ KEY----- PEM key\n")
    r = run(root)
    assert r.returncode == 0, r.stdout


def test_baked_service_private_key_fails(tmp_path):
    # e.g. libvirt's pre-generated /etc/pki/libvirt/private/*.pem
    root = make_rootfs(tmp_path)
    p = root / "usr/etc/pki/libvirt/private/serverkey.pem"
    p.parent.mkdir(parents=True)
    p.write_text("Public Key Info:\n  stuff\n" + PEM)
    r = run(root)
    assert r.returncode == 1
    assert "serverkey.pem" in r.stdout


@pytest.mark.parametrize("shadow", ["root::19000::::::\n", "root:$6$abc$def:19000::::::\n"])
def test_root_must_be_locked(tmp_path, shadow):
    root = make_rootfs(tmp_path)
    (root / "usr/etc/shadow").write_text(shadow)
    r = run(root)
    assert r.returncode == 1
    assert "root" in r.stdout


def test_unit_state_outside_var_fails(tmp_path):
    root = make_rootfs(tmp_path)
    (root / "usr/lib/systemd/system/culture-node.service").write_text(
        "[Service]\nExecStart=/usr/bin/x --data-dir /usr/share/x\nEnvironment=HOME=/opt/x\n"
    )
    r = run(root)
    assert r.returncode == 1
    assert "/usr/share/x" in r.stdout
    assert "/opt/x" in r.stdout


def test_missing_rootfs_is_an_environment_error(tmp_path):
    r = run(tmp_path / "nope")
    assert r.returncode == 2


def test_extracts_an_ostree_tarball(tmp_path):
    root = make_rootfs(tmp_path)
    tar = tmp_path / "img.ostree.tar"
    subprocess.run(["tar", "-cf", str(tar), "-C", str(root), "."], check=True)
    r = run(tar)
    assert r.returncode == 0, r.stdout + r.stderr
