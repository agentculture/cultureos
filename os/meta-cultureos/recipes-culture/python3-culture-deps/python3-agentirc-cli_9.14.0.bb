# agentirc-cli 9.14.0 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "Agent-friendly IRCd: server core for AI agent meshes"
HOMEPAGE = "https://pypi.org/project/agentirc-cli/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=601c0d3364cf29fc181440c4847c6176"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "a307ed9046e19c887d6c0f733bde544a2ce235f1276639862e400d68de7b16e1"

RDEPENDS:${PN} += " \
    python3-core \
    python3-aiohttp \
    python3-jinja2 \
    python3-opentelemetry-api \
    python3-opentelemetry-exporter-otlp-proto-grpc \
    python3-opentelemetry-instrumentation-aiohttp-server \
    python3-opentelemetry-sdk \
    python3-pyyaml \
"
