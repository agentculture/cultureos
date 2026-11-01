SUMMARY = "CultureOS first-boot provisioning: login user, SSH key, Wi-Fi"
DESCRIPTION = "cultureos-provision.service (oneshot, first boot only) reads an \
operator-supplied cultureos-provision.toml from the ESP or a USB stick, validates \
it, creates the non-root login user arduino (home under /var, password from a crypt \
hash, SSH authorized key), writes an optional NetworkManager Wi-Fi profile (0600) \
and hostname, removes the input and writes /var/lib/cultureos/provisioned. \
No credentials are shipped. See docs/os/provisioning.md."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = " \
    file://cultureos-provision \
    file://cultureos-provision.service \
    file://cultureos-provision-tmpfiles.conf \
"

S = "${UNPACKDIR}"

inherit systemd features_check

REQUIRED_DISTRO_FEATURES = "systemd"

SYSTEMD_SERVICE:${PN} = "cultureos-provision.service"
SYSTEMD_AUTO_ENABLE = "enable"

# python3-core + tomllib run the helper; shadow gives useradd/usermod/chpasswd;
# coreutils gives shred and chown; util-linux blkid/mount find a USB stick or
# an unmounted ESP. networkmanager reads the profile it writes.
RDEPENDS:${PN} = " \
    python3-core \
    python3-tomllib \
    shadow \
    coreutils \
    util-linux-blkid \
    util-linux-mount \
    util-linux-umount \
    networkmanager \
"

do_install() {
    install -D -m 0755 ${S}/cultureos-provision \
        ${D}${libexecdir}/cultureos-provision/cultureos-provision
    install -D -m 0644 ${S}/cultureos-provision.service \
        ${D}${systemd_system_unitdir}/cultureos-provision.service
    install -D -m 0644 ${S}/cultureos-provision-tmpfiles.conf \
        ${D}${nonarch_libdir}/tmpfiles.d/cultureos-provision.conf
}

FILES:${PN} += " \
    ${libexecdir}/cultureos-provision \
    ${systemd_system_unitdir}/cultureos-provision.service \
    ${nonarch_libdir}/tmpfiles.d/cultureos-provision.conf \
"
