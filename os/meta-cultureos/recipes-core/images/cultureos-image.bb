SUMMARY = "CultureOS image for the Arduino VENTUNO Q"
DESCRIPTION = "The upstream Qualcomm console image (ssh, base utilities) as an \
OSTree-managed system under the cultureos distro. CultureOS packages are \
wired in by CULTUREOS_PACKAGES below."

require recipes-products/images/qcom-console-image.bb

LICENSE = "MIT"

# CultureOS packages (plan task t19 is the only task that edits this file).
#   arduino-router          MCU bridge for sketches (t8, d5)
#   tailscale tailscaled    tailnet; enrollment is a manual `tailscale up` (t9, q2)
#   cultureos-provision     first-boot user / SSH key / Wi-Fi from a file (t10)
#   cultureos-local-access  USB CDC-ACM + UART login consoles, no adbd (t11, d3)
#   cultureos-security      key-only sshd, signed OSTree remote (t12, d4)
#   culture-node            Culture mesh node, tailnet-only listener (t13, r13)
#   python3-cultureos       the cultureos CLI (`cultureos os status`, t14)
#   cultureos-trialboot     one-shot trial boot, watchdog, health-gated promote (t15)
#   cultureos-update-agent  timer pull + `cultureos-update now` (t16)
CULTUREOS_PACKAGES = "\
    arduino-router \
    tailscale tailscaled \
    cultureos-provision \
    cultureos-local-access \
    cultureos-security \
    culture-node \
    python3-cultureos \
    cultureos-trialboot \
    cultureos-update-agent \
"

CORE_IMAGE_EXTRA_INSTALL += "${CULTUREOS_PACKAGES}"

# --- Hardening of the upstream base image (t12 findings, d3) ---------------
# meta-qcom ci/base.yml adds "allow-empty-password empty-root-password
# allow-root-login" via EXTRA_IMAGE_FEATURES and qcom-minimal-image adds
# allow-root-login; drop all three so sshd_config is not rewritten to allow
# root or empty passwords.
IMAGE_FEATURES:remove = "allow-empty-password empty-root-password allow-root-login"
# qcom-minimal-image sets a fixed, publicly documented root password hash.
# Lock root instead: logins are the provisioned `arduino` user (t10, wheel/run0).
EXTRA_USERS_PARAMS = "usermod -L root;"
# image-adbd (inherited by qcom-minimal-image) installs adbd, which has adb
# authorization disabled in meta-oe: a root shell over USB. Local access is the
# login consoles of cultureos-local-access instead (d3).
# packagegroup-qcom-virtualization (libvirt + qemu, added by qcom-console-image for
# the virtualization DISTRO_FEATURE): CultureOS runs no VMs, and libvirt-libvirtd
# ships pre-generated private keys in /etc/pki/libvirt/private that would be the
# same on every board (found by os/scripts/audit-image.sh).
PACKAGE_INSTALL:remove = "\
    android-tools-adbd android-tools-adbd-cmdline \
    packagegroup-qcom-virtualization \
"
