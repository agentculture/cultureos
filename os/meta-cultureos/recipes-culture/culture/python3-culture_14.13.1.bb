# culture 14.13.1 (the AgentCulture mesh: CLI, agentirc server, harnesses),
# built from its sha256-pinned PyPI sdist. The node service that runs it is
# recipes-culture/culture-node; docs/os/culture-node.md has the full audit.
#
# PACKAGING ROUTE (plan t13, lapse l3): per-package recipes, no venv.
#
# Audit of culture==14.13.1 + cultureos==0.10.1 resolved for linux/aarch64
# (77 distributions). Compiled/native ones: aiohttp, frozenlist, multidict,
# propcache, yarl, wrapt, markupsafe, pyyaml (C); cffi (C); grpcio (C++);
# protobuf (upb C); cryptography, pydantic-core, rpds-py (Rust);
# argon2-cffi-bindings (C, vendored libargon2). Every one of them except
# argon2-cffi-bindings already has a cross-building recipe in oe-core or
# meta-python at the pinned layer commits, so the native code is built by the
# layer recipes for the target, not shipped as foreign manylinux wheels.
# The 26 distributions with no recipe anywhere in the stack (culture and
# cultureos included) are pure Python (hatchling or setuptools sdists) except
# argon2-cffi-bindings (scikit-build-core + CMake, whose build tools are in
# meta-python); they get one recipe each under recipes-culture/ (this dir and
# python3-culture-deps/), 27 recipes with the googleapis-common-protos
# override below.
#
# Rejected: a build-time venv / wheel bundle. It is possible (all 15 native
# deps above publish cp314 or abi3 manylinux aarch64 wheels), but fetching
# wheels inside do_compile breaks bitbake's no-network rule, and pre-fetched
# manylinux wheels would put 15 foreign-built native extensions in the image
# outside the toolchain, QA, CVE and license tracking.
#
# Target Python is oe-core's python3 3.14.9; culture requires >=3.12.
#
# Version set: the layer recipes' versions are used where they exist (anyio
# 4.15.1, pydantic 2.13.5, starlette 1.6.0, uvicorn 0.49.0, grpcio 1.84.1,
# multidict 6.7.1, ...); `uv pip compile` with those as constraints resolves.
# Two exceptions:
#   - googleapis-common-protos: meta-python's 1.63.2 needs protobuf<6 and
#     the stack has protobuf 6.33.6, so this layer carries 1.76.0
#     (python3-culture-deps/, overrides meta-python by layer priority).
#   - importlib-metadata: opentelemetry-api 1.41.1 declares <8.8 but
#     meta-python ships 9.1.0. That is a metadata-only conflict (nothing
#     checks Requires-Dist at runtime); culture --version, cultureos
#     --version and otel entry-point lookup were smoke-tested against
#     exactly this set on CPython 3.14.9. Kept on meta-python's 9.1.0.
#
# Runtime network: none. Everything is fetched at do_fetch from PyPI by
# sha256; the image installs no pip and fetches nothing at runtime.
SUMMARY = "CULTURE.DEV: the professional workspace for agents (CLI, harnesses, AgentIRC mesh)"
HOMEPAGE = "https://pypi.org/project/culture/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://LICENSE;md5=601c0d3364cf29fc181440c4847c6176"

inherit pypi python_hatchling

SRC_URI[sha256sum] = "74ace0aa8b7084a61bf63cabef1d68c5e3f643a86640326fab148f872d77da24"

# python3-modules: culture uses a broad slice of the stdlib (asyncio, sqlite3,
# email, logging, http, ...); pulling the whole split stdlib is simpler and
# safer than tracking each split package.
RDEPENDS:${PN} += " \
    python3-core \
    python3-modules \
    python3-agentfront \
    python3-agentirc-cli \
    python3-agex-cli \
    python3-agtag \
    python3-aiohttp \
    python3-cultureagent \
    python3-grant \
    python3-irc-lens \
    python3-mistune \
    python3-opentelemetry-api \
    python3-opentelemetry-exporter-otlp-proto-grpc \
    python3-opentelemetry-instrumentation-aiohttp-server \
    python3-opentelemetry-sdk \
    python3-opentelemetry-semantic-conventions \
    python3-pyyaml \
    python3-steward-cli \
"
