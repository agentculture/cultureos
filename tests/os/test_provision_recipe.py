"""Offline checks for the cultureos-provision recipe, unit and doc (t10)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECIPE_DIR = ROOT / "os" / "meta-cultureos" / "recipes-core" / "cultureos-provision"
RECIPE = RECIPE_DIR / "cultureos-provision_1.0.bb"
UNIT = RECIPE_DIR / "files" / "cultureos-provision.service"
TMPFILES = RECIPE_DIR / "files" / "cultureos-provision-tmpfiles.conf"
DOC = ROOT / "docs" / "os" / "provisioning.md"


def _unit():
    return UNIT.read_text()


def test_recipe_installs_helper_unit_and_tmpfiles():
    t = RECIPE.read_text()
    assert 'LICENSE = "MIT"' in t
    assert "LIC_FILES_CHKSUM" in t
    assert 'SYSTEMD_SERVICE:${PN} = "cultureos-provision.service"' in t
    assert 'SYSTEMD_AUTO_ENABLE = "enable"' in t
    assert "${libexecdir}/cultureos-provision/cultureos-provision" in t
    assert "tmpfiles.d/cultureos-provision.conf" in t
    for dep in ("python3-core", "python3-tomllib", "shadow", "networkmanager"):
        assert dep in t


def test_unit_is_a_first_boot_oneshot_ordered_before_logins_and_network():
    u = _unit()
    assert "Type=oneshot" in u
    assert "ConditionPathExists=!/var/lib/cultureos/provisioned" in u
    assert "ExecStart=/usr/libexec/cultureos-provision/cultureos-provision" in u
    before = " ".join(re.findall(r"^Before=(.*)$", u, re.M)).split()
    for unit in (
        "NetworkManager.service",
        "sshd.socket",
        "systemd-user-sessions.service",
        "serial-getty@ttyGS1.service",
        "serial-getty@ttyMSM0.service",
        "network-pre.target",
    ):
        assert unit in before
    assert "WantedBy=multi-user.target" in u
    assert "DefaultDependencies=no" in u


def test_tmpfiles_creates_home_target_under_var():
    t = TMPFILES.read_text()
    assert re.search(r"^d /var/rootdirs/home 0755 root root", t, re.M)


def test_no_credentials_in_recipe_dir():
    for p in RECIPE_DIR.rglob("*"):
        if p.is_file():
            text = p.read_text()
            assert "psk=" not in text, p
            assert "tskey-" not in text, p
            assert "BEGIN" not in text or "PRIVATE KEY" not in text, p
            assert not re.search(r"\$6\$[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}", text), p
            assert not re.search(r"ssh-(ed25519|rsa) AAAA", text), p


def test_helper_compiles():
    helper = RECIPE_DIR / "files" / "cultureos-provision"
    compile(helper.read_text(), str(helper), "exec")  # no __pycache__ in the layer
    assert helper.read_text().startswith("#!/usr/bin/env python3\n")


def test_image_recipe_wires_provisioning_in():
    img = (ROOT / "os/meta-cultureos/recipes-core/images/cultureos-image.bb").read_text()
    assert "cultureos-provision" in img  # wired in by t19


def test_doc_format_uses_placeholders_only():
    d = DOC.read_text()
    blocks = re.findall(r"```toml\n(.*?)```", d, re.S)
    assert blocks, "doc must show the file format"
    fmt = blocks[0]
    for key in ("password_hash", "ssh_authorized_keys", "ssid", "psk", "hostname"):
        assert key in fmt
    # placeholders, not values
    assert "<" in fmt
    assert ">" in fmt
    assert not re.search(r"\$6\$[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}", d)
    assert not re.search(r"ssh-ed25519 AAAA", d)
    assert "tskey-" not in d
    for needle in (
        "openssl passwd -6",
        "/var/lib/cultureos/provisioned",
        "NOT VERIFIED",
        "shred",
        "/etc/NetworkManager/system-connections",
        "/var/rootdirs/home",
        "tailscale up",
    ):
        assert needle in d, needle
