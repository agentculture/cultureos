"""Offline tests for the cultureos-provision helper (t10, acceptance 1, 2 and 4).

The helper runs as a real subprocess against a fake root directory
(``CULTUREOS_PROVISION_ROOT``) with stub ``useradd`` / ``usermod`` /
``chpasswd`` / ``chown`` / ``shred`` / ``sync`` / ``blkid`` / ``mount`` /
``umount`` on ``PATH`` that record their calls. Every value below is a
placeholder: the hash is of a dummy password, the key is not a real key.
"""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = (
    ROOT / "os" / "meta-cultureos" / "recipes-core" / "cultureos-provision" / "files"
) / "cultureos-provision"

HASH = (
    "$6$testsalt$S6Vh29xwjGJl8KXb2oP.X/6wLhG2U6BlY7NPihwD0cJFbAUGuzBG8xWMU7BsgRoPRszLa8xTcy"
    "Bs9bDenbRBr0"
)
KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPlaceholderPlaceholderPlaceholderPlace op@example"
SSID = "Example Net"
PASSPHRASE = "placeholder-passphrase-123"

FULL = f"""
[user]
password_hash = "{HASH}"
ssh_authorized_keys = ["{KEY}"]

[wifi]
ssid = "{SSID}"
psk = "{PASSPHRASE}"

[system]
hostname = "cultureos-test"
"""

ETHERNET_ONLY = f"""
[user]
password_hash = "{HASH}"
ssh_authorized_keys = "{KEY}"
"""

STUBS = {
    "useradd": """#!/bin/sh
echo "useradd $*" >> "$STUB_LOG"
for last; do :; done
echo "$last:x:1000:1000::/home/$last:/bin/sh" >> "$CULTUREOS_PROVISION_ROOT/etc/passwd"
mkdir -p "$CULTUREOS_PROVISION_ROOT/home/$last"
""",
    "usermod": '#!/bin/sh\necho "usermod $*" >> "$STUB_LOG"\n',
    "chpasswd": '#!/bin/sh\necho "chpasswd $*" >> "$STUB_LOG"\ncat > "$STUB_DIR/chpasswd.in"\n',
    "chown": '#!/bin/sh\necho "chown $*" >> "$STUB_LOG"\n',
    "shred": """#!/bin/sh
echo "shred $*" >> "$STUB_LOG"
for last; do :; done
rm -f "$last"
""",
    "sync": '#!/bin/sh\necho "sync" >> "$STUB_LOG"\n',
    # A vfat "device" is a directory; mount copies it in, umount copies it back.
    "blkid": '#!/bin/sh\necho "blkid $*" >> "$STUB_LOG"\n[ -n "$FAKE_DEV" ] && echo "$FAKE_DEV"\n',
    "mount": """#!/bin/sh
echo "mount $*" >> "$STUB_LOG"
case "$*" in *remount*) exit 0;; esac
for last; do :; done
dev=""
for a; do [ "$a" = "$last" ] && break; dev="$a"; done
cp -a "$dev/." "$last/"
echo "$dev" > "$STUB_DIR/mounted"
""",
    "umount": """#!/bin/sh
echo "umount $*" >> "$STUB_LOG"
dev=$(cat "$STUB_DIR/mounted")
rm -rf "$dev"; mkdir "$dev"; cp -a "$1/." "$dev/"
find "$1" -mindepth 1 -delete
""",
}


class Rig:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.root = tmp / "root"
        (self.root / "etc").mkdir(parents=True)
        (self.root / "etc" / "passwd").write_text("root:x:0:0:root:/root:/bin/sh\n")
        (self.root / "var" / "rootdirs").mkdir(parents=True)
        (self.root / "home").symlink_to("var/rootdirs/home")
        (self.root / "boot").mkdir()
        self.stubs = tmp / "stubs"
        self.stubs.mkdir()
        for name, body in STUBS.items():
            p = self.stubs / name
            p.write_text(body)
            p.chmod(0o755)
        self.log = tmp / "stub.log"
        self.log.write_text("")
        self.input = self.root / "boot" / "cultureos-provision.toml"

    def run(self, **env):
        e = {
            "PATH": f"{self.stubs}:/usr/bin:/bin",
            "CULTUREOS_PROVISION_ROOT": str(self.root),
            "CULTUREOS_PROVISION_WAIT": "0",
            "STUB_LOG": str(self.log),
            "STUB_DIR": str(self.stubs),
        }
        e.update(env)
        return subprocess.run(
            [sys.executable, str(HELPER)], env=e, capture_output=True, text=True, check=False
        )

    @property
    def calls(self):
        return self.log.read_text().splitlines()

    @property
    def marker(self):
        return self.root / "var" / "lib" / "cultureos" / "provisioned"

    @property
    def ssh(self):
        return self.root / "var" / "rootdirs" / "home" / "arduino" / ".ssh"

    @property
    def profile(self):
        return (
            self.root
            / "etc"
            / "NetworkManager"
            / "system-connections"
            / "cultureos-wifi.nmconnection"
        )


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def _mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


def _assert_nothing_applied(rig):
    assert not rig.marker.exists()
    assert not rig.profile.exists()
    assert not (rig.root / "var" / "rootdirs" / "home" / "arduino").exists()
    assert not any(c.split()[0] in {"useradd", "usermod", "chpasswd", "shred"} for c in rig.calls)


def _assert_no_secrets(r):
    out = r.stdout + r.stderr
    for secret in (PASSPHRASE, HASH, HASH[:20], "testsalt"):
        assert secret not in out


def test_valid_full_file(rig):
    rig.input.write_text(FULL)
    r = rig.run()
    assert r.returncode == 0, r.stderr
    assert r.stdout == ""  # diagnostics go to stderr (journal), nothing to stdout
    _assert_no_secrets(r)
    # user: created non-root with home under /var, password via stdin hash
    useradd = [c for c in rig.calls if c.startswith("useradd")]
    assert len(useradd) == 1
    assert "--home-dir /home/arduino" in useradd[0]
    assert useradd[0].endswith(" arduino")
    assert "--groups wheel,dialout" in useradd[0]
    assert (rig.stubs / "chpasswd.in").read_text() == f"arduino:{HASH}\n"
    assert any(c.startswith("chpasswd --encrypted") for c in rig.calls)
    assert not any(HASH in c for c in rig.calls)  # never in argv
    # ssh
    keys = rig.ssh / "authorized_keys"
    assert keys.read_text() == KEY + "\n"
    assert _mode(rig.ssh) == 0o700
    assert _mode(keys) == 0o600
    assert _mode(rig.root / "var" / "rootdirs" / "home") == 0o755
    assert any(c.startswith("chown -R arduino:arduino") for c in rig.calls)
    # wifi
    prof = rig.profile.read_text()
    assert _mode(rig.profile) == 0o600
    assert "[wifi-security]" in prof
    assert "key-mgmt=wpa-psk" in prof
    assert f"ssid={SSID}" in prof
    assert f"psk={PASSPHRASE}" in prof
    assert "type=wifi" in prof
    assert "id=cultureos-wifi" in prof
    # hostname, marker, input gone
    assert (rig.root / "etc" / "hostname").read_text() == "cultureos-test\n"
    assert rig.marker.is_file()
    assert PASSPHRASE not in rig.marker.read_text()
    assert not rig.input.exists()
    assert any(c.startswith("shred -u") for c in rig.calls)


def test_ethernet_only(rig):
    rig.input.write_text(ETHERNET_ONLY)
    r = rig.run()
    assert r.returncode == 0, r.stderr
    assert not rig.profile.exists()
    assert (rig.ssh / "authorized_keys").read_text() == KEY + "\n"
    assert not (rig.root / "etc" / "hostname").exists()
    assert rig.marker.is_file()
    assert not rig.input.exists()
    assert "Ethernet only" in r.stderr


@pytest.mark.parametrize(
    "text, reason",
    [
        ("this is = = not toml", "not valid TOML"),
        (FULL.replace(KEY, "not a key"), "OpenSSH public key"),
        (FULL.replace(KEY, "-----BEGIN OPENSSH " + "PRIVATE KEY-----"), "private key"),
        (FULL.replace(PASSPHRASE, "short"), "printable ASCII"),
        (FULL.replace('ssid = "Example Net"\n', ""), "wifi.ssid"),
        (FULL.replace("cultureos-test", "bad_host!"), "hostname"),
        (FULL.replace("[system]", "[sytsem]"), "unknown section"),
        (FULL + 'tailscale_note = "x"\n', "unknown key"),
        (FULL.replace("[system]", '[system]\nnote = "tskey-auth-PLACEHOLDER"'), "Tailscale"),
        ('[wifi]\nssid = "x"\npsk = "placeholder-passphrase"\n', "missing [user]"),
        (ETHERNET_ONLY.replace(f'"{KEY}"', "[]"), "at least one"),
    ],
)
def test_invalid_file_applies_nothing_and_is_kept(rig, text, reason):
    rig.input.write_text(text)
    r = rig.run()
    assert r.returncode == 1
    assert reason in r.stderr
    assert "nothing applied, file kept" in r.stderr
    _assert_nothing_applied(rig)
    assert rig.input.read_text() == text
    _assert_no_secrets(r)


@pytest.mark.parametrize(
    "user_block",
    [
        f'password = "not-a-real-password"\nssh_authorized_keys = ["{KEY}"]',
        f'password_hash = "not-a-real-password"\nssh_authorized_keys = ["{KEY}"]',
    ],
)
def test_plaintext_password_refused(rig, user_block):
    rig.input.write_text(f"[user]\n{user_block}\n")
    r = rig.run()
    assert r.returncode == 1
    assert "plaintext" in r.stderr
    assert "not-a-real-password" not in r.stderr + r.stdout
    _assert_nothing_applied(rig)
    assert rig.input.exists()


def test_done_marker_is_a_noop(rig):
    rig.marker.parent.mkdir(parents=True)
    rig.marker.write_text("provisioned_at=earlier\n")
    rig.input.write_text(FULL)
    r = rig.run()
    assert r.returncode == 0
    assert "already provisioned" in r.stderr
    assert rig.calls == []
    assert rig.input.exists()
    assert not rig.profile.exists()


def test_no_input_is_a_noop(rig):
    r = rig.run()
    assert r.returncode == 0
    assert "nothing to do" in r.stderr
    assert not rig.marker.exists()
    assert [c.split()[0] for c in rig.calls] == ["blkid"]


def test_existing_user_is_updated_not_recreated(rig):
    with (rig.root / "etc" / "passwd").open("a") as f:
        f.write("arduino:x:1000:1000::/home/arduino:/bin/sh\n")
    rig.input.write_text(ETHERNET_ONLY)
    r = rig.run()
    assert r.returncode == 0, r.stderr
    assert not any(c.startswith("useradd") for c in rig.calls)
    assert "usermod -a -G wheel,dialout arduino" in rig.calls


def test_apply_failure_keeps_file_and_no_marker(rig):
    (rig.stubs / "chpasswd").write_text("#!/bin/sh\necho 'chpasswd: boom' >&2\nexit 1\n")
    rig.input.write_text(FULL)
    r = rig.run()
    assert r.returncode == 2
    assert "will retry next boot" in r.stderr
    assert rig.input.exists()
    assert not rig.marker.exists()
    _assert_no_secrets(r)


def test_root_is_never_touched(rig):
    rig.input.write_text(FULL)
    rig.run()
    for c in rig.calls:
        words = c.split()
        assert "root" not in words
    assert "root:" not in (rig.stubs / "chpasswd.in").read_text()


def test_usb_stick_found_by_scan_and_input_removed(rig):
    dev = rig.tmp / "usbdev"
    dev.mkdir()
    (dev / "cultureos-provision.toml").write_text(ETHERNET_ONLY)
    (dev / "other.txt").write_text("keep me")
    r = rig.run(FAKE_DEV=str(dev))
    assert r.returncode == 0, r.stderr
    mounts = [c for c in rig.calls if c.startswith("mount")]
    assert "ro" in mounts[0]
    assert "-t vfat" in mounts[0]
    assert "remount,rw" in mounts[1]
    assert any(c.startswith("umount") for c in rig.calls)
    assert not (dev / "cultureos-provision.toml").exists()
    assert (dev / "other.txt").read_text() == "keep me"
    assert rig.marker.read_text().count(str(dev)) == 1


def test_numeric_ssid_written_as_bytes(rig):
    rig.input.write_text(FULL.replace(SSID, "12345"))
    assert rig.run().returncode == 0
    assert "ssid=49;50;51;52;53;" in rig.profile.read_text()


def test_helper_has_no_scan_trigger_literals():
    # The helper ships in the image; the rootfs scan must not trip on it.
    text = HELPER.read_text()
    assert "psk=" not in text
    assert "tskey-" not in text
    assert os.access(HELPER, os.X_OK)
