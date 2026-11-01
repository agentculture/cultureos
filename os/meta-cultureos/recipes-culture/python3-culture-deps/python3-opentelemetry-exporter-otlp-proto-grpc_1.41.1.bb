# opentelemetry-exporter-otlp-proto-grpc 1.41.1 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "OpenTelemetry Collector Protobuf over gRPC Exporter"
HOMEPAGE = "https://pypi.org/project/opentelemetry-exporter-otlp-proto-grpc/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=86d3f3a95c324c9479bd8986968f4327"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "b05df8fa1333dc9a3fda36b676b96b5095ab6016d3f0c3296d430d629ba1443b"

RDEPENDS:${PN} += " \
    python3-core \
    python3-googleapis-common-protos \
    python3-grpcio \
    python3-opentelemetry-api \
    python3-opentelemetry-exporter-otlp-proto-common \
    python3-opentelemetry-proto \
    python3-opentelemetry-sdk \
    python3-typing-extensions \
"
