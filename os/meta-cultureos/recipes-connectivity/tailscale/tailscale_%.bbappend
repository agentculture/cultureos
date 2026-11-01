# CultureOS: reuse meta-networking's tailscale recipe (pinned by SRCREV to a
# tagged release there) and ship our own tailscaled.service: enabled at boot,
# state under /var/lib/tailscale (/var survives OSTree deployments). No auth
# key is configured anywhere; enrollment is a manual login
# (docs/os/tailscale.md).

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://tailscaled.service"

SYSTEMD_AUTO_ENABLE:${BPN}d = "enable"

do_install:append() {
    if ${@bb.utils.contains('DISTRO_FEATURES', 'systemd', 'true', 'false', d)}; then
        install -m 0644 ${UNPACKDIR}/tailscaled.service \
            ${D}${systemd_system_unitdir}/${BPN}d.service
    fi
}
