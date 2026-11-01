# Rollback: one-shot trial boot, watchdog, health-gated promotion

How CultureOS keeps a bad update from sticking: decision c39 (spec question
q5), plan task t15. Layer 2, the eMMC rescue agent for an NVMe OS that cannot
load at all, is task t21 and not described here.

## The mechanism in one paragraph

A new OSTree deployment is staged **non-default**. The board boots it once
through systemd-boot's `LoaderEntryOneShot` EFI variable (`bootctl
set-oneshot`). systemd-boot deletes the variable when it reads it, so any reset
during the trial lands on the unchanged default. Resets come from a kernel
panic (`panic=5` on the kernel command line), a hang (the `qcom_wdt` hardware
watchdog, armed by systemd), a failed or timed-out health check (the helper
reboots), or a promotion deadline (a timer reboots). Only a health check that
passes on the trial boot lets the promote unit make the deployment the
default.

## What ships

Recipe `os/meta-cultureos/recipes-core/cultureos-trialboot/` (package
`cultureos-trialboot`) and one distro snippet:

| File (on the device) | Role |
|----------------------|------|
| `/usr/sbin/cultureos-trialboot` | The helper (Python 3, stdlib only): `stage`, `check`, `health-exit`, `promote`, `deadline`, `status` |
| `cultureos-trialboot-health.service` | `check`; `Before=` and `RequiredBy=boot-complete.target`; `ExecStopPost=` `health-exit` |
| `cultureos-trialboot-promote.service` | `promote`; `Requires=` and `After=boot-complete.target`, after `systemd-bless-boot.service`; `WantedBy=multi-user.target` |
| `cultureos-trialboot-deadline.timer` + `.service` | `deadline`, 15 min after boot |
| `/usr/lib/systemd/system.conf.d/50-cultureos-watchdog.conf` | `WatchdogDevice=/dev/watchdog0`, `RuntimeWatchdogSec=20s`, `RebootWatchdogSec=60s` |
| `/usr/lib/modules-load.d/cultureos-watchdog.conf` | Loads `qcom_wdt` early in sysinit |
| `/usr/lib/cultureos/health.d/` | Empty directory for health checks other packages ship |
| `conf/distro/include/cultureos-trialboot.inc` (build) | `OSTREE_KERNEL_ARGS:append = " panic=${CULTUREOS_PANIC_TIMEOUT}"`, default 5 |

The image recipe is not touched. The integration task (t19) adds
`cultureos-trialboot` to `CULTUREOS_PACKAGES` and this line to
`conf/distro/cultureos.conf`:

```bitbake
require conf/distro/include/cultureos-trialboot.inc
```

## What the build showed

Read from the t5 build of `cultureos-image` (pinned stack, see
[`building.md`](building.md)) and the upstream layers:

- **ESP**: `cultureos-image-ventuno-q.rootfs.ota-esp` holds
  `EFI/BOOT/bootaa64.efi` (systemd-boot), an empty `loader/loader.conf`,
  `loader/ostree_bootversion` = `loader.1`, one UKI under `ostree/`, and one
  entry, `loader/entries/ostree-1+3.conf`:

  ```text
  title CultureOS (OTA-enabled) 2.99+snapshot-5e5cbc72... (ostree:0)
  version 1
  options console=ttyMSM0,115200 root=LABEL=otaroot rootfstype=ext4 qcom_scm.download_mode=1 arm64.nopauth ostree=/ostree/boot.1/cultureos/22501ac9.../0
  uki /ostree/cultureos-22501ac9.../uki-7.3.0-rc6-gc7896917e523.efi
  ```

- **OSTree** is libostree 2026.5 with meta-updater's three systemd-boot
  patches (loader directory instead of symlink, an `sd-boot` bootloader
  backend, UKI entries). `sota_qcom.bbclass` sets
  `sysroot.boot-counting-tries:3`. In `ostree-sysroot-deploy.c` that only
  names entries: a **new** deployment's entry is written as
  `ostree-<n>+3.conf`; an existing entry keeps its counter state, and a
  blessed entry (no counter) stays blessed. Entries are named
  `ostree-<n - index>.conf`, so the default (index 0) has the highest number,
  and systemd-boot picks it by version order.
- **Kernel command line**: `OSTREE_KERNEL_ARGS` becomes the `options` line;
  `UKI_CMDLINE = ""` (the UKI carries no command line), so systemd-stub hands
  the `options` to the kernel. `ostree admin deploy` copies the merge
  deployment's options to the new one. This is why `panic=` goes into
  `OSTREE_KERNEL_ARGS` and not into the UKI.
- **systemd 262** ships `bootctl`, `systemd-bless-boot`,
  `systemd-bless-boot-generator` and `boot-complete.target` in the `systemd`
  package. The generator pulls in `systemd-bless-boot.service` only when
  systemd-boot booted a counted entry (`LoaderBootCountPath` is set).
- **Watchdog**: meta-qcom-distro's `qcom-base.inc` already sets
  `WATCHDOG_RUNTIME_SEC:pn-systemd = "30"`, so the built
  `/etc/systemd/system.conf` has `RuntimeWatchdogSec=30` and
  `RebootWatchdogSec=60`. The factory Ubuntu has the watchdog off
  ([`board-baseline.md`](board-baseline.md)). The drop-in pins 20 s, under the
  30 s `qcom_wdt` default, whatever upstream does later. The kernel has
  `CONFIG_QCOM_WDT=m` (module `kernel-module-qcom-wdt` is in the image), and
  systemd 262 retries opening `/dev/watchdog0` on every ping until the module
  is loaded, so the modules-load.d entry only makes that happen sooner.
- **Panic**: the kernel is built with `CONFIG_PANIC_TIMEOUT=0`, so without
  `panic=` a panic before the watchdog is armed would hang the board.
- **EFI variables**: the kernel has `CONFIG_EFIVAR_FS=y` and
  `CONFIG_QCOM_QSEECOM_UEFISECAPP=y` (EFI variables through the TrustZone
  `uefisecapp`, as on Snapdragon laptops), and the board has `uefisecapp_a/b`
  and `uefivarstore` partitions. Whether `bootctl set-oneshot` can write
  `LoaderEntryOneShot` at runtime on this firmware is not known until a
  CultureOS image boots on the board (risk r5).

## Boot counting and the one-shot together

Upstream boot counting (systemd boot assessment) and the plan's one-shot trial
are compatible; they do different jobs:

- **The one-shot decides what boots once.** The trial entry is never the
  default before promotion, so a failed trial costs exactly one boot. Boot
  counting alone would give three tries (the default count) of a deployment
  that is already the default.
- **Boot counting blesses.** The trial entry is new, so it is
  `ostree-1+3.conf`. When systemd-boot boots it, it renames it to
  `ostree-1+2-1.conf`; after `boot-complete.target`,
  `systemd-bless-boot.service` renames it to `ostree-1.conf`. The promote unit
  runs after `systemd-bless-boot.service`, so `ostree admin set-default`
  carries the blessed state over and the promoted entry is
  `ostree-2.conf`: no counter, never decremented again.
- **A failed trial** keeps a decremented counter on a non-default entry. That
  is harmless: the next boot of the default records the rollback and
  undeploys it.

One interaction is a real hazard, and the helper guards it: if the **default**
entry still has a counter (never blessed) and keeps failing to reach
`boot-complete.target`, systemd-boot marks it bad after three boots and falls
through to the next entry, which would be a staged trial. So:

1. On a normal (non-trial) boot the health check exits 0 at once. It never
   blocks `boot-complete.target`, so the default always gets blessed.
2. `stage` refuses to stage a trial while the default entry reports
   `triesLeft` in `bootctl list --json`, and also when systemd-boot's default
   entry is not OSTree's index 0 (for example when `LoaderEntryDefault` is
   set).

The first boot of a freshly flashed image boots `ostree-1+3.conf` and blesses
it once `boot-complete.target` is reached; staging works from then on.

## Flow

`stage REF [--reboot]` (called by the update agent, t16):

1. Refuse unless the booted deployment is the default, the default entry is
   blessed and matches OSTree, and `REF` is not the running commit.
2. `ostree admin deploy --not-as-default --os=cultureos --karg=panic=5 REF`.
   The new deployment goes right after the booted one (index 1); older
   non-booted deployments, including an earlier failed trial, are dropped.
3. Check that the default did not change and that the trial's entry
   `ostree-1.conf` exists and is not the default.
4. Write `/var/lib/cultureos/trialboot.json` (`status: pending`), then
   `bootctl set-oneshot ostree-1.conf`. If that fails, the state becomes
   `failed`, the exit code is 2, and nothing else changed.

On the trial boot:

| Step | Unit | What happens |
|------|------|--------------|
| 1 | `cultureos-trialboot-health.service` | Records that the trial reached user space, runs the checks, records `pass` or `fail` with the boot id |
| 2 | `boot-complete.target` | Reached only when step 1 passed |
| 3 | `systemd-bless-boot.service` | Blesses the trial's entry |
| 4 | `cultureos-trialboot-promote.service` | Re-checks that a `pass` exists for this boot id and this deployment, then `ostree admin set-default 1`; writes `applied` |

Failure paths. In each, the one-shot is already used up and the next boot is
the old default:

| Failure | What resets the board | Reason recorded |
|---------|----------------------|-----------------|
| Health check fails | `check` runs `systemctl reboot` | `health check failed: <check> exited <n>: <last line>` |
| A check hangs | per-check timeout (120 s) or total budget (300 s), then reboot | `... timed out after ...` |
| `check` itself is killed (unit timeout, 7 min) | `ExecStopPost` `health-exit` reboots | `health check unit ended with result timeout ...` |
| Boot never reaches the check (a unit hangs) | deadline timer, 15 min | `trial boot was not promoted before the deadline` |
| User space hangs or dies | `qcom_wdt` (20 s without a ping) | `... reached user space but its health check did not finish ...` |
| Kernel panic | `panic=5` | `the trial deployment never reached the health check ...` |
| Firmware ignores `LoaderEntryOneShot` | (no trial boot) | same as the panic case; the text names `LoaderEntryOneShot` |

On the next boot of the default, `check` (which runs every boot) reconciles:
a `pending` trial staged in an earlier boot, while the default is booted, has
rolled back. It undeploys the trial, sets `status: rolled-back` with the
reason, and writes the outcome.

Booting an older entry by hand from the boot menu is not a trial: the state
file must name the booted deployment as `pending`. Nothing is promoted and
nothing reboots.

## Health checks

Executables in `/usr/lib/cultureos/health.d/` (shipped by packages) and
`/etc/cultureos/health.d/` (local) run in name order on trial boots only. A
file in `/etc` overrides the one with the same name in `/usr/lib`; a symlink
to `/dev/null` masks it. Non-zero exit or a timeout fails the trial; the last
line of stderr (or stdout) goes into the reason. Each check runs in its own
process group, which is killed on timeout. The health unit is not ordered
after `multi-user.target` (that would be a cycle with the promote unit), so a
check that needs a service waits for it itself.

With no checks installed, a trial passes once it reaches the health unit:
kernel, initramfs, OSTree root and systemd came up. The checks that make the
gate meaningful (tailnet up, culture node running) come with the packages
they test; wiring them in is integration work (t19).

Environment overrides (for the units or tests): `CULTUREOS_TRIALBOOT_TIMEOUT`
(total, default 300 s), `CULTUREOS_TRIALBOOT_CHECK_TIMEOUT` (per check, 120 s),
`CULTUREOS_TRIALBOOT_PANIC`, `CULTUREOS_TRIALBOOT_HEALTH_DIRS`,
`CULTUREOS_TRIALBOOT_STATE`, `CULTUREOS_UPDATE_STATE`, and the commands
`CULTUREOS_TRIALBOOT_OSTREE`, `_BOOTCTL`, `_SYSTEMCTL`.

## State and outcome

- `/var/lib/cultureos/trialboot.json`: the trial (`status` `pending`,
  `applied`, `rolled-back` or `failed`; commit, serial, entry id, previous
  commit, boot ids, health record, reason). `cultureos-trialboot status`
  prints it.
- `/var/lib/cultureos/update-state.json` ([`update-state.md`](update-state.md)):
  the helper writes `applied` when it promotes and `rolled-back` when it
  reconciles, so `cultureos os status` reports trial outcomes. The update
  agent (t16) writes `failed` for fetch, verify and deploy errors, including
  a non-zero exit from `stage`.

## Proven offline

`tests/os/test_trialboot_helper.py` runs the real helper against fake
`ostree`, `bootctl` and `systemctl` (`tests/os/trialboot_fake.py`) that model
the deployments, the BLS entry ids, blessing and the one-shot variable; the
test's `reboot()` plays firmware and systemd-boot. Cases: pass, health fail,
health timeout (per check and total), unit timeout, crash before the check,
panic before user space, one-shot ignored, deadline, a pass from another boot
or another commit, a manual boot of an older entry, and each `stage`
precondition. After every test the fake's audit log is checked: every
`ostree admin set-default` ran while a passing health record for the current
boot existed. `tests/os/test_trialboot_recipe.py` checks the recipe, the unit
ordering, the watchdog value and the `panic=` snippet.

## Not verified (hardware)

These need a CultureOS image booting on the board (plan risk r5; the end-to-end
run is t22):

- that `bootctl set-oneshot` can write `LoaderEntryOneShot` at runtime on the
  QCS8300 UEFI, and that systemd-boot honours and clears it;
- that systemd-boot can rename counted entries on the ESP and sets
  `LoaderBootCountPath`, so `systemd-bless-boot` runs;
- that `qcom_wdt` resets the board when PID 1 stops pinging and that the
  firmware then boots the default;
- that `panic=5` reaches the kernel through the UKI.

Procedure for t22 (on the board, after a CultureOS install):

1. `systemctl show -p RuntimeWatchdogUSec` shows 20 s and
   `cat /sys/class/watchdog/watchdog0/state` shows `active`;
   `cat /proc/cmdline` contains `panic=5`; `bootctl list` shows the default
   entry without tries left.
2. Health fail: stage a commit that ships a failing check in
   `/usr/lib/cultureos/health.d/`; `cultureos-trialboot stage <ref> --reboot`.
   Expect one trial boot, a reboot, the old default, and
   `cultureos os status` reporting `rolled-back`.
3. Panic: stage a good commit, reboot into the trial, then
   `echo c > /proc/sysrq-trigger` before the check passes (for example with a
   check that sleeps). Expect a reset within about 5 s and the old default.
4. Hang (watchdog): as in step 3, but first `sysctl -w kernel.panic=0`, so
   the panic halts the board instead of rebooting it. Nothing pings
   `qcom_wdt` any more; expect a reset after about 20 s and the old default.
5. Pass: stage a good commit. Expect `ostree admin status` to show it as the
   default after the trial boot, `bootctl list` to show its entry without a
   counter, and `applied`.
6. One-shot probe: right after `stage`, `bootctl status` or
   `bootctl list` should show the one-shot entry. If the write fails or the
   trial never boots, the reason in `cultureos-trialboot status` names
   `LoaderEntryOneShot`.

## If the one-shot fails on this firmware

The plan's fallback (decision q5) is GRUB EFI plus a boot counter plus
greenboot. The build shows a cheaper candidate that has not been decided: keep
systemd-boot and use only its boot counting. Stage the deployment **as
default** with `sysroot.boot-counting-tries` set to 1; systemd-boot tries it
once, marks it bad if it does not reach `boot-complete.target`, and boots the
previous entry. No EFI variable is written from Linux; systemd-boot renames
files on the ESP itself. The costs: OSTree's index 0 points at the trial
before the health check passes (acceptance criterion 3 as written forbids
that), and a failed trial needs OSTree cleanup on the next boot. This is a
proposed deviation for the user to decide after the hardware test, not
something implemented here.

## Residual risk

- A hang in early boot before PID 1 opens `/dev/watchdog0` (firmware,
  systemd-boot, kernel before `panic=` matters, initramfs) is not caught
  here; the watchdog is inactive until then (plan risk on early hangs). A
  panic in that window is caught by `panic=5`.
- `bootctl` needs the ESP mounted; meta-updater leaves an empty `/boot` in
  the sysroot for systemd to mount it on. `systemd-bless-boot` and OSTree
  need it writable. Not checked on a running CultureOS system yet.
- A trial that passes its checks but is broken in a way the checks do not
  test is promoted. Gate quality depends on the checks that get installed.
