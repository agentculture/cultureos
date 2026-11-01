# The Culture mesh node of a CultureOS board: culture-node.service runs the
# culture (agentirc) server in the foreground as the `culture` system user.
#
# Identity and state: culture keeps everything under $HOME/.culture (server
# name/default, mesh.yaml, data, logs, pids). The unit sets
# HOME=/var/lib/culture for the culture user and lets systemd create that
# directory (StateDirectory=culture), so all of it lands in
# /var/lib/culture/.culture without patching culture. Nothing is installed
# into /var at build time: OSTree does not carry build-time /var content to a
# deployed system, and /var survives OSTree updates and rollbacks.
#
# Python packaging route for culture and its dependencies: see
# python3-culture_*.bb (per-package recipes from pinned PyPI sdists, native
# deps from oe-core/meta-python, no venv, no runtime network).
#
# Mesh enrollment (node name, mesh.yaml peers, link passwords) is an operator
# step; no credentials or mesh secrets are part of this recipe. See
# docs/os/culture-node.md.
SUMMARY = "Culture mesh node service (culture server under systemd)"
HOMEPAGE = "https://github.com/agentculture/cultureos"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/Apache-2.0;md5=89aea4e17d99a7cacdbeed46a0096b10"

SRC_URI = " \
    file://culture-node.service \
    file://culture-node-start \
    file://node.env.example \
"

S = "${UNPACKDIR}"

inherit allarch systemd useradd

USERADD_PACKAGES = "${PN}"
USERADD_PARAM:${PN} = "--system --home-dir /var/lib/culture --no-create-home \
    --shell /sbin/nologin --user-group culture"

SYSTEMD_SERVICE:${PN} = "culture-node.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_install() {
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/culture-node.service ${D}${systemd_system_unitdir}/
    install -d ${D}${libexecdir}/culture-node
    install -m 0755 ${UNPACKDIR}/culture-node-start ${D}${libexecdir}/culture-node/
    install -d ${D}${datadir}/culture-node
    install -m 0644 ${UNPACKDIR}/node.env.example ${D}${datadir}/culture-node/
}

FILES:${PN} += " \
    ${systemd_system_unitdir}/culture-node.service \
    ${libexecdir}/culture-node \
    ${datadir}/culture-node \
"

RDEPENDS:${PN} += " \
    python3-culture \
    python3-cultureos \
"
