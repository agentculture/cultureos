# httpx-sse 0.4.3 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "Consume Server-Sent Event (SSE) messages with HTTPX."
HOMEPAGE = "https://pypi.org/project/httpx-sse/"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=847662516af24b720ff6168b0dfcc6b1"

inherit pypi python_setuptools_build_meta

SRC_URI[sha256sum] = "9b1ed0127459a66014aec3c56bebd93da3c1bc8bb6618c8082039a44889a755d"

DEPENDS += "python3-setuptools-scm-native python3-wheel-native"

RDEPENDS:${PN} += " \
    python3-core \
"
