# Release workflow (culture-rules)

A CultureOS release is one culture-rules workflow run on the Spark: build the
image, bundle it, sign and publish the OSTree commit, tell the board to update,
then read what the board did. Covers plan task t18. The definitions are
exported files in `os/release/culture-rules/`; **nothing here is imported into
the live culture-rules store**: the operator does that after review (below).

## What is in the export

```text
os/release/culture-rules/
  actors/spark-cultureos-release.json     runner actor on spark: the six release commands
  workflows/cultureos-release.json        the pipeline
  rules/cultureos-release.json            event rule that starts it (ships disabled)
```

The runner actor is needed because a workflow step can only run a registered
command of a `runner` actor (`machine.command`, no shell, no inline script).
Every command is `os/scripts/release-step.sh <step> ...` in the release
checkout.

| Step id | Command | Runs | Records (stdout) |
|---------|---------|------|------------------|
| `sync` | `release_sync ref` | detaches the release checkout at `ref` (`origin/main` or a sha); refuses a dirty checkout | the commit sha |
| `build` | `release_build` | `os/scripts/bb.sh <release checkout>` ([`building.md`](building.md)) | `built <sha>` |
| `bundle` | `release_bundle version` | `os/scripts/bundle-release.sh <deploy> <out> <version>` ([`release-bundle.md`](release-bundle.md)) | the tarball path |
| `publish` | `release_publish` | `os/scripts/publish-ostree.sh`: import by checksum, ed25519 sign, verify, move the ref, signed summary; the ref is unchanged on failure ([`release-repo.md`](release-repo.md)) | `published` |
| `notify` | `release_trigger` | `ssh arduino@cultureos cultureos-update now --json` over Tailscale ([`update-agent.md`](update-agent.md)) | the board's one JSON line (`result`, `commit`, `version`, `booted_commit`, `reboot_in`, `reason`, `run_id`, `at`) |
| `status` | `release_status update_json wait_s` | after a `staged` result, waits out the reboot and trial boot, then reads `cultureos os status --json` ([`update-state.md`](update-state.md)) until the staged commit is `applied` or `rolled-back` (at most `wait_s`, 1200) | the board's status JSON |

The board step is called `notify` because `trigger` is a reserved step id.

The workflow's inputs are `ref` and `version`. Its **outputs** (the only
values a run exports, see culture-rules `docs/run-events.md`) are `commit`,
`bundle`, `update` (the board's update JSON) and `board_status` (the final
`os status` JSON). So a finished run shows the commit built, the bundle, the
deployment the board was told to take and its outcome, applied or rolled back.

All six steps are placed on machine `spark`, and each is `idempotent` (a
node restart re-runs a step instead of failing it `unsafe_retry`; every step
is safe to repeat: a second publish is a no-op, a second `now` answers
`up-to-date` or `pending`).

## Failure stops the run

- Each step is chained to the previous one by an edge on its `after` input
  (the previous step's `exit_code`), and the runner fails a step on any
  non-zero exit or timeout. A failed step fails the run and no later step
  starts. There is no `on_error: skip` anywhere.
- So a failed build, bundle or publish never reaches the board: `notify` is
  downstream of `publish`.
- `release-step.sh` exits with the tool's own code and puts the reason first in
  stderr: `<step> failed (exit N); log: <path>` plus the last lines of the log
  (the full log is `$HOME/cultureos-release/logs/<step>-<time>.log`; the run
  keeps only the first 500 characters of stderr).
- `notify` fails the run on the agent's exit 1 (`failed`), 2 (`error`) and 3
  (`unreachable` or `deferred`); the board's JSON line is copied into the error
  so the run still records it. Exit 0 results (`up-to-date`, `staged`,
  `pending`, `held`) succeed.
- `status` fails the run (exit 1) when the board rolled the update back, and
  exits 3 if no final outcome arrives in `wait_s`. If `notify` did not return
  `staged`, `status` reads the board once and reports it.

## One-time setup (operator, on the Spark)

1. **Release checkout.** A clean clone of cultureos, never a dev worktree,
   because `sync` moves its HEAD and refuses local changes:

   ```bash
   git clone https://github.com/agentculture/cultureos "$HOME/cultureos-release-checkout"
   ```

2. **Actor path.** The actor's `argv[0]` is the placeholder
   `/REPLACE-WITH-RELEASE-CHECKOUT/os/scripts/release-step.sh`. Replace it in a
   copy outside the repo, then import that copy (below):

   ```bash
   mkdir -p "$HOME/cultureos-release-import" && cp -r os/release/culture-rules/. "$HOME/cultureos-release-import/"
   sed -i "s#/REPLACE-WITH-RELEASE-CHECKOUT#$HOME/cultureos-release-checkout#" \
     "$HOME/cultureos-release-import/actors/spark-cultureos-release.json"
   ```

3. **Config** in `$HOME/.config/cultureos/release.env` (the file
   `publish-ostree.sh` already reads): the signing key path outside the repo
   (`CULTUREOS_SIGN_KEY`, `release-repo.md`) and optionally `CULTUREOS_BOARD`
   (default `arduino@cultureos`, the tailnet MagicDNS name; the `arduino` ssh
   alias exists only on the operator's account), `CULTUREOS_BUILD_ROOT`,
   `CULTUREOS_RELEASE_OUT`. The runner starts commands with no `HOME`, so
   `release-step.sh` sets it and `PATH` itself. No key or token is in the
   exported files.
4. **Board access.** The user the culture-rules node runs as on the Spark must
   be able to `ssh arduino@cultureos` without a prompt (key in its own ssh
   directory, host key already known) and that account must be in `wheel`
   (polkit rule of the update agent).
5. A host `ostree` with ed25519 support and the signing key
   ([`release-repo.md`](release-repo.md) prerequisites).

## Dry-run validation

Offline, no store and no token: culture-rules' own reader and validator, the
same code its import runs first, over the export directory:

```bash
PYTHONPATH=<culture-rules checkout> python3 -P -c '
import sys
from culture_rules.io.exchange import read_bundle
r = read_bundle(sys.argv[1])
print(len(r.bundle.actors), "actor(s),", len(r.bundle.workflows), "workflow(s),",
      len(r.bundle.rules), "rule(s),", len(r.errors), "error(s)")
for e in r.errors:
    print(e)
sys.exit(1 if r.errors else 0)' os/release/culture-rules
```

Against the store, `import` without `--apply` is a dry run: it POSTs the
files with `apply: false`, so the server validates and plans and writes
nothing. Each noun's `import` picks only its own directory, so run all three
(actors first, they are referenced by the workflow) and read the plans:

```bash
cd "$HOME/cultureos-release-import"
culture-rules actors import .
culture-rules workflows import .
culture-rules rules import .
```

The CLI needs `CULTURE_RULES_TOKEN` (a service token) and the API URL; a
missing token answers `HTTP 401`.

## Import, enable, run (operator only)

Not part of this task and never done by it. After the dry runs look right:

```bash
culture-rules actors import . --apply
culture-rules workflows import . --apply
culture-rules rules import . --apply
```

The rule ships `enabled: false`. A release is normally started by hand:

```bash
echo '{"ref": "origin/main", "version": "0.12.0"}' > inputs.json
culture-rules workflows run cultureos-release --inputs-json @inputs.json --apply
culture-rules runs list --rule-id cultureos-release --json
```

Enabling the rule (`culture-rules rules enable cultureos-release --apply`)
starts the same workflow from an event of type `cultureos.release.requested`
whose `data` has `ref` and `version`. Bump the version in `pyproject.toml`
first; `version` names the bundle only, the board's version comes from the
built image.

## Verified here, and not

- Verified offline (`tests/os/test_release_workflow.py`): the export's
  structure; culture-rules' validator accepts it with 0 errors; in
  culture-rules' in-memory engine with a fake actor, a failure injected in any
  one step fails the run and no later step is called, and the board's JSON
  reaches `update` and `board_status`; the wrapper's behaviour with stub
  `bb.sh`, bundle, publish and `ssh` (exit codes, log pointer, rollback is a
  failed step, board JSON kept on failure). The culture-rules tests skip when
  no culture-rules checkout is found (`CULTURE_RULES_SRC`).
- NOT verified (hardware and live services): a real run against the live
  store, a real build, a real signing round trip, and the board's reboot and
  rollback, since no CultureOS image is on the board yet.
- `ostree` on the board must verify ed25519 first (an open item of
  [`release-repo.md`](release-repo.md), image task t19); until then `notify`
  returns `failed` and the run stops there, by design.
