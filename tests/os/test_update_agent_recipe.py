"""Offline checks for the cultureos-update-agent recipe, units and polkit rule (t16,
acceptance 1: the timer (pull) and the ssh-callable `cultureos-update now` (push))."""

import configparser
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECIPE_DIR = ROOT / "os" / "meta-cultureos" / "recipes-core" / "cultureos-update-agent"
FILES = RECIPE_DIR / "files"
RECIPE = RECIPE_DIR / "cultureos-update-agent.bb"


def _unit(name: str) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read_string((FILES / name).read_text())
    return cp


def test_recipe_ships_every_file():
    text = RECIPE.read_text()
    for name in (
        "cultureos-update",
        "cultureos-update.service",
        "cultureos-update.timer",
        "50-cultureos-update.rules",
    ):
        assert (FILES / name).is_file(), name
        assert f"file://{name}" in text, name
    assert 'LICENSE = "MIT"' in text


def test_only_the_timer_is_enabled():
    text = RECIPE.read_text()
    assert "inherit systemd" in text
    m = re.search(r'SYSTEMD_SERVICE:\$\{PN\} = "([^"]+)"', text)
    assert m
    assert m.group(1).split() == ["cultureos-update.timer"]
    assert 'SYSTEMD_AUTO_ENABLE = "enable"' in text
    assert "[Install]" not in (FILES / "cultureos-update.service").read_text()
    assert _unit("cultureos-update.timer")["Install"]["WantedBy"] == "timers.target"


def test_recipe_installs_command_on_the_default_path():
    text = RECIPE.read_text()
    assert "${D}${bindir}/cultureos-update" in text  # /usr/bin: on arduino's PATH over ssh
    assert "${systemd_system_unitdir}/cultureos-update.service" in text
    assert "${systemd_system_unitdir}/cultureos-update.timer" in text
    assert "${datadir}/polkit-1/rules.d" in text
    # remote and branch come from the distro, baked in at build time
    assert 'CULTUREOS_UPDATE_REMOTE ?= "${OSTREE_OSNAME}"' in text
    assert 'CULTUREOS_UPDATE_BRANCH ?= "${OSTREE_BRANCHNAME}"' in text
    assert "s/^REMOTE = .*/" in text
    assert "s/^BRANCH = .*/" in text


def test_recipe_rdepends():
    text = RECIPE.read_text()
    m = re.search(r'RDEPENDS:\$\{PN\} = "([^"]+)"', text)
    assert m
    deps = m.group(1).split()
    for dep in (
        "python3-core",
        "python3-json",
        "python3-io",
        "python3-fcntl",
        "ostree",
        "polkit",
        "cultureos-trialboot",
        "cultureos-security",
    ):
        assert dep in deps, dep


def test_service_runs_the_agent_once_per_start():
    cp = _unit("cultureos-update.service")
    s = cp["Service"]
    assert s["Type"] == "oneshot"
    assert s["ExecStart"] == "/usr/bin/cultureos-update run"
    assert s["SuccessExitStatus"].split() == ["3"]  # deferred is not a unit failure
    text = (FILES / "cultureos-update.service").read_text()
    after = " ".join(ln.split("=", 1)[1] for ln in text.splitlines() if ln.startswith("After="))
    assert "network-online.target" in after
    assert "tailscaled.service" in after
    assert "cultureos-trialboot-health.service" in after
    assert "cultureos-trialboot-promote.service" in after
    assert cp["Unit"]["ConditionPathExists"] == "/run/ostree-booted"
    assert "EnvironmentFile=-/etc/cultureos/update.conf" in text


def test_timer_is_hourly_with_a_fixed_offset_and_catches_up():
    t = _unit("cultureos-update.timer")["Timer"]
    assert t["OnCalendar"] == "hourly"
    assert t["RandomizedDelaySec"] == "15min"
    assert t["FixedRandomDelay"] == "true"
    assert t["Persistent"] == "true"
    assert t["AccuracySec"] == "1s"


def test_polkit_rule_grants_only_starting_the_one_unit_to_wheel():
    js = (FILES / "50-cultureos-update.rules").read_text()
    code = "\n".join(ln for ln in js.splitlines() if not ln.lstrip().startswith("//"))
    assert 'action.id == "org.freedesktop.systemd1.manage-units"' in code
    assert 'action.lookup("unit") == "cultureos-update.service"' in code
    assert 'action.lookup("verb") == "start"' in code
    assert 'subject.isInGroup("wheel")' in code
    assert code.count("polkit.Result.YES") == 1
    assert "AUTH_ADMIN" not in code
    assert "restart" not in code
