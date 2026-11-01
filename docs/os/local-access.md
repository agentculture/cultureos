# Local no-network access

How to get a login on a CultureOS board with no network at all: Ethernet
unplugged, Wi-Fi off. Plan task t11 (covers c28, h23), reworked under
deviation d3: no adbd, no unauthenticated root path. Recipe:
`os/meta-cultureos/recipes-core/cultureos-local-access/`.

## What the recipe does

Two serial consoles, both a plain `agetty` then `login`:

| Console | Device (board) | Device (host) | Unit |
|---------|----------------|---------------|------|
| USB CDC-ACM gadget port | `/dev/ttyGS1` | `/dev/ttyACM<n>` (the second ACM interface of the board) | `serial-getty@ttyGS1.service` |
| SoC debug UART | `/dev/ttyMSM0` (115200 8N1) | USB-UART adapter, `/dev/ttyUSB<n>` | `serial-getty@ttyMSM0.service` |
| Reserved for the arduino-router bridge | `/dev/ttyGS0` | `/dev/ttyACM<n>` (the first ACM interface) | none, no getty |

`cultureos-usb-gadget.service` (oneshot, `/usr/bin/cultureos-usb-gadget`)
builds a configfs gadget `cultureos` bound to the first UDC in
`/sys/class/udc` (factory: `a600000.usb`; override with `UDC=` in
`/etc/default/cultureos-usb-gadget`). It has two CDC-ACM functions, created
in order: `acm.GS0` becomes `ttyGS0`, `acm.GS1` becomes `ttyGS1` (the kernel
numbers ports in creation order). The `serial-getty@ttyGS1` instance has a
drop-in that requires and orders after the gadget unit, because the tty only
exists once the gadget is bound.

Why two ports: the factory OS exposes `acm.GS0` as `/dev/ttyGS0`, and
`arduino-router-serial.service` (socat to the router on TCP 7500) owns it.
CultureOS keeps that port free for the router bridge (task t8) and puts the
login on a second port, so neither fights over a tty.

USB IDs: `2341:007a` (Arduino, VENTUNO Q), the same as the factory gadget.
This is not an adb-specific ID: the factory uses it for an adb plus ACM
composite and Arduino tooling matches on it, while CDC-ACM binds on interface
class, so the host needs no special driver. The device class is `EF/02/01`
(interface association) because the gadget is a composite of two CDC
functions. The serial number is the SoC serial, as on the factory OS.

Login rules (deviation d3):

- No autologin, no root login. Root is locked by the image (t12 and t19); the
  non-root login user (`arduino`) and its password hash come from first-boot
  provisioning (t10). The recipe creates no users. Until provisioning has
  run, there is no account that can log in on these consoles.
- Nothing in this recipe provides adbd.

## For t19 (image integration)

- Add `cultureos-local-access` to `CULTUREOS_PACKAGES`.
- `qcom-minimal-image` inherits `image-adbd`, which adds
  `android-tools-adbd android-tools-adbd-cmdline` to `PACKAGE_INSTALL`
  (and the `enable-adbd` feature touches `/etc/usb-debugging-enabled`). In
  `cultureos-image.bb`, after the `require`, add:

  ```bitbake
  PACKAGE_INSTALL:remove = "android-tools-adbd android-tools-adbd-cmdline"
  ```

  and do not set `IMAGE_FEATURES += "enable-adbd"`. The upstream class also
  warns but does not fail when those packages are absent. Check the image
  manifest has no `android-tools-adbd`.
- This recipe depends on the kernel modules `libcomposite`, `usb_f_acm` and
  `u_serial` (all `=m` in the pinned kernel config, and already in the image).

## Test procedure (hardware)

Status: **NOT VERIFIED (hardware)**. It needs a CultureOS image booted on the
board with provisioning done; no NVMe install exists yet.

1. Boot the CultureOS image. Unplug the Ethernet cable; make sure Wi-Fi is
   off. Check on the board console that no network link is up (`ip -br link`
   shows nothing UP except loopback) later in step 4.
2. Connect the Spark to the board's USB device (Type-C) port.
3. On the Spark: `dmesg | tail` shows two `cdc_acm` interfaces,
   `/dev/ttyACM<n>` and `/dev/ttyACM<n+1>` (see the by-id links under
   `/dev/serial/by-id/` for `Arduino VENTUNO Q - CultureOS`). The first is
   `ttyGS0` (router bridge, do not use), the second is `ttyGS1`.
4. Open the second port: `picocom -b 115200 /dev/ttyACM<n+1>` (or
   `screen /dev/ttyACM<n+1> 115200`), press Enter. A `login:` prompt appears.
   Log in as the provisioned user with its password. `ip -br link` there
   confirms no network link is up; `root` must be refused.
5. On the board: `systemctl is-enabled serial-getty@ttyMSM0 serial-getty@ttyGS1
   cultureos-usb-gadget` prints `enabled` three times;
   `cat /sys/kernel/config/usb_gadget/cultureos/UDC` names the UDC;
   `systemctl is-active android-tools-adbd` is not `active`.
6. UART fallback: connect a 3.3 V USB-UART adapter to the debug UART and run
   `picocom -b 115200 /dev/ttyUSB<n>`; a `login:` prompt comes from
   `serial-getty@ttyMSM0`.

Pass: step 4 (or step 6) yields a password login for the non-root user with
no network interface up, and root cannot log in.
