#!/usr/bin/env bash
# M0 reference build (plan task t1): build the UNMODIFIED upstream VENTUNO Q
# Yocto image with kas-container, on this host, outside the repo.
#
# Usage: os/scripts/build-reference.sh [--fetch-only]
#
# Env overrides:
#   CULTUREOS_REF_DIR     build workspace   (default: $HOME/yocto/cultureos-ref)
#   CULTUREOS_REF_BRANCH  meta-qcom-arduino branch (default: main)
#   CULTUREOS_BB_THREADS  BB_NUMBER_THREADS (default: 8)
#   CULTUREOS_PM_JOBS     PARALLEL_MAKE -j  (default: 8)
#   DL_DIR / SSTATE_DIR   shared caches (default: $HOME/yocto/cache/{downloads,sstate-cache},
#                         the same ones os/scripts/bb.sh uses; see docs/os/building.md)
#
# Records host arch, timing, disk use and layer SHAs to $REF_DIR/build-report.txt.
set -euo pipefail

REF_DIR="${CULTUREOS_REF_DIR:-$HOME/yocto/cultureos-ref}"
BRANCH="${CULTUREOS_REF_BRANCH:-main}"
BB_THREADS="${CULTUREOS_BB_THREADS:-8}"
PM_JOBS="${CULTUREOS_PM_JOBS:-8}"
# kas-container mounts these into the container. The old build/downloads and
# build/sstate-cache are host symlinks that do not resolve inside it.
export DL_DIR="${DL_DIR:-$HOME/yocto/cache/downloads}"
export SSTATE_DIR="${SSTATE_DIR:-$HOME/yocto/cache/sstate-cache}"
REPO_URL="https://github.com/qualcomm-linux/meta-qcom-arduino.git"

command -v kas-container >/dev/null || { echo "error: kas-container not on PATH (uv tool install kas)" >&2; exit 2; }
command -v docker >/dev/null || { echo "error: docker not available" >&2; exit 2; }

mkdir -p "$REF_DIR"
cd "$REF_DIR"

if [ ! -d meta-qcom-arduino/.git ]; then
  git clone --branch "$BRANCH" "$REPO_URL" meta-qcom-arduino
fi

# kas refuses to concatenate files from a git repo with files outside it, so
# a wrapper config (outside VCS) includes the upstream ci files by repo
# reference, pins the layer commit, and adds resource caps (the Spark runs
# other workloads; keep the build polite).
SHA="$(git -C meta-qcom-arduino rev-parse HEAD)"
cat > reference.yml <<EOF
header:
  version: 14
  includes:
    - repo: meta-qcom-arduino
      file: ci/ventuno-q.yml
    - repo: meta-qcom-arduino
      file: ci/qcom-distro.yml
repos:
  meta-qcom-arduino:
    url: ${REPO_URL}
    commit: ${SHA}
    branch: ${BRANCH}
local_conf_header:
  cultureos_limits: |
    BB_NUMBER_THREADS = "${BB_THREADS}"
    PARALLEL_MAKE = "-j ${PM_JOBS}"
EOF

CONFIG="reference.yml"
REPORT="$REF_DIR/build-report.txt"

{
  echo "date_start: $(date -Is)"
  echo "host_arch: $(uname -m)"
  echo "host_kernel: $(uname -r)"
  echo "kas: $(kas --version 2>&1)"
  echo "meta-qcom-arduino: $BRANCH $(git -C meta-qcom-arduino rev-parse HEAD)"
  echo "BB_NUMBER_THREADS: $BB_THREADS  PARALLEL_MAKE: -j $PM_JOBS"
  echo "config: $CONFIG"
} > "$REPORT"

if [ "${1:-}" = "--fetch-only" ]; then
  kas-container checkout "$CONFIG"
  exit 0
fi

start=$(date +%s)
set +e
kas-container build "$CONFIG"
rc=$?
set -e
end=$(date +%s)

{
  echo "exit_code: $rc"
  echo "wall_seconds: $((end - start))"
  echo "date_end: $(date -Is)"
  echo "disk_build_dir: $(du -sh "$REF_DIR" 2>/dev/null | cut -f1)"
  echo "layers:"
  for d in */ ; do
    [ -d "$d/.git" ] && echo "  ${d%/}: $(git -C "$d" rev-parse HEAD)"
  done
  echo "qcomflash_dirs:"
  find "$REF_DIR/build/tmp/deploy/images" -maxdepth 2 -name '*.qcomflash' 2>/dev/null | sed 's/^/  /'
} >> "$REPORT"

cat "$REPORT"
exit "$rc"
