# Reference build (M0)

Milestone M0 of the plan (task t1): build the **unmodified** upstream
VENTUNO Q Yocto image on the DGX Spark, to prove the host can build it before
any CultureOS layer exists. Nothing here is CultureOS yet.

## How to run

```bash
os/scripts/build-reference.sh              # full build
os/scripts/build-reference.sh --fetch-only # kas checkout only
```

The script builds outside the repo, in `$HOME/yocto/cultureos-ref`
(override with `CULTUREOS_REF_DIR`). It clones
[`meta-qcom-arduino`](https://github.com/qualcomm-linux/meta-qcom-arduino),
writes a wrapper `reference.yml` that includes `ci/ventuno-q.yml` and
`ci/qcom-distro.yml` by repo reference, pins the layer commit, caps
`BB_NUMBER_THREADS` and `PARALLEL_MAKE` (`CULTUREOS_BB_THREADS`,
`CULTUREOS_PM_JOBS`, default 8 each), and runs `kas-container build`. It
writes `build-report.txt` next to the build.

The wrapper exists because kas refuses to concatenate config files from a git
repo with files outside it ("All concatenated config files must belong to the
same repository").

## Result, 2026-11-01

| Item | Value |
|------|-------|
| Host | DGX Spark, `uname -m` = `aarch64`, kernel `7.0.0-1019-nvidia` |
| kas | 5.5 (`kas-container`) |
| Threads | `BB_NUMBER_THREADS = "8"`, `PARALLEL_MAKE = "-j 8"` |
| Exit code | 0 |
| Tasks | 17,096 attempted, all succeeded |
| Wall time | 10,923 s (3 h 02 min), 09:46 to 12:48 local, cold cache |
| Build dir size | 164 GB at the end of the build |
| `downloads/` | 42 GB |
| `sstate-cache/` | 32 GB |

The disk figure is the final size of the build dir. Peak use was not sampled
during the build. `rm_work` is not enabled, so nothing is deleted
mid-build and the final size is a close upper-bound proxy for the peak.

28 warnings, all of them upstream fetch fallbacks to mirrors (for example
`volume-key`, `trousers`, `fio`). None failed the build.

### Layer commits

| Layer | Commit |
|-------|--------|
| meta-qcom-arduino (main) | `cdc9ba7c16f44cc00705113bd56bcda0a848c7b1` |
| bitbake | `1763256342ae4d7f8028e8222400c6fc8c24d4a3` |
| oe-core | `5e5cbc72ba0f88f82dd5781881922cba827553e5` |
| meta-qcom | `4cd87176382a393d9558690e892d5aa9d2343ee6` |
| meta-qcom-distro | `5e4fabeba8b9666b33a037f8da2f96ab1dbf4924` |
| meta-openembedded | `53276e6882048b990201b3c230e0b1fd0b8311b6` |
| meta-updater | `068174256b46cdc14eaee9bfaf0fddb48b55b95e` |
| meta-security | `663084f075b98a4b91d86ca0d254a7a7bf1fd0e0` |
| meta-selinux | `f08bba920b73d985d7c80b87417ae99d66d1747d` |
| meta-virtualization | `b1846974dc1eeaee327310e9964ede7903eb8a74` |
| meta-audioreach | `e971991b11bed9ce8e7c83ece9df14cd94653f2d` |
| meta-ai | `ec488d7f302c0bccd4a903c0963e9794f4409592` |

### Outputs

Deploy dir: `build/tmp/deploy/images/ventuno-q/`. The CI config builds four
images, each as an `.ext4` rootfs plus a `.qcomflash` directory (and
`.qcomflash.tar.gz`) ready for `arduino-flasher-cli` / QDL:

| Image | `.qcomflash` size |
|-------|-------------------|
| `qcom-networking-image` | 1.9 GB |
| `qcom-multimedia-image` | 2.8 GB |
| `qcom-multimedia-proprietary-image` | 7.7 GB |
| `qcom-container-orchestration-image` | 8.6 GB |

Each `.qcomflash` directory holds `rawprogram0.xml`, `rawprogram1.xml`,
`patch0.xml`, `patch1.xml`, the GPTs, the firehose programmers
(`prog_firehose_ddr.elf`), the boot firmware (`tz.mbn`, `hypvm.mbn`,
`aop.mbn`, ...), `efi.bin` and `rootfs.img`.

Also deployed: kernel `7.2+7.3-rc6` (`Image`, `linux-ventuno-q.efi`), DTB
`monaco-arduino-monza.dtb`, `systemd-bootaa64.efi` and the ESP image.

## What this tells the plan

- **Risk r1 (aarch64 host build) is cleared.** The Spark builds the full
  upstream image natively; no x86 build host is needed.
- **systemd-boot is the deployed bootloader.** That matches the q5 decision
  (c39): keep systemd-boot and use its one-shot entry for trial boots.
- **No OSTree output yet.** `ci/qcom-distro.yml` selects `qcom-distro`, not
  `qcom-distro-sota`, so no OSTree repo or OTA artifact was produced.
  Switching to the SOTA distro is part of the CultureOS kas manifest (t5).
- **A warm rebuild should be much faster.** The 42 GB downloads and 32 GB
  sstate cache are the input to t5's shared `DL_DIR` / `SSTATE_DIR`
  (deviation d1).
- Nothing was flashed. The `.qcomflash` output is not written to the board
  before the NVMe arrives (decision q7).
