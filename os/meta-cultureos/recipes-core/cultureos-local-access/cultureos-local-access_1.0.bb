SUMMARY = "CultureOS local no-network shell: USB CDC-ACM gadget + serial logins"
DESCRIPTION = "Gives a login with Ethernet unplugged and Wi-Fi off, with no Android debug daemon. \
cultureos-usb-gadget.service builds a configfs USB gadget with two CDC-ACM \
functions on the board's UDC: ttyGS0 stays free for the arduino-router serial \
bridge, ttyGS1 carries serial-getty@ttyGS1. serial-getty@ttyMSM0 serves the UART. \
Both gettys are plain agetty -> login: password login only, no root login (root is locked \
and the login user comes from first-boot provisioning). No users are created here."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = " \
    file://cultureos-usb-gadget.sh \
    file://cultureos-usb-gadget.service \
    file://gadget-getty.conf \
"

S = "${UNPACKDIR}"

RDEPENDS:${PN} = "systemd kernel-module-libcomposite kernel-module-usb-f-acm kernel-module-u-serial"

# The getty units live in the systemd package, so systemd.bbclass
# SYSTEMD_SERVICE can only cover our own gadget unit; the gettys are enabled in
# a postinst. `systemctl enable` is idempotent.
inherit systemd
SYSTEMD_SERVICE:${PN} = "cultureos-usb-gadget.service"
SYSTEMD_AUTO_ENABLE = "enable"

CULTUREOS_LOCAL_GETTYS = "serial-getty@ttyMSM0.service serial-getty@ttyGS1.service"

pkg_postinst:${PN}() {
    if [ -n "$D" ]; then
        OPTS="--root=$D"
    fi
    systemctl $OPTS enable ${CULTUREOS_LOCAL_GETTYS}
}

do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${UNPACKDIR}/cultureos-usb-gadget.sh ${D}${bindir}/cultureos-usb-gadget

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/cultureos-usb-gadget.service ${D}${systemd_system_unitdir}/

    install -d ${D}${systemd_system_unitdir}/serial-getty@ttyGS1.service.d
    install -m 0644 ${UNPACKDIR}/gadget-getty.conf \
        ${D}${systemd_system_unitdir}/serial-getty@ttyGS1.service.d/10-cultureos-gadget.conf
}

FILES:${PN} += "${systemd_system_unitdir}"

PACKAGE_ARCH = "${MACHINE_ARCH}"
