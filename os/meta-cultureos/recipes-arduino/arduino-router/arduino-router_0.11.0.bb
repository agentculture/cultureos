SUMMARY = "Arduino Router: MessagePack-RPC router between the Linux side and the MCU"
DESCRIPTION = "arduino-router owns the board's MCU serial link and serves \
MessagePack-RPC clients on /var/run/arduino-router.sock. Built from the tagged \
upstream release, same version as the factory Ubuntu package. This recipe only \
builds and runs the router; it never installs or flashes MCU firmware."
HOMEPAGE = "https://github.com/arduino/arduino-router"
SECTION = "console/utils"

LICENSE = "GPL-3.0-or-later"
LIC_FILES_CHKSUM = "file://src/${GO_IMPORT}/LICENSE.txt;md5=1ebbd3e34237af26da5dc08a4e440464"
require ${BPN}-licenses.inc

SRC_URI = "git://github.com/arduino/arduino-router.git;protocol=https;branch=main;destsuffix=${GO_SRCURI_DESTSUFFIX};tag=v${PV} \
           file://arduino-router.service \
           file://arduino-router.default \
           file://99-cultureos-stm-tty.rules \
           "
SRCREV = "cb7b2cecee1c04e0ba0a7fb48da63a8a7a1dba71"
require ${BPN}-go-mods.inc

GO_IMPORT = "github.com/arduino/arduino-router"
GO_INSTALL = "${GO_IMPORT} ${GO_IMPORT}/cmd/arduino-router-cli"
GO_LINKSHARED = ""

# Pure Go (go.bug.st/serial needs no cgo on Linux): a static binary.
export CGO_ENABLED = "0"
# Truly static: no -buildmode=pie (go.bbclass adds it for aarch64, which makes
# the linker emit a PT_INTERP) and no dynamic loader path.
GOBUILDFLAGS:remove = "-buildmode=pie"
GO_LINUXLOADER = ""
GO_EXTRA_LDFLAGS = "-X main.Version=${PV}"

inherit go-mod go-mod-update-modules systemd useradd

# The router chowns its socket to the "arduino-router" group when it exists.
USERADD_PACKAGES = "${PN}"
GROUPADD_PARAM:${PN} = "--system arduino-router"

SYSTEMD_PACKAGES = "${PN}"
SYSTEMD_SERVICE:${PN} = "arduino-router.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${B}/${GO_BUILD_BINDIR}/arduino-router ${D}${bindir}/arduino-router
    install -m 0755 ${B}/${GO_BUILD_BINDIR}/arduino-router-cli ${D}${bindir}/arduino-router-cli

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/arduino-router.service ${D}${systemd_system_unitdir}/arduino-router.service

    install -d ${D}${nonarch_base_libdir}/udev/rules.d
    install -m 0644 ${UNPACKDIR}/99-cultureos-stm-tty.rules ${D}${nonarch_base_libdir}/udev/rules.d/99-cultureos-stm-tty.rules

    install -d ${D}${sysconfdir}/default
    install -m 0644 ${UNPACKDIR}/arduino-router.default ${D}${sysconfdir}/default/arduino-router
}

# Static Go binaries are stripped by the Go toolchain; skip the QA checks that
# assume a dynamically linked, unstripped binary.
INSANE_SKIP:${PN} += "ldflags already-stripped"
FILES:${PN} += "${nonarch_base_libdir}/udev/rules.d/99-cultureos-stm-tty.rules ${systemd_system_unitdir}/arduino-router.service ${sysconfdir}/default/arduino-router"
FILES:${PN}-src += "${libdir}/go/src"
RDEPENDS:${PN}-dev += "${PN}-staticdev"
