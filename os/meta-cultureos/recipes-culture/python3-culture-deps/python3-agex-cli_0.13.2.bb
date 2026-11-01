# agex-cli 0.13.2 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "Agent-operated developer-experience CLI ��� deterministic per-backend markdown briefings for autonomous agents."
HOMEPAGE = "https://pypi.org/project/agex-cli/"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=24a760f554ee214e5414e0b87076392c"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "cf682331405b6a953f658daf3ddc33f36defd715add80844e8e93dd41ece1e87"

RDEPENDS:${PN} += " \
    python3-core \
    python3-jinja2 \
    python3-portalocker \
    python3-pyyaml \
    python3-tomlkit \
    python3-typer \
"
