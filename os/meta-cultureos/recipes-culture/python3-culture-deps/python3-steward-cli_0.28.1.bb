# steward-cli 0.28.1 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "Steward ��� aligns and maintains resident agents across Culture projects."
HOMEPAGE = "https://pypi.org/project/steward-cli/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=601c0d3364cf29fc181440c4847c6176"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "0c82eab6a8b2386ec86d7df29d42109da496bfc3f26946c36ff73c275fd73d88"

RDEPENDS:${PN} += " \
    python3-core \
    python3-pyyaml \
"
