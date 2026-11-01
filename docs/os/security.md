# Device hardening: sshd and the signed OSTree remote

What the `cultureos-security` recipe puts on the device, what upstream's
base image still leaves open, and how the signature check was tested. Plan
task t12 (covers h24).

## What the recipe ships

`os/meta-cultureos/recipes-core/cultureos-security/`:

| File | Installed as | Purpose |
|------|--------------|---------|
| `files/01-cultureos-hardening.conf` | `/etc/ssh/sshd_config.d/01-cultureos-hardening.conf` | key-only sshd, no root login |
| `files/ostree-remote.conf.in` | `/etc/ostree/remotes.d/cultureos.conf` | the OTA remote, `sign-verify=true` |
| (the release public key, from the build host) | `/usr/share/cultureos/ostree/cultureos-ostree-ed25519.pub` | the key the remote verifies against |
| `ostree_%.bbappend` | (build config) | builds ostree with ed25519 support |

The package `cultureos-security` is not in the image yet: the image
integration task (t19) adds it to `CULTUREOS_PACKAGES`.

## sshd

The image uses OpenSSH (`openssh-sshd` 10.6p1, socket-activated through
`sshd.socket` / `sshd@.service`), not dropbear. Its `/etc/ssh/sshd_config`
(from oe-core, edited by the `allow-root-login` and `allow-empty-password`
image features) begins:

```text
Include /etc/ssh/sshd_config.d/*.conf
PermitRootLogin yes
AuthorizedKeysFile .ssh/authorized_keys
PermitEmptyPasswords yes
KbdInteractiveAuthentication no
UsePAM yes
```

sshd keeps the first value it reads for a keyword, and the `Include` comes
first, with the drop-ins read in lexical order. The image already has
`20-systemd-userdb.conf` there (a link into `/usr/lib/systemd/sshd_config.d/`).
The CultureOS drop-in is named `01-` so it is read first and wins over both
that file and the permissive lines of the main config. No edit of the main
`sshd_config` is needed.

The drop-in sets:

```text
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
PermitRootLogin no
PubkeyAuthentication yes
AuthenticationMethods publickey
```

So login over ssh needs a non-root account with a key in its
`authorized_keys`; provisioning (t10/t11) must create that account and key,
or the board is reachable only on the console.

## The OSTree remote

`/etc/ostree/remotes.d/cultureos.conf`, generated from
`ostree-remote.conf.in`:

```ini
[remote "cultureos"]
url=http://spark.tail0be7e0.ts.net:8650/
gpg-verify=false
sign-verify=true
verification-ed25519-file=/usr/share/cultureos/ostree/cultureos-ostree-ed25519.pub
```

Each value comes from a recipe variable (set it in the distro conf or
`local.conf`):

| Variable | Default | Meaning |
|----------|---------|---------|
| `CULTUREOS_OSTREE_URL` | `http://spark.tail0be7e0.ts.net:8650/` | the Spark's release repo over Tailscale (t17, `docs/os/release-repo.md`); the real endpoint is defined by t17 |
| `CULTUREOS_OSTREE_PUBKEY_FILE` | `os/keys/cultureos-ostree.pub` in this repo | the release public key on the build host (committed by t17) |
| `CULTUREOS_OSTREE_PUBKEY_PATH` | `${datadir}/cultureos/ostree/cultureos-ostree-ed25519.pub` | where it lands on the device |
| `CULTUREOS_OSTREE_REMOTE` | `${OSTREE_OSNAME}` (`cultureos`) | remote name |

The remote is named after `OSTREE_OSNAME` because meta-updater's `ota-ext4`
deploys the first commit as `${OSTREE_OSNAME}:${OSTREE_BRANCHNAME}`
(`cultureos:ventuno-q`), so `ostree admin upgrade` pulls from that remote.

With `sign-verify=true` every pulled commit must carry a valid ed25519
signature from a key in the key file. An unsigned commit, a commit signed by
another key, and a missing key file all make the pull fail. If the key file
is missing at build time the recipe warns and still installs the remote, so
the device fails closed (refuses every pull) rather than accepting unsigned
updates. `sign-verify-summary` is left at its default (off): commits are
verified, the summary is not. Signing the summary as well is t17's choice.

GPG is off because meta-updater builds ostree without gpgme.

### ostree needs ed25519 support

The stock target ostree in this stack cannot check signatures at all:
meta-oe builds it with glib crypto (`PACKAGECONFIG` `glib`, no
`ed25519-libsodium` / `ed25519-openssl`) and meta-updater removes `gpgme`.
In the unmodified image `ostree` depends on neither libsodium nor libssl, and
meta-updater only adds `ed25519-libsodium` under its `cfs-signed` override,
which CultureOS does not use.

`ostree_%.bbappend` adds `ed25519-libsodium` to `PACKAGECONFIG`. That applies
to `ostree-native` too, which the release pipeline (t17) needs for
`ostree sign`. `ostree --version` lists `sign-ed25519` when it is there. The
bbappend sits in the `cultureos-security` directory (the layer's `BBFILES`
matches `recipes-*/*/*.bbappend`) so all of the hardening is in one place.

### Key format and generation (operator step)

The key file holds one base64-encoded raw 32-byte ed25519 public key per
line. `ostree sign` takes the secret as base64 of the 64-byte libsodium
secret key (seed followed by public key). One way to make a pair with
`openssl`, run by the operator outside the repo; only the `.pub` file is
committed (by t17, under `os/keys/`):

```bash
openssl genpkey -algorithm ed25519 -out release.pem
python3 - <<'EOF'
import base64, subprocess
der = lambda *a: subprocess.run(["openssl", "pkey", "-in", "release.pem", *a, "-outform", "DER"], check=True, capture_output=True).stdout
seed, pub = der()[-32:], der("-pubout")[-32:]
open("cultureos-ostree.pub", "w").write(base64.b64encode(pub).decode() + "\n")
open("cultureos-ostree-ed25519.sec", "w").write(base64.b64encode(seed + pub).decode() + "\n")
EOF
```

The secret key never goes into the repo or the image.

## Tests

`tests/os/test_cultureos_security.py`:

- the drop-in sets the keywords above and sorts before `20-systemd-userdb.conf`;
- `sshd -T` on the upstream main config (as above) plus the drop-in reports
  `permitrootlogin no`, `passwordauthentication no`,
  `permitemptypasswords no`, `authenticationmethods publickey` (skipped when
  the host has no `/usr/sbin/sshd`);
- the remote template has `sign-verify=true`, `gpg-verify=false` and a
  `verification-ed25519-file`; URL and key path are recipe variables; no key
  material in the recipe directory; the bbappend enables `ed25519-libsodium`;
- the refusal test: a throwaway archive repo with a signed, an unsigned and a
  wrong-key commit, made with a throwaway ed25519 key generated in the test's
  temp dir; a client repo whose remote is the committed template (URL
  `file://`, key path the temp key) pulls each. The unsigned and wrong-key
  pulls fail with ostree's reason on stderr, the signed pull succeeds, and a
  missing key file refuses even the signed commit.

The messages ostree gives (target ostree 2026.5): unsigned,
`error: Can't verify commit <sha>: ed25519: commit have no signatures of my
type`; wrong key, `... ed25519: Signature couldn't be verified with: key
'<key>'`; no key file, `error: Failed loading 'ed25519' keys from '<path>'`.

The refusal test needs an ostree with `sign-ed25519`. It uses
`$CULTUREOS_TEST_OSTREE` (a command line) or `ostree` on `PATH`, and skips
with the reason when there is none, or when that ostree lacks ed25519 (for
example Ubuntu 24.04's `ostree` 2024.5, which has no `sign-ed25519`
feature). In CI it skips. To run it against the device's own ostree binary
(the Spark is aarch64 like the board), unpack the image rootfs and run it
through the image's dynamic loader:

```bash
R=<dir with the unpacked rootfs from cultureos-image-ventuno-q.rootfs.ostree.tar.zst>
export CULTUREOS_TEST_OSTREE="$R/usr/lib/ld-linux-aarch64.so.1 --library-path $R/usr/lib $R/usr/bin/ostree"
uv run pytest tests/os/test_cultureos_security.py -rs
```

## Build result, 2026-11-01

`os/scripts/bb.sh "$PWD" cultureos-security ostree ostree-native cultureos-image`
from the t12 worktree, with a throwaway kas override (not committed) that
added `IMAGE_INSTALL:append:pn-cultureos-image = " cultureos-security"`:
exit 0, 10,470 tasks, all succeeded. The one recipe warning is the expected
"no OSTree release public key" (t17 has not committed it yet).

In the resulting image:

- the manifest lists `cultureos-security`, `ostree` 2026.5 and `libsodium26`;
- `/usr/etc/ssh/sshd_config.d/` holds `01-cultureos-hardening.conf` and
  `20-systemd-userdb.conf`; `/usr/etc/ostree/remotes.d/cultureos.conf` is
  as shown above; `/usr/share/cultureos/ostree/` is empty (no key yet);
- the image's own `ostree --version`, run on the Spark through the image's
  loader, lists `sign-ed25519`; the refusal test passes 13 of 13 with it;
- the image's own `sshd -T` on the image's `sshd_config` (Include pointed at
  copies of the two drop-ins, HostKey replaced by a temporary key) prints
  `PermitRootLogin no`, `PasswordAuthentication no`,
  `PermitEmptyPasswords no`, `KbdInteractiveAuthentication no`,
  `AuthenticationMethods publickey`;
- `ostree-native` links `libsodium.so.26` as well.

## What upstream still leaves open (for t19)

The recipe hardens ssh only. The base image keeps upstream's local root
access, set outside this layer:

| What | Where | Effect in the image |
|------|-------|---------------------|
| `EXTRA_IMAGE_FEATURES += "allow-empty-password empty-root-password allow-root-login"` | meta-qcom `ci/base.yml` (`local_conf_header` `extra`), pulled in by the kas include chain | `sshd_config` gets `PermitRootLogin yes` and `PermitEmptyPasswords yes`; root's password is not zapped |
| `IMAGE_FEATURES += "... allow-root-login ..."` | meta-qcom-distro `qcom-minimal-image.bb` | the same, independent of `ci/base.yml` |
| `EXTRA_USERS_PARAMS = "usermod -p '<hash>' root;"` (comment: "Default root password: oelinux123") | meta-qcom-distro `qcom-minimal-image.bb` | `/etc/shadow` has that hash for root: a fixed, public root password on the console |
| `inherit image-adbd` | meta-qcom-distro `qcom-minimal-image.bb` | installs `android-tools-adbd`; its unit starts when `/etc/usb-debugging-enabled` exists or the kernel command line contains `adbd`, giving a root shell over USB |

The drop-in makes all of this unreachable over ssh. On the console (and over
adb, if enabled) the fixed root password still works. Proposed change for
the image recipe (t19), not made here:

```bitbake
IMAGE_FEATURES:remove = "allow-empty-password empty-root-password allow-root-login"
# lock root: no password login at all (replaces upstream's fixed hash)
EXTRA_USERS_PARAMS = "usermod -L root;"
# no adb root shell (or keep it and make sure the kernel command line
# cannot be edited at boot)
PACKAGE_INSTALL:remove = "android-tools-adbd android-tools-adbd-cmdline"
```

Removing `allow-root-login` makes oe-core also rewrite the main
`sshd_config` to `PermitRootLogin no`, a second layer under the drop-in.
`EXTRA_USERS_PARAMS` must keep whatever users provisioning adds. Before
locking root, the image needs another way in (the provisioned user with sudo,
or a rescue path), since the board otherwise has no local login.

## Not verified on hardware

Booting a CultureOS image with this package needs the NVMe install, which
does not exist yet. On the board, once it does:

1. `sshd -T | grep -Ei 'permitrootlogin|passwordauthentication|authenticationmethods'`
   shows `no`, `no`, `publickey`; `ssh root@<board>` and a password login
   are refused.
2. `ostree remote list -u` shows `cultureos` with the configured URL,
   `/etc/ostree/remotes.d/cultureos.conf` has `sign-verify=true`, and
   `ostree --version` lists `sign-ed25519`.
3. Publishing an unsigned commit on the Spark's repo and running
   `ostree admin upgrade` fails, and the journal of the update agent (t16)
   shows ostree's signature error.
