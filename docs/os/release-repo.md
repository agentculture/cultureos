# OSTree release repo

The signed OSTree repository that boards pull CultureOS updates from. It lives
on the DGX Spark, outside the git checkout, and is served over HTTP on the
Tailscale address only. Covers plan task t17 (claim c29).

## Layout

| Thing | Where | Committed? |
|-------|-------|-----------|
| Build output (input) | the shared build's `deploy/images/ventuno-q/ostree_repo`, ref `ventuno-q` | no |
| Release repo (archive mode) | `$HOME/cultureos-ostree/repo` (`CULTUREOS_RELEASE_REPO`) | no |
| Signing **private** key | `$HOME/cultureos-ostree/keys/ostree-ed25519.secret` (`CULTUREOS_SIGN_KEY`) | never |
| Signing **public** key | `os/keys/cultureos-ostree.pub` | yes |
| Publish script | `os/scripts/publish-ostree.sh` | yes |
| Serving unit | `os/systemd/cultureos-ostree-http.service` | yes |

Optional per-user config: an env-style file at
`$HOME/.config/cultureos/release.env` (override the path with
`CULTUREOS_RELEASE_CONF`) can set `CULTUREOS_BUILD_REPO`, `CULTUREOS_OSTREE_REF`,
`CULTUREOS_RELEASE_REPO`, `CULTUREOS_SIGN_KEY`, `CULTUREOS_PUBKEY`,
`CULTUREOS_SERVE_PORT`. The same file is read by the serving unit.

## Prerequisites (operator)

- A host `ostree` **with ed25519 support**. Install it with
  `sudo apt install ostree`, then check `ostree --version` lists `ed25519`.
  The script refuses an ostree without it.
- A signing key, created once, outside the repo. Print the exact commands:

  ```bash
  os/scripts/publish-ostree.sh --print-keygen
  ```

  Run them yourself, then commit only `os/keys/cultureos-ostree.pub`
  (see `os/keys/README.md`). The script refuses a key path inside any git work
  tree. Back the private key up out of band: losing it means re-keying every
  board.

## Publishing

```bash
os/scripts/publish-ostree.sh
```

The script is all-or-nothing for the published ref:

1. Pull the build's commit **by checksum** into the release repo. No ref is
   created yet, so nothing is visible to boards.
2. Sign that commit with ed25519.
3. Verify it as a board would: pull it into a throwaway repo through a remote
   configured with `--sign-verify=ed25519=file:<public key>`.
4. Move the ref (`refs --create --force`), then `summary --update` with a
   signed summary.
5. Re-verify the summary the same way.

If any step fails, the script restores the previous ref (or removes a
first-time ref) and the previous `summary` / `summary.sig` files, and exits
non-zero. Orphaned objects from a failed run are harmless; reclaim them with
`ostree --repo=<release repo> prune --refs-only`. Re-running with the ref
already at the build's commit is a no-op.

Caveat: `ostree sign` and `ostree summary --sign` take the secret key on the
command line (this ostree version has no key-file option), so it is briefly
visible in the process list of the publishing user. Acceptable on a
single-user host; do not publish from a shared machine.

## Serving over Tailscale

The unit runs `python3 -m http.server` as a static file server, bound to the
address printed by `tailscale ip -4` at start. It never binds `0.0.0.0`; if
Tailscale has no IPv4 address yet, it fails and systemd retries every 10 s.
Install and start it yourself (this task does not):

```bash
mkdir -p "$HOME/.config/systemd/user"
cp os/systemd/cultureos-ostree-http.service "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable --now cultureos-ostree-http.service
loginctl enable-linger "$USER"   # keep it running without a login session
systemctl --user status cultureos-ostree-http.service
```

The default port is 8650 (`CULTUREOS_SERVE_PORT`).

### URL the board uses

Boards on the tailnet reach the repo at the Spark's MagicDNS name:

```text
http://spark.tail0be7e0.ts.net:8650/
```

(the Spark's tailnet name as reported by `tailscale status --json` at the time
of writing; confirm before baking it into an image). On the board, the remote
is installed by the `cultureos-security` recipe (`docs/os/security.md`):
`/etc/ostree/remotes.d/cultureos.conf` points at this URL with
`sign-verify=true`, and `os/keys/cultureos-ostree.pub` is installed as
`/usr/share/cultureos/ostree/cultureos-ostree-ed25519.pub`. The URL and key
path are bitbake variables (`CULTUREOS_OSTREE_URL`,
`CULTUREOS_OSTREE_PUBKEY_FILE`) if either changes.

## Status and known gaps

- Verified here: the publish flow's ordering and its rollback on an injected
  failure at each step (stub-based tests in `tests/os/test_publish_ostree.py`),
  the key-outside-repo guard, and the unit's bind logic by inspection.
- NOT verified: a real signing round trip. The Spark has no host `ostree`
  installed (`sudo apt install ostree`; Ubuntu 24.04's 2024.5 lacks
  `sign-ed25519`, so use the build's `ostree-native`). A real-ostree test exists
  and runs automatically once an ed25519-capable `ostree` is on PATH.
- ed25519 support: fixed by `cultureos-security`'s `ostree_%.bbappend`
  (`PACKAGECONFIG ed25519-libsodium`, deviation d4) for both the board's
  `ostree` and `ostree-native`. The image's own `ostree` refused an unsigned
  commit and accepted a correctly signed one (`docs/os/security.md`).
