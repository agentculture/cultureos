# sse-starlette 3.6.0 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "SSE plugin for Starlette"
HOMEPAGE = "https://pypi.org/project/sse-starlette/"
LICENSE = "BSD-3-Clause"
LIC_FILES_CHKSUM = "file://LICENSE;md5=512780230e4edd77125d98c5f52abafe"

inherit pypi python_setuptools_build_meta

SRC_URI[sha256sum] = "623151d6c20dc0eebf1b3379c27faae91fff883bac7ab6665f16f46440a88b3a"

RDEPENDS:${PN} += " \
    python3-core \
    python3-anyio \
    python3-starlette \
"
