# Update agent: timer pull, ssh push, hand-off to the trial boot

How a CultureOS board picks up a new release: plan task t16 (claims c38,
h27). The agent pulls the signed commit from the release repo on the DGX
Spark ([`release-repo.md`](release-repo.md)), over Tailscale only, and hands
a new commit to the trial-boot helper ([`rollback.md`](rollback.md)), which
boots it once and promotes it only if its health check passes.

## What ships

Recipe `os/meta-cultureos/recipes-core/cultureos-update-agent/` (package
`cultureos-update-agent`):

| File (on the device) | Role |
|----------------------|------|
| `/usr/bin/cultureos-update` | The agent (Python 3, stdlib only): `run`, `now [--no-wait]`, `status` |
| `cultureos-update.service` | Oneshot, runs `cultureos-update run` as root; no `[Install]`, started by the timer or by `now` |
| `cultureos-update.timer` | Hourly (pull path); the only unit the recipe enables |
| `/usr/share/polkit-1/rules.d/50-cultureos-update.rules` | Lets group `wheel` start `cultureos-update.service`, nothing else (push path) |

`RDEPENDS` pulls in `cultureos-trialboot` (stages the commit),
`cultureos-security` (the signed remote), `polkit` and `ostree`. The image
recipe is not touched: the integration task (t19) adds
`cultureos-update-agent` to `CULTUREOS_PACKAGES`.

The remote and the branch are baked in at build time from `OSTREE_OSNAME`
(`cultureos`) and `OSTREE_BRANCHNAME` (`ventuno-q`, the machine), through
`CULTUREOS_UPDATE_REMOTE` and `CULTUREOS_UPDATE_BRANCH` in the recipe. The
agent reads neither from its environment.

## One check

`cultureos-update run` (what the service runs) takes an exclusive `flock` on
`/run/cultureos-update.lock`, then:

1. **Trial pending?** `cultureos-trialboot status`. If a trial is staged or
   running, stop: result `pending`. This runs before any network access, so
   checks during a pending trial cost nothing.
2. **Remote on the tailnet?** `ostree remote show-url cultureos` must be an
   `http`/`https` URL whose host is a `*.ts.net` name or a tailnet address
   (`100.64.0.0/10`, `fd7a:115c:a1e0::/48`). Anything else is refused
   (result `error`, exit 2): the agent never pulls from the public internet.
3. **Reachable?** A TCP connect to the remote's host and port, 10 s timeout.
   The connected peer must be a tailnet address, so a MagicDNS name that
   resolves through public DNS while Tailscale is down does not count.
   Failure: result `unreachable`.
4. **Metadata:** `ostree pull --timestamp-check
   --timestamp-check-from-rev=<booted> --commit-metadata-only cultureos
   ventuno-q` fetches the commit object and verifies its ed25519 signature
   (`sign-verify=true`, [`security.md`](security.md)). It also checks the
   commit's timestamp. A commit older than the booted one, or older than the
   one the local ref already holds, is refused even when validly signed, so a
   replayed or downgraded release is never fetched or staged. That is the
   replay protection: the summary is not signed
   ([`release-repo.md`](release-repo.md)). Then `ostree rev-parse
   cultureos:ventuno-q` gives the remote commit and `ostree show
   --print-metadata-key=version` its version. How a failed metadata pull is
   handled:

   - network error: `unreachable`
   - signature failure: `failed`, recorded with the commit named in ostree's
     message
   - timestamp refusal: `failed`, recorded, reason `refused: older than
     booted commit (downgrade): ...`
   - anything else: `error`, exit 2, logged to the journal; the state file is
     not touched, so the last real outcome stays.
5. **New?** If the remote commit is the booted one: `up-to-date`. If
   `update-state.json` records this same commit as `failed` or
   `rolled-back` (or the trial state says it rolled back): `held`. A commit
   that failed here is not tried again until a newer one is published, so a
   bad release cannot cause an hourly deploy-and-roll-back loop.
   `cultureos-update run --retry` (root, for example
   `run0 cultureos-update run --retry`) skips this hold once.
6. **Can the board stage?** `cultureos-trialboot preflight` runs the stage
   preconditions before anything is downloaded ([`rollback.md`](rollback.md)).
   A `transient` refusal (a trial is already staged) is `deferred`, nothing
   recorded. A `persistent` one is `failed`. The booted deployment not being
   the default, a systemd-boot default that is not OSTree's, or an unblessed
   default never clear by themselves. The agent records them with
   `deployed_commit: null` and reason `cannot stage updates on this board:
   ...`, so `cultureos os status` shows the board degraded. The commit is not
   held: it is staged at the first check after the condition is fixed. The
   same refusal is not rewritten each hour, and no content is pulled while it
   lasts.
7. **Content:** `ostree pull --timestamp-check
   --timestamp-check-from-rev=<booted> cultureos ventuno-q`. The signature
   and timestamp are verified again.
8. **Hand-off:** `cultureos-trialboot stage cultureos:ventuno-q`. Exit 0:
   `staged`. Exit 1: a refusal, handled by its kind as in step 6. Exit 2:
   `failed`.
9. **Reboot:** after `staged`, a transient timer
   (`systemd-run --on-active=30s --unit=cultureos-update-reboot systemctl
   reboot`) reboots into the trial. The delay lets an ssh caller read the
   result first. With `CULTUREOS_UPDATE_REBOOT=no` nothing is scheduled and
   the trial runs at the next reboot.

The agent writes `/var/lib/cultureos/update-state.json`
([`update-state.md`](update-state.md)) only with outcome `failed`, in these
cases:

- a pull that fails verification (`Can't verify commit`, `No signatures
  found`, `ed25519: ...`). The reason from ostree's stderr goes into
  `reason` and the journal.
- a pull refused by the timestamp check (downgrade)
- a content pull that fails for a non-network reason (for example a full
  disk)
- a persistent trial-boot refusal
- a `stage` that exits 2

An unclassified metadata pull error is not recorded. Writing the same failure
of the same commit again is skipped, so a repeated check never changes the
file. `applied` and `rolled-back` are
written by `cultureos-trialboot`. `cultureos os status` reads the file.

## Results and exit codes

Every `run` and `now` prints exactly one line on stdout: JSON with `--json`,
otherwise `result: commit (version): detail`. Diagnostics go to stderr (the
journal, for the service). The JSON keys: `schema_version` (1), `run_id`,
`result`, `exit_code`, `at` (UTC), `ref`, `commit`, `version`,
`booted_commit`, `reboot_in` (seconds or null), `reason`; `now --no-wait`
adds `previous_run_id`.

| Result | Exit | Meaning | State written |
|--------|------|---------|---------------|
| `up-to-date` | 0 | The remote commit is the booted one | none |
| `staged` | 0 | New commit pulled and staged as a one-shot trial; reboot in `reboot_in` s | none (the helper writes the outcome after the trial) |
| `pending` | 0 | A trial is already staged or running | none |
| `held` | 0 | The remote commit already failed or rolled back here | none |
| `started` | 0 | `now --no-wait` only: the unit was started; poll `status` | none |
| `failed` | 1 | Verify, downgrade, download or stage error on a fetched commit, or a persistent trial-boot refusal | `failed` |
| `error` | 2 | Environment error: not root for `run`, ostree missing, remote not on the tailnet, the unit did not run or could not be started, an unclassified metadata pull error | none |
| `unreachable` | 3 | Network or Tailscale down, or a transient HTTP/curl error | none |
| `deferred` | 3 | The trial-boot helper refused for a reason that clears by itself | none |

`unreachable` and `deferred` are retried by the next timer run. The service
has `SuccessExitStatus=3`, so being offline does not mark the unit failed;
`failed` does (`systemctl --failed` shows it).

Network failures are recognized from the probe (no TCP connection, or a
peer off the tailnet) and from ostree's stderr: libcurl errors
`While fetching <url>: [N] ...` with N one of 5, 6, 7, 18, 28, 35, 52, 55,
56, 92 (resolve, connect, timeout, TLS connect, empty reply, send/receive,
partial transfer, HTTP/2 stream), `Server returned HTTP 5xx`, and the usual
connection texts. Everything else from a pull is a failure.

`cultureos-update status [--json]` prints the last result (kept in
`/run/cultureos-update/result.json`, mode 0644; gone after a reboot).

## Pull path: the timer

```ini
[Timer]
OnCalendar=hourly
RandomizedDelaySec=15min
FixedRandomDelay=true
AccuracySec=1s
Persistent=true
```

`FixedRandomDelay=true` gives each board a stable offset in the first 15
minutes of the hour, so a fleet does not hit the Spark at once and two
consecutive checks are exactly one interval apart: a commit published at any
time is staged by the next check, at most one interval later (plus the pull
time). `Persistent=true` runs a check right after boot if the board was off
at check time; during a trial boot that check returns `pending`. The service
is ordered after `network-online.target`, `tailscaled.service` and the
trial-boot health and promote units, so a trial is reconciled or promoted
before the first check of a boot.

Change the interval with a drop-in in `/etc` (it survives updates; `/etc` is
merged by OSTree):

```ini
# /etc/systemd/system/cultureos-update.timer.d/interval.conf
[Timer]
OnCalendar=
OnCalendar=*:0/15
RandomizedDelaySec=5min
```

then `run0 systemctl daemon-reload`. To stop automatic checks:
`run0 systemctl disable --now cultureos-update.timer` (the push path still
works).

Other settings go in `/etc/cultureos/update.conf` (an optional
`EnvironmentFile`, not shipped):

| Variable | Default | Meaning |
|----------|---------|---------|
| `CULTUREOS_UPDATE_REBOOT` | `yes` | Reboot into the trial after `staged` |
| `CULTUREOS_UPDATE_REBOOT_DELAY` | `30` | Seconds between `staged` and the reboot |

## Push path: `cultureos-update now` over ssh

```bash
ssh arduino@<board> cultureos-update now --json
```

`now` runs `systemctl --no-ask-password start cultureos-update.service`.
Starting a oneshot unit blocks until it has run, then `now` reads the
result file and prints that run's line with its exit code. If a timer run
is in progress, systemd attaches the request to that run and `now` reports
its result. Two `now` calls never run two checks at once; the `flock` in
`run` also covers a manual `run0 cultureos-update run`. A run with no new
commit is a no-op with exit 0, so the release workflow (t18) can call it as
often as it likes. `now` blocks for as long as the check takes (up to the
unit's `TimeoutStartSec=4h` for a slow pull).

`now --no-wait` is for unattended callers that must not hold an ssh
connection for hours. The release workflow uses it. It runs
`systemctl --no-ask-password --no-block start cultureos-update.service`,
which queues the start job and returns, and prints one line with result
`started`, a `run_id`, `at` and `previous_run_id`. `previous_run_id` is the
`run_id` of the result on file before the start, or null. The caller polls
`cultureos-update status --json` until a result with another `run_id`
appears, and `cultureos os status --json` for the trial's outcome.
`--no-block` changes nothing for polkit: systemd v262 still calls `StartUnit`
and passes verb `start`, so the rule below covers it. A refused start is
`error`, exit 2.

### Why a polkit rule, and not `run0` or `sudo`

`run` must be root: it writes `/ostree`, the ESP and `/var/lib/cultureos`.
The ssh user is `arduino` (group `wheel`), root is locked and there is no
`sudo` ([`provisioning.md`](provisioning.md)). The options:

- **`run0 cultureos-update run`:** polkit's default admin rule asks for
  `arduino`'s password. The release workflow runs unattended, so it would
  have to hold that password, and the prompt needs a TTY. Rejected.
- **A polkit rule that makes `run0` passwordless for `wheel`:** grants a root
  shell to anyone with the ssh key. Far broader than needed. Rejected.
- **setuid or sudo:** not in the image, and a setuid Python script is not
  possible. Rejected.
- **The chosen one:** the check always runs inside
  `cultureos-update.service` as root, and one polkit rule lets members of
  `wheel` **start that one unit** without a password:

  ```javascript
  action.id == "org.freedesktop.systemd1.manage-units" &&
  action.lookup("unit") == "cultureos-update.service" &&
  action.lookup("verb") == "start" &&
  subject.isInGroup("wheel")
  ```

  The caller cannot pass arguments, environment or a different ref to the
  unit; the unit's command line is fixed. The worst a caller can do is run
  one more update check. Stop, restart, enable, mask and every other unit
  still need admin authentication. `--no-ask-password` keeps `now`
  non-interactive: without the rule it fails with exit 2 instead of
  prompting.

## Proven offline

`tests/os/test_update_agent.py` runs the agent as a subprocess against fake
`ostree`, `systemctl` and `systemd-run` (`tests/os/update_fake.py`) and the
**real** `cultureos-trialboot` helper, which runs against the t15 fakes
(`tests/os/trialboot_fake.py`). The reachability probe connects to a
listening or closed socket on loopback; nothing leaves the machine.

- Acceptance 1 (push, idempotent): `now` goes through
  `systemctl start cultureos-update.service`; three `now` calls with no new
  commit are `up-to-date`, exit 0, no content pull, no deploy, no state file.
  After `staged`, repeated `now` calls are `pending` with no second deploy or
  reboot. Two concurrent `run`s serialize on the lock: one `staged`, one
  `pending`, one deploy.
- Acceptance 2 (hand-off, state): `staged` deploys non-default and sets the
  one-shot entry through the real helper, after a full (not partial) pull;
  the full cycle stage, trial boot, health check, bless, promote ends in
  `applied` and then `up-to-date` with the state file unchanged. A bad
  signature, a full disk and a `stage` exit 2 record `failed` with the reason
  (and `cultureos os status` exits 1 on it); repeating writes nothing. A
  rolled-back or failed commit is `held` until a newer one is published;
  `--retry` overrides.
- Review fixes (`tests/os/test_update_agent_safety.py`). Every pull carries
  `--timestamp-check` and `--timestamp-check-from-rev=<booted>`. The fake
  ostree models libostree 2026.5's timestamp refusal. A validly signed
  commit older than the booted one, or older than the local ref, is
  `failed`, `refused: ... (downgrade)`, recorded once, with no content pull
  and no deploy. An unclassified metadata error is `error`, exit 2, and an
  earlier `applied` record stays. A signature failure is still recorded,
  with the commit. An unblessed default, or a booted deployment that is not
  the default, is `failed` before any content pull. It is recorded once and
  `os status` exits 1. The same commit is staged once the condition is
  fixed. A transient `stage` refusal is `deferred` and not recorded; a
  persistent one is `failed`. `now --no-wait` calls
  `systemctl --no-block start`, returns `started` with `previous_run_id`,
  and the run's result is then visible through `status`. A refused start is
  `error`.
- Network: probe failure, curl errors 6, 7 and 28, and HTTP 502 are
  `unreachable` (exit 3, also through `now`), nothing recorded, and the next
  check stages. A peer outside the tailnet is unreachable; a remote URL
  outside the tailnet is refused before any pull; only `cultureos` /
  `ventuno-q` is ever pulled.
- Acceptance 3 (timer alone, simulated clock): the test reads the shipped
  `.timer`, fires the agent at `k * interval + offset` with the clock injected
  through `CULTUREOS_UPDATE_NOW`, publishes a commit at a random time, never
  calls `now` (no `systemctl start` is seen), and checks the commit is staged
  at most one interval after publication: four random seeds and the worst
  case (published just after a check). With the network down at the first
  check after publication, the commit is staged one interval later and
  nothing is recorded as failed.

`tests/os/test_update_agent_recipe.py` checks the recipe, the units and the
polkit rule.

## Build

`os/scripts/bb.sh <worktree> cultureos-update-agent`: exit 0. The package
holds `/usr/bin/cultureos-update`, the two units, the systemd preset that
enables the timer and the polkit rule; `RDEPENDS` resolved to
`cultureos-security cultureos-trialboot ostree polkit python3-core
python3-fcntl python3-io python3-json systemd`.

A throwaway `cultureos-image` build with `IMAGE_INSTALL:append:pn-cultureos-image
= " cultureos-update-agent"` (an untracked kas override passed through
`CULTUREOS_KAS_CONFIG`, deleted afterwards) exited 0. In its
`rootfs.ostree.tar.zst`: `/usr/bin/cultureos-update` with `REMOTE =
"cultureos"` and `BRANCH = "ventuno-q"` substituted, both units, the polkit
rule in `/usr/share/polkit-1/rules.d/`, the timer enabled
(`/usr/etc/systemd/system/timers.target.wants/cultureos-update.timer`), the
`cultureos` remote from `cultureos-security`, groups `wheel` and `polkitd`,
and `python3-core`, `-io`, `-json`, `-fcntl` (manifest also lists
`cultureos-trialboot`, `cultureos-security`, `polkit 127`, `ostree 2026.5`).

## Not verified (hardware)

Needs a CultureOS image running on the board (the end-to-end run is t22):

- that polkit evaluates the rule for an ssh session of `arduino` and
  `systemctl start` succeeds without a password;
- that the real `ostree pull` against the Spark's repo verifies the
  signature, and the exact stderr texts of a failed verification and of a
  dead network on this ostree build (the classifier is written from the
  libostree 2026.5 source);
- the timer firing on the board, and the reboot into the trial;
- the timestamp refusal on the real pull. The classifier matches libostree
  2026.5's `_ostree_compare_timestamps` message (`... is chronologically
  older than current revision ...`), read from the source, not from a run.
  Also that `now --no-wait` passes polkit for `arduino`.

Procedure for t22 (on the board, after a CultureOS install with t19's
image, Tailscale up, `os/scripts/publish-ostree.sh` run on the Spark):

1. `systemctl list-timers cultureos-update.timer` shows the next run within
   the hour; `cultureos-update status` shows `none` or the last result.
2. From the Spark: `ssh arduino@<board> cultureos-update now --json`. With
   nothing new published: `up-to-date`, exit 0. Run it again: same line,
   and `stat /var/lib/cultureos/update-state.json` is unchanged.
3. Publish a new commit, then `now --json` again: `staged`, exit 0,
   `reboot_in` 30; the board reboots into the trial, then
   `cultureos os status` shows `applied` and the new commit as booted.
4. Concurrency: `systemctl start cultureos-update.service &` and
   `cultureos-update now` at once; one check runs, both report it.
5. Network down: `run0 tailscale down`, then `now --json`: `unreachable`,
   exit 3, `systemctl is-failed cultureos-update.service` says not failed,
   update-state unchanged. `run0 tailscale up`.
6. Bad signature: publish a commit signed with another key (a throwaway
   repo and key on the Spark), `now --json`: `failed`, exit 1, `reason`
   names the ed25519 verification error; `cultureos os status` exits 1.
7. Timer alone (acceptance 3 on hardware): publish a commit and do not call
   `now`. Within one hour `journalctl -u cultureos-update.service` shows it
   staged, followed by the trial reboot.
8. Interval drop-in: install the drop-in above, `daemon-reload`,
   `systemctl list-timers` shows the new schedule.
9. Downgrade: re-point the Spark's ref at an older signed commit
   (`ostree --repo=<release repo> refs --create=ventuno-q --force <older>`
   and `summary -u`), then `now --json`: `failed`, exit 1, reason `refused:
   older than booted commit (downgrade)`; nothing pulled or staged. Restore
   the ref.
10. `now --no-wait --json` returns at once with `started`;
    `cultureos-update status --json` then shows the run's result.
