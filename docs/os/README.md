# OS workstream

CultureOS is meant to be an operating system, not only a CLI. This directory
documents the OS workstream: a pinned, reproducible Yocto image for the
Arduino VENTUNO Q that stays current on its own.

## Goal

The VENTUNO Q boots a CultureOS Yocto image (`meta-cultureos`, built with a
pinned kas manifest) from NVMe, joins the tailnet without hands-on steps,
runs a supervised Culture mesh node, and later receives signed OSTree
updates with automatic rollback. The board needs nothing but power.

## Today

- The board runs the factory Ubuntu 24.04 plus the Arduino App Lab stack on
  eMMC. It is reachable as `ssh arduino` (Ethernet, Wi-Fi, Tailscale
  `cultureos`).
- Nothing on it is CultureOS, reproducible, or self-updating yet.

## Design in one paragraph

CultureOS is installed on NVMe only. eMMC keeps the firmware and the factory
Ubuntu as fallback and rescue, and the installer never writes eMMC. OTA uses
OSTree via meta-updater (`qcom-distro-sota`), with a signed repo hosted on the
DGX Spark and pulled only over Tailscale. Releases are driven by a
culture-rules workflow. A systemd-boot one-shot trial boot, a watchdog and
health-gated promotion roll back a bad update; persistent data lives outside
the OSTree-managed tree. An eMMC rescue agent covers the case where NVMe does
not boot. Recovery to the official image is an EDL reflash with
`arduino-flasher-cli`.

## References

- Issue [#3](https://github.com/agentculture/cultureos/issues/3): the Yocto
  distro for the VENTUNO Q.
- Issue [#4](https://github.com/agentculture/cultureos/issues/4): the
  appliance suite built on top of that image.
- Spec: [`docs/specs/2026-11-01-ventuno-q-cultureos-ota.md`](../specs/2026-11-01-ventuno-q-cultureos-ota.md)
- Plan: [`docs/plans/2026-11-01-ventuno-q-cultureos-ota.md`](../plans/2026-11-01-ventuno-q-cultureos-ota.md)
  (task split: [`-split.md`](../plans/2026-11-01-ventuno-q-cultureos-ota-split.md))

## Planned documents

Docs and scripts of the OS workstream:

| Document | Purpose | Status |
|----------|---------|--------|
| `docs/os/board-baseline.md` | Measured state of the factory board | present |
| `docs/os/recovery.md` | Restore-to-official-image path (EDL reflash) | present |
| `docs/os/reference-build.md` | Building the upstream reference image on the Spark | present |
| `docs/os/update-state.md` | OTA update state and `cultureos os status` | present |

Related code (present): `os/scripts/install-flasher.sh`,
`os/scripts/capture-baseline.sh`, `os/scripts/build-reference.sh` and the
`cultureos os status` verb.
