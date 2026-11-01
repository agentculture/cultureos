#!/usr/bin/env bash
# Shared, serialized CultureOS build: run kas-container / bitbake against ONE
# build dir and ONE download + sstate cache, with the layer taken from the
# caller's worktree.
#
# Usage:
#   os/scripts/bb.sh <worktree>                    kas build (targets from the manifest)
#   os/scripts/bb.sh <worktree> <bitbake args...>  bitbake <args> inside the kas env
#   os/scripts/bb.sh <worktree> --kas <cmd> [opts] kas-container <cmd> [opts] <manifest>
#
# Examples:
#   os/scripts/bb.sh "$PWD"                            # build cultureos-image
#   os/scripts/bb.sh "$PWD" tailscale                  # build one recipe
#   os/scripts/bb.sh "$PWD" -c cleansstate tailscale   # any bitbake args
#   os/scripts/bb.sh "$PWD" -e cultureos-image         # inspect variables
#   os/scripts/bb.sh "$PWD" --kas lock                 # refresh os/kas/cultureos.lock.yml
#
# <worktree> is a checkout of this repo (the main checkout or any git
# worktree). Its os/kas/cultureos.yml is the manifest for the run, and since
# that manifest adds os/meta-cultureos from "this repo" (no url), the layer
# used is the one in <worktree>. kas-container mounts <worktree> at /repo
# (read-only), so every run sees its layer at the same in-container path and
# runs from different worktrees do not clobber each other's layer content.
#
# Serialization: every run takes an exclusive flock on $CULTUREOS_BB_LOCK. A
# second caller waits (it prints who holds the lock) and runs when the first
# is done; it never fails because of the lock. The lock is released when the
# holder exits, whatever its exit code.
#
# Env overrides:
#   CULTUREOS_BUILD_ROOT    KAS_WORK_DIR, upstream layer checkouts (default: $HOME/yocto/cultureos-build)
#                           the bitbake build dir is $CULTUREOS_BUILD_ROOT/build
#   CULTUREOS_CACHE_DIR     shared caches (default: $HOME/yocto/cache)
#                           DL_DIR=$CULTUREOS_CACHE_DIR/downloads
#                           SSTATE_DIR=$CULTUREOS_CACHE_DIR/sstate-cache
#   CULTUREOS_BB_LOCK       lock file (default: $CULTUREOS_BUILD_ROOT/bb.lock)
#   CULTUREOS_KAS_CONFIG    manifest(s), relative to <worktree>, ':'-separated
#                           (default: os/kas/cultureos.yml)
#   CULTUREOS_KAS_CONTAINER kas-container binary (default: kas-container)
#
# Exit codes: the kas-container / bitbake exit code; 1 usage error (bad
# arguments, <worktree> without the manifest or layer); 2 environment error
# (kas-container or flock missing).
set -euo pipefail

usage() {
  sed -n '6,10p' "$0" | sed 's/^# \{0,1\}//'
}

if [ $# -eq 0 ]; then
  echo "bb.sh: error: missing <worktree>" >&2
  usage >&2
  exit 1
fi
case "$1" in
  -h | --help)
    usage
    exit 0
    ;;
esac

WORKTREE="$1"
shift
if [ ! -d "$WORKTREE" ]; then
  echo "bb.sh: error: $WORKTREE is not a directory (expected a checkout holding os/kas/cultureos.yml)" >&2
  exit 1
fi
WORKTREE="$(cd "$WORKTREE" && pwd -P)"

CONFIG_REL="${CULTUREOS_KAS_CONFIG:-os/kas/cultureos.yml}"
CONFIG=""
IFS=':' read -r -a config_parts <<<"$CONFIG_REL"
for part in "${config_parts[@]}"; do
  if [ ! -f "$WORKTREE/$part" ]; then
    echo "bb.sh: error: $WORKTREE/$part not found (expected os/kas/cultureos.yml in a cultureos checkout)" >&2
    exit 1
  fi
  CONFIG="${CONFIG:+$CONFIG:}$WORKTREE/$part"
done
if [ ! -f "$WORKTREE/os/meta-cultureos/conf/layer.conf" ]; then
  echo "bb.sh: error: $WORKTREE/os/meta-cultureos/conf/layer.conf not found" >&2
  exit 1
fi

KAS_CONTAINER="${CULTUREOS_KAS_CONTAINER:-kas-container}"
command -v "$KAS_CONTAINER" >/dev/null 2>&1 || {
  echo "bb.sh: error: kas-container ($KAS_CONTAINER) not found (uv tool install kas)" >&2
  exit 2
}
command -v flock >/dev/null 2>&1 || {
  echo "bb.sh: error: flock not found (util-linux)" >&2
  exit 2
}

BUILD_ROOT="${CULTUREOS_BUILD_ROOT:-$HOME/yocto/cultureos-build}"
CACHE_DIR="${CULTUREOS_CACHE_DIR:-$HOME/yocto/cache}"
LOCK="${CULTUREOS_BB_LOCK:-$BUILD_ROOT/bb.lock}"

mkdir -p "$BUILD_ROOT/build" "$CACHE_DIR/downloads" "$CACHE_DIR/sstate-cache" "$(dirname "$LOCK")"

export KAS_WORK_DIR="$BUILD_ROOT"
export KAS_BUILD_DIR="$BUILD_ROOT/build"
export DL_DIR="$CACHE_DIR/downloads"
export SSTATE_DIR="$CACHE_DIR/sstate-cache"

if [ $# -eq 0 ]; then
  cmd=(build "$CONFIG")
elif [ "$1" = "--kas" ]; then
  shift
  if [ $# -eq 0 ]; then
    echo "bb.sh: error: --kas needs a kas-container subcommand" >&2
    exit 1
  fi
  cmd=("$@" "$CONFIG")
else
  bb_cmd="bitbake"
  for arg in "$@"; do
    bb_cmd+=" $(printf '%q' "$arg")"
  done
  cmd=(--repo-ro shell -c "$bb_cmd" "$CONFIG")
fi

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "bb.sh: build busy (lock $LOCK held by: $(cat "$LOCK.owner" 2>/dev/null || echo unknown)); waiting..." >&2
  flock 9
fi
echo "pid=$$ worktree=$WORKTREE since=$(date -Is) cmd=${cmd[*]}" >"$LOCK.owner"

echo "bb.sh: $KAS_CONTAINER ${cmd[*]}" >&2
set +e
"$KAS_CONTAINER" "${cmd[@]}"
rc=$?
set -e
: >"$LOCK.owner"
exit "$rc"
