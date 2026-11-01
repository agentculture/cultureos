# Offline-reproducible build

How CultureOS builds without the network: a local source + sstate mirror on
the Spark, and a second, clean build that runs with `BB_NO_NETWORK = "1"`.
Plan task t6 (hypothesis h1).

Only config, a script and this document are committed. The mirror itself is
a directory outside the repo.

## Pieces

| Path | What it is |
|------|------------|
| `os/kas/mirror.yml` | `PREMIRRORS` and `SSTATE_MIRRORS` pointing at `file:///repo-ref/{downloads,sstate-cache}` |
| `os/kas/offline.yml` | `BB_NO_NETWORK = "1"`: a fetch not satisfied locally fails |
| `os/kas/mirror-refresh.yml` | `BB_GENERATE_MIRROR_TARBALLS = "1"`, used only by `refresh-mirror.sh --fetch` |
| `os/scripts/refresh-mirror.sh` | Builds and refreshes the mirror from the shared caches |
| `$HOME/yocto/mirror/` | The mirror (not in git), override with `CULTUREOS_MIRROR_DIR` |

Mirror layout:

```text
$HOME/yocto/mirror/downloads/      source files, crates, uninative, git2_<name>.tar.gz (+ .done)
$HOME/yocto/mirror/sstate-cache/   sstate objects
```

The mirror is a real copy of the shared caches in `~/yocto/cache` (never
hard links: the live `git2/` bare repos are updated in place). Git sources
are stored as BitBake mirror tarballs (`git2_<host.path>.tar.gz`), which is
the form `PREMIRRORS` serves; the bare clones themselves are not copied.

## How the mirror reaches the container

`bb.sh` runs kas-container, which mounts only the checkout, the build root,
`DL_DIR` and `SSTATE_DIR`. kas-container also mounts the directory in
`KAS_REPO_REF_DIR` read-write at `/repo-ref`, and `bb.sh` leaves that variable
alone. So the mirror is passed by exporting it, with no change to `bb.sh`:

```bash
export KAS_REPO_REF_DIR="$HOME/yocto/mirror"
```

`mirror.yml` then refers to `file:///repo-ref/downloads/` and
`file:///repo-ref/sstate-cache/PATH`. (kas also uses `KAS_REPO_REF_DIR` as a
reference clone cache for layer repos; with no matching directory in the
mirror root it does nothing.) Without the variable the mirror paths simply do
not exist and BitBake falls through to the upstream URLs.

## Disk use

| Item | Size |
|------|------|
| `downloads/` (without `git2/`) | 8.4 GB |
| `downloads/` git mirror tarballs (`git2_*.tar.gz`, 285 files) | 33 GB |
| `sstate-cache/` | 39 GB |
| Total (`du -sh $HOME/yocto/mirror`) | 81 GB |

Measured 2026-11-01 on the Spark's 3.7 TB NVMe (about 1.2 TB free before the
mirror was made). Growth tracks the shared caches: every new package version
or revision adds to both. The git tarballs are compressed copies of the bare
clones, which are the bulk of the shared `downloads/git2/` (34 GB).

## Refresh the mirror

Run when the manifest pins move or after a build that fetched new sources:

```bash
os/scripts/refresh-mirror.sh                  # rsync caches -> mirror, tar new git2 clones
os/scripts/refresh-mirror.sh --dry-run        # show the steps
os/scripts/refresh-mirror.sh --fetch "$PWD"   # also `bitbake --runall=fetch cultureos-image`
                                              # with the mirror as DL_DIR
```

`--fetch` goes through `bb.sh` (so it is serialized with other builds) and
fills in sources that are in the manifest but missing from the shared cache.
It needs the network. The copy steps are incremental (`rsync -a`) and the
git tarball step skips what already has a `.done` file. A git source whose
upstream moved to a new revision needs a new tarball: delete the old
`git2_<name>.tar.gz` and its `.done` in the mirror, then refresh.

## Clean second build with `BB_NO_NETWORK=1`

The check is a fresh build root (so it cannot reuse the shared `tmp/`),
fresh and empty `DL_DIR` and `SSTATE_DIR`, and the mirror as the only source.
The shared build dir is not touched. The layer checkouts are copied from the
shared build root (kas finds the pinned commits there and does not clone).

```bash
V="$HOME/yocto/offline-verify"
mkdir -p "$V" "$V/cache/downloads" "$V/cache/sstate-cache"
for r in bitbake meta-ai meta-audioreach meta-openembedded meta-qcom meta-qcom-arduino \
         meta-qcom-distro meta-security meta-selinux meta-updater meta-virtualization oe-core; do
  cp -a "$HOME/yocto/cultureos-build/$r" "$V/"
done

export KAS_REPO_REF_DIR="$HOME/yocto/mirror"
export CULTUREOS_BUILD_ROOT="$V" CULTUREOS_CACHE_DIR="$V/cache"
export CULTUREOS_KAS_CONFIG=os/kas/cultureos.yml:os/kas/mirror.yml:os/kas/offline.yml
os/scripts/bb.sh "$PWD" --runall=fetch cultureos-image   # every do_fetch, from the mirror
os/scripts/bb.sh "$PWD"                                   # the image
```

`--runall=fetch` runs `do_fetch` for every recipe whether or not its sstate
exists, so it proves the sources, not only the sstate, are in the mirror.
Delete `$V` afterwards to free the space (it is only a verification scratch
area; nothing in it is shared).

## Qualcomm boot binaries

The QCS8300 boot binaries are fetched from
`softwarecenter.qualcomm.com/nexus/generic/product/chip/tech-package/QCS8300_bootbinaries.1.0/...`
by two recipes of meta-qcom (`recipes-bsp/firmware-boot/`):

- `firmware-qcom-boot-qcs8300` (`firmware-qcom-boot-qcs8300_00150.bb`):
  `QCS8300_bootbinaries_00150.zip` and
  `QCS8300_bootbinaries_immutable_00150.zip`;
- `firmware-qcom-cdt-qcs8300`: the CDT binaries.

Both are in the mirror's `downloads/`. The "https?://.*/.*" premirror line in
`mirror.yml` covers that host.

## Verification run, 2026-11-01

Run from the t6 worktree with the commands above, shared build dir untouched
(a separate `CULTUREOS_BUILD_ROOT`, empty `DL_DIR` and `SSTATE_DIR`):

| Step | Result |
|------|--------|
| `--runall=fetch cultureos-image` | exit 0; 1,156 tasks, all succeeded; fresh `downloads/` ended at 8.8 GB |
| `bb.sh` (kas build, target `cultureos-image`) | exit 0; 10,411 tasks, all succeeded; 7 min wall time |
| sstate | `Wanted 5008 Local 0 Mirrors 4999 Missed 9`: nothing local, 4,999 objects from the mirror, the 9 misses were built offline |
| Output | `deploy/images/ventuno-q/` has `.ostreecommit.tar.zst` (503 MB), `.ota-ext4` (2.7 GB), `.qcomflash/` and `.qcomflash.tar.gz` |

Boot binaries: `log.do_fetch` of `firmware-qcom-boot-qcs8300` shows
`https://softwarecenter.qualcomm.com/.../QCS8300_bootbinaries_00150.zip`
rewritten to `file:///repo-ref/downloads/QCS8300_bootbinaries_00150.zip`
("Trying mirrors in PREMIRRORS"), and the fresh `downloads/` then held
`QCS8300_bootbinaries_00150.zip` and `QCS8300_bootbinaries_immutable_00150.zip`.
Its `firmware-qcom-cdt-ventuno-q` sibling (the VENTUNO Q CDT, in
meta-qcom-arduino) also fetched from the mirror.

## Gotchas found while doing it

- **Parsing needs the network by default.** meta-qcom's `linux-qcom_6.18.bb`
  and `linux-qcom-next_git.bb` carry an unselected `devupstream` variant with
  `SRCREV = ${AUTOREV}`. BitBake runs `git ls-remote` for it at parse time, so
  with `BB_NO_NETWORK` the whole parse fails. `offline.yml` pins
  `SRCREV:class-devupstream` to a fixed revision; the variants are never
  built.
- **Aliased git clones.** BitBake leaves `git2/<old-name>` symlinks (with an
  in-container target path) when a source's URL changed
  (`git.netfilter.org.libnftnl` to `repo.or.cz.libnftnl.git`).
  `refresh-mirror.sh` turns those into tarball symlinks; without them the
  fetch falls through to the network and fails.
- **Stale `.done` markers.** The shared cache can hold a `git2_*.tar.gz.done`
  with no tarball (trousers did). The script only skips a source when both
  exist.
- `BB_NO_NETWORK` stops BitBake's own fetches; it is not a network sandbox.
  Success proves every fetch was served locally, which is the point.
