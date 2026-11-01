# googleapis-common-protos 1.76.0 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "Common protobufs used in Google APIs"
HOMEPAGE = "https://pypi.org/project/googleapis-common-protos/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=3b83ef96387f14655fc854ddc3c6bd57"

inherit pypi python_setuptools_build_meta

SRC_URI[sha256sum] = "71db0e44a1d4c2dd024ebad44ca67129cc1e2892e4861df466764749d5ef8642"

RDEPENDS:${PN} += " \
    python3-core \
    python3-protobuf \
"
