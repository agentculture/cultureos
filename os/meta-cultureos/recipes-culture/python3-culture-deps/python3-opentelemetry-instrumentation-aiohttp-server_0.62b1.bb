# opentelemetry-instrumentation-aiohttp-server 0.62b1 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "Aiohttp server instrumentation for OpenTelemetry"
HOMEPAGE = "https://pypi.org/project/opentelemetry-instrumentation-aiohttp-server/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/Apache-2.0;md5=89aea4e17d99a7cacdbeed46a0096b10"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "c1f271376d3d07ab7bb26a68c76a96d9ce99339839f2d653cd340c3ea5d08539"

RDEPENDS:${PN} += " \
    python3-core \
    python3-opentelemetry-api \
    python3-opentelemetry-instrumentation \
    python3-opentelemetry-semantic-conventions \
    python3-opentelemetry-util-http \
    python3-wrapt \
"
