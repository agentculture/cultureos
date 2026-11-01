#!/usr/bin/env bash
# Read-only capture of the VENTUNO Q factory baseline. Emits the command/output
# sections of docs/os/board-baseline.md on stdout. Never writes to the board,
# never uses sudo, never prints secrets (no PSKs, no tailnet keys, no MACs).
# Usage: os/scripts/capture-baseline.sh [ssh-host]   (default: arduino)
set -euo pipefail
HOST="${1:-arduino}"
EFI=/sys/firmware/efi/efivars
GUID=8be4df61-93ca-11d2-aa0d-00e098032b8c

section() { # title, remote-command
  printf '### %s\n\n```console\n$ ssh %s "%s"\n' "$1" "$HOST" "$2"
  local rc=0
  ssh -o BatchMode=yes "$HOST" "$2" | expand -t 8 || rc=$?
  # A non-zero remote command (e.g. `systemctl is-active` on a stopped unit) is
  # part of the baseline: record it and go on. ssh's own failure (255) aborts.
  [ "$rc" -eq 0 ] || printf '(exit %s)\n' "$rc"
  printf '```\n\n'
  if [ "$rc" -eq 255 ]; then
    echo "ssh to $HOST failed; capture aborted" >&2
    exit 255
  fi
}

section "os-release" "cat /etc/os-release"
section "Kernel" "uname -srvm; cat /proc/cmdline | tr ' ' '\\n' | grep -v '^root=UUID'"
section "Installed boot/Arduino packages" \
  "dpkg -l | awk '/^ii/ && (/arduino|adbd|tailscale|linux-image-.*qcom|shim-signed|grub-efi/){print \$2, \$3}'"
section "GPT partition table (eMMC)" \
  "lsblk -d -n -o NAME,PTTYPE,PTUUID /dev/mmcblk0; lsblk -b -n -o NAME,START,SIZE,PARTLABEL,PARTUUID /dev/mmcblk0"
section "Filesystem partitions and mounts" \
  "lsblk -n -o NAME,SIZE,FSTYPE,PARTLABEL,MOUNTPOINTS /dev/mmcblk0p69 /dev/mmcblk0p70 /dev/mmcblk0p71; cat /etc/fstab"
section "UEFI BootOrder and BootCurrent (raw)" \
  "cd $EFI; for v in BootOrder BootCurrent; do echo \"\$v:\"; od -An -tx1 \$v-$GUID; done; ls | grep -E '^Boot[0-9A-F]{4}-'"
section "UEFI Boot0000 (raw bytes and UTF-16 text)" \
  "cd $EFI; od -An -tx1 Boot0000-$GUID; od -An -c Boot0000-$GUID"
section "Watchdog (qcom_wdt)" \
  "for f in identity state timeout nowayout status; do echo \"\$f: \$(cat /sys/class/watchdog/watchdog0/\$f)\"; done; readlink -f /sys/class/watchdog/watchdog0/device; lsmod | grep -i wdt; systemctl show -p RuntimeWatchdogUSec -p RebootWatchdogUSec"
section "Running services (unit names)" \
  "systemctl list-units --type=service --state=running --no-legend --no-pager | awk '{print \$1}'"
section "Arduino / network unit files" \
  "systemctl list-unit-files --no-legend --no-pager | grep -i -E 'arduino|tailscale|ssh' | awk '{print \$1, \$2}'"
section "Network paths (IPv4 only, no MACs)" \
  "ip -4 -br addr; ip route; nmcli -t -f DEVICE,TYPE,STATE dev; tailscale ip -4; systemctl is-active tailscaled NetworkManager ssh"
