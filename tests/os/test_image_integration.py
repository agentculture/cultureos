"""Image integration (plan task t19): cultureos-image wires in every CultureOS package and
hardens the upstream base image. Static checks of the recipe and distro config; the image
audit (os/scripts/audit-image.sh) covers the built rootfs."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYER = ROOT / "os" / "meta-cultureos"
IMAGE = LAYER / "recipes-core" / "images" / "cultureos-image.bb"
DISTRO = LAYER / "conf" / "distro" / "cultureos.conf"

# acceptance 1: arduino-router, tailscale, provisioning, local-access, security, culture
# node, cultureos CLI, trialboot and update-agent.
REQUIRED = [
    "arduino-router",
    "tailscale",
    "tailscaled",
    "cultureos-provision",
    "cultureos-local-access",
    "cultureos-security",
    "culture-node",
    "python3-cultureos",
    "cultureos-trialboot",
    "cultureos-update-agent",
]


def _words(var: str) -> list[str]:
    """Words of a (possibly backslash-continued) `VAR = "..."` assignment."""
    text = IMAGE.read_text()
    m = re.search(rf'^{re.escape(var)} = "(.*?)"$', text, re.M | re.S)
    assert m, f"{var} assignment not found"
    return m.group(1).replace("\\", " ").split()


def _packages() -> list[str]:
    return _words("CULTUREOS_PACKAGES")


def test_every_cultureos_package_is_installed():
    pkgs = _packages()
    missing = [p for p in REQUIRED if p not in pkgs]
    assert not missing, f"not wired into cultureos-image: {missing}"
    assert "${CULTUREOS_PACKAGES}" in IMAGE.read_text()


def test_every_wired_package_has_a_recipe_in_the_layer_or_upstream():
    names = {p.name for p in LAYER.rglob("*.bb")} | {p.name for p in LAYER.rglob("*.bbappend")}
    for pkg in set(_packages()) - {"tailscaled"}:  # tailscaled is a tailscale subpackage
        assert any(n.startswith(pkg + "_") or n == pkg + ".bb" for n in names), pkg


def test_root_logins_and_empty_passwords_are_removed():
    text = IMAGE.read_text()
    m = re.search(r'^IMAGE_FEATURES:remove = "(.*)"$', text, re.M)
    assert m
    assert set(m.group(1).split()) >= {
        "allow-empty-password",
        "empty-root-password",
        "allow-root-login",
    }


def test_root_is_locked_not_given_the_upstream_password():
    text = IMAGE.read_text()
    assert re.search(r'^EXTRA_USERS_PARAMS = "usermod -L root;"$', text, re.M)
    assert "usermod -p" not in text


def test_adbd_is_not_installed():
    assert {"android-tools-adbd", "android-tools-adbd-cmdline"} <= set(
        _words("PACKAGE_INSTALL:remove")
    )
    assert "enable-adbd" not in IMAGE.read_text()


def test_virtualization_packagegroup_is_not_installed():
    # libvirt-libvirtd ships pre-generated, identical-on-every-image private keys in
    # /etc/pki/libvirt/private (found by audit-image.sh); CultureOS runs no VMs.
    assert "packagegroup-qcom-virtualization" in _words("PACKAGE_INSTALL:remove")


def test_distro_pulls_in_the_trialboot_kernel_args():
    assert "require conf/distro/include/cultureos-trialboot.inc" in DISTRO.read_text()


def test_no_uptane_client_in_the_image():
    assert "aktualizr" not in IMAGE.read_text()
