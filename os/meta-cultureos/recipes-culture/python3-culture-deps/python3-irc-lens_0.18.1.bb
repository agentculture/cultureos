# irc-lens 0.18.1 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "Web chat console for CULTURE.DEV ��� the reactive, Playwright-driveable lens on the AgentIRC mesh behind chat.culture.dev."
HOMEPAGE = "https://pypi.org/project/irc-lens/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=601c0d3364cf29fc181440c4847c6176"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "89f2a9dcfe372fa3d0c9c565fc4ba99f84999c7436fba4c4c602dc5ded3f5943"

# Extras: agentfront[mcp] -> python3-mcp, pyjwt[crypto] -> python3-cryptography.
RDEPENDS:${PN} += " \
    python3-core \
    python3-agentfront \
    python3-mcp \
    python3-aiohttp \
    python3-argon2-cffi \
    python3-jinja2 \
    python3-pyjwt \
    python3-cryptography \
    python3-pyyaml \
"
