# pydantic-settings 2.15.0 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "Settings management using Pydantic"
HOMEPAGE = "https://pypi.org/project/pydantic-settings/"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=9adde1a30a7e74a03e57e456551c19ae"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "694b793e84f766ba76a90ebdefc01d0a9a045dab0382bee70393da93712ad117"

RDEPENDS:${PN} += " \
    python3-core \
    python3-pydantic \
    python3-python-dotenv \
    python3-typing-inspection \
"
