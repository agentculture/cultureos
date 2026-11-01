# opentelemetry-semantic-conventions 0.62b1 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "OpenTelemetry Semantic Conventions"
HOMEPAGE = "https://pypi.org/project/opentelemetry-semantic-conventions/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=86d3f3a95c324c9479bd8986968f4327"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "c5cc6e04a7f8c7cdd30be2ed81499fa4e75bfbd52c9cb70d40af1f9cd3619802"

RDEPENDS:${PN} += " \
    python3-core \
    python3-opentelemetry-api \
    python3-typing-extensions \
"
