# Tailscale on CultureOS

How the CultureOS image ships Tailscale, where its state lives, and how an
operator enrolls the board. Plan task t9 (covers c12).

## What ships

The recipe is not new: `meta-networking` (part of the pinned
`meta-openembedded`) already builds Tailscale from source, pinned by `SRCREV`
to a tagged release, with the Go module dependencies fetched at build time.
`meta-cultureos` extends it with
`os/meta-cultureos/recipes-connectivity/tailscale/tailscale_%.bbappend`, which:

- replaces the packaged `tailscaled.service` with
  `files/tailscaled.service` from this layer;
- sets `SYSTEMD_AUTO_ENABLE:${BPN}d = "enable"`, so `tailscaled.service` is
  enabled in the image.

Two packages result: `tailscale` (the CLI, a symlink to `tailscaled`) and
`tailscaled` (the daemon, the unit and `/etc/default/tailscaled`). The image
recipe installs them (`tailscale tailscaled`); that wiring is the
integration task's job (t19), not this recipe's.

## State

`tailscaled` runs with `--state=/var/lib/tailscale/tailscaled.state`, and the
unit declares `StateDirectory=tailscale` (mode 0700), so systemd creates
`/var/lib/tailscale` on first boot. `/var` is not replaced by an OSTree
deployment, so the node identity survives OTA updates and rollbacks. The
control socket is `/run/tailscale/tailscaled.sock`.

No auth key is in the recipe, the unit or the image. A test
(`tests/os/test_tailscale_recipe.py`) fails if a `tskey-` string, an
auth-key flag or a `tailscale up` call appears in the recipe directory.

## One-time enrollment (manual)

Enrollment is deliberately manual (decision q2). On the board, over the local
shell (serial console or the keyboard and screen), as root:

```bash
tailscale up
```

Open the printed login URL on another device and approve the node. Check it
with `tailscale status`. The credentials are stored in
`/var/lib/tailscale/tailscaled.state` and persist across reboots and OTA
updates; `tailscale up` is not needed again.

Recommended: in the Tailscale admin console, open the node's menu and choose
"Disable key expiry". Otherwise the node key expires (180 days by default)
and the board silently drops off the tailnet; with no one at the board, that
means a manual re-login on the local shell.

## Verification

Offline: `uv run pytest tests/os/test_tailscale_recipe.py`.

Build: `os/scripts/bb.sh "$PWD" tailscale`, then inspect the packages with
`oe-pkgdata-util list-pkg-files tailscaled`.

On hardware (needs a booted CultureOS image; not verifiable before the NVMe
install): `systemctl is-enabled tailscaled`, `systemctl is-active tailscaled`,
`ls -l /var/lib/tailscale`, then `tailscale up` and `tailscale status`.
