"""t10 acceptance 2: the image rootfs carries no Wi-Fi PSK and no Tailscale auth key.

Runs against an extracted rootfs (for example the ``ostree.tar.zst`` of a
``cultureos-image`` build) named by ``CULTUREOS_ROOTFS_DIR``; skipped
otherwise, because CI has no image.

- No Tailscale key (``tskey-<kind>-<id>-<secret>`` or legacy ``tskey-<hex>``)
  in any file, text or binary. Deviation d8: a bare ``tskey-`` is not a key;
  tailscaled contains the constant ``tskey-wrap``. Same rule as
  ``os/scripts/audit-image.sh``.
- ``psk=`` must not occur in any non-ELF file except on a comment line.
  ELF binaries are exempt: upstream wpa_supplicant, wpa_cli, wpa_passphrase
  and hostapd carry ``psk=%s`` style format strings (measured on the t5
  image), which are code, not secrets. A baked PSK would sit in a config file
  (a NetworkManager keyfile, wpa_supplicant.conf), which this does catch.
"""

import os
import re
from pathlib import Path

import pytest

ROOTFS = os.environ.get("CULTUREOS_ROOTFS_DIR")

pytestmark = pytest.mark.skipif(
    not ROOTFS,
    reason="CULTUREOS_ROOTFS_DIR not set: no extracted image rootfs to scan",
)

PSK = b"psk="
TSKEY = re.compile(rb"tskey-(?:[a-z]+-)?[A-Za-z0-9]{6,}-[A-Za-z0-9]{16,}|tskey-[0-9a-f]{20,}")
COMMENT_PREFIXES = (b"#", b";", b"//")


def _files(root: Path):
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            p = Path(dirpath) / name
            if p.is_symlink() or not p.is_file():
                continue
            yield p


def _scan(root: Path):
    tskey_hits, psk_hits, elf_exempt = [], [], []
    for p in _files(root):
        try:
            data = p.read_bytes()
        except OSError:
            continue
        rel = p.relative_to(root)
        if TSKEY.search(data):
            tskey_hits.append(str(rel))
        if PSK not in data:
            continue
        if data[:4] == b"\x7fELF":
            elf_exempt.append(str(rel))
            continue
        for n, line in enumerate(data.splitlines(), 1):
            if PSK in line and not line.lstrip().startswith(COMMENT_PREFIXES):
                psk_hits.append(f"{rel}:{n}")
    return tskey_hits, psk_hits, elf_exempt


def test_rootfs_has_no_psk_or_tailscale_key():
    root = Path(ROOTFS)
    assert root.is_dir(), f"{root} is not a directory"
    assert (root / "usr").is_dir(), f"{root} does not look like a rootfs"
    tskey_hits, psk_hits, elf_exempt = _scan(root)
    print(f"ELF files with psk= format strings (exempt): {sorted(elf_exempt)}")
    assert tskey_hits == [], f"Tailscale key found in: {tskey_hits}"
    assert psk_hits == [], f"uncommented psk= found at: {psk_hits}"
    connections = root / "usr" / "etc" / "NetworkManager" / "system-connections"
    if connections.is_dir():
        assert list(connections.iterdir()) == [], "image ships NetworkManager profiles"
