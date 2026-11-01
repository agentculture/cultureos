# agentfront 0.21.3 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "Agent First Interface ��� scaffold CLI, MCP, and HTTP interfaces for agent-first tools."
HOMEPAGE = "https://pypi.org/project/agentfront/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=351bcd0f0eb29d4c544110cd603128f7"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "7ffdae45e94c084c31ee5ad8abc7b74b96f293ff91e1d34271ddf446b8e80f36"

RDEPENDS:${PN} += " \
    python3-core \
"
