# opentelemetry-api 1.41.1 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "OpenTelemetry Python API"
HOMEPAGE = "https://pypi.org/project/opentelemetry-api/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=86d3f3a95c324c9479bd8986968f4327"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "0ad1814d73b875f84494387dae86ce0b12c68556331ce6ce8fe789197c949621"

RDEPENDS:${PN} += " \
    python3-core \
    python3-importlib-metadata \
    python3-typing-extensions \
"
