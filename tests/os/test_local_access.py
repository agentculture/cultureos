"""Offline checks for the cultureos-local-access recipe and its doc (t11, deviation d3)."""

import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECIPE_DIR = ROOT / "os" / "meta-cultureos" / "recipes-core" / "cultureos-local-access"
RECIPE = RECIPE_DIR / "cultureos-local-access_1.0.bb"
SCRIPT = RECIPE_DIR / "files" / "cultureos-usb-gadget.sh"
UNIT = RECIPE_DIR / "files" / "cultureos-usb-gadget.service"
DROPIN = RECIPE_DIR / "files" / "gadget-getty.conf"
DOC = ROOT / "docs" / "os" / "local-access.md"


def _all_text() -> str:
    parts = [p.read_text() for p in RECIPE_DIR.rglob("*") if p.is_file()]
    return "\n".join(parts)


def test_recipe_exists_with_license():
    t = RECIPE.read_text()
    assert 'LICENSE = "MIT"' in t
    assert "LIC_FILES_CHKSUM" in t


def test_no_adbd_anywhere_in_recipe_dir():
    # Deviation d3: no adbd, no unauthenticated root path. Comments may not
    # mention it either, so the check is over the whole directory.
    t = _all_text().lower()
    assert "adbd" not in t
    assert "android-tools" not in t
    assert "usb-debugging-enabled" not in t
    assert "ffs." not in t


def test_gadget_has_two_acm_functions_ordered():
    s = SCRIPT.read_text()
    funcs = re.findall(r'mkdir "\$G/functions/(acm\.GS\d)"', s)
    assert funcs == ["acm.GS0", "acm.GS1"]
    assert "ID_VENDOR=0x2341" in s
    assert "ID_PRODUCT=0x007a" in s


def test_gadget_script_is_valid_shell():
    assert subprocess.run(["sh", "-n", str(SCRIPT)]).returncode == 0
    if shutil.which("shellcheck"):
        assert subprocess.run(["shellcheck", str(SCRIPT)]).returncode == 0


def test_gadget_unit_and_installed():
    u = UNIT.read_text()
    assert "Type=oneshot" in u
    assert "cultureos-usb-gadget start" in u
    assert "cultureos-usb-gadget.service" in RECIPE.read_text()


def test_gettys_enabled_for_uart_and_ttygs1_only():
    t = RECIPE.read_text()
    assert "serial-getty@ttyMSM0.service" in t
    assert "serial-getty@ttyGS1.service" in t
    assert "systemctl $OPTS enable" in t
    # ttyGS0 belongs to the arduino-router bridge.
    assert "serial-getty@ttyGS0" not in _all_text()
    d = DROPIN.read_text()
    assert "Requires=cultureos-usb-gadget.service" in d


def test_no_autologin_no_users():
    t = _all_text().lower()
    assert "autologin" not in t
    assert "--autologin" not in t
    assert "extrausers" not in t
    assert "useradd" not in t
    assert "usermod" not in t
    assert "ttygs1" in t


def test_image_recipe_untouched_by_this_task():
    img = ROOT / "os/meta-cultureos/recipes-core/images/cultureos-image.bb"
    # t19 wires the package in; this task only documents the adbd removal.
    assert "android-tools-adbd.service" not in RECIPE.read_text()
    assert img.is_file()


def test_doc_has_procedure():
    d = DOC.read_text()
    for needle in ("ttyGS0", "ttyGS1", "ttyMSM0", "Ethernet", "Wi-Fi", "NOT VERIFIED", "picocom"):
        assert needle in d
    assert "image-adbd" in d  # exact line t19 needs
