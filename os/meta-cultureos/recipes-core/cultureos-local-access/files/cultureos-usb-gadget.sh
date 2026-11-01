#!/bin/sh
# Build the CultureOS USB device-mode gadget through configfs: two CDC-ACM
# serial functions, no mass storage, no network function.
#   acm.GS0 -> /dev/ttyGS0  reserved for the arduino-router serial bridge
#   acm.GS1 -> /dev/ttyGS1  login console (serial-getty@ttyGS1)
# ttyGS<n> numbers are allocated in function creation order, so GS0 is
# created first. Usage: cultureos-usb-gadget {start|stop}
set -eu

G=/sys/kernel/config/usb_gadget/cultureos
ID_VENDOR=0x2341  # Arduino
ID_PRODUCT=0x007a # VENTUNO Q (same IDs as the factory OS gadget)

# shellcheck source=/dev/null
[ -r /etc/default/cultureos-usb-gadget ] && . /etc/default/cultureos-usb-gadget

pick_udc() {
    if [ -n "${UDC:-}" ]; then
        echo "$UDC"
        return
    fi
    for u in /sys/class/udc/*; do [ -e "$u" ] && basename "$u" && break; done
}

start() {
    [ -d /sys/kernel/config/usb_gadget ] || modprobe libcomposite
    udc=$(pick_udc)
    if [ -z "$udc" ]; then
        echo "cultureos-usb-gadget: no UDC in /sys/class/udc, nothing to do" >&2
        exit 0
    fi
    if [ -d "$G" ]; then
        stop
    fi
    serial=$(tr -d ' \n' </sys/devices/soc0/serial_number 2>/dev/null || echo cultureos)

    mkdir "$G"
    echo "$ID_VENDOR" >"$G/idVendor"
    echo "$ID_PRODUCT" >"$G/idProduct"
    # Interface association descriptors: composite device with 2 CDC functions.
    echo 0xEF >"$G/bDeviceClass"
    echo 0x02 >"$G/bDeviceSubClass"
    echo 0x01 >"$G/bDeviceProtocol"
    mkdir "$G/strings/0x409"
    echo "Arduino" >"$G/strings/0x409/manufacturer"
    echo "VENTUNO Q - CultureOS" >"$G/strings/0x409/product"
    echo "$serial" >"$G/strings/0x409/serialnumber"

    mkdir "$G/configs/c.1"
    mkdir "$G/configs/c.1/strings/0x409"
    echo "CultureOS serial" >"$G/configs/c.1/strings/0x409/configuration"
    echo 120 >"$G/configs/c.1/MaxPower"

    mkdir "$G/functions/acm.GS0"
    mkdir "$G/functions/acm.GS1"
    ln -s "$G/functions/acm.GS0" "$G/configs/c.1/"
    ln -s "$G/functions/acm.GS1" "$G/configs/c.1/"

    echo "$udc" >"$G/UDC"
    echo "cultureos-usb-gadget: bound to UDC $udc" >&2
}

stop() {
    [ -d "$G" ] || exit 0
    echo "" >"$G/UDC" 2>/dev/null || true
    rm -f "$G"/configs/c.1/acm.GS0 "$G"/configs/c.1/acm.GS1
    rmdir "$G/configs/c.1/strings/0x409" "$G/configs/c.1" 2>/dev/null || true
    rmdir "$G/functions/acm.GS0" "$G/functions/acm.GS1" 2>/dev/null || true
    rmdir "$G/strings/0x409" "$G" 2>/dev/null || true
}

case "${1:-}" in
    start) start ;;
    stop) stop ;;
    *)
        echo "Usage: $0 {start|stop}" >&2
        exit 1
        ;;
esac
