# opentelemetry-sdk 1.41.1 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "OpenTelemetry Python SDK"
HOMEPAGE = "https://pypi.org/project/opentelemetry-sdk/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=86d3f3a95c324c9479bd8986968f4327"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "724b615e1215b5aeacda0abb8a6a8922c9a1853068948bd0bd225a56d0c792e6"

RDEPENDS:${PN} += " \
    python3-core \
    python3-opentelemetry-api \
    python3-opentelemetry-semantic-conventions \
    python3-typing-extensions \
"
