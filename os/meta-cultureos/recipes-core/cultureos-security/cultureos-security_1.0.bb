SUMMARY = "CultureOS device hardening: key-only sshd and a signed OSTree remote"
DESCRIPTION = "An sshd_config drop-in that allows public-key login only and no \
root login, and the OSTree remote the device updates from, with ed25519 \
signature verification (sign-verify=true) against the release public key."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = " \
    file://01-cultureos-hardening.conf \
    file://ostree-remote.conf.in \
"

S = "${UNPACKDIR}"

inherit allarch

# Where the device pulls OTA commits from: the DGX Spark's OSTree repo, served
# over Tailscale (MagicDNS name "spark"). Plan task t17 defines the real
# endpoint; set CULTUREOS_OSTREE_URL in the distro or local.conf to change it.
CULTUREOS_OSTREE_URL ?= "http://spark.tail0be7e0.ts.net:8650/"

# The release public key on the build host: the raw 32-byte ed25519 public key,
# base64-encoded, one key per line (the format of ostree's
# verification-ed25519-file). The real key is committed by plan task t17
# under os/keys/; this default is that path, relative to this recipe. See
# docs/os/security.md.
CULTUREOS_OSTREE_PUBKEY_FILE ?= "${@os.path.normpath(os.path.join(d.getVar('FILE_DIRNAME'), '../../../keys/cultureos-ostree.pub'))}"

# Where the key lands on the device (read-only, under /usr).
CULTUREOS_OSTREE_PUBKEY_PATH ?= "${datadir}/cultureos/ostree/cultureos-ostree-ed25519.pub"

# The remote name must be OSTREE_OSNAME: meta-updater's ota-ext4 deploys the
# first commit as ${OSTREE_OSNAME}:${OSTREE_BRANCHNAME}, so `ostree admin
# upgrade` pulls from the remote of that name.
CULTUREOS_OSTREE_REMOTE ?= "${OSTREE_OSNAME}"

# Rebuild when the key file appears or changes.
do_install[file-checksums] += "${CULTUREOS_OSTREE_PUBKEY_FILE}:True"
do_install[vardeps] += "CULTUREOS_OSTREE_URL CULTUREOS_OSTREE_PUBKEY_PATH CULTUREOS_OSTREE_REMOTE"

do_install() {
    install -d -m 0755 ${D}${sysconfdir}/ssh/sshd_config.d
    install -m 0644 ${S}/01-cultureos-hardening.conf ${D}${sysconfdir}/ssh/sshd_config.d/

    install -d -m 0755 ${D}${sysconfdir}/ostree/remotes.d
    sed -e 's|@REMOTE@|${CULTUREOS_OSTREE_REMOTE}|g' \
        -e 's|@URL@|${CULTUREOS_OSTREE_URL}|g' \
        -e 's|@PUBKEY_PATH@|${CULTUREOS_OSTREE_PUBKEY_PATH}|g' \
        ${S}/ostree-remote.conf.in > ${D}${sysconfdir}/ostree/remotes.d/${CULTUREOS_OSTREE_REMOTE}.conf
    chmod 0644 ${D}${sysconfdir}/ostree/remotes.d/${CULTUREOS_OSTREE_REMOTE}.conf

    install -d -m 0755 $(dirname ${D}${CULTUREOS_OSTREE_PUBKEY_PATH})
    if [ -f "${CULTUREOS_OSTREE_PUBKEY_FILE}" ]; then
        install -m 0644 "${CULTUREOS_OSTREE_PUBKEY_FILE}" ${D}${CULTUREOS_OSTREE_PUBKEY_PATH}
    else
        # Fail closed: the remote still demands a signature, and with no key
        # file every pull is refused. Plan task t17 commits the real key.
        bbwarn "cultureos-security: no OSTree release public key at ${CULTUREOS_OSTREE_PUBKEY_FILE}; the device will refuse every OTA pull until one is installed"
    fi
}

FILES:${PN} = " \
    ${sysconfdir}/ssh/sshd_config.d \
    ${sysconfdir}/ostree/remotes.d \
    ${datadir}/cultureos/ostree \
"
CONFFILES:${PN} = " \
    ${sysconfdir}/ssh/sshd_config.d/01-cultureos-hardening.conf \
    ${sysconfdir}/ostree/remotes.d/${CULTUREOS_OSTREE_REMOTE}.conf \
"

# The drop-in only means something to OpenSSH's sshd, and the remote needs an
# ostree built with ed25519 support (ostree_%.bbappend next to this recipe).
RDEPENDS:${PN} = "openssh-sshd ostree"
