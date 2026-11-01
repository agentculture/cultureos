SUMMARY = "CultureOS trial boot: one-shot trial, watchdog, health-gated promotion"
DESCRIPTION = "Rollback mechanism of decision c39. cultureos-trialboot stages a new \
OSTree deployment non-default and boots it once via systemd-boot's \
LoaderEntryOneShot; a health check ordered before boot-complete.target gates a \
promote unit that makes it the default. The qcom_wdt watchdog is armed early by \
PID 1 and a panic reboots, so a bad trial lands back on the unchanged default. \
See docs/os/rollback.md."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = " \
    file://cultureos-trialboot \
    file://cultureos-trialboot-health.service \
    file://cultureos-trialboot-promote.service \
    file://cultureos-trialboot-deadline.service \
    file://cultureos-trialboot-deadline.timer \
    file://50-cultureos-watchdog.conf \
    file://cultureos-watchdog-modules.conf \
    file://health.d/10-sshd \
    file://health.d/20-tailscale \
    file://health.d/30-culture-node \
"

# The health gate's own checks (docs/os/rollback.md): ssh, the tailnet, the
# culture node. A trial with no checks installed fails, so these must ship.
CULTUREOS_HEALTH_CHECKS = "10-sshd 20-tailscale 30-culture-node"

S = "${UNPACKDIR}"

inherit systemd features_check

REQUIRED_DISTRO_FEATURES = "systemd usrmerge"

# Same value as conf/distro/include/cultureos-trialboot.inc (panic= on the
# kernel command line of the first deployment); the helper re-applies it to
# every trial deployment it stages.
CULTUREOS_PANIC_TIMEOUT ??= "5"

SYSTEMD_SERVICE:${PN} = " \
    cultureos-trialboot-health.service \
    cultureos-trialboot-promote.service \
    cultureos-trialboot-deadline.timer \
"
SYSTEMD_AUTO_ENABLE = "enable"

do_install() {
    install -D -m 0755 ${S}/cultureos-trialboot ${D}${sbindir}/cultureos-trialboot
    sed -i -e 's/^PANIC_TIMEOUT_DEFAULT = .*/PANIC_TIMEOUT_DEFAULT = "${CULTUREOS_PANIC_TIMEOUT}"/' \
        ${D}${sbindir}/cultureos-trialboot

    for unit in cultureos-trialboot-health.service cultureos-trialboot-promote.service \
                cultureos-trialboot-deadline.service cultureos-trialboot-deadline.timer; do
        install -D -m 0644 ${S}/${unit} ${D}${systemd_system_unitdir}/${unit}
    done

    install -D -m 0644 ${S}/50-cultureos-watchdog.conf \
        ${D}${systemd_unitdir}/system.conf.d/50-cultureos-watchdog.conf
    install -D -m 0644 ${S}/cultureos-watchdog-modules.conf \
        ${D}${nonarch_libdir}/modules-load.d/cultureos-watchdog.conf

    # Health checks (executables, run in name order on a trial boot); other
    # packages may add more, /etc/cultureos/health.d overrides or masks them.
    install -d -m 0755 ${D}${nonarch_libdir}/cultureos/health.d
    for check in ${CULTUREOS_HEALTH_CHECKS}; do
        install -m 0755 ${S}/health.d/${check} ${D}${nonarch_libdir}/cultureos/health.d/${check}
    done
}

FILES:${PN} += " \
    ${systemd_system_unitdir}/cultureos-trialboot-deadline.service \
    ${systemd_unitdir}/system.conf.d/50-cultureos-watchdog.conf \
    ${nonarch_libdir}/modules-load.d/cultureos-watchdog.conf \
    ${nonarch_libdir}/cultureos/health.d \
"

# bootctl and systemd-bless-boot ship in the systemd package.
RDEPENDS:${PN} = "python3-core python3-json ostree systemd kernel-module-qcom-wdt"

# kernel-module-qcom-wdt is machine specific.
PACKAGE_ARCH = "${MACHINE_ARCH}"
