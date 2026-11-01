# arduino-router recipe

Plan task t8. `os/meta-cultureos/recipes-arduino/arduino-router/` builds
[arduino-router](https://github.com/arduino/arduino-router) from the tagged
release `v0.11.0` (the version of the factory Ubuntu package, commit
`cb7b2cec`, pinned by `SRCREV`) and installs a systemd unit that runs it.

## What it installs

| Path on the target | Source |
|--------------------|--------|
| `/usr/bin/arduino-router`, `/usr/bin/arduino-router-cli` | static Go binaries (`CGO_ENABLED=0`) |
| `/usr/lib/systemd/system/arduino-router.service` | enabled in `multi-user.target` |
| `/etc/default/arduino-router` | serial port and baud rate for the unit |

The recipe also creates the `arduino-router` system group; the router
chowns its socket `/var/run/arduino-router.sock` (mode 0660) to that group
when it exists, as on the factory board.

## Unit

Copied from the factory unit (`systemctl cat arduino-router` on the board):
`ExecStart=/usr/bin/arduino-router --unix-port /var/run/arduino-router.sock ...`,
`Restart=always`, `RestartSec=3`, journal output. Differences:

- the serial port and baud come from `/etc/default/arduino-router`
  (`ARDUINO_ROUTER_SERIAL_PORT`, default `/dev/ttySTM0`; baud 115200), not
  from a drop-in generated at boot from the board model;
- the factory's `gpioset` pre/post hooks (MCU ready line, boot animation)
  are not carried over: those GPIO lines are specific to the factory board
  configs and are not known for this image. Add them only once measured.
- the factory's `arduino-router-serial` units (socat bridge of `/dev/ttyGS0`
  to the monitor port) are not included; they are not part of this task.

## Serial device: /dev/ttySTM0

The MCU enumerates as a USB CDC-ACM device (`1209:ca01`) on the board's
internal USB. The factory image names it with a udev rule
(`SYMLINK+="ttySTM0"`) and its router runs with `--serial-port /dev/ttySTM0`
(journal: "Opened serial connection serial=/dev/ttySTM0"). The recipe ships
the same rule as `/usr/lib/udev/rules.d/99-cultureos-stm-tty.rules`, adding
`GROUP="arduino-router"`, `MODE="0660"`. An earlier draft used `/dev/ttyACM0`;
that kernel name is not stable. The unit does not use `BindsTo=` on the
device: that would stop the router when the MCU re-enumerates and nothing
would start it again. It keeps the factory's `Restart=always`,
`RestartSec=3`, so the router retries until the device node is back. The
factory `gpioset` hooks are still not carried over (GPIO lines not measured
for this board).

`arduino-router` is the only unit in the layer that names the MCU tty
(`ttyACM*` or `ttySTM*`; the device-side gadget `ttyGS*` is unrelated),
and nothing in the layer installs or flashes MCU firmware. Both are
enforced by `tests/os/test_arduino_router.py`, which greps the whole layer.

## Go modules

Module sources are fetched through bitbake's fetcher: the two generated
files `arduino-router-go-mods.inc` and `arduino-router-licenses.inc` list
them. Do not edit them by hand. Regenerate after bumping the tag (needs
network, and a writable copy of the recipe dir, since the task writes next
to the recipe and `bb.sh` mounts the layer read-only):

```bash
bitbake -c update_modules arduino-router
```

## Verifying

```bash
os/scripts/bb.sh "$PWD" arduino-router
file ~/yocto/cultureos-build/build/tmp/work/*/arduino-router/*/image/usr/bin/arduino-router
```

Result on 2026-11-01 (`bitbake arduino-router`, exit 0): `file` on the
packaged `/usr/bin/arduino-router` reports `ELF 64-bit LSB executable, ARM
aarch64, ... statically linked`, no `PT_INTERP`; `arduino-router version`
prints `Arduino Router 0.11.0`; run against a scratch socket it creates the
unix socket. Go's default `-buildmode=pie` (added by `go.bbclass` on aarch64)
yields a binary `file` calls dynamically linked, so the recipe removes it.
`rm_work` and other builds delete the image dir and deploy output, so
inspect the rpm right after the build.

Not verified without hardware: that the unit starts at boot and that the
socket appears, which needs a CultureOS image booted on the board.
