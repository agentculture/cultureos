# cultureagent 0.16.0 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "cultureagent ��� agent runtime for the Culture mesh."
HOMEPAGE = "https://pypi.org/project/cultureagent/"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=1e0cf1d0d773ce7f6eb2d4b364b70760"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "1c1f2fde5d3c98265e9aa1e55bba9334b551954d3629a43ed16b897a97edb4da"

RDEPENDS:${PN} += " \
    python3-core \
    python3-agentirc-cli \
    python3-opentelemetry-api \
    python3-opentelemetry-exporter-otlp-proto-grpc \
    python3-opentelemetry-instrumentation-aiohttp-server \
    python3-opentelemetry-sdk \
    python3-opentelemetry-semantic-conventions \
    python3-pyyaml \
"
