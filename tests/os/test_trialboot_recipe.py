"""Offline checks for the cultureos-trialboot recipe, units and config (t15, acceptance 1 and 2)."""

import configparser
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYER = ROOT / "os" / "meta-cultureos"
RECIPE_DIR = LAYER / "recipes-core" / "cultureos-trialboot"
FILES = RECIPE_DIR / "files"
RECIPE = RECIPE_DIR / "cultureos-trialboot.bb"
INC = LAYER / "conf" / "distro" / "include" / "cultureos-trialboot.inc"
HELPER = FILES / "cultureos-trialboot"

QCOM_WDT_TIMEOUT_S = 30  # docs/os/board-baseline.md: watchdog0 qcom_wdt, timeout 30 s


def _unit(name: str) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read_string((FILES / name).read_text())
    return cp


def _words(cp: configparser.ConfigParser, section: str, key: str) -> list[str]:
    return cp.get(section, key, fallback="").split()


def _seconds(value: str) -> int:
    m = re.fullmatch(r"(\d+)\s*(s|sec|min)?", value.strip())
    assert m, value
    n = int(m.group(1))
    return n * 60 if m.group(2) == "min" else n


def test_recipe_ships_every_file():
    text = RECIPE.read_text()
    for name in (
        "cultureos-trialboot",
        "cultureos-trialboot-health.service",
        "cultureos-trialboot-promote.service",
        "cultureos-trialboot-deadline.service",
        "cultureos-trialboot-deadline.timer",
        "50-cultureos-watchdog.conf",
        "cultureos-watchdog-modules.conf",
    ):
        assert (FILES / name).is_file(), name
        assert f"file://{name}" in text, name


def test_recipe_installs_and_enables_units():
    text = RECIPE.read_text()
    assert 'LICENSE = "MIT"' in text
    assert "inherit systemd" in text
    m = re.search(r'SYSTEMD_SERVICE:\$\{PN\} = "([^"]+)"', text)
    assert m
    services = m.group(1).split()
    assert "cultureos-trialboot-health.service" in services
    assert "cultureos-trialboot-promote.service" in services
    assert "cultureos-trialboot-deadline.timer" in services
    assert 'SYSTEMD_AUTO_ENABLE = "enable"' in text
    assert "${systemd_unitdir}/system.conf.d/50-cultureos-watchdog.conf" in text
    assert "modules-load.d" in text
    rdepends = re.search(r'RDEPENDS:\$\{PN\} = "([^"]+)"', text).group(1).split()
    for pkg in ("python3-core", "python3-json", "ostree", "systemd", "kernel-module-qcom-wdt"):
        assert pkg in rdepends, pkg


def test_helper_stages_non_default_and_sets_oneshot():
    """Acceptance 1, deploy helper: the commands it runs (behaviour: test_trialboot_helper)."""
    text = HELPER.read_text()
    assert text.startswith("#!/usr/bin/env python3")
    assert '"--not-as-default"' in text
    assert '"set-oneshot"' in text
    assert '"set-default"' in text


def test_health_unit_gates_boot_complete():
    """Acceptance 1: health check ordered before boot-complete.target."""
    u = _unit("cultureos-trialboot-health.service")
    assert "boot-complete.target" in _words(u, "Unit", "Before")
    assert "boot-complete.target" in _words(u, "Install", "RequiredBy")
    assert u.get("Service", "Type") == "oneshot"
    assert u.get("Service", "ExecStart") == "/usr/sbin/cultureos-trialboot check"
    assert u.get("Service", "ExecStopPost") == "/usr/sbin/cultureos-trialboot health-exit"
    # Ordering after multi-user.target would form a cycle with the promote unit.
    assert "multi-user.target" not in _words(u, "Unit", "After")


def test_promote_unit_runs_only_after_boot_complete():
    """Acceptance 1: promote only after the health check passed (boot-complete reached)."""
    u = _unit("cultureos-trialboot-promote.service")
    assert "boot-complete.target" in _words(u, "Unit", "Requires")
    after = _words(u, "Unit", "After")
    for dep in (
        "boot-complete.target",
        "cultureos-trialboot-health.service",
        "systemd-bless-boot.service",
    ):
        assert dep in after, dep
    assert u.get("Service", "ExecStart") == "/usr/sbin/cultureos-trialboot promote"
    assert "multi-user.target" in _words(u, "Install", "WantedBy")


def test_deadline_timer():
    t = _unit("cultureos-trialboot-deadline.timer")
    assert _seconds(t.get("Timer", "OnBootSec")) >= 5 * 60
    assert "timers.target" in _words(t, "Install", "WantedBy")
    s = _unit("cultureos-trialboot-deadline.service")
    assert s.get("Service", "ExecStart") == "/usr/sbin/cultureos-trialboot deadline"
    # the deadline must be later than the longest health check can take
    health = _unit("cultureos-trialboot-health.service")
    assert _seconds(t.get("Timer", "OnBootSec")) > _seconds(
        health.get("Service", "TimeoutStartSec")
    )


def test_runtime_watchdog_within_qcom_wdt_timeout():
    """Acceptance 2: RuntimeWatchdogSec <= qcom_wdt's 30 s."""
    cp = _unit("50-cultureos-watchdog.conf")
    sec = _seconds(cp.get("Manager", "RuntimeWatchdogSec"))
    assert 0 < sec <= QCOM_WDT_TIMEOUT_S
    assert cp.get("Manager", "WatchdogDevice") == "/dev/watchdog0"


def test_watchdog_driver_loaded_early():
    lines = [
        ln.strip()
        for ln in (FILES / "cultureos-watchdog-modules.conf").read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    assert lines == ["qcom_wdt"]


def test_panic_reboot_on_kernel_cmdline():
    """Acceptance 2: panic=N on the OSTree BLS options (meta-updater OSTREE_KERNEL_ARGS)."""
    text = INC.read_text()
    assert re.search(r'^CULTUREOS_PANIC_TIMEOUT \?= "(\d+)"$', text, re.M)
    assert 'OSTREE_KERNEL_ARGS:append = " panic=${CULTUREOS_PANIC_TIMEOUT}"' in text
    n = int(re.search(r'^CULTUREOS_PANIC_TIMEOUT \?= "(\d+)"$', text, re.M).group(1))
    assert 0 < n < QCOM_WDT_TIMEOUT_S
    # The helper re-applies the same value to every staged deployment.
    recipe = RECIPE.read_text()
    assert 'CULTUREOS_PANIC_TIMEOUT ??= "%d"' % n in recipe
    assert f'PANIC_TIMEOUT_DEFAULT = "{n}"' in HELPER.read_text()
