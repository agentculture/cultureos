# opentelemetry-proto 1.41.1 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "OpenTelemetry Python Proto"
HOMEPAGE = "https://pypi.org/project/opentelemetry-proto/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=86d3f3a95c324c9479bd8986968f4327"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "4b9d2eb631237ea43b80e16c073af438554e32bc7e9e3f8ca4a9582f900020e5"

RDEPENDS:${PN} += " \
    python3-core \
    python3-protobuf \
"
