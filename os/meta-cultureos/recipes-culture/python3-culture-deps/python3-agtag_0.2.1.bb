# agtag 0.2.1 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "Agent to Agent communication CLI."
HOMEPAGE = "https://pypi.org/project/agtag/"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=1e0cf1d0d773ce7f6eb2d4b364b70760"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "a616449975a58b4f89acc253101d713af9da586c86feafe176cda79c910084f8"

RDEPENDS:${PN} += " \
    python3-core \
    python3-pyyaml \
"
