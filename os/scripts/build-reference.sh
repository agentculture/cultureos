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
#
# Records host arch, timing, disk use and layer SHAs to $REF_DIR/build-report.txt.
set -euo pipefail

REF_DIR="${CULTUREOS_REF_DIR:-$HOME/yocto/cultureos-ref}"
BRANCH="${CULTUREOS_REF_BRANCH:-main}"
BB_THREADS="${CULTUREOS_BB_THREADS:-8}"
PM_JOBS="${CULTUREOS_PM_JOBS:-8}"
REPO_URL="https://github.com/qualcomm-linux/meta-qcom-arduino.git"

command -v kas-container >/dev/null || { echo "error: kas-container not on PATH (uv tool install kas)" >&2; exit 2; }
command -v docker >/dev/null || { echo "error: docker not available" >&2; exit 2; }

mkdir -p "$REF_DIR"
cd "$REF_DIR"

if [ ! -d meta-qcom-arduino/.git ]; then
  git clone --branch "$BRANCH" "$REPO_URL" meta-qcom-arduino
elif ! git -C meta-qcom-arduino checkout -q "$BRANCH" 2>/dev/null; then
  # Reused clone without the requested branch locally: fetch it, then switch.
  git -C meta-qcom-arduino fetch -q origin "$BRANCH:$BRANCH"
  git -C meta-qcom-arduino checkout -q "$BRANCH"
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
  # A failed build may have no deploy dir; the report must still be written.
  find "$REF_DIR/build/tmp/deploy/images" -maxdepth 2 -name '*.qcomflash' 2>/dev/null \
    | sed 's/^/  /' || true
} >> "$REPORT"

cat "$REPORT"
exit "$rc"
