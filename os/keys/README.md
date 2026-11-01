# OSTree signing keys (public half only)

This directory holds the **public** ed25519 key that boards use to verify
CultureOS OSTree commits: `cultureos-ostree.pub` (one line,
base64, 32 bytes).

The matching private key never enters this repository. It lives on the
release host, outside any git work tree, at the path named by
`CULTUREOS_SIGN_KEY` (see [`docs/os/release-repo.md`](../../docs/os/release-repo.md)).
`os/scripts/publish-ostree.sh` refuses a key path inside a git work tree.

The key has not been generated yet (operator step). Print the exact commands
with:

```bash
os/scripts/publish-ostree.sh --print-keygen
```

Then commit only `cultureos-ostree.pub`. Do not add a placeholder key here.
