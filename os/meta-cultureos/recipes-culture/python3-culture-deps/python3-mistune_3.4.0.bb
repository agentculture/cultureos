# mistune 3.4.0 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "A sane and fast Markdown parser with useful plugins and renderers"
HOMEPAGE = "https://pypi.org/project/mistune/"
LICENSE = "BSD-3-Clause"
LIC_FILES_CHKSUM = "file://LICENSE;md5=7662a489238001edfceff24a3ce11cbd"

inherit pypi python_setuptools_build_meta

SRC_URI[sha256sum] = "2eaf7952af928ca8d33b779762effc1da517b62c6ad85ec8ca957e3b07b9782a"

RDEPENDS:${PN} += " \
    python3-core \
"
