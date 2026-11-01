SUMMARY = "CultureOS image for the Arduino VENTUNO Q"
DESCRIPTION = "The upstream Qualcomm console image (ssh, base utilities) as an \
OSTree-managed system under the cultureos distro. CultureOS packages are \
wired in by CULTUREOS_PACKAGES below."

require recipes-products/images/qcom-console-image.bb

LICENSE = "MIT"

# CultureOS packages. Empty in the layer skeleton; the image integration task
# (t19) is the only one that fills this list (arduino-router, tailscale,
# provisioning, local access, security, culture node, cultureos CLI, trial
# boot, update agent). Recipe tasks add their recipes under recipes-*/ and
# leave this file alone.
CULTUREOS_PACKAGES = ""

CORE_IMAGE_EXTRA_INSTALL += "${CULTUREOS_PACKAGES}"
