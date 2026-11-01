# Release bundle

`os/scripts/bundle-release.sh` assembles a CultureOS release bundle locally from a
Yocto deploy dir. It never uploads or publishes anything.

```bash
os/scripts/bundle-release.sh <deploy-dir> <out-dir> [version]
# e.g. <deploy-dir> = the build's tmp/deploy; <out-dir> outside the repo
```

The output is `<out-dir>/cultureos-release-<version>.tar` (version defaults to the date).

## Contents

| Path in the tarball | What |
|---------------------|------|
| `images/*.qcomflash.tar.gz` | EDL flash bundle (Qualcomm firmware, **binary only**) |
| `images/*.ostreecommit.tar.zst` | OSTree commit for OTA |
| `licenses/<recipe>/` | Licence texts of every recipe that carries a Qualcomm licence, including `LICENSE.qcom-2` |
| `MANIFEST.sha256` | sha256 of every other file in the bundle (`sha256sum -c` compatible) |

The Qualcomm licence (`LICENSE.qcom-2`) permits redistribution of the firmware in
binary form together with the licence text, which is why the licence texts travel
with the images.

## Checks (script exits non-zero and removes any partial tarball)

- `LICENSE.qcom-2` must be found under `<deploy-dir>/licenses` and appear in the manifest.
- No firmware source: no file in the staged bundle, and no member of the flash
  tarball, may match `*.c *.h *.S *.s *.cc *.cpp *.patch *.diff`, source tarballs/zips
  or `*.src.rpm`.
- Both image artifacts must exist in `<deploy-dir>/images/ventuno-q`.

Tests: `tests/os/test_bundle_release.py` (fixture deploy dir; fails when the licence
is missing or a source file is present).
