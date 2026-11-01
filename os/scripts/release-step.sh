#!/usr/bin/env bash
# One step of the CultureOS release workflow, run by a culture-rules runner actor
# (os/release/culture-rules/, docs/os/release-workflow.md). The runner starts commands
# with a minimal environment (no HOME) and no shell, so this wrapper sets HOME and PATH,
# loads the release config, runs one step and exits with its status. A non-zero exit
# fails the culture-rules step, which stops the run before any later step.
#
# Usage: os/scripts/release-step.sh <step> [args]
#   sync <ref>                   clean checkout of <ref> (a sha, or origin/<branch>)
#   build                        os/scripts/bb.sh <this checkout>
#   bundle <version>             os/scripts/bundle-release.sh <deploy> <out> <version>
#   publish                      os/scripts/publish-ostree.sh (sign + move the ref)
#   trigger                      ssh <board> cultureos-update now --json
#   status <update-json> <wait>  read the board's outcome after the trial boot
#
# Config: env vars, optionally from CULTUREOS_RELEASE_CONF (default
# $HOME/.config/cultureos/release.env, the file publish-ostree.sh also reads):
#   CULTUREOS_BOARD         ssh target of the board   (default: arduino@cultureos, tailnet name)
#   CULTUREOS_BUILD_ROOT    shared build root         (default: $HOME/yocto/cultureos-build)
#   CULTUREOS_RELEASE_OUT   where bundles are written (default: $HOME/cultureos-release)
#   CULTUREOS_RELEASE_LOGS  step logs                 (default: $CULTUREOS_RELEASE_OUT/logs)
# Test hooks: BB_SH, BUNDLE_SH, PUBLISH_SH, SSH, SLEEP replace the programs run.
#
# stdout carries one short result (a sha, a path, the board's JSON line); tool output goes
# to a log file. On failure stderr starts with "<step> failed (exit N); log: <path>".
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

if [ -z "${HOME:-}" ]; then
  HOME="$(getent passwd "$(id -u)" | cut -d: -f6)"
  export HOME
fi
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

CONF="${CULTUREOS_RELEASE_CONF:-$HOME/.config/cultureos/release.env}"
if [ -f "$CONF" ]; then
  # shellcheck disable=SC1090
  . "$CONF"
fi
BOARD="${CULTUREOS_BOARD:-arduino@cultureos}"
BUILD_ROOT="${CULTUREOS_BUILD_ROOT:-$HOME/yocto/cultureos-build}"
OUT="${CULTUREOS_RELEASE_OUT:-$HOME/cultureos-release}"
LOGS="${CULTUREOS_RELEASE_LOGS:-$OUT/logs}"
BB_SH="${BB_SH:-$HERE/bb.sh}"
BUNDLE_SH="${BUNDLE_SH:-$HERE/bundle-release.sh}"
PUBLISH_SH="${PUBLISH_SH:-$HERE/publish-ostree.sh}"
SSH="${SSH:-ssh}"
SLEEP="${SLEEP:-sleep}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=20)

die() { echo "release-step: $*" >&2; exit "${2:-1}"; }

[ $# -ge 1 ] || die "usage: $0 <sync|build|bundle|publish|trigger|status> [args]" 1
STEP=$1
shift

# Run a command with its output in a log; fail with a short, log-pointing message.
run_logged() {
  local log rc=0
  mkdir -p "$LOGS"
  log="$LOGS/$STEP-$(date -u +%Y%m%dT%H%M%SZ).log"
  "$@" >"$log" 2>&1 || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "$STEP failed (exit $rc); log: $log" >&2
    tail -n 5 "$log" >&2 || true
    exit "$rc"
  fi
}

# Run the board command, capture its one JSON line, and on failure put that line in stderr
# (the culture-rules run keeps stderr of a failed step, not its stdout).
board() {
  local out rc=0
  out="$("$SSH" "${SSH_OPTS[@]}" "$BOARD" "$@" 2>&1)" || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "$STEP failed (exit $rc): $out" >&2
    exit "$rc"
  fi
  printf '%s\n' "$out"
}

case "$STEP" in
  sync)
    REF=${1:-origin/main}
    [[ "$REF" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]] || die "bad ref: $REF"
    [ -z "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ] \
      || die "release checkout $ROOT has local changes; refusing to build it"
    run_logged git -C "$ROOT" fetch --quiet origin
    SHA="$(git -C "$ROOT" rev-parse --verify --quiet "$REF^{commit}")" || die "unknown ref: $REF"
    run_logged git -C "$ROOT" checkout --quiet --detach "$SHA"
    echo "$SHA"
    ;;
  build)
    run_logged "$BB_SH" "$ROOT"
    echo "built $(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
    ;;
  bundle)
    VERSION=${1:-}
    [[ "$VERSION" =~ ^[0-9A-Za-z][0-9A-Za-z._-]*$ ]] || die "bad version: ${VERSION:-<empty>}"
    run_logged "$BUNDLE_SH" "$BUILD_ROOT/build/tmp/deploy" "$OUT" "$VERSION"
    echo "$OUT/cultureos-release-$VERSION.tar"
    ;;
  publish)
    run_logged "$PUBLISH_SH"
    echo "published"
    ;;
  trigger)
    board cultureos-update now --json
    ;;
  status)
    UPDATE_JSON=${1:-} WAIT=${2:-1200}
    [[ "$WAIT" =~ ^[0-9]+$ ]] || die "bad wait: $WAIT"
    read -r RESULT TARGET REBOOT_IN < <(
      python3 -c '
import json, sys
try:
    d = json.loads(sys.argv[1])
except ValueError:
    d = {}
print(d.get("result") or "-", d.get("commit") or "-", int(d.get("reboot_in") or 0))
' "$UPDATE_JSON"
    ) || die "cannot read the update result"
    if [ "$RESULT" != "staged" ]; then
      # Nothing was staged (up-to-date, pending, held): one read of the board's state.
      board cultureos os status --json
      exit 0
    fi
    "$SLEEP" $((REBOOT_IN + 10))
    DEADLINE=$((SECONDS + WAIT))
    LAST=""
    while :; do
      RC=0
      OUTPUT="$("$SSH" "${SSH_OPTS[@]}" "$BOARD" cultureos os status --json 2>&1)" || RC=$?
      if [ "$RC" -eq 0 ] || [ "$RC" -eq 1 ]; then
        LAST=$OUTPUT
        VERDICT="$(python3 -c '
import json, sys
d = json.loads(sys.argv[1])
target = sys.argv[2]
if d["booted"]["commit"] == target and d["outcome"] == "applied":
    print("applied")
elif d["outcome"] in ("rolled-back", "failed") and d["last_update"].get("deployed_commit") == target:
    print("rolled-back")
else:
    print("waiting")
' "$OUTPUT" "$TARGET" 2>/dev/null || echo waiting)"
        case "$VERDICT" in
          applied) printf '%s\n' "$OUTPUT"; exit 0 ;;
          rolled-back)
            echo "status failed (exit 1): the board rolled back $TARGET: $OUTPUT" >&2
            exit 1
            ;;
        esac
      fi
      if [ "$SECONDS" -ge "$DEADLINE" ]; then
        echo "status failed (exit 3): no final outcome for $TARGET within ${WAIT}s: ${LAST:-$OUTPUT}" >&2
        exit 3
      fi
      "$SLEEP" 15
    done
    ;;
  *)
    die "unknown step: $STEP"
    ;;
esac
