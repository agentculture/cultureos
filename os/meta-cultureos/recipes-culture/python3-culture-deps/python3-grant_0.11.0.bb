# grant 0.11.0 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "grant CLI"
HOMEPAGE = "https://pypi.org/project/grant/"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=24a760f554ee214e5414e0b87076392c"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "a8af8e5f1e4f795d0bdd39b2dfabc4ee508a40604c2a95b24b16591f61aa984e"

RDEPENDS:${PN} += " \
    python3-core \
"
