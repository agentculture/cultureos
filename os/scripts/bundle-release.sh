#!/usr/bin/env bash
# Build a local CultureOS release bundle from a Yocto deploy dir. Never uploads.
# Usage: os/scripts/bundle-release.sh <deploy-dir> <out-dir> [version]
#   <deploy-dir>  tmp/deploy (holds images/ventuno-q/ and licenses/)
#   <out-dir>     where cultureos-release-<version>.tar is written (outside the repo)
# Exits non-zero, leaving no tarball, if LICENSE.qcom-2 is missing or anything
# source-like for the Qualcomm firmware would be bundled. See docs/os/release-bundle.md.
set -euo pipefail

[ $# -ge 2 ] || { echo "usage: $0 <deploy-dir> <out-dir> [version]" >&2; exit 1; }
DEPLOY=$1 OUT=$2 VERSION=${3:-$(date +%Y%m%d)}
IMG="$DEPLOY/images/ventuno-q"
NAME="cultureos-release-$VERSION"
TARBALL="$OUT/$NAME.tar"
SRC_RE='\.(c|h|S|s|cc|cpp|patch|diff)$|\.(tar|tgz|zip)(\.[a-z0-9]+)?$|\.src\.rpm$'

die() { echo "bundle-release: $*" >&2; exit 2; }

[ -d "$IMG" ] || die "no $IMG"
[ -d "$DEPLOY/licenses" ] || die "no $DEPLOY/licenses"
mkdir -p "$OUT"
STAGE=$(mktemp -d "$OUT/.stage.XXXXXX")
cleanup() { rm -rf "$STAGE"; }
on_exit() {
  local rc=$?
  cleanup
  if [ "$rc" -ne 0 ]; then rm -f "$TARBALL"; fi
  exit "$rc"
}
trap on_exit EXIT
B="$STAGE/$NAME"
mkdir -p "$B/images" "$B/licenses"

# Images: the flash bundle (binary firmware) and the OSTree commit. Unversioned
# symlinks are dereferenced; the real build-stamped name is kept.
for pat in '.rootfs*.qcomflash.tar.gz' '.rootfs*.ostreecommit.tar.zst'; do
  f=$(find "$IMG" -maxdepth 1 -name "cultureos-image-ventuno-q$pat" | sort | tail -n 1)
  [ -n "$f" ] || die "missing image artifact $pat in $IMG"
  cp -L "$f" "$B/images/$(basename "$(readlink -f "$f")")"
done

# Licences: every recipe dir that carries a Qualcomm licence (LICENSE.qcom-2 or
# the LicenseRef-*qcom-2 generic). Licence text only; recipe dirs hold no sources.
found=0
while IFS= read -r d; do
  r=$(basename "$d")
  mkdir -p "$B/licenses/$r"
  cp -L "$d"/* "$B/licenses/$r/" 2>/dev/null || true
  if [ -f "$d/LICENSE.qcom-2" ]; then found=1; fi
done < <(find "$DEPLOY/licenses" -mindepth 2 -maxdepth 2 -type d \
  \( -exec test -e '{}/LICENSE.qcom-2' \; -o -exec sh -c "ls \"\$1\"/generic_LicenseRef-*qcom* >/dev/null 2>&1" _ '{}' \; \) -print | sort)
[ "$found" -eq 1 ] || die "LICENSE.qcom-2 not found under $DEPLOY/licenses; refusing to bundle"

# No-firmware-source check: nothing source-like staged, nor inside the flash tarball.
bad=$(find "$B" -type f | grep -E "$SRC_RE" | grep -v -E '\.(tar\.gz|tar\.zst)$' || true)
[ -z "$bad" ] || die "source-like files staged: $bad"
bad=$(tar tzf "$B"/images/*.qcomflash.tar.gz | grep -E "$SRC_RE" || true)
[ -z "$bad" ] || die "source-like files inside the flash bundle: $bad"

# MANIFEST: sha256 of every other file, written last, then archive.
(cd "$B" && find . -type f | sort | sed 's|^\./||' | xargs -d '\n' sha256sum >"$STAGE/MANIFEST.tmp")
mv "$STAGE/MANIFEST.tmp" "$B/MANIFEST.sha256"
grep -q 'LICENSE\.qcom-2$' "$B/MANIFEST.sha256" || die "manifest lacks LICENSE.qcom-2"
tar -C "$STAGE" -cf "$TARBALL" "$NAME"
echo "$TARBALL"
