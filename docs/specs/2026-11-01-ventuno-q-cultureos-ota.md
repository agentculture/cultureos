# ventuno-q cultureos ota

> The Arduino VENTUNO Q runs CultureOS — our own pinned, reproducible Yocto image (meta-cultureos) built from this repo and installed on NVMe — reachable over Tailscale; OSTree-based OTA follows once the OS lives on NVMe, so the board ends up needing nothing but power to stay current.
> instruction: kas lock file committed; CI/build script reproduces from clean clone

## Audience

- The operator (Ori), who wants the VENTUNO Q to be a hands-off CultureOS box on power only, and mesh agents that reach it as a Culture node
  - instruction: doc review

## Before → After

- Before: Today the VENTUNO Q runs the factory Ubuntu 24.04 + Arduino App Lab stack on eMMC; it is reachable (Ethernet .221, Wi-Fi .222, Tailscale 'cultureos', ssh arduino) but nothing on it is CultureOS, reproducible, or self-updating
  - instruction: ssh arduino 'cat /etc/os-release; lsblk'
- After: The board boots a CultureOS Yocto image from NVMe, comes up on Ethernet/Wi-Fi and Tailscale with no hands-on steps, runs a supervised Culture node, and later receives OSTree updates with automatic rollback
  - instruction: trace table in the plan

## Why it matters

- A Culture node that needs hands-on maintenance does not scale; a pinned, reproducible image that updates itself is the foundation issues #3 and #4 build on
  - instruction: read issue #3 milestones, #4 A3

## Requirements

- Before CultureOS replaces the factory OS, a tested restore-to-official-image path exists and is documented (issue #3 'Safe deployment' + M0: recovery path tested before replacing the factory OS)
  - instruction: arduino-flasher-cli flash ventunoq run + board boots Ubuntu; log kept in docs/
  - honesty: EDL reflash to the official Ubuntu image has actually been performed once on this board and booted, before any CultureOS image is flashed
- OTA updates the root/system image while preserving a separate persistent data area (/var/lib/cultureos, later NVMe per issue #4), so app state such as culture-rules' MongoDB run state (culture-rules README:39) survives updates and rollbacks
  - instruction: write /var/lib/cultureos/marker, update, rollback, verify marker
  - honesty: An update and a rollback both leave /var data (incl. a test marker file) intact
- The updated image boots into a supervised Culture mesh node (culture installs via 'uv tool install culture' + 'culture server start', culture/README.md:73-74) so the board is reachable on the mesh after every OTA (issue #3 M2)
  - instruction: systemctl is-enabled culture-\*; mesh peer list shows cultureos after reboot
  - honesty: culture runs under a systemd unit that restarts it and starts at boot, and the node is visible on the mesh after reboot
- OTA uses OSTree via meta-updater: meta-qcom-distro's qcom-distro-sota distro (conf/distro/qcom-distro-sota.conf, ci/qcom-distro-sota.yml) is the only update framework shipped by the Qualcomm layers — no RAUC/SWUpdate/Mender found — giving atomic rootfs deployments with rollback
  - instruction: kas build of ventuno-q.yml:qcom-distro-sota.yml exit 0; ostree repo present in deploy dir
  - honesty: The ventuno-q + qcom-distro-sota kas stack builds and produces an OSTree repo + ota-ext4 artifact
- Recovery = EDL reflash of the official Ubuntu image with arduino-flasher-cli >=0.5.4 (linux-arm64 build exists): JCTL pin1-GND to pin2 `FORCED_USB_BOOT_N` jumper, barrel power, then USB-C; shows as 05c6:9008; needs udev rule + dialout; flashing erases all data (docs-content flash-image.md)
  - instruction: lsusb shows 05c6:9008 with jumper; arduino-flasher-cli list ventunoq works
  - honesty: The flasher (linux-arm64) runs from the DGX Spark and the board enumerates as 05c6:9008 with the JCTL jumper
- The board joins the tailnet (Tailscale) so it is reachable for management and OTA from anywhere, not just the home LAN — the DGX Spark is already on it (tailscale0 100.127.105.72)
  - instruction: reboot; tailscale status shows cultureos with same 100.x IP
  - honesty: tailscaled is enabled at boot and the node keeps its tailnet identity across reboots (key expiry disabled in admin)
- Persistent data (Culture identity, Tailscale state, app data such as culture-rules' MongoDB state) lives outside the OSTree-managed OS — in OSTree's preserved /var or a separate NVMe data partition — never on the 30M eMMC persist partition
  - instruction: ostree admin status + findmnt; data dirs not under /usr
  - honesty: The OSTree-managed tree contains no mutable app data; data paths resolve under /var or the NVMe data mount
- Connectivity survives the reflash: the CultureOS image restores Wi-Fi (bar-`nachum_EXT`, credentials provisioned at first boot, never committed), installs Tailscale (operator runs tailscale up once, per q2), and ships the operator's SSH public key for user arduino
  - instruction: python3 scripts/scan-secrets.py clean; inspect image for psk/authkey: none
  - honesty: No Wi-Fi password, Tailscale auth key or private key is committed to the repo or baked into the published image

## Honesty conditions

- Every artifact (layers, kas manifest, recipes) is pinned and lives in this repo; a clean checkout rebuilds a bit-identical-config image
- No code or workflow in rollout-cli is invoked by the OTA path
- The CultureOS image either ships arduino-router or explicitly documents its absence; no OTA step writes MCU firmware
- Both readers are served: operator via ssh/Tailscale, agents via the mesh node
- Matches today's measured state of the board
- Issues #3 and #4 both depend on a booting, updatable image
- Each clause of the after-state is checked by a success signal (c23-c25) or honesty condition
- The build ran on the Spark itself (aarch64), not an x86 machine
- No human touches the board between power cycles
- Rollback is triggered by the boot itself, not by a manual command

## Success signals

- Milestone 0: the unmodified upstream ventuno-q reference image builds on the aarch64 DGX Spark with exit 0 and produces a \*.qcomflash directory
  - instruction: uname -m in the build log = aarch64
- After 3 consecutive power cycles with no keyboard/monitor, ssh arduino (Tailscale) succeeds within 120 s each time on the CultureOS image
  - instruction: test protocol notes
- OTA: one update deployed over Tailscale reboots into the new OSTree deployment, and a deliberately broken deployment rolls back to the previous one within 1 reboot cycle without hands-on access
  - instruction: use greenboot/boot-count style check, not ostree admin rollback by hand

## Scope / boundaries

- rollout-cli is cross-repo code propagation (rollout-cli/README.md), not device OTA; the OTA mechanism is chosen from embedded update frameworks, not reused from it
  - instruction: grep image/OTA code for rollout-cli references: none
- MCU stays out of the OS image path: STM32H5 runs Zephyr, Linux talks to it via arduino-router on /dev/ttyACM0 (+ /var/run/arduino-router.sock); CultureOS must preserve or package arduino-router and never flash MCU firmware as part of OTA (issue #3 MCU boundary)
  - instruction: check image manifest for arduino-router; audit OTA payload for MCU firmware: none

## Assumptions

- 'Our OS' means reading (b) from issue #1: a real installable Yocto image (meta-cultureos layer + pinned kas manifest, per issue #3), not the conceptual mesh-as-OS reading (a)
- The ventuno-q image can be built on this aarch64 DGX Spark: kas 5.5 container is multi-arch and meta-qcom CI runs arm64 jobs, but meta-qcom-arduino builds ventuno-q only on amd64 runners (.github/workflows/build-yocto.yml:118) — plausible, unproven
- The CultureOS OS (ESP-chainloaded kernel + OSTree sysroot) lives on NVMe; the eMMC keeps the boot firmware (`_a`/`_b`, untouched) and, if UEFI can boot NVMe, the factory Ubuntu as an always-available fallback OS — so a bad CultureOS install never bricks the board
- The QCS8275 UEFI (`uefi_a`/`_b` on eMMC) can boot a kernel/rootfs from NVMe — or at minimum chain to an NVMe rootfs while the ESP stays on eMMC; unverified on VENTUNO Q (no NVMe present to test)

## Scope exploration

- `s1` — `GitHub issue #3 (Yocto distribution)`: Owns image build + flashing; mandates M0 'reference boots, recovery path tested' before replacing factory OS, and lists 'defined update/recovery strategy' under Minimal runtime — OTA is a sub-item of #3, not a new workstream
  - seeds: `c2`
- `s2` — `GitHub issue #4 (appliance suite)`: Covers full suite on top of the image (AgentIRC, Rules, Library, Embodiment, NVMe persistence, backups); explicitly defers BSP/flashing to #3 — so it sits after the OS+OTA first goal
  - seeds: `c3`
- `s3` — `GitHub issue #1 (build brief)`: Leaves 'what layer is the OS' open between (a) conceptual mesh-OS and (b) real distro image; user's request ('set it up with our own OS', OTA, power-only) points to (b)
  - seeds: `c4`
- `s4` — `culture-rules (README, pyproject store extra)`: Persists run state in a MongoDB replica set with TLS/auth across hosts (README:39,127,209; 'orin third voter'); not single-node-standalone — app data must live outside the OTA-replaced rootfs
  - seeds: `c5`
- `s5` — `rollout-cli`: README: cross-repo propagation built on refactor-cli — not a device update mechanism
  - seeds: `c6`
- `s6` — `culture (README)`: Installed as a Python tool (uv tool install culture) and started with 'culture server start'; image must carry Python/uv + a systemd unit to supervise it
  - seeds: `c7`
- `s7` — `meta-qcom / meta-qcom-distro (OTA)`: Only OTA path is OSTree/aktualizr via meta-updater (qcom-distro-sota); no ventuno-q CI for it — stack ci/ventuno-q.yml with qcom-distro-sota.yml, untested
  - seeds: `c8`
- `s8` — `meta-qcom-arduino (ventuno-q.conf, qbootctl)`: ventuno-q.conf does not add qbootctl/bless-boot unlike uno-q.conf; boot-chain A/B support for QCS8300 unverified
  - seeds: `q1` (question, resolved)
- `s9` — `kas container + meta-qcom-arduino CI`: kas:5.5 image has arm64 manifest; upstream ventuno-q builds run on amd64 self-hosted (build-yocto.yml:118); arm64 host build of ventuno-q unproven
  - seeds: `c9`
- `s10` — `arduino docs-content flash-image.md + user manual`: Factory OS is Ubuntu; recovery is EDL jumper + arduino-flasher-cli flash ventunoq (arm64 host supported); user 'arduino', password set at first setup; USB-C exposes adb in normal boot; power via barrel jack BEFORE plugging USB-C
  - seeds: `c10`
- `s11` — `arduino docs bridge.md (MCU)`: STM32H5 Zephyr MCU reached via arduino-router on /dev/ttyACM0; no MCU firmware recipe in meta-qcom-arduino recipes-bsp
  - seeds: `c11`
- `s12` — `live device probe (lsusb, kernel log, adb, LAN sweep)`: With official barrel power + known-good data cable + Ethernet: MCU alive (LED matrix, power LED) but Linux SoC shows no sign of life — zero USB kernel events across replugs, adb empty, no new DHCP host on 192.168.1.0/24 (only .215, no open ports, Wi-Fi-like jitter), fan idle. Factory OS state unknown; EDL (05c6:9008) is the OS-independent path
- `s13` — `board fingerprint over SSH (192.168.1.221)`: Ubuntu 24.04.4, kernel 6.8.0-1078-qcom, GRUB EFI (grub-efi-arm64 2.12), 8 cores, 14Gi RAM; eMMC 59.3G: firmware partitions A/B, Linux single-slot efi/persist/system; no NVMe; docker, snapd, fwupd, unattended-upgrades, adbd, arduino-router(-serial), arduino-app-cli, arduino-cloud-connector running; hostname already 'cultureos'; no qbootctl/ostree installed
  - seeds: `c13`, `c14`, `c15`, `q1` (question, resolved)
- `s14` — `DGX Spark network (ip addr)`: Spark already on Tailscale (tailscale0 100.127.105.72); board on LAN only
  - seeds: `c12`

## Decisions

- Route A chosen: CultureOS is a Yocto image (meta-cultureos) per issue #3; no interim CultureOS layer on the factory Ubuntu (the factory Ubuntu only hosts today's remote access: Wi-Fi, Tailscale, SSH)
- OTA is deferred until the NVMe is installed; the OS will be installed on NVMe, and OTA is built on top of that layout
- Yocto is the long-term base for CultureOS (issue #3 route), customized into a CultureOS distro over time

## Hard questions

- Does the VENTUNO Q (QCS8300) boot firmware support `boot_a`/`boot_b` slots with boot-count rollback? ventuno-q.conf omits qbootctl that uno-q.conf adds ('boot firmware will switch to slot B and fail to boot otherwise') — rootfs-only OSTree rollback vs full boot-chain A/B depends on it (resolved: User: 'q1 confirmed A/B OSTree as suggested' — OS-level rollback via OSTree deployments; boot-firmware `_a`/`_b` untouched)
- Tailnet enrollment: how does the image get its Tailscale auth key without baking a secret into the image — pre-auth key provisioned at first boot (via grant?), tagged ephemeral-no node, or manual 'tailscale up' once? (resolved: User: 'I'm in and can install tailscale' — manual one-time enrollment by the operator (interactive tailscale up), no auth key baked into the image)
- Route A (Yocto image now) or route B (layer on factory Ubuntu first, Yocto later) for the first OTA-capable CultureOS? (resolved: User: 'Yocto is great and we may want to stay with it and customize as cultureos later' — route A: Yocto (issue #3) is the base; no interim Ubuntu layer)
- Can VENTUNO Q's UEFI boot from NVMe, or must ESP/kernel stay on eMMC with only the rootfs on NVMe? Determines image partitioning and where OSTree's sysroot lives (resolved: User: 'q4 yes, confirmed by another project of someone else' — VENTUNO Q UEFI booting from NVMe is reported working by an external project (not yet verified on this board); per user 'q4 as suggested': build the safe baseline first (ESP on eMMC, OS root on NVMe), switch to full NVMe boot once verified here)

## Resolved vagueness

- [unknown_blocking] VENTUNO Q is not visible to the host: lsusb shows no Qualcomm/Arduino device, kernel log shows no new USB device after 08:15 (only the ASUS keyboard disconnect), and the user reports the fan is not spinning — board is likely powered off / not booting; nothing on-device can be verified until it powers up and enumerates (or is reachable via Ethernet) — resolved: Board was waiting at first-run setup; after user completed setup via monitor it enumerated on USB (2341:007a VENTUNO Q, adb serial 1687124638) and took DHCP 192.168.1.221 over Ethernet with SSH key auth working
