#!/usr/bin/env bash
# Refresh the local CultureOS source + sstate mirror from the shared caches.
#
# Usage: os/scripts/refresh-mirror.sh [--dry-run] [--fetch <worktree>]
#
# Mirror layout (outside the repo):
#   $CULTUREOS_MIRROR_DIR/downloads      source tarballs, crates, git2_*.tar.gz mirror tarballs
#   $CULTUREOS_MIRROR_DIR/sstate-cache   copy of the shared sstate
# A real copy, never hard links: the shared caches keep changing (git2/ bare
# repos are updated in place), the mirror must not.
#
# Steps:
#   1. rsync $CULTUREOS_CACHE_DIR/downloads -> mirror (without git2/)
#   2. rsync $CULTUREOS_CACHE_DIR/sstate-cache -> mirror
#   3. one git2_<name>.tar.gz (+ .done) per bare clone in git2/ that has none
#   4. with --fetch <worktree>: bb.sh --runall=fetch cultureos-image against the
#      mirror as DL_DIR (BB_GENERATE_MIRROR_TARBALLS), to pull sources that are
#      in the manifest but not yet in the shared cache
#
# Env: CULTUREOS_CACHE_DIR (default $HOME/yocto/cache), CULTUREOS_MIRROR_DIR
# (default $HOME/yocto/mirror), CULTUREOS_MIRROR_JOBS (tar jobs, default 4).
# Exit codes: 0 ok, 1 usage error, 2 missing tool or source dir.
set -euo pipefail

CACHE_DIR="${CULTUREOS_CACHE_DIR:-$HOME/yocto/cache}"
MIRROR_DIR="${CULTUREOS_MIRROR_DIR:-$HOME/yocto/mirror}"
JOBS="${CULTUREOS_MIRROR_JOBS:-4}"
DRY=0
FETCH_WT=""

while [ $# -gt 0 ]; do
  case "$1" in
    -h | --help)
      sed -n '2,3p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    --dry-run) DRY=1 ;;
    --fetch)
      [ $# -ge 2 ] || {
        echo "refresh-mirror.sh: error: --fetch needs a <worktree>" >&2
        exit 1
      }
      FETCH_WT="$2"
      shift
      ;;
    *)
      echo "refresh-mirror.sh: error: unknown argument: $1" >&2
      exit 1
      ;;
  esac
  shift
done

command -v rsync >/dev/null 2>&1 || {
  echo "refresh-mirror.sh: error: rsync not found" >&2
  exit 2
}
if [ ! -d "$CACHE_DIR/downloads" ] || [ ! -d "$CACHE_DIR/sstate-cache" ]; then
  echo "refresh-mirror.sh: error: $CACHE_DIR/{downloads,sstate-cache} not found" >&2
  exit 2
fi

run() {
  if [ "$DRY" = 1 ]; then
    echo "dry-run: $*"
  else
    "$@"
  fi
}

run mkdir -p "$MIRROR_DIR/downloads" "$MIRROR_DIR/sstate-cache"
run rsync -a --exclude=/git2 --exclude=/svn --exclude='*.lock' \
  "$CACHE_DIR/downloads/" "$MIRROR_DIR/downloads/"
run rsync -a --exclude='*.lock' "$CACHE_DIR/sstate-cache/" "$MIRROR_DIR/sstate-cache/"

tar_one() {
  local src="$1" dst="$2" name tarball
  name="$(basename "$src")"
  tarball="$dst/git2_$name.tar.gz"
  if [ -s "$tarball" ] && [ -f "$tarball.done" ]; then return 0; fi
  tar -czf "$tarball.tmp" -C "$src" .
  mv "$tarball.tmp" "$tarball"
  touch "$tarball.done"
}
export -f tar_one

if [ -d "$CACHE_DIR/downloads/git2" ]; then
  if [ "$DRY" = 1 ]; then
    echo "dry-run: git2_<name>.tar.gz for each bare clone in $CACHE_DIR/downloads/git2"
  else
    # shellcheck disable=SC2016
    find "$CACHE_DIR/downloads/git2" -mindepth 1 -maxdepth 1 -type d -print0 |
      xargs -0 -I{} -P "$JOBS" bash -c 'tar_one "$1" "$2"' _ {} "$MIRROR_DIR/downloads"
    # BitBake aliases a source that moved (git2/<old> -> git2/<new>) with a symlink to an
    # in-container path; mirror it as a tarball symlink.
    find "$CACHE_DIR/downloads/git2" -mindepth 1 -maxdepth 1 -type l -print0 |
      while IFS= read -r -d '' link; do
        name="$(basename "$link")"
        target="$(basename "$(readlink "$link")")"
        ln -sfn "git2_$target.tar.gz" "$MIRROR_DIR/downloads/git2_$name.tar.gz"
        touch "$MIRROR_DIR/downloads/git2_$name.tar.gz.done"
      done
  fi
fi

if [ -n "$FETCH_WT" ]; then
  here="$(cd "$(dirname "$0")" && pwd -P)"
  run env CULTUREOS_CACHE_DIR="$MIRROR_DIR" \
    CULTUREOS_KAS_CONFIG=os/kas/cultureos.yml:os/kas/mirror-refresh.yml \
    "$here/bb.sh" "$FETCH_WT" --runall=fetch cultureos-image
fi

if [ "$DRY" = 0 ]; then
  du -sh "$MIRROR_DIR/downloads" "$MIRROR_DIR/sstate-cache" >&2
fi
