#!/usr/bin/env bash
# Publish a CultureOS build's OSTree commit to the signed release repo on the Spark.
#
# Steps (all-or-nothing for the published ref):
#   1. pull the build's commit, BY CHECKSUM (no ref is created), into the release repo
#   2. sign that commit (ed25519) with the private key kept outside the git repo
#   3. verify it the way a board will: pull it into a throwaway repo through a remote
#      that has --sign-verify=ed25519=file:<public key>
#   4. only now move the published ref, then update + sign the summary
#   5. re-verify the summary the same way; on ANY failure after step 4, put the ref and
#      the summary files back exactly as they were
# A failure at any step therefore leaves the published ref (and summary) unchanged.
#
# Config: env vars, optionally loaded from an env-style file (CULTUREOS_RELEASE_CONF,
# default $HOME/.config/cultureos/release.env). See docs/os/release-repo.md.
#   CULTUREOS_BUILD_REPO    build's OSTree repo (default: shared build's deploy/ ostree_repo)
#   CULTUREOS_OSTREE_REF    ref to publish                       (default: ventuno-q)
#   CULTUREOS_RELEASE_REPO  release repo, archive mode           (default: $HOME/cultureos-ostree/repo)
#   CULTUREOS_SIGN_KEY      file holding the base64 ed25519 secret key; MUST be outside this git repo
#   CULTUREOS_PUBKEY        file holding the base64 ed25519 public key (default: os/keys/cultureos-ostree.pub)
#   OSTREE                  ostree binary (default: ostree)
# Usage: os/scripts/publish-ostree.sh [--print-keygen]
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

keygen_help() {
  cat <<'KG'
# Operator step: create the signing key OUTSIDE the git repo (never commit the secret).
KEYDIR="$HOME/cultureos-ostree/keys"; mkdir -p "$KEYDIR"; chmod 700 "$KEYDIR"
umask 077
openssl genpkey -algorithm ed25519 -outform PEM -out "$KEYDIR/ostree-ed25519.pem"
PUBLIC="$(openssl pkey -outform DER -pubout -in "$KEYDIR/ostree-ed25519.pem" | tail -c 32 | base64)"
SEED="$(openssl pkey -outform DER -in "$KEYDIR/ostree-ed25519.pem" | tail -c 32 | base64)"
# ostree wants the 64-byte secret key = seed || public, base64:
(echo "$SEED" | base64 -d; echo "$PUBLIC" | base64 -d) | base64 -w 0 > "$KEYDIR/ostree-ed25519.secret"
# The public key is the only thing that gets committed (os/keys/cultureos-ostree.pub):
echo "$PUBLIC" > os/keys/cultureos-ostree.pub
KG
}

if [ "${1:-}" = "--print-keygen" ]; then
  keygen_help
  exit 0
elif [ $# -gt 0 ]; then
  echo "usage: $0 [--print-keygen]" >&2
  exit 1
fi

CONF="${CULTUREOS_RELEASE_CONF:-$HOME/.config/cultureos/release.env}"
if [ -f "$CONF" ]; then
  # shellcheck disable=SC1090
  . "$CONF"
fi

BUILD_REPO="${CULTUREOS_BUILD_REPO:-$HOME/yocto/cultureos-build/build/tmp/deploy/images/ventuno-q/ostree_repo}"
REF="${CULTUREOS_OSTREE_REF:-ventuno-q}"
REL="${CULTUREOS_RELEASE_REPO:-$HOME/cultureos-ostree/repo}"
KEY="${CULTUREOS_SIGN_KEY:-$HOME/cultureos-ostree/keys/ostree-ed25519.secret}"
PUB="${CULTUREOS_PUBKEY:-$REPO_ROOT/os/keys/cultureos-ostree.pub}"
OSTREE="${OSTREE:-ostree}"

die() { echo "publish-ostree: $*" >&2; exit "${2:-1}"; }
log() { echo "publish-ostree: $*" >&2; }

# ---- preflight (nothing is modified yet) ----
command -v "$OSTREE" >/dev/null 2>&1 || die "ostree not found on PATH (set OSTREE=...). Operator: sudo apt install ostree" 2
"$OSTREE" --version 2>&1 | grep -qi ed25519 \
  || die "this ostree was built without ed25519 support (see 'ostree --version'); install one that has it" 2
[ -d "$BUILD_REPO" ] || die "build repo not found: $BUILD_REPO"
[ -f "$KEY" ] || die "signing key not found: $KEY (run: $0 --print-keygen)"
[ -f "$PUB" ] || die "public key not found: $PUB (commit it under os/keys/; see os/keys/README.md)"

KEY_REAL="$(realpath "$KEY")"
case "$KEY_REAL/" in
  "$REPO_ROOT"/*) die "signing key must live outside the git repo: $KEY_REAL" ;;
esac
if git -C "$(dirname "$KEY_REAL")" rev-parse --show-toplevel >/dev/null 2>&1; then
  die "signing key must not live inside any git work tree: $KEY_REAL"
fi
[ "$(stat -c %a "$KEY_REAL")" = "600" ] || log "warning: $KEY_REAL is not mode 600"

REV="$("$OSTREE" --repo="$BUILD_REPO" rev-parse "$REF")" || die "ref '$REF' not found in $BUILD_REPO"
SECRET="$(tr -d '[:space:]' <"$KEY_REAL")"

if [ ! -d "$REL/objects" ]; then
  mkdir -p "$REL"
  "$OSTREE" --repo="$REL" init --mode=archive
fi

PREV="$("$OSTREE" --repo="$REL" rev-parse "$REF" 2>/dev/null || true)"
if [ "$PREV" = "$REV" ] && [ -f "$REL/summary" ]; then
  log "$REF is already at $REV; nothing to do"
  exit 0
fi

WORK="$(mktemp -d)"
BACKUP="$WORK/backup"
mkdir -p "$BACKUP"
for f in summary summary.sig; do
  [ -f "$REL/$f" ] && cp -p "$REL/$f" "$BACKUP/$f"
done
MOVED=0

rollback() {
  log "FAILED; restoring the published state"
  if [ "$MOVED" = 1 ]; then
    if [ -n "$PREV" ]; then
      "$OSTREE" --repo="$REL" refs --create="$REF" --force "$PREV" \
        || log "WARNING: could not restore $REF to $PREV; fix by hand"
    else
      "$OSTREE" --repo="$REL" refs --delete "$REF" \
        || log "WARNING: could not delete $REF; fix by hand"
    fi
    for f in summary summary.sig; do
      if [ -f "$BACKUP/$f" ]; then cp -p "$BACKUP/$f" "$REL/$f"; else rm -f "${REL:?}/$f"; fi
    done
  fi
}
cleanup() {
  local rc=$?
  [ "$rc" -eq 0 ] || rollback
  rm -rf "$WORK"
  exit "$rc"
}
trap cleanup EXIT

# verify_pull <what-to-pull> [summary]: pull from the release repo into a throwaway repo
# through a remote that demands a valid ed25519 signature from $PUB.
verify_pull() {
  local what="$1" with_summary="${2:-}" v="$WORK/verify"
  rm -rf "$v"
  "$OSTREE" --repo="$v" init --mode=archive
  "$OSTREE" --repo="$v" remote add --no-gpg-verify --sign-verify="ed25519=file:$PUB" \
    ${with_summary:+--set=sign-verify-summary=true} release "file://$REL"
  "$OSTREE" --repo="$v" pull release "$what"
}

log "importing $REV ($REF) from $BUILD_REPO"
"$OSTREE" --repo="$REL" pull-local "$BUILD_REPO" "$REV"

log "signing commit"
"$OSTREE" --repo="$REL" sign --sign-type=ed25519 "$REV" "$SECRET"

log "verifying commit signature against $PUB"
verify_pull "$REV"

log "moving $REF -> $REV"
MOVED=1
"$OSTREE" --repo="$REL" refs --create="$REF" --force "$REV"

log "updating and signing summary"
"$OSTREE" --repo="$REL" summary --update --sign-type=ed25519 --sign="$SECRET"

log "verifying summary signature"
verify_pull "$REF" summary

log "published $REF = $REV"
