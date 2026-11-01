# argon2-cffi 25.1.0 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "Argon2 for Python"
HOMEPAGE = "https://pypi.org/project/argon2-cffi/"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=e91e96ef55f45fe9caf7fc3e73672c4b"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "694ae5cc8a42f4c4e2bf2ca0e64e51e23a040c6a517a85074683d3959e1346c1"

DEPENDS += "python3-hatch-vcs-native python3-hatch-fancy-pypi-readme-native"

RDEPENDS:${PN} += " \
    python3-core \
    python3-argon2-cffi-bindings \
"
