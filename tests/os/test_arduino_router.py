"""Offline checks for the arduino-router recipe and unit (plan task t8)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYER = ROOT / "os" / "meta-cultureos"
RECIPE_DIR = LAYER / "recipes-arduino" / "arduino-router"
RECIPE = RECIPE_DIR / "arduino-router_0.11.0.bb"
UNIT = RECIPE_DIR / "files" / "arduino-router.service"
DEFAULTS = RECIPE_DIR / "files" / "arduino-router.default"

# Annotated tag v0.11.0 of github.com/arduino/arduino-router (the factory version).
V0_11_0_SHA = "cb7b2cecee1c04e0ba0a7fb48da63a8a7a1dba71"
SERIAL_PORT = "/dev/ttySTM0"
RULES = RECIPE_DIR / "files" / "99-cultureos-stm-tty.rules"


def _layer_files():
    return [p for p in LAYER.rglob("*") if p.is_file() and "__pycache__" not in p.parts]


def test_recipe_pins_tag_not_older_than_factory():
    text = RECIPE.read_text()
    m = re.search(r"arduino-router_(\d+)\.(\d+)\.(\d+)\.bb", RECIPE.name)
    assert m
    assert tuple(map(int, m.groups())) >= (0, 11, 0)
    assert "github.com/arduino/arduino-router" in text
    assert f'SRCREV = "{V0_11_0_SHA}"' in text
    assert "tag=v${PV}" in text


def test_recipe_is_static_go_build():
    text = RECIPE.read_text()
    assert "inherit go-mod" in text
    assert 'CGO_ENABLED = "0"' in text
    assert "-X main.Version=${PV}" in text
    assert (RECIPE_DIR / "arduino-router-go-mods.inc").is_file()
    assert (RECIPE_DIR / "arduino-router-licenses.inc").is_file()


def test_unit_matches_factory_behaviour():
    text = UNIT.read_text()
    assert "--unix-port /var/run/arduino-router.sock" in text
    assert "Restart=always" in text
    assert "WantedBy=multi-user.target" in text
    assert "--serial-port ${ARDUINO_ROUTER_SERIAL_PORT}" in text
    assert "EnvironmentFile=" in text
    assert f'ARDUINO_ROUTER_SERIAL_PORT="{SERIAL_PORT}"' in DEFAULTS.read_text()


def test_recipe_enables_unit_and_creates_group():
    text = RECIPE.read_text()
    assert "inherit" in text
    assert "systemd" in text
    assert 'SYSTEMD_SERVICE:${PN} = "arduino-router.service"' in text
    assert 'SYSTEMD_AUTO_ENABLE:${PN} = "enable"' in text
    assert 'GROUPADD_PARAM:${PN} = "--system arduino-router"' in text


def test_udev_rule_gives_stable_name():
    text = RULES.read_text()
    assert 'ATTRS{idVendor}=="1209"' in text
    assert 'ATTRS{idProduct}=="ca01"' in text
    assert 'SYMLINK+="ttySTM0"' in text
    assert 'GROUP="arduino-router"' in text
    assert 'MODE="0660"' in text
    assert "99-cultureos-stm-tty.rules" in RECIPE.read_text()


def test_only_arduino_router_recipe_touches_the_mcu_tty():
    # Host-side MCU tty names. ttyGS* (device-side gadget) is unrelated.
    pattern = re.compile(r"ttyACM\d*|ttySTM\d*")
    hits = [p for p in _layer_files() if pattern.search(p.read_text(errors="ignore"))]
    assert hits, "the router recipe must name its serial port"
    for p in hits:
        assert RECIPE_DIR in p.parents, f"{p} names the MCU tty outside arduino-router"
    assert {p.name for p in hits} <= {
        "arduino-router.default",
        "arduino-router.service",
        "99-cultureos-stm-tty.rules",
        "arduino-router_0.11.0.bb",
    }


def test_no_stm32_firmware_installed_or_flashed():
    pattern = re.compile(r"stm32|dfu-util|openocd|stm32flash|zephyr", re.I)
    allowed_note = "NO-STM32-FLASHING-NOTE"
    for p in _layer_files():
        if p.suffix in {".bb", ".bbappend", ".inc", ".service", ".conf", ".sh", ".default"}:
            for line in p.read_text(errors="ignore").splitlines():
                if pattern.search(line) and allowed_note not in line:
                    raise AssertionError(f"{p}: {line.strip()}")
