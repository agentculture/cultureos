# argon2-cffi-bindings 26.1.0 from its PyPI sdist (sha256-pinned), built for the
# CultureOS culture node. Generated with the rest of recipes-culture; the
# packaging route and the pin set are documented in
# recipes-culture/culture/python3-culture_*.bb and docs/os/culture-node.md.
SUMMARY = "Low-level CFFI bindings for Argon2"
HOMEPAGE = "https://pypi.org/project/argon2-cffi-bindings/"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=3ee3eeb863160c2e6cece695dc3bb188"

inherit pypi python_pep517

SRC_URI[sha256sum] = "63505c71542a44b68b1e38060450fb006404170da375feb31af153e7f9c6205d"

DEPENDS += "python3-scikit-build-core-native python3-setuptools-scm-native cmake-native ninja-native"

# The vendored libargon2's CMake decides on SSE2 from CMAKE_SYSTEM_PROCESSOR,
# which is not the target's here, and passes -msse2 to the aarch64 compiler.
# Use the portable reference implementation (upstream's documented switch).
export ARGON2_CFFI_USE_SSE2 = "0"

# scikit-build-core + CMake builds the cffi extension against the vendored
# libargon2 (extras/libargon2); same cross settings as meta-python's pyzmq.
PEP517_BUILD_OPTS = "--skip-dependency-check \
    -Ccmake.define.CMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY \
    -Ccmake.define.CMAKE_FIND_ROOT_PATH_MODE_PROGRAM=ONLY \
    -Ccmake.define.CMAKE_FIND_ROOT_PATH_MODE_LIBRARY=ONLY \
    -Ccmake.define.CMAKE_FIND_ROOT_PATH_MODE_INCLUDE=ONLY \
    -Ccmake.define.CMAKE_FIND_ROOT_PATH="${STAGING_DIR_NATIVE}" \
    -Ccmake.build-type="RelWithDebInfo" \
    -Cbuild-dir="${B}" \
"

RDEPENDS:${PN} += " \
    python3-core \
    python3-cffi \
"
