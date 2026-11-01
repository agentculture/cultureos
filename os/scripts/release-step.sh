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
#   publish                      os/scripts/publish-ostree.sh (sign + move the ref); prints
#                                the published OSTree commit, the release's target
#   trigger                      ssh <board> cultureos-update now --no-wait --json: starts
#                                the board's update unit and returns at once
#   status <target> <trigger-json> <wait>
#                                poll the board until <target> is booted and the default
#                                (exit 0), or a terminal outcome for it (exit 1-3), or
#                                <wait> seconds pass (exit 3)
#
# Config: env vars, optionally from CULTUREOS_RELEASE_CONF (default
# $HOME/.config/cultureos/release.env, the file publish-ostree.sh also reads):
#   CULTUREOS_BOARD         ssh target of the board   (default: arduino@cultureos, tailnet name)
#   CULTUREOS_BUILD_ROOT    shared build root         (default: $HOME/yocto/cultureos-build)
#   CULTUREOS_RELEASE_OUT   where bundles are written (default: $HOME/cultureos-release)
#   CULTUREOS_RELEASE_LOGS  step logs                 (default: $CULTUREOS_RELEASE_OUT/logs)
#   CULTUREOS_RELEASE_REPO, CULTUREOS_OSTREE_REF  as for publish-ostree.sh
#   CULTUREOS_RELEASE_POLL  seconds between board polls in `status` (default: 30)
# Test hooks: BB_SH, BUNDLE_SH, PUBLISH_SH, SSH, SLEEP, OSTREE replace the programs run.
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
OSTREE="${OSTREE:-ostree}"
REL="${CULTUREOS_RELEASE_REPO:-$HOME/cultureos-ostree/repo}"
OREF="${CULTUREOS_OSTREE_REF:-ventuno-q}"
POLL="${CULTUREOS_RELEASE_POLL:-30}"
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
    # The commit the board must end up on: what the release repo's ref now names.
    COMMIT="$("$OSTREE" rev-parse --repo="$REL" "$OREF" 2>&1)" \
      || die "publish failed: cannot read $OREF in $REL: $COMMIT"
    [[ "$COMMIT" =~ ^[0-9a-f]{64}$ ]] || die "publish failed: $OREF in $REL is not a commit: $COMMIT"
    echo "$COMMIT"
    ;;
  trigger)
    # Non-blocking: a content pull can take hours; `status` polls for the outcome.
    board cultureos-update now --no-wait --json
    ;;
  status)
    TARGET=${1:-} TRIGGER_JSON=${2:-} WAIT=${3:-16200}
    [[ "$TARGET" =~ ^[0-9a-f]{64}$ ]] || die "bad target commit: ${TARGET:-<empty>}"
    [[ "$WAIT" =~ ^[0-9]+$ ]] || die "bad wait: $WAIT"
    [[ "$POLL" =~ ^[0-9]+$ ]] || die "bad CULTUREOS_RELEASE_POLL: $POLL"
    # A board result counts only if its run_id differs from the one on file before the
    # trigger (previous_run_id), so a stale result never decides this release.
    PREV="$(python3 -c '
import json, sys
try:
    d = json.loads(sys.argv[1])
except ValueError:
    d = {}
print((d.get("previous_run_id") if isinstance(d, dict) else None) or "-")
' "$TRIGGER_JSON")"
    DEADLINE=$((SECONDS + WAIT))
    while :; do
      OS_RC=0
      OS_OUT="$("$SSH" "${SSH_OPTS[@]}" "$BOARD" cultureos os status --json 2>&1)" || OS_RC=$?
      UPD_RC=0
      UPD_OUT="$("$SSH" "${SSH_OPTS[@]}" "$BOARD" cultureos-update status --json 2>&1)" \
        || UPD_RC=$?
      # verdict: "applied 0 -", "fail <exit> <why>" or "wait 0 <why>"
      read -r VERDICT CODE WHY < <(python3 -c '
import json, sys

target, prev, os_rc, os_out, upd_rc, upd_out = sys.argv[1:7]


def load(text):
    try:
        d = json.loads(text)
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def say(verdict, code, why):
    print(verdict, code, " ".join(str(why).split()) or "-")
    sys.exit(0)


st = load(os_out) if os_rc in ("0", "1") else None
if st:
    booted = (st.get("booted") or {}).get("commit")
    deps = st.get("deployments") or [{}]
    default = deps[0].get("commit")
    last = st.get("last_update") or {}
    # Success only when the target runs AND is the default: during the trial boot it is
    # booted but not yet promoted.
    if booted == target and default == target:
        say("applied", 0, "-")
    outcome, why = st.get("outcome"), last.get("reason")
    if outcome in ("rolled-back", "failed") and last.get("deployed_commit") == target:
        say("fail", 1, f"the board reports {outcome} for {target}: {why}")
board = "board " + (f"os status: booted {booted}" if st else f"os status unreadable ({os_rc})")
res = load(upd_out) if upd_rc == "0" else None
if not res or res.get("run_id") == prev or res.get("result") in (None, "none", "started"):
    say("wait", 0, f"{board}; no update result since the trigger")
kind, commit, reason = res["result"], res.get("commit"), res.get("reason")
if kind in ("pending", "deferred"):
    say("wait", 0, f"{board}; update {kind}: {reason}")
if kind == "staged" and commit == target:
    say("wait", 0, f"{board}; staged {target}, waiting for the trial boot")
if kind in ("staged", "up-to-date") and commit != target:
    say("fail", 1, f"board {kind} {commit}, not the release target {target}")
if kind == "up-to-date":
    say("wait", 0, f"{board}; up-to-date with {target}")
code = {"held": 1, "failed": 1, "error": 2, "unreachable": 3}.get(kind, 1)
say("fail", code, f"board update {kind} for {commit}: {reason}")
' "$TARGET" "$PREV" "$OS_RC" "$OS_OUT" "$UPD_RC" "$UPD_OUT")
      case "$VERDICT" in
        applied) printf '%s\n' "$OS_OUT"; exit 0 ;;
        fail)
          echo "status failed (exit $CODE): $WHY" >&2
          exit "$CODE"
          ;;
      esac
      if [ "$SECONDS" -ge "$DEADLINE" ]; then
        echo "status failed (exit 3): no final outcome for $TARGET within ${WAIT}s: $WHY" >&2
        exit 3
      fi
      "$SLEEP" "$POLL"
    done
    ;;
  *)
    die "unknown step: $STEP"
    ;;
esac
