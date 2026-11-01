SUMMARY = "CultureOS update agent: hourly signed OSTree pull and a push entrypoint"
DESCRIPTION = "cultureos-update checks the Tailscale-served OSTree remote for a new \
signed release commit and hands it to cultureos-trialboot. cultureos-update.timer \
runs the check hourly (pull); `cultureos-update now`, callable over ssh by group \
wheel through a polkit rule scoped to starting cultureos-update.service, runs the \
same check on demand (push). Writes the failed outcome to \
/var/lib/cultureos/update-state.json. See docs/os/update-agent.md."
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = " \
    file://cultureos-update \
    file://cultureos-update.service \
    file://cultureos-update.timer \
    file://50-cultureos-update.rules \
"

S = "${UNPACKDIR}"

inherit systemd features_check

REQUIRED_DISTRO_FEATURES = "systemd usrmerge"

# The remote (cultureos-security writes /etc/ostree/remotes.d/<remote>.conf) and the
# branch the release repo publishes (docs/os/release-repo.md). Baked into the agent;
# it does not take them from its environment.
CULTUREOS_UPDATE_REMOTE ?= "${OSTREE_OSNAME}"
CULTUREOS_UPDATE_BRANCH ?= "${OSTREE_BRANCHNAME}"
do_install[vardeps] += "CULTUREOS_UPDATE_REMOTE CULTUREOS_UPDATE_BRANCH"

# Only the timer is enabled; the service has no [Install] section and runs when the
# timer or `cultureos-update now` starts it.
SYSTEMD_SERVICE:${PN} = "cultureos-update.timer"
SYSTEMD_AUTO_ENABLE = "enable"

do_install() {
    install -D -m 0755 ${S}/cultureos-update ${D}${bindir}/cultureos-update
    sed -i -e 's/^REMOTE = .*/REMOTE = "${CULTUREOS_UPDATE_REMOTE}"/' \
        -e 's/^BRANCH = .*/BRANCH = "${CULTUREOS_UPDATE_BRANCH}"/' \
        ${D}${bindir}/cultureos-update

    install -D -m 0644 ${S}/cultureos-update.service \
        ${D}${systemd_system_unitdir}/cultureos-update.service
    install -D -m 0644 ${S}/cultureos-update.timer \
        ${D}${systemd_system_unitdir}/cultureos-update.timer

    # Same location and mode as meta-oe's polkit-group-rule-* recipes.
    install -d -m 0755 ${D}${datadir}/polkit-1/rules.d
    install -m 0644 ${S}/50-cultureos-update.rules ${D}${datadir}/polkit-1/rules.d/
}

FILES:${PN} += " \
    ${systemd_system_unitdir}/cultureos-update.service \
    ${datadir}/polkit-1/rules.d \
"

# python3-io: socket; python3-fcntl: the run lock. cultureos-trialboot stages the
# commit; cultureos-security provides the signed remote; polkit enforces the rule.
RDEPENDS:${PN} = " \
    python3-core python3-json python3-io python3-fcntl \
    ostree systemd polkit \
    cultureos-trialboot cultureos-security \
"

# OSTREE_BRANCHNAME is the machine (SOTA_HARDWARE_ID).
PACKAGE_ARCH = "${MACHINE_ARCH}"
