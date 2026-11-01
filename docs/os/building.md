# Building CultureOS

How to build the CultureOS image on the DGX Spark: the `meta-cultureos`
layer, the pinned kas manifest, the shared caches, and `os/scripts/bb.sh`,
the one entry point every build goes through. Plan task t5 plus deviation d1.

## What is in the repo

| Path | What it is |
|------|------------|
| `os/kas/cultureos.yml` | kas manifest: upstream `ci/ventuno-q.yml` (meta-qcom-arduino) plus `ci/qcom-distro-sota.yml` (meta-qcom), every repo pinned by commit, distro `cultureos`, target `cultureos-image`, `BB_NUMBER_THREADS` and `PARALLEL_MAKE` capped at 8 |
| `os/kas/cultureos.lock.yml` | kas lock file. kas loads it automatically. It must agree with the pins in the manifest (a test checks this) |
| `os/meta-cultureos/conf/layer.conf` | Layer `cultureos`, priority 20, depends on `core`, `qcom`, `qcom-arduino`, `qcom-distro`, `sota` |
| `os/meta-cultureos/conf/distro/cultureos.conf` | Distro `cultureos` = `qcom-distro-sota` with no Uptane client |
| `os/meta-cultureos/recipes-core/images/cultureos-image.bb` | The image: upstream `qcom-console-image` plus `CULTUREOS_PACKAGES` (empty for now) |
| `os/scripts/bb.sh` | Build wrapper: shared build dir and caches, serialized with `flock` |

Only config, the layer, scripts and docs live in git. Builds, caches and the
upstream layer checkouts live outside the repo.

## The pinned stack

The manifest pins the commits of the M0 reference build
([`reference-build.md`](reference-build.md)):

| Repo | Commit |
|------|--------|
| meta-qcom-arduino | `cdc9ba7c16f44cc00705113bd56bcda0a848c7b1` |
| meta-qcom | `4cd87176382a393d9558690e892d5aa9d2343ee6` |
| meta-qcom-distro | `5e4fabeba8b9666b33a037f8da2f96ab1dbf4924` |
| meta-updater | `068174256b46cdc14eaee9bfaf0fddb48b55b95e` |
| oe-core | `fa83da7da277a641c3a997d3da26041fa46d48ab` |
| bitbake | `1763256342ae4d7f8028e8222400c6fc8c24d4a3` |
| meta-openembedded | `53276e6882048b990201b3c230e0b1fd0b8311b6` |
| meta-security | `663084f075b98a4b91d86ca0d254a7a7bf1fd0e0` |
| meta-selinux | `c716a95ae931ee2f1c7cd90e83208ce0bcd499d6` |
| meta-virtualization | `b1846974dc1eeaee327310e9964ede7903eb8a74` |
| meta-audioreach | `e971991b11bed9ce8e7c83ece9df14cd94653f2d` |
| meta-ai | `ec488d7f302c0bccd4a903c0963e9794f4409592` |

These are upstream commits. kas applies meta-qcom's patches to oe-core and
meta-selinux on top of them at checkout, so the HEAD of those two checkouts
is a local commit that exists on no remote.

The upstream ci files are included by repo reference
(`repo: meta-qcom-arduino, file: ci/ventuno-q.yml`) because kas refuses to
concatenate config files from different repositories. `meta-cultureos` is a
layer of "this repo" (a `repos:` entry with no `url`), which is what lets
`bb.sh` take the layer from whichever checkout it is pointed at.

To move a pin: edit `commit:` in `cultureos.yml`, then regenerate the lock:

```bash
os/scripts/bb.sh "$PWD" --kas dump --lock --indent 2 > os/kas/cultureos.lock.yml
```

(and keep the two comment lines at the top of the lock file). `kas lock`
itself writes nothing here, because no repo floats: it reports "No floating
repos found".

## What meta-updater imposes, and what CultureOS overrides

`qcom-distro-sota` requires meta-updater's `conf/distro/sota.conf.inc`, which
adds `DISTRO_FEATURES` `sota usrmerge` and inherits `sota.bbclass`. That
class:

- installs `${SOTA_CLIENT}` (default `aktualizr`), `aktualizr-info` (only when
  the client is `aktualizr`) and `${SOTA_CLIENT_PROV}` (default
  `aktualizr-shared-prov`), plus `ostree`, `ostree-kernel`,
  `ostree-initramfs`;
- adds image types `ota-ext4`, and `ostreecommit.tar.zst` because
  `qcom-distro-sota` sets `BUILD_OSTREE_REPO_TARBALL = "1"`;
- adds the garage-sign push image types only when `SOTA_PACKED_CREDENTIALS`
  is set (it is not);
- through `sota_qcom.bbclass`: `OSTREE_BOOTLOADER ?= "systemd-boot"`,
  `EFI_PROVIDER:sota` = systemd-boot, `ota-esp` and `qcomflash` image types,
  and OSTree boot counting (`sysroot.boot-counting-tries:3`) in the repo
  config.

`cultureos.conf` keeps all of that except the Uptane client (decision c35,
plain signed OSTree pull):

```bitbake
SOTA_CLIENT = ""
SOTA_CLIENT_PROV = ""
SOTA_DEPLOY_CREDENTIALS = "0"
SOTA_SKIP_CRED_WARN = "1"
OSTREE_OSNAME = "cultureos"
```

It does not touch `EFI_PROVIDER` or `OSTREE_BOOTLOADER`: systemd-boot stays,
as upstream sets it (decision c39). Note for the trial-boot work (t15):
upstream already enables OSTree boot counting with 3 tries.

## The image recipe

`cultureos-image.bb` requires the upstream `qcom-console-image` (minimal qcom
image plus ssh server and base utilities) and installs `CULTUREOS_PACKAGES`.
The integration task (t19) is the only task that edits it:

| Package | What it brings | Doc |
|---------|----------------|-----|
| `arduino-router` | MCU bridge for sketches | [arduino-router.md](arduino-router.md) |
| `tailscale` `tailscaled` | tailnet; enrollment is a manual `tailscale up` | [tailscale.md](tailscale.md) |
| `cultureos-provision` | first-boot `arduino` user, SSH key, Wi-Fi | [provisioning.md](provisioning.md) |
| `cultureos-local-access` | USB CDC-ACM and UART login consoles | [local-access.md](local-access.md) |
| `cultureos-security` | key-only sshd, signed OSTree remote | [security.md](security.md) |
| `culture-node` | Culture mesh node (pulls in `python3-culture`) | [culture-node.md](culture-node.md) |
| `python3-cultureos` | the `cultureos` CLI (`cultureos os status`) | [update-state.md](update-state.md) |
| `cultureos-trialboot` | one-shot trial boot, watchdog, health-gated promotion | [rollback.md](rollback.md) |
| `cultureos-update-agent` | hourly pull plus `cultureos-update now` | [update-agent.md](update-agent.md) |

It also hardens the upstream base image:

- `IMAGE_FEATURES:remove` drops `allow-empty-password empty-root-password
  allow-root-login` (added by meta-qcom `ci/base.yml` and
  `qcom-minimal-image`), so `sshd_config` is not rewritten to allow root or
  empty passwords.
- `EXTRA_USERS_PARAMS = "usermod -L root;"` replaces `qcom-minimal-image`'s
  fixed, publicly documented root password: root is locked. Logins are the
  provisioned `arduino` user (in `wheel`, admin through `run0`).
- `PACKAGE_INSTALL:remove` drops adbd, which `image-adbd` installs and which
  has adb authorization disabled in meta-oe (deviation d3).

`conf/distro/cultureos.conf` requires `include/cultureos-trialboot.inc`
(`panic=N` on the OSTree kernel command line). The kernel has `CONFIG_TUN=y`;
Tailscale uses userspace WireGuard, so no extra kernel modules are needed.

### Image audit

`os/scripts/audit-image.sh <rootfs dir or *.ostree.tar.zst>` checks a built
image: nothing but directories and symlinks under `/var` and `/home` (OSTree
does not carry `/var` content across deployments), CultureOS units keep state
under `/var`, no `tskey-` anywhere, no uncommented `psk=` outside ELF binaries
(deviation d6), no private-key blocks or baked SSH host keys, root locked and
no empty passwords. Exit 0 clean, 1 findings, 2 environment error.

### Known follow-up: system users after OTA (risk r14)

First-boot provisioning adds the `arduino` user, so `/etc/passwd` and
`/etc/shadow` become locally modified and OSTree's three-way `/etc` merge keeps
the board's copies. A system user that a later image adds at build time (the
way `culture` and `arduino-router` are added today) would then be missing after
an update. Any recipe that adds a system user in a later release needs a
`sysusers.d` entry (or the image needs nss-altfiles) before that release ships.

## Shared build dir and caches

| Path (host) | In the container | Use |
|-------------|------------------|-----|
| `~/yocto/cultureos-build/` | `/work` | `KAS_WORK_DIR`: upstream layer checkouts |
| `~/yocto/cultureos-build/build/` | `/work/build` | the one bitbake build dir (`tmp/`, `conf/`) |
| `~/yocto/cache/downloads/` | `/downloads` | `DL_DIR`, shared with every build |
| `~/yocto/cache/sstate-cache/` | `/sstate` | `SSTATE_DIR`, shared with every build |
| `~/yocto/cultureos-build/bb.lock` | | the `flock` lock (`bb.lock.owner` names the holder) |
| the caller's checkout | `/repo` (read-only) | manifest and `os/meta-cultureos` |

The caches were seeded from the M0 reference build (42 GB downloads, 32 GB
sstate). They were moved, not copied: `~/yocto/cultureos-ref/build/downloads`
and `build/sstate-cache` are now symlinks to `~/yocto/cache/`, and
`build-reference.sh` passes `DL_DIR` / `SSTATE_DIR` so kas-container mounts
them.

## `bb.sh`

```text
os/scripts/bb.sh <worktree>                     kas build (targets from the manifest)
os/scripts/bb.sh <worktree> <bitbake args...>   bitbake <args> in the kas environment
os/scripts/bb.sh <worktree> --kas <cmd> [opts]  kas-container <cmd> [opts] <manifest>
```

`<worktree>` is any checkout of this repo: the main checkout or a git
worktree. For that run, its `os/kas/cultureos.yml` is the manifest and its
`os/meta-cultureos` is the layer. kas-container mounts the checkout at
`/repo` read-only, so the layer path inside the container is always the same
and runs from different worktrees never overwrite each other's layer.

Every run takes an exclusive `flock` on the lock file. A second caller does
not fail: it prints `bb.sh: build busy (lock ..., held by: ...); waiting...`
and runs when the first finishes. The exit code is the one from
kas-container / bitbake; `1` means a usage error (no manifest or layer in
`<worktree>`), `2` that kas-container or `flock` is missing.

Env overrides: `CULTUREOS_BUILD_ROOT` (default `~/yocto/cultureos-build`),
`CULTUREOS_CACHE_DIR` (default `~/yocto/cache`), `CULTUREOS_BB_LOCK`,
`CULTUREOS_KAS_CONFIG` (`:`-separated manifests relative to `<worktree>`,
default `os/kas/cultureos.yml`, for example
`os/kas/cultureos.yml:os/kas/mirror.yml`), `CULTUREOS_KAS_CONTAINER`.

### For recipe tasks (t6, t8 to t13, t15, t17)

Work in your own worktree, add your recipe under
`os/meta-cultureos/recipes-<area>/<name>/`, then build it from there:

```bash
os/scripts/bb.sh "$PWD" <recipe>                  # build the recipe
os/scripts/bb.sh "$PWD" -c cleansstate <recipe>   # rebuild from scratch
os/scripts/bb.sh "$PWD" -e <recipe> | grep '^SRC_URI='
os/scripts/bb.sh "$PWD" --kas --repo-ro shell -c 'oe-pkgdata-util list-pkg-files <pkg>'
```

Run it in the background and wait: if another agent holds the lock, your run
queues behind it. Build the recipe, not `cultureos-image`; the image is
integrated once, in t19. The build output is at
`~/yocto/cultureos-build/build/tmp/` (for example
`deploy/rpm/` for packages). `rm_work` is on (`ci/base.yml`), so a recipe's
`WORKDIR` is removed after it builds. To keep one for inspection, put
`RM_WORK_EXCLUDE += "<recipe>"` in a kas file in your worktree (for example
`os/kas/debug.yml` with a `local_conf_header`) and pass it with
`CULTUREOS_KAS_CONFIG=os/kas/cultureos.yml:os/kas/debug.yml`; don't commit
it.

The next run from another worktree re-runs `kas` against that worktree's
manifest and layer, so recipes that only exist in your worktree disappear
from the build again. That is intended. Build output stays in `tmp/` and
sstate, so a re-run is cheap.

## Build result, 2026-11-01

`os/scripts/bb.sh "$PWD"` (that is, `kas-container build`) from the t5
worktree, warm caches from the M0 reference build:

| Item | Value |
|------|-------|
| Exit code | 0 |
| Wall time | 3,428 s (57 min), 13:02 to 13:59 local |
| Tasks | 10,411 attempted, 6,439 did not need to rerun, all succeeded |
| sstate at start | 5,586 wanted, 3,825 local hits (68 %), 1,761 missed |
| Build `tmp/` | 39 GB; sstate grew from 32 to 39 GB |

The sstate miss rate is expected: the SOTA distro adds the `sota` and
`usrmerge` distro features, which change the signature of almost every
target package. Native tools came from the reference build's sstate.

Deploy dir `~/yocto/cultureos-build/build/tmp/deploy/images/ventuno-q/`
(acceptance 3):

| Artifact | Size |
|----------|------|
| `cultureos-image-ventuno-q.rootfs.ostreecommit.tar.zst` (OSTree repo tarball) | 504 MB |
| `cultureos-image-ventuno-q.rootfs.ostree.tar.zst` (rootfs as committed) | 494 MB |
| `cultureos-image-ventuno-q.rootfs.ota-ext4` (ext4, OSTree-deployed sysroot) | 2.7 GB |
| `cultureos-image-ventuno-q.rootfs.ota-esp` (EFI system partition image) | 537 MB |
| `cultureos-image-ventuno-q.rootfs.qcomflash/` (+ `.tar.gz`, flashable with QDL) | 2.0 GB |
| `ostree_repo/` (archive repo, ref `ventuno-q` = `0c5c87e1...`) | 520 MB |

The repo tarball holds an OSTree repo with `refs/heads/ventuno-q`.

Uptane client check (acceptance 4):

- The image manifest (`cultureos-image-ventuno-q.rootfs.manifest`, 2,222
  packages) has no line matching `aktualizr` (`grep -ci aktualizr` = 0). It
  does list `ostree`, `ostree-kernel`, `ostree-initramfs`, `os-release`,
  `zstd` and `systemd-boot`.
- The rootfs file list from `ostree.tar.zst` has no path matching
  `aktualizr`; it has `/usr/bin/ostree` and `/usr/bin/bootctl`.
- `/usr/lib/os-release` reads `ID=cultureos`,
  `NAME="CultureOS (OTA-enabled)"`.
- `grep -r rollout-cli os/` finds nothing (a test enforces it).

Warnings worth knowing (none failed the build): meta-qcom's floating-branch
kernel recipes that are not selected, old-style `LICENSE` in meta-selinux,
the shared-sstate notice, "Android repo tool not found" from
`image_repo_manifest`, and `do_image_ostree`: "Data in 'var/lib' directory
is not preserved by OSTree". The last one matters for the image audit (t19):
whatever upstream puts in `/var/lib` at build time does not reach a deployed
system.

`VERSION` in os-release is `2.99+snapshot-<METADATA_REVISION>`, which is
the kas-patched local oe-core HEAD (`5e5cbc72...`), not the upstream pin.
