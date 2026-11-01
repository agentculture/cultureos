# mcp 1.30.0 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "Model Context Protocol SDK"
HOMEPAGE = "https://pypi.org/project/mcp/"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=7ae711d8a91d3871696f50e34ad3c2d7"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "445414625fce5c295faa505bb11bacece661ab6f4028d57c935db57820b7a3e4"

# mcp derives its version from git tags through uv-dynamic-versioning. An
# sdist has no git, and meta-python's native plugin lacks its own deps
# (dunamai), so pin the version to PV and drop the plugin.
do_configure:prepend() {
    sed -i -e 's/^dynamic = \["version"\]$/version = "${PV}"/' \
        -e 's/^requires = \["hatchling", "uv-dynamic-versioning"\]$/requires = ["hatchling"]/' \
        -e '/^\[tool.hatch.version\]$/,/^$/d' \
        ${S}/pyproject.toml
    grep -q '^version = "${PV}"$' ${S}/pyproject.toml || bbfatal "mcp pyproject.toml: version pin failed"
    ! grep -q 'uv-dynamic-versioning"' ${S}/pyproject.toml || bbfatal "mcp pyproject.toml: plugin still required"
}

# Extra: pyjwt[crypto] -> python3-cryptography.
RDEPENDS:${PN} += " \
    python3-core \
    python3-anyio \
    python3-httpx \
    python3-httpx-sse \
    python3-jsonschema \
    python3-pydantic \
    python3-pydantic-settings \
    python3-pyjwt \
    python3-cryptography \
    python3-python-multipart \
    python3-sse-starlette \
    python3-starlette \
    python3-typing-extensions \
    python3-typing-inspection \
    python3-uvicorn \
"
