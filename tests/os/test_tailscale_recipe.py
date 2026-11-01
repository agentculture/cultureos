"""Offline checks for the tailscale recipe extension (t9)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECIPE_DIR = ROOT / "os" / "meta-cultureos" / "recipes-connectivity" / "tailscale"
BBAPPEND = RECIPE_DIR / "tailscale_%.bbappend"
UNIT = RECIPE_DIR / "files" / "tailscaled.service"


def test_bbappend_and_unit_exist():
    assert BBAPPEND.is_file()
    assert UNIT.is_file()


def test_unit_state_is_under_var_lib_tailscale():
    text = UNIT.read_text()
    assert "--state=/var/lib/tailscale/tailscaled.state" in text
    assert "StateDirectory=tailscale" in text
    assert "WantedBy=multi-user.target" in text


def test_bbappend_installs_unit_and_enables_service():
    text = BBAPPEND.read_text()
    assert "file://tailscaled.service" in text
    assert 'SYSTEMD_AUTO_ENABLE:${BPN}d = "enable"' in text
    assert "FILESEXTRAPATHS:prepend" in text
    assert "${systemd_system_unitdir}/${BPN}d.service" in text
    # state dir must be shipped by the package so it exists on a fresh deploy
    assert "/var/lib/tailscale" in text or "StateDirectory" in UNIT.read_text()


def test_no_auth_key_anywhere_in_recipe_dir():
    pattern = re.compile(r"tskey-|--auth-?key|TS_AUTHKEY|authkey", re.IGNORECASE)
    for path in RECIPE_DIR.rglob("*"):
        if path.is_file():
            assert not pattern.search(path.read_text()), path


def test_unit_does_not_run_tailscale_up():
    for path in RECIPE_DIR.rglob("*"):
        if path.is_file():
            assert not re.search(r"tailscale\s+up\b", path.read_text()), path
