# VENTUNO Q recovery (EDL reflash) prep

This page documents how to recover the Arduino VENTUNO Q if the OS is
unbootable. Preparing for it is safe; actually reflashing is destructive.

> **Warning:** a reflash **erases the eMMC**. Everything on the board (the OS,
> `/home`, installed packages, keys) is lost. Back up first if the board still
> boots. Never run `arduino-flasher-cli flash` casually.

## 1. Install the flasher (no board needed)

```bash
bash os/scripts/install-flasher.sh
```

This downloads `arduino-flasher-cli` v0.5.4 (linux-arm64) from the GitHub
release, verifies its sha256 (the release asset digest,
`bb48d3c5...ee38`), installs it into the per-user bin directory (`INSTALL_DIR`, default under
`$HOME`), and checks the version.
It never touches the board.

Installed and verified on the DGX Spark:

```text
$ arduino-flasher-cli version
Arduino Flasher CLI version 0.5.4
```

Note: the CLI has a `version` subcommand; `--version` is an unknown flag.

Listing images is read-only and works without a board
(`arduino-flasher-cli list ventunoq`), for example:

```text
BOARD     OS      VERSION        LATEST
ventunoq  ubuntu  20260729-248   yes
ventunoq  ubuntu  20260710-235
```

A flash needs up to 12 GiB of temporary space.

## 2. udev rule and group (needs sudo, run by the operator)

The host needs permission to talk to the Qualcomm device (vendor `05c6`) in
EDL mode. The user must be in the `dialout` group (check with `id`; add with
`sudo usermod -aG dialout "$USER"`, then log in again).

Install the rule with this one-liner:

```bash
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="05c6", MODE="0660", GROUP="dialout"' | sudo tee /etc/udev/rules.d/99-ventunoq-edl.rules && sudo udevadm control --reload-rules && sudo udevadm trigger
```

The rule text follows the usual Qualcomm EDL convention. Arduino's official
page (<https://docs.arduino.cc/tutorials/ventuno-q/flash-image/>) is rendered
client-side and could not be fetched here, so compare the rule against it
before relying on it.

## 3. Enter EDL (forced USB boot) mode

1. Power the board off and unplug everything.
2. On the JCTL header, bridge **pin1 (GND)** to **pin2 (FORCED_USB_BOOT_N)**
   with a jumper.
3. Connect barrel power first, then connect USB-C to the Spark.
4. Check the host sees the device in EDL mode:

   ```bash
   lsusb | grep 05c6:9008
   ```

   Expected: a line like `Bus 00x Device 00y: ID 05c6:9008 Qualcomm, Inc.
   Gobi Wireless Modem (QDL mode)`.
5. Only then (and only when you accept the eMMC erase) flash:
   `arduino-flasher-cli flash ventunoq`.
6. After flashing, remove the jumper and power-cycle.
