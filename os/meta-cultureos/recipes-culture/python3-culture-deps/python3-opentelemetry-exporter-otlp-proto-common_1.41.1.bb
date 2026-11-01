# opentelemetry-exporter-otlp-proto-common 1.41.1 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "OpenTelemetry Protobuf encoding"
HOMEPAGE = "https://pypi.org/project/opentelemetry-exporter-otlp-proto-common/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=86d3f3a95c324c9479bd8986968f4327"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "0e253156ea9c36b0bd3d2440c5c9ba7dd1f3fb64ba7a08fc85fbac536b56e1fb"

RDEPENDS:${PN} += " \
    python3-core \
    python3-opentelemetry-proto \
"
