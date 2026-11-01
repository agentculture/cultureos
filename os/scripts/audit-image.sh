#!/usr/bin/env bash
# Audit a built CultureOS image (plan task t19, acceptance 2):
#   1. no mutable app data outside /var: the OSTree tree ships nothing but
#      directories and symlinks under /var and /home (OSTree does not carry /var
#      content across deployments), and CultureOS units keep their state, data and
#      HOME under /var (or /run, /tmp);
#   2. the secrets scan: no Tailscale key (tskey-<kind>-<id>-<secret>, or legacy
#      tskey-<hex>) anywhere, binaries included (deviation d8 narrows d6's bare
#      "tskey-" match: tailscaled contains the constant "tskey-wrap"); no
#      uncommented "psk=" in any non-ELF file (deviation d6: upstream wpa_supplicant /
#      hostapd binaries carry "psk=%s" format strings); no full PEM private key
#      (BEGIN, base64 body, END) in any non-ELF file (programs embed bare markers,
#      gnutls embeds FIPS self-test vectors); the PEM and psk= checks read only non-ELF
#      files up to 4 MiB (CULTUREOS_AUDIT_TEXT_CAP), the tskey check streams every file
#      in 1 MiB chunks (CULTUREOS_AUDIT_CHUNK) so memory stays bounded; no
#      baked SSH host keys; root locked and no account with an empty password.
#
# Usage: os/scripts/audit-image.sh <rootfs-dir | *.tar | *.tar.zst | *.tar.gz>
#   e.g. .../deploy/images/ventuno-q/cultureos-image-ventuno-q.rootfs.ostree.tar.zst
# Exit: 0 clean, 1 findings (listed on stdout), 2 environment error.
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "usage: $0 <rootfs-dir | rootfs tarball>" >&2
  exit 2
fi
src="$1"
command -v python3 >/dev/null || { echo "audit: python3 not found" >&2; exit 2; }

scratch=""
cleanup() { if [ -n "$scratch" ]; then rm -rf "$scratch"; fi; }
trap cleanup EXIT

if [ -d "$src" ]; then
  root="$src"
elif [ -f "$src" ]; then
  scratch="$(mktemp -d)"
  case "$src" in
    *.zst) zstd -dc "$src" | tar -xf - -C "$scratch" ;;
    *.gz) tar -xzf "$src" -C "$scratch" ;;
    *) tar -xf "$src" -C "$scratch" ;;
  esac
  root="$scratch"
else
  echo "audit: no such rootfs: $src" >&2
  exit 2
fi

exec python3 -I - "$root" <<'PY'
import os
import re
import sys

root = sys.argv[1]
findings = []

STATE_UNITS = re.compile(r"^(cultureos-.*|culture-node.*|tailscaled.*|arduino-router.*)\.service$")
STATE_ARGS = re.compile(r"(?:--data-dir|--statedir|--state-dir|--state)[ =](\S+)")
STATE_ENV = re.compile(r"Environment=\"?(?:HOME|[A-Z_]*_DIR)=(\S+?)\"?(?:\s|$)")
WRITABLE_OK = ("/var/", "/run/", "/tmp/")
# A real PEM private key: BEGIN line, a base64 body, END line. Programs (sshd,
# gnutls, NetworkManager, mime/magic databases) embed the bare marker strings,
# which are not keys.
PRIVATE_KEY = re.compile(
    rb"-----BEGIN ([A-Z ]*)PRIVATE KEY-----\r?\n"
    rb"(?:[A-Za-z0-9+/=:, -]*\r?\n)*?[A-Za-z0-9+/=]{16,}\r?\n"
    rb"(?:[A-Za-z0-9+/=]*\r?\n)*-----END \1PRIVATE KEY-----"
)
# A Tailscale key: tskey-<kind>-<id>-<secret> (auth/api/client/...) or the legacy
# tskey-<hex>. tailscaled itself contains constants such as "tskey-wrap".
TSKEY = re.compile(rb"tskey-(?:[a-z]+-)?[A-Za-z0-9]{6,}-[A-Za-z0-9]{16,}|tskey-[0-9a-f]{20,}")


# Memory stays bounded: every file is scanned for tskey in CHUNK-sized reads with an
# OVERLAP-byte tail carried over so a key straddling a chunk boundary is still seen
# (a key's shortest matching prefix is ~40 bytes; OVERLAP is far larger). The PEM and
# psk= checks read a non-ELF file whole only when it is at most TEXT_CAP bytes.
CHUNK = max(int(os.environ.get("CULTUREOS_AUDIT_CHUNK", 1 << 20)), 1024)
TEXT_CAP = int(os.environ.get("CULTUREOS_AUDIT_TEXT_CAP", 4 << 20))
OVERLAP = 256


def scan_tskey(fh):
    fh.seek(0)
    tail = b""
    while True:
        block = fh.read(CHUNK)
        if not block:
            return False
        buf = tail + block
        if TSKEY.search(buf):
            return True
        tail = buf[-OVERLAP:]


def rel(p):
    return os.path.relpath(p, root)


# 1a. Nothing but directories and symlinks under /var and /home.
for top in ("var", "home"):
    base = os.path.join(root, top)
    if os.path.islink(base) or not os.path.isdir(base):
        continue
    for d, dirs, files in os.walk(base):
        for f in files:
            p = os.path.join(d, f)
            if not os.path.islink(p):
                findings.append(f"mutable data shipped in the image: {rel(p)}")

# 1b. CultureOS units keep state under /var.
for unit_dir in ("usr/lib/systemd/system", "lib/systemd/system", "etc/systemd/system",
                 "usr/etc/systemd/system"):
    ud = os.path.join(root, unit_dir)
    if not os.path.isdir(ud):
        continue
    for name in sorted(os.listdir(ud)):
        path = os.path.join(ud, name)
        if not STATE_UNITS.match(name) or not os.path.isfile(path):
            continue
        text = open(path, encoding="utf-8", errors="replace").read()
        for m in list(STATE_ARGS.finditer(text)) + list(STATE_ENV.finditer(text)):
            value = m.group(1)
            if value.startswith("/") and not value.startswith(WRITABLE_OK):
                findings.append(f"{unit_dir}/{name}: state path outside /var: {value}")

# 2. Secrets.
for d, dirs, files in os.walk(root):
    for f in files:
        p = os.path.join(d, f)
        if os.path.islink(p) or not os.path.isfile(p):
            continue
        if f.startswith("ssh_host_") and f.endswith("_key"):
            findings.append(f"baked SSH host key: {rel(p)}")
        try:
            with open(p, "rb") as fh:
                head = fh.read(4)
                is_elf = head == b"\x7fELF"
                if scan_tskey(fh):
                    findings.append(f"Tailscale key (tskey-...) in {rel(p)}")
                size = os.fstat(fh.fileno()).st_size
                # Key files only: ELF code may embed known test vectors (gnutls FIPS
                # self-tests). PEM and psk= checks need whole lines/blocks, so they run
                # on non-ELF files up to TEXT_CAP (key and config files are small).
                if is_elf or size > TEXT_CAP:
                    continue
                fh.seek(0)
                data = fh.read(TEXT_CAP + 1)
        except OSError:
            continue
        if PRIVATE_KEY.search(data):
            findings.append(f"PRIVATE KEY block in {rel(p)}")
        if b"psk=" in data:
            for line in data.splitlines():
                s = line.strip()
                if b"psk=" in s and not s.startswith((b"#", b";")):
                    findings.append(f"uncommented psk= in {rel(p)}")
                    break

for shadow in ("etc/shadow", "usr/etc/shadow"):
    sp = os.path.join(root, shadow)
    if not os.path.isfile(sp):
        continue
    for line in open(sp, encoding="utf-8", errors="replace"):
        fields = line.rstrip("\n").split(":")
        if len(fields) < 2:
            continue
        user, pw = fields[0], fields[1]
        if pw == "":
            findings.append(f"{shadow}: {user} has an empty password")
        elif user == "root" and not pw.startswith(("!", "*")):
            findings.append(f"{shadow}: root is not locked")

for line in findings:
    print(f"FINDING: {line}")
if findings:
    print(f"audit: {len(findings)} finding(s)")
    sys.exit(1)
print("audit: OK (no data outside /var, secrets scan clean, root locked)")
PY
