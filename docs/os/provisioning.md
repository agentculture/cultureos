# First-boot provisioning

How a fresh CultureOS board gets its login user, SSH key, Wi-Fi and hostname
without any of them being baked into the image. Plan task t10 (covers c26,
h11), with the login user required by deviation d3. Recipe:
`os/meta-cultureos/recipes-core/cultureos-provision/`.

The image ships no credentials: no Wi-Fi passphrase, no password, no public
key, no Tailscale key. The operator writes them into one small file,
`cultureos-provision.toml`, puts it on the ESP or a USB stick, and boots.
`cultureos-provision.service` applies it once, removes it, and never runs
again.

## The provisioning file

TOML, read with Python's `tomllib` (python3 3.14 and `python3-tomllib` are in
the image already, for culture). TOML was chosen over a shell `key=value`
file because SSIDs and passphrases may contain spaces, quotes, `#` and `=`,
which TOML strings quote unambiguously, and the helper can then validate the
whole file before it changes anything.

Format (every value is a placeholder):

```toml
[user]
# crypt hash of the arduino user's password; never the password itself
password_hash = "<output of: openssl passwd -6>"
# one or more OpenSSH public key lines (the .pub file, not the private key)
ssh_authorized_keys = [
  "<contents of your id_ed25519.pub>",
]

# optional: leave the whole section out to use Ethernet only
[wifi]
ssid = "<your Wi-Fi network name>"
psk = "<your Wi-Fi passphrase, 8 to 63 characters, or 64 hex digits>"
hidden = false            # optional, true for a hidden network

# optional
[system]
hostname = "<one DNS label, for example cultureos-01>"
```

Rules the helper enforces (anything else is an error, nothing is applied):

| Key | Required | Accepted |
|-----|----------|----------|
| `user.password_hash` | yes | `$6$` (sha512crypt), `$5$` (sha256crypt) or `$y$` (yescrypt) crypt hash. A `user.password` key or any non-hash value is refused as plaintext |
| `user.ssh_authorized_keys` | yes | a string or list of OpenSSH public key lines (`ssh-ed25519`, `ssh-rsa`, `ecdsa-sha2-nistp*`, `sk-*`); a private key block is refused |
| `wifi.ssid` | with `[wifi]` | 1 to 32 bytes, no control characters |
| `wifi.psk` | with `[wifi]` | 8 to 63 printable ASCII characters, or 64 hex digits (WPA2/WPA3-transition PSK) |
| `wifi.hidden` | no | `true` / `false` |
| `system.hostname` | no | one DNS label: letters, digits, `-`, at most 63 characters |

Unknown sections or keys are errors (a typo such as `pasword_hash` must not
silently leave the board without a login). Any value containing a Tailscale
auth key prefix is refused: tailnet enrollment stays a manual `tailscale up`
(decision q2, [`tailscale.md`](tailscale.md)).

### Creating the password hash

On the operator's machine, never on a shared screen or into the repo:

```bash
openssl passwd -6            # prompts twice, prints $6$<salt>$<hash>
# or, with the whois package installed:
mkpasswd -m sha-512
```

Paste only the printed hash into `password_hash`. This password is what the
local login consoles (USB CDC-ACM `ttyGS1` and UART `ttyMSM0`,
[`local-access.md`](local-access.md)) and `run0` ask for. SSH does not
accept it: sshd is key-only (t12).

### Getting the public key

Use an existing key's `.pub` file, or create a key for the board first
(operator step, outside the repo):

```bash
ssh-keygen -t ed25519 -f <path for the new key>
cat <path for the new key>.pub      # this line goes into ssh_authorized_keys
```

## Where to put the file

The helper looks, in order, for `cultureos-provision.toml` in the root of:

1. a filesystem already mounted at `/boot`, `/efi` or `/boot/efi` (the ESP
   when systemd mounts it);
2. any vfat partition the kernel sees (`blkid -t TYPE=vfat`), each mounted
   read-only on `/run/cultureos-provision/mnt` just long enough to look. This
   covers the NVMe ESP when it is not mounted, and a USB stick. If none has
   the file, it retries for 10 seconds so a USB stick can enumerate.

Only the partition that holds the file is ever remounted read-write (to
remove it). Other vfat partitions, including the eMMC ones of the factory
OS, are only mounted read-only.

Two ways to get the file there:

- **ESP of the NVMe**: from the factory Ubuntu on eMMC (or any machine the
  NVMe is attached to), find the NVMe's vfat ESP with `lsblk -f`, mount it,
  copy the file to its root, `sync`, unmount.
- **USB stick**: a vfat-formatted stick with the file in its root, plugged
  in before power-on.

## What the service does

`cultureos-provision.service` is a oneshot with
`ConditionPathExists=!/var/lib/cultureos/provisioned`, enabled in
`multi-user.target`. It has `DefaultDependencies=no`, runs after
`sysinit.target` (local filesystems, tmpfiles, udev trigger) and is ordered
before `NetworkManager.service`, `network-pre.target`, `sshd.socket`,
`systemd-user-sessions.service` and the two serial gettys, so the first
network connection and the first login prompt already see the result. It runs
`/usr/libexec/cultureos-provision/cultureos-provision`, which:

1. stops (exit 0) if the done-marker exists or no input is found;
2. parses and validates the whole file; on any error it logs the reason to the
   journal, applies nothing, keeps the file and exits 1 (the unit shows as
   failed);
3. creates the user `arduino` (`useradd --create-home --home-dir /home/arduino
   --shell /bin/sh --user-group --groups wheel,dialout`), or, if it already
   exists, adds the groups;
4. sets the password with `chpasswd --encrypted`, the hash passed on stdin
   (never on the command line, which any user can read in `/proc`);
5. writes `.ssh/authorized_keys` in the home of `arduino`;
6. writes the NetworkManager Wi-Fi profile if `[wifi]` is present, and the
   hostname if given;
7. removes the input with `shred -u -z`, then `sync`;
8. writes the done-marker `/var/lib/cultureos/provisioned`
   (`provisioned_at=` and `source=` lines, no secrets).

If a step from 3 on fails (exit 2), the file is kept and no marker is
written, so the next boot runs the whole apply again; every step is
idempotent (an existing user is updated, files are rewritten). Root is never
touched: it stays locked (t12, t19) and the helper does not depend on it
having a password.

The helper never prints the passphrase, the password hash or the key
material; journal lines name only what was done (`created user arduino`,
`installed 1 SSH key(s)`, `wrote NetworkManager profile ... (0600)`). Read
them with `journalctl -u cultureos-provision`.

### Files it writes

| Path | Mode, owner | Persistence on OSTree |
|------|-------------|-----------------------|
| `/home/arduino` (really `/var/rootdirs/home/arduino`) | per `useradd`, `arduino` | `/var`: kept across updates and rollbacks |
| `.ssh/` in that home | `0700`, `arduino` | `/var` |
| `.ssh/authorized_keys` in that home | `0600`, `arduino` | `/var` |
| `/etc/NetworkManager/system-connections/cultureos-wifi.nmconnection` | `0600`, root | `/etc`, see below |
| `/etc/hostname` | `0644`, root | `/etc`, see below |
| `/etc/passwd`, `/etc/shadow`, `/etc/group`, `/etc/gshadow` | as shadow writes them | `/etc`, see below |
| `/var/lib/cultureos/provisioned` | `0644`, root | `/var` |

The recipe also installs `/usr/lib/tmpfiles.d/cultureos-provision.conf`,
which creates `/var/rootdirs/home` (and `/var/lib/cultureos`). In this image
`/home` is a symlink to `var/rootdirs/home`, and nothing else creates that
directory (upstream `00ostree-tmpfiles.conf` creates `opt`, `mnt`, `media`
and `srv` under `/var/rootdirs`, not `home`), so without it `/home` would
dangle. The helper creates it too if tmpfiles has not.

### Network manager

The image runs **NetworkManager 1.58** with `wpa_supplicant` as its Wi-Fi
backend (image manifest: `networkmanager`, `networkmanager-wifi`,
`wpa-supplicant`; no iwd, no systemd-networkd config). Its keyfile plugin
reads `/etc/NetworkManager/system-connections/` (plus the read-only
`/usr/lib/...` and volatile `/run/...` directories); it has no profile
directory under `/var`, so the profile goes into `/etc`. NetworkManager
ignores keyfiles that are not root-owned with mode `0600`, which is what the
helper writes. The profile (`cultureos-wifi`, `autoconnect=true`, DHCP on
IPv4, auto IPv6) binds to no interface name, so it uses the board's Wi-Fi
device (factory OS: `wlp3s0`). Ethernet needs no profile: NetworkManager's
default wired connection does DHCP.

### `/etc` and OSTree updates

OSTree keeps `/var` as is across deployments and does a 3-way merge of
`/etc`: a file changed locally (the running system's `/etc` differs from the
old deployment's `/usr/etc`) is carried into the new deployment unchanged;
an unchanged file takes the new deployment's version. For provisioning that
means:

- The Wi-Fi profile and `/etc/hostname` are local files, so every later
  deployment keeps them. A rollback keeps them too.
- `/etc/passwd`, `/etc/shadow`, `/etc/group` and `/etc/gshadow` become
  locally modified the moment `arduino` is created, so updates keep the
  `arduino` user, its password and group memberships.
- The flip side: from then on, these files are **not** updated from new
  images. A system user that a later image adds at build time (as t13's
  `culture` user is: it lands in `/usr/etc/passwd`) does not appear in the
  running `/etc/passwd` after an update. Today every system user is already
  in the first image, so nothing breaks yet. Any later recipe that adds a
  system user must also ship a `sysusers.d` entry (systemd-sysusers adds
  missing users to `/etc/passwd` at boot), or the image must switch to
  nss-altfiles. This applies to the update work (t16) and to every later
  recipe.
- The user's home and SSH key live in `/var`, so they survive updates and
  rollbacks regardless of `/etc`.

### Administration with root locked

Root is locked and there is no `sudo` in the image. `arduino` is in `wheel`,
which polkit's default rule (`50-default.rules`: `addAdminRule` returns
`unix-group:wheel`) makes the admin group. So `run0 <command>` (systemd's
privilege tool, in the image) asks for the `arduino` password and runs the
command as root. That is the route for root-only operator steps such as
`run0 tailscale up` ([`tailscale.md`](tailscale.md)) and writing
`/var/lib/culture/node.env` ([`culture-node.md`](culture-node.md)). `run0`
on this image is not checked yet (it needs polkit and the PAM stack on a
running board).

### Removing the file: what `shred` achieves

`shred -u -z` overwrites the file's data in place, then zeroes and unlinks
it. On vfat that rewrites the same clusters, so the old content is not left
in free clusters of the filesystem. On flash media (USB sticks, NVMe) the
controller's wear levelling may keep the old blocks physically until they are
erased, so treat removal as best effort: once the board is up, change the
Wi-Fi passphrase only if the stick or NVMe could fall into other hands, and
reformat a USB stick that carried the file. If `shred` is missing or fails,
the helper overwrites the file once with zeros and unlinks it.

## Provisioning again

To re-run, as root on the board (`run0`): remove
`/var/lib/cultureos/provisioned`, put a new file in place and reboot. Because
the user exists by then, the helper updates its password, groups and keys,
and rewrites the profile.

## Tailscale

The file has no Tailscale section and refuses anything that looks like an
auth key. After provisioning, log in (SSH with the key, or a local console)
and enroll by hand: `run0 tailscale up` ([`tailscale.md`](tailscale.md)).

## For t19 (image integration)

- Add `cultureos-provision` to `CULTUREOS_PACKAGES`. Its `RDEPENDS` (python3
  core and tomllib, shadow, coreutils, util-linux blkid and mount,
  NetworkManager) are all in the image already.
- With root locked by t19 and adbd removed (d3), provisioning is the only way
  to get any login. An image without this package cannot be logged into.
- A failed provisioning (bad file) leaves `cultureos-provision.service` in
  `failed` state. If a health check counts failed units, it must not run on
  the very first boot or must ignore this unit (first boot is not a trial
  boot today, so t15's gate does not apply).

## Test procedure (hardware)

Status: **NOT VERIFIED (hardware)**. It needs a CultureOS image with this
package booted from NVMe; no NVMe install exists yet. Offline tests
(`tests/os/test_provision.py`) run the helper against a fake root with stub
`useradd`, `chpasswd`, `mount` and friends.

1. On the Spark, write a provisioning file with a test network's SSID and
   passphrase, a fresh test key's `.pub` line, a hash from `openssl passwd -6`,
   and `hostname = "cultureos-test"`. Keep it outside the repo.
2. Copy it to the root of the NVMe ESP (or a vfat USB stick), `sync`.
3. Unplug Ethernet. Boot the CultureOS image.
4. On a local console (USB `ttyGS1`, [`local-access.md`](local-access.md)):
   a `login:` prompt appears; `root` is refused; `arduino` with the
   password logs in.
5. As `arduino`:
   - `journalctl -u cultureos-provision -b` shows `created user arduino`,
     `installed 1 SSH key(s)`, the profile line, the removal line and
     `provisioning complete`, and no passphrase or hash;
   - `cat /var/lib/cultureos/provisioned` exists;
   - `cd; ls -ld /home "$PWD" .ssh; ls -l .ssh/authorized_keys` shows
     `/home -> var/rootdirs/home`, `0700` and `0600`;
   - `run0 ls -l /etc/NetworkManager/system-connections/` shows
     `cultureos-wifi.nmconnection` as `-rw------- root root`;
   - `nmcli -t -f NAME,DEVICE con show --active` lists `cultureos-wifi` on
     the Wi-Fi device; `hostname` prints `cultureos-test`;
   - the provisioning file is gone from the ESP or stick.
6. From the Spark, over Wi-Fi: `ssh -i <test key> arduino@<board address>`
   works; `ssh root@<board address>` and password-only SSH are refused.
7. Reboot: `systemctl status cultureos-provision` shows the unit skipped
   (condition `!/var/lib/cultureos/provisioned` failed); Wi-Fi and SSH still
   work.
8. Negative: with the marker removed, put a file whose `password_hash` is a
   plain word on the stick and reboot. The unit is `failed`, the journal
   says `plaintext ... refused`, the file is still on the stick, nothing
   changed.
9. After an OSTree update (once t16 exists): `arduino`, its key, the Wi-Fi
   profile and hostname are all still there.

Pass: steps 4 to 8 as described.
