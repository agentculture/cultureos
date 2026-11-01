# Culture mesh node

How CultureOS runs a Culture mesh node: the `recipes-culture` recipes that
package `culture` and the `cultureos` CLI, the `culture-node.service` unit
that runs the node, where its identity and state live, and the operator
steps that put it on the mesh. Plan task t13 (claims c7, h5).

## What is in the layer

| Path under `os/meta-cultureos/recipes-culture/` | What it is |
|-----|-----|
| `culture/python3-culture_14.13.1.bb` | `culture` from its pinned PyPI sdist; its header records the packaging route |
| `culture/python3-cultureos_0.10.1.bb` | this repo's CLI from its pinned PyPI sdist |
| `python3-culture-deps/*.bb` | 25 recipes for culture's dependencies that no layer in the stack provides |
| `culture-node/culture-node_1.0.bb` | the node: `culture` system user, unit, start script |
| `culture-node/files/culture-node.service` | the systemd unit |
| `culture-node/files/culture-node-start` | the `ExecStart` wrapper (POSIX sh) |
| `culture-node/files/node.env.example` | commented settings, installed to `/usr/share/culture-node/` |

The image integration task (t19) adds `culture-node` to `CULTUREOS_PACKAGES`;
it pulls in `python3-culture` and `python3-cultureos` through `RDEPENDS`.
This task does not touch `cultureos-image.bb`.

## Packaging route

Decision: **per-package recipes from pinned PyPI sdists; native
dependencies come from the oe-core and meta-python recipes at the pinned
layer commits.** No venv, no wheel bundle, no pip on the target.

### Audit

`culture==14.13.1` plus `cultureos==0.10.1`, resolved with
`uv pip compile --python-platform aarch64-unknown-linux-gnu`, is 77
distributions. The target Python is oe-core's `python3` 3.14.9 (recipe
`python3_3.14.9.bb`); culture requires Python 3.12 or newer.

Fifteen of them carry native code (platform-tagged wheels on PyPI):

| Distribution | Native code | Recipe in the stack |
|-----|-----|-----|
| aiohttp, frozenlist, multidict, propcache, yarl, wrapt | C extensions | meta-python |
| markupsafe, pyyaml, cffi | C extensions | oe-core |
| grpcio | C++ (bundled core) | meta-python |
| protobuf | upb C extension | meta-python |
| cryptography, rpds-py | Rust (PyO3) | oe-core |
| pydantic-core | Rust (PyO3) | meta-python |
| argon2-cffi-bindings | C, vendored libargon2 | **none**: new recipe here (scikit-build-core + CMake, both in meta-python/oe-core) |

argon2-cffi-bindings is needed by `argon2-cffi`, which irc-lens imports
for guest passwords. It is small (one cffi module over the vendored
libargon2), so it does not block packaging. Its recipe sets
`ARGON2_CFFI_USE_SSE2=0`: upstream's CMake otherwise passes the x86 flag
`-msse2` to the aarch64 cross compiler.

The other distributions are pure Python. 26 of the 77 have no recipe
anywhere in the stack (culture and cultureos included); all of those except
argon2-cffi-bindings build with hatchling or setuptools, which oe-core
provides (plus `hatch-vcs`, `hatch-fancy-pypi-readme`, `setuptools-scm` and
meta-python's `uv-dynamic-versioning` for the few that need them).

### Why not a venv or wheel bundle

A wheel bundle is possible: all 15 native distributions publish cp314 or
abi3 manylinux aarch64 wheels. It was rejected because downloading inside
`do_compile` breaks bitbake's no-network rule, and pre-fetched manylinux
wheels would put 15 foreign-built native extensions into the image outside
the cross toolchain, QA checks, CVE and license tracking. Per-package
recipes give each distribution its own license and sha256 pin.

### Version set

Where oe-core or meta-python has a recipe, its version is used (for
example anyio 4.15.1, pydantic 2.13.5, starlette 1.6.0, uvicorn 0.49.0,
grpcio 1.84.1, multidict 6.7.1). Resolving culture with those versions as
constraints succeeds, with two exceptions:

- **googleapis-common-protos**: meta-python ships 1.63.2, which requires
  `protobuf<6`; the stack has protobuf 6.33.6 and
  opentelemetry-exporter-otlp-proto-grpc needs the newer one. This layer
  carries 1.76.0, which wins over meta-python by layer priority (20).
- **importlib-metadata**: opentelemetry-api 1.41.1 declares `<8.8`;
  meta-python ships 9.1.0. Nothing checks `Requires-Dist` at runtime, and
  the exact set (all layer versions, importlib-metadata 9.1.0) was
  smoke-tested on CPython 3.14.9: `culture --version`,
  `cultureos --version`, the OpenTelemetry SDK, OTLP gRPC exporter and
  aiohttp-server instrumentation imports, entry-point lookup through
  `opentelemetry.util._importlib_metadata`, `irc_lens.guest_store` and
  `mcp`. The image keeps meta-python's 9.1.0.

The pins live in the recipe file names (`PV`) and `SRC_URI[sha256sum]`. To
move culture: re-run the audit for the new version, update or add recipes,
and rebuild `culture-node`.

## The node service

`culture-node.service` (system unit, enabled by default):

| Setting | Value | Why |
|-----|-----|-----|
| `Wants=` / `After=` | `network-online.target` (and after `tailscaled.service`) | links to peers need the network; ordering on tailscaled is harmless if it is absent |
| `User=` / `Group=` | `culture` (system user, home `/var/lib/culture`, no login shell) | the node does not run as root |
| `StateDirectory=` | `culture` | systemd creates `/var/lib/culture` (0750, owned by `culture`) at start |
| `Environment=` | `HOME=/var/lib/culture` | culture keeps everything under `$HOME/.culture`, so all state lands in `/var/lib/culture/.culture` without patching culture |
| `EnvironmentFile=` | `-/var/lib/culture/node.env` | optional operator settings |
| `ExecStart=` | `/usr/libexec/culture-node/culture-node-start` | runs `culture server start --foreground` |
| `Restart=` | `on-failure`, `RestartSec=5` | |
| `RestartPreventExitStatus=` | `78` | culture's exit contract: 78 is a permanent config error, so the unit parks instead of crash-looping (as in culture's own generated units) |
| hardening | `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp` | the state directory stays writable |

Nothing is installed into `/var` at build time. OSTree does not carry
build-time `/var` content to a deployed system, and `/var` is kept across
OSTree updates and rollbacks, so the node's identity survives both.

What lives in `/var/lib/culture/.culture/`: `data/` (server history and
rooms), `mesh.yaml` (peers, written by the operator), `server.yaml` (if the
operator adds one), `pids/`, `logs/`, `run/` (agent sockets), and the
default-server file.

### Start script settings

All optional, in `/var/lib/culture/node.env` (see
`/usr/share/culture-node/node.env.example`):

| Variable | Default | Passed as |
|-----|-----|-----|
| `CULTURE_NODE_NAME` | `uname -n` | `--name` (validated: `A-Z a-z 0-9 . _ -`, not starting with `.`; otherwise exit 78) |
| `CULTURE_NODE_HOST` | the board's tailnet IPv4 (`tailscale ip -4`), else `127.0.0.1` | `--host`; never all interfaces (risk r13). The webhook port always binds `127.0.0.1` (agentirc) |
| `CULTURE_NODE_PORT` | `6667` | `--port` |
| `CULTURE_NODE_WEBHOOK_PORT` | `7680` | `--webhook-port` |
| `CULTURE_NODE_MESH_CONFIG` | `/var/lib/culture/.culture/mesh.yaml` | `--mesh-config`, only if the file exists |
| `CULTURE_NODE_EXTRA_ARGS` | empty | appended, word-split |

`--data-dir` is always `/var/lib/culture/.culture/data`. The script also
removes a stale `pids/server-<name>.pid` before starting: systemd already
guarantees one instance, and after a reboot a stale pid could name an
unrelated live process and make culture refuse to start.

Without a `mesh.yaml` the node starts as an unlinked server: up and
reachable, but not part of a mesh. Exposure of the listen ports beyond the
tailnet is the security task's (t12) firewall decision.

## Operator steps: putting the node on the mesh

The recipe ships no credentials, link passwords, node names or peer lists.
Enrollment is an operator step on the board (as root) and on the peer:

1. Pick the node name and write `/var/lib/culture/node.env`:

   ```bash
   install -m 0640 -o root -g culture /usr/share/culture-node/node.env.example /var/lib/culture/node.env
   # edit: CULTURE_NODE_NAME=<unique-name>
   ```

2. Write the peer list to `/var/lib/culture/.culture/mesh.yaml` (owned by
   `culture`), in culture's `mesh.yaml` format: `server.name`,
   `server.links[]` with `name`, `host` (the peer's tailnet name), `port`,
   `trust`.

3. Add the reverse link on the peer (for example the Spark's mesh server)
   with the same shared password, using the peer's normal culture setup
   (`culture mesh setup`).

4. Give the board its copy of the link password (see the gap below), then
   `systemctl restart culture-node`.

Run culture commands as the node's user so they see the same state:
`runuser -u culture -- env -u XDG_RUNTIME_DIR HOME=/var/lib/culture culture <args>`.

### Known gap: link passwords on a headless board

culture reads link passwords for `--mesh-config` from the OS credential
store, which on Linux is `secret-tool` (libsecret talking to a Secret
Service such as gnome-keyring over a D-Bus session bus). A system service
on CultureOS has neither, so links from `mesh.yaml` are skipped with a
"No credential found for peer" warning; the server still starts.

Options, none of which this task picks for the operator:

- `--link <name>:<host>:<port>:<password>` through
  `CULTURE_NODE_EXTRA_ARGS` in a root-only `node.env` (mode 0600). This is
  culture's documented flag and works today, but the password is then in
  the process's argv, readable by local users through `/proc`.
- Ship libsecret plus a Secret Service provider and a session bus for the
  `culture` user. Heavy for an appliance.
- An upstream culture change: a credential backend that reads a root-owned
  file or a systemd credential (`LoadCredential=`). This is the clean fix
  and belongs in the culture repo, not in a CultureOS patch.

## Verification

### Offline tests

`tests/os/test_culture_node.py`: pinned file names and sha256 for every
recipe, license checksums, no pip or index URLs anywhere, the `RDEPENDS`
closure (every dependency is a recipe here, an oe-core/meta-python recipe
from the audit, or the Python stdlib), the route recorded in the recipe
header and here, the unit settings above, no secrets in the recipe files,
and the start script's behaviour against a stub `culture` (argv, mesh
config only when present, stale pid removal, name validation, shellcheck).

### Build

Built with `os/scripts/bb.sh` as `docs/os/building.md` describes.

Results, 2026-11-01 (shared build dir, warm caches):

| Run | Result |
|-----|-----|
| `bb.sh "$PWD" -k python3-culture python3-cultureos` | failed in `python3-argon2-cffi-bindings` `do_compile` (`-msse2` passed to the aarch64 compiler); fixed with `ARGON2_CFFI_USE_SSE2=0` |
| `bb.sh "$PWD" -k python3-culture python3-cultureos culture-node` | exit 0, 3,893 tasks, all succeeded, no QA warnings from these recipes |
| `cultureos-image` plus a throwaway kas file with `IMAGE_INSTALL:append = " culture-node"` (not committed) | first exit 0, but `mcp` was missing from the image: the dependency is only named through extras (`agentfront[mcp]`, `pyjwt[crypto]`) and the recipe generator had dropped them. With them added, two more recipe fixes: `python3-wheel-native` for httpx-sse, and a `PV` version pin for mcp (its git-tag version plugin cannot run on an sdist). Final run: exit 0, 12,083 tasks, all succeeded |

Checks on the final image (`cultureos-image-ventuno-q.rootfs.manifest` and
the OSTree rootfs tarball):

- The manifest has `culture-node`, and every one of the 77 distributions of
  the audit is installed at the audited version (`python3-culture`
  14.13.1, `python3-cultureos` 0.10.1, `python3-mcp` 1.30.0,
  `python3-googleapis-common-protos` 1.76.0, `python3-importlib-metadata`
  9.1.0, ...).
- The rootfs has `/usr/lib/systemd/system/culture-node.service`, the enable
  link `/usr/etc/systemd/system/multi-user.target.wants/culture-node.service`,
  `/usr/libexec/culture-node/culture-node-start`, the `culture` user
  (`/usr/etc/passwd`: home `/var/lib/culture`, shell `/sbin/nologin`), the
  `culture` and `cultureos` commands in `/usr/bin`, and an aarch64
  `_argon2_cffi_bindings/_ffi.abi3.so`.
- The Spark is aarch64, so the image's own `python3.14` ran from the
  extracted rootfs through its dynamic loader: culture, cultureos, the
  OpenTelemetry SDK and exporter, irc-lens, mcp, argon2 (hash and verify),
  grpc, protobuf, pydantic-core, rpds, cryptography and libyaml-backed
  PyYAML all import and work, and `culture-node-start` with
  `CULTURE_BIN` pointed at that interpreter started the server, which
  answered an IRC client on a loopback port as server `t13probe`. This is
  the image's userland on the Spark's kernel, not the board.

`rm_work` and other worktrees' runs prune this layer's packages from the
shared deploy dir (see `building.md`); rebuild to inspect them again.

### On the board (acceptance 3, hardware)

NOT VERIFIED: it needs a CultureOS image booted from NVMe (t19 onward).
Procedure, once an image with `culture-node` boots:

1. `systemctl is-enabled culture-node` prints `enabled`;
   `systemctl is-active culture-node` prints `active`.
2. `systemctl show -p After culture-node` includes
   `network-online.target`; `ls -ld /var/lib/culture` shows owner
   `culture`.
3. `journalctl -u culture-node -b` shows
   `Server '<name>' starting in foreground`.
4. After the operator steps above, from a peer:
   `culture server status` / the peer's mesh view lists the board's
   server name as linked.
5. `systemctl reboot`; after boot repeat steps 1, 3 and 4 without any
   manual action, and check that `/var/lib/culture/.culture/data` still
   holds the history written before the reboot.
6. Optional: `systemctl kill -s KILL culture-node`; the unit is `active`
   again within about 5 s (`Restart=on-failure`).
