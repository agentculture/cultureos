# opentelemetry-instrumentation 0.62b1 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "Instrumentation Tools & Auto Instrumentation for OpenTelemetry Python"
HOMEPAGE = "https://pypi.org/project/opentelemetry-instrumentation/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=86d3f3a95c324c9479bd8986968f4327"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "90e92a905ba4f84db06ac3aec96701df6c079b2d66e9379f8739f0a1bdcc7f45"

RDEPENDS:${PN} += " \
    python3-core \
    python3-opentelemetry-api \
    python3-opentelemetry-semantic-conventions \
    python3-packaging \
    python3-wrapt \
"
