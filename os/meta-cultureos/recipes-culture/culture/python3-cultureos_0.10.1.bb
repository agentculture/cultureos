# cultureos 0.10.1 (this repo's CLI, zero third-party runtime deps) from its
# sha256-pinned PyPI sdist. Bump PV and the sha256 together when a new
# cultureos release should go into the image. Route: see
# python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "CultureOS - an operating system built on Culture, the AgentCulture agent mesh."
HOMEPAGE = "https://pypi.org/project/cultureos/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=601c0d3364cf29fc181440c4847c6176"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "9012667cb869e2eb4398a7a0d1ba1a91bf197d39b8541cef82bafcdbc37bb868"

RDEPENDS:${PN} += " \
    python3-core \
    python3-modules \
"
