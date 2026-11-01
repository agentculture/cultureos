# opentelemetry-util-http 0.62b1 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "Web util for OpenTelemetry"
HOMEPAGE = "https://pypi.org/project/opentelemetry-util-http/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/Apache-2.0;md5=89aea4e17d99a7cacdbeed46a0096b10"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "adf6facbb89aef8f8bc566e2f04624942ba08a7b678b3479a91051a8f4dc70a3"

RDEPENDS:${PN} += " \
    python3-core \
"
