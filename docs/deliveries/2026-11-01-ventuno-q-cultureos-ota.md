# Delivery Summary — ventuno-q cultureos ota

plan: `ventuno-q-cultureos-ota` · run: `partial` · date: `2026-11-01`
baseline: `devague summary skeleton`

## Intent

> The Arduino VENTUNO Q runs CultureOS — our own pinned, reproducible Yocto image (meta-cultureos) built from this repo and installed on NVMe — reachable over Tailscale; OSTree-based OTA follows once the OS lives on NVMe, so the board ends up needing nothing but power to stay current.

After: The board boots a CultureOS Yocto image from NVMe, comes up on Ethernet/Wi-Fi and Tailscale with no hands-on steps, runs a supervised Culture node, and later receives OSTree updates with automatic rollback

This run executed waves 0–4 of the plan: everything that can be built and
tested on the DGX Spark. The hardware waves (5–7: `t20`–`t22`) wait for the
NVMe, per decision q7 ("we prepare now and flash/reflash on the NVMe when it
arrives"). Nothing was flashed or installed on the board.

## Planned Work

Quoted verbatim from the `devague summary` skeleton:

- `t1` — M0 reference build: unmodified upstream ventuno-q image built on the aarch64 DGX Spark
- `t2` — Recovery prep: arduino-flasher-cli on the Spark + 05c6 udev rule + documented EDL procedure (no flashing)
- `t3` — Record the factory baseline of the board (before state) in docs/os/board-baseline.md
- `t4` — Docs + harness prompts describe the OS workstream
- `t5` — meta-cultureos layer skeleton + pinned kas manifest stacking ventuno-q + qcom-distro-sota
- `t6` — Offline-reproducible build: local `DL_DIR`/sstate mirror, second build with `BB_NO_NETWORK`=1
- `t7` — Release bundle carries Qualcomm LICENSE.qcom-2, firmware binary-only
- `t8` — Recipe: arduino-router (Go, from github.com/arduino/arduino-router) + systemd unit owning /dev/ttyACM0
- `t9` — Recipe: Tailscale with tailscaled enabled and state under /var/lib/tailscale
- `t10` — First-boot provisioning: Wi-Fi + SSH authorized key from an operator-supplied input, stored only under /var
- `t11` — Local no-network shell: USB gadget (adbd or CDC-ACM getty) + serial getty on ttyMSM0
- `t12` — Device hardening: key-only sshd and OSTree remote with signature verification
- `t13` — Recipe: Culture mesh node (culture + cultureos CLI) under systemd, identity under /var
- `t14` — cultureos CLI: 'os status' verb reporting OSTree deployment, version and last update outcome
- `t15` — Rollback mechanism: one-shot trial boot + early `qcom_wdt` + panic reboot + health-gated promotion
- `t16` — Board update agent: systemd timer pull + idempotent push entrypoint, writing update-state.json
- `t17` — OSTree release repo + signing + publish script on the Spark, served over Tailscale
- `t18` — culture-rules release rule/workflow: build -> bundle -> sign+publish -> trigger board
- `t19` — Image integration: wire all CultureOS packages into cultureos-image and build it
- `t20` — NVMe install + UEFI boot order NVMe-then-eMMC; eMMC untouched
- `t21` — eMMC Ubuntu rescue agent: repair NVMe OSTree default on fall-through, capped retries, alert over Tailscale
- `t22` — End-to-end hardware validation: power cycles, OTA, rollback (panic/hang/health), /var survival, NVMe-missing fall-through

## Actual Delivery

22 tasks: 19 delivered (software), 3 blocked (hardware, NVMe not installed).

| Plan task | Status | What actually landed |
|-----------|--------|----------------------|
| `t1` | delivered | `os/scripts/build-reference.sh`, `docs/os/reference-build.md`; upstream image built on the aarch64 Spark, exit 0, 17,096/17,096 tasks (PR #5). Doc errors found later and corrected (lapses l6, l7). |
| `t2` | delivered | `os/scripts/install-flasher.sh` (arduino-flasher-cli 0.5.4, sha256-pinned, verify-before-install), `docs/os/recovery.md`; 05c6 udev rule installed on the Spark by the operator (PR #5; `version` subcommand per d2) |
| `t3` | delivered | `os/scripts/capture-baseline.sh` (read-only), `docs/os/board-baseline.md` (PR #5) |
| `t4` | delivered | OS-workstream sections in `CLAUDE.md`, `AGENTS.override.md`, `AGENTS.colleague.md`, `QWEN.md`, `docs/os/README.md`; kept current through PR #7 |
| `t5` | delivered | `os/meta-cultureos/` layer, distro `cultureos` on qcom-distro-sota (no Uptane client, systemd-boot kept), `os/kas/cultureos.yml` + lock, `os/scripts/bb.sh` shared flock build (d1); first image with OSTree commit + ota-ext4 (PR #5) |
| `t6` | delivered | `os/kas/mirror.yml`, `offline.yml`, `os/scripts/refresh-mirror.sh`, `docs/os/reproducibility.md`; a clean build with `BB_NO_NETWORK=1` from the mirror succeeded, Qualcomm boot binaries included (PR #7) |
| `t7` | delivered | `os/scripts/bundle-release.sh`, `docs/os/release-bundle.md`; a real 1.3 GB bundle produced locally, nothing published (PR #7) |
| `t8` | delivered | arduino-router 0.11.0 recipe, static aarch64, udev `ttySTM0` rule (d5) (PR #7) |
| `t9` | delivered | tailscale bbappend on meta-networking 1.104.1, state in `/var/lib/tailscale`, no auth key (PR #7) |
| `t10` | delivered | `cultureos-provision`: TOML on ESP/USB creates `arduino` (key, password hash, `wheel` per d7), Wi-Fi keyfile, hostname, input shredded (PR #7; d6) |
| `t11` | delivered | `cultureos-local-access`: configfs CDC-ACM gadget (ttyGS0 router, ttyGS1 login) + UART getty, no adbd (d3, operator choice) (PR #7) |
| `t12` | delivered | `cultureos-security`: key-only sshd drop-in, signed OSTree remote, ostree ed25519 (d4) (PR #7) |
| `t13` | delivered | culture 14.13.1 + cultureos + 77 pinned Python sdists, `culture-node` service, state in `/var/lib/culture`, tailnet-only listener (PR #7) |
| `t14` | delivered | `cultureos os status [--json]`, `docs/os/update-state.md` (PR #5, hardened by the #5 review) |
| `t15` | delivered | `cultureos-trialboot`: one-shot stage, health/promote units, watchdog drop-in, `panic=5`, health checks shipped after the #7 review (PR #7) |
| `t16` | delivered | `cultureos-update-agent`: hourly timer, `cultureos-update now [--no-wait]`, polkit rule, timestamp-checked pulls (PR #7) |
| `t17` | delivered | `os/scripts/publish-ostree.sh` (signs via `--keys-file`, summary unsigned), Tailscale-bound user unit, `docs/os/release-repo.md`; release key not yet generated (operator step) (PR #7) |
| `t18` | delivered | `os/release/culture-rules/` actor + workflow + rule (rule ships disabled, not imported), `os/scripts/release-step.sh`, `docs/os/release-workflow.md` (PR #7) |
| `t19` | delivered | `cultureos-image` integrates all packages; root locked, root-login/empty-password features, adbd and libvirt/qemu removed (d9); `os/scripts/audit-image.sh`; real image `20261101140301` built and audited clean (PR #7) |
| `t20` | blocked | not started: needs the NVMe drive installed (q7, risk r8) |
| `t21` | blocked | not started: depends on `t20` |
| `t22` | blocked | not started: depends on `t18` and `t21`, and on hardware |

## Mid-work Decisions

- `d1` — t5 additionally provides a shared `DL_DIR`/`SSTATE_DIR` outside the repo and a flock-serialized build wrapper (os/scripts/bb.sh) so wave-2 recipe agents queue their bitbake runs through one build instead of N parallel build dirs — N parallel bitbake builds would each need a full build dir and thrash the Spark; user approved at gate 2 ('wrapper yes')
- `d2` — t2 acceptance criterion says 'verifies --version' but arduino-flasher-cli has no --version flag for its own version (--version selects an image to flash); the script uses the 'version' subcommand instead — criterion was worded from the flash doc's --version image selector; the tool's own version check is the 'version' subcommand
- `d3` — t11 local access drops adbd: the no-network shell is a USB CDC-ACM serial console plus the UART console on ttyMSM0, both requiring the provisioned non-root user's login password; no unauthenticated root path — meta-oe adbd has authorization disabled, so adbd = root shell for anyone at the USB port; conflicts with t12 hardening (risk r11). Operator chose 'Login consoles'.
- `d4` — t12 adds `ostree_`%.bbappend (PACKAGECONFIG ed25519-libsodium) in its own recipe dir, a file its brief does not name — target and native ostree have no signature engine (r10); sign-verify=true cannot work without it; verified refusal/acceptance with the image's own ostree
- `d5` — t8 arduino-router talks to the MCU via the stable udev symlink /dev/ttySTM0 (udev rule: tty with idVendor 1209 idProduct ca01, as the factory 99-stm-tty.rules) instead of the raw /dev/ttyACM0 named in t8's criterion and c11/c27 — factory board (read-only ssh): 10-monza generator drop-in runs --serial-port /dev/ttySTM0; 99-stm-tty.rules symlinks the STM32 USB-ACM device 1209:ca01; ttyACM0 is only correct when the MCU is the first ACM device
- `d6` — t10 criterion 2 'image rootfs contains no psk= strings' is read as: no tskey- anywhere (binaries included); no uncommented psk= in any non-ELF file; ELF binaries exempt for psk= (listed by the test) — upstream `wpa_supplicant`/`wpa_cli`/`wpa_passphrase`/hostapd binaries contain psk=%s format strings and /etc/hostapd.conf has commented #`wpa_psk`= examples, so the literal check can never pass; the reading still catches any baked PSK in a config/keyfile
- `d7` — t10 adds the provisioned arduino user to group wheel (polkit admin via run0, password-prompted), beyond criterion 4's 'non-root login user' — image has no sudo; with root locked, wheel+run0 is the only admin path (e.g. run0 tailscale up, editing culture node.env); dropping it is one line
- `d8` — t19 audit-image.sh narrows d6's secrets reading: a Tailscale key is a key-shaped string (`tskey-<kind>-<id>-<secret>` or legacy `tskey-<hex>`), not any 'tskey-'; PEM private keys are flagged as full BEGIN/body/END blocks in non-ELF files — on the integrated image tailscaled contains the constant 'tskey-wrap' and sshd/gnutls/NetworkManager/mime databases embed bare PEM markers; gnutls embeds FIPS self-test EC keys. The narrowed checks still catch baked key files (they found libvirt's) and any real Tailscale key, binaries included.
- `d9` — t19 removes packagegroup-qcom-virtualization (libvirt + qemu) from cultureos-image — libvirt-libvirtd ships pre-generated private keys in /etc/pki/libvirt/private, identical on every board built from the image (audit-image.sh finding); CultureOS runs no VMs; removes ~30 packages
- The commit is signed with `ostree sign --keys-file` and **the OSTree summary is no longer signed**. In ostree 2026.5, `ostree summary --sign` takes the secret key only on argv, where any user on the shared Spark can read it. Replay and downgrade protection moved to the board, which pulls with `--timestamp-check` against the booted commit. c29 (signed commits, refusal of unsigned ones) still holds. No deviation record covers this, because the change stays within t17's contract. It came out of the `/code-review` of PR #7.
- Trial boots ship real health checks (sshd, tailscaled with a tailnet address, culture-node), and a trial with no checks installed fails. The plan placed the checks in t19; they landed in the trialboot recipe during the #7 review fixes. No record covers this; it is captured here.
- Two CI gates landed outside the plan (PR #6, operator request): a 1000-line limit on tracked source files (cited from colleague) and a gate that fails a PR with any unresolved SonarCloud issue (cited from culture-rules). Fixes to both were offered upstream: culture-rules#132 and colleague#502.

## Drift From Plan

| Plan item | Reason for divergence | Classification |
|-----------|-----------------------|----------------|
| `t5` (`d1`) | N parallel bitbake builds would each need a full build dir and thrash the Spark; user approved at gate 2 ('wrapper yes') | acceptable |
| `t2` (`d2`) | criterion was worded from the flash doc's --version image selector; the tool's own version check is the 'version' subcommand | acceptable |
| `t11` (`d3`) | meta-oe adbd has authorization disabled, so adbd = root shell for anyone at the USB port; conflicts with t12 hardening (risk r11). Operator chose 'Login consoles'. | acceptable |
| `t12` (`d4`) | target and native ostree have no signature engine (r10); sign-verify=true cannot work without it; verified refusal/acceptance with the image's own ostree | acceptable |
| `t8` (`d5`) | factory board (read-only ssh): 10-monza generator drop-in runs --serial-port /dev/ttySTM0; 99-stm-tty.rules symlinks the STM32 USB-ACM device 1209:ca01; ttyACM0 is only correct when the MCU is the first ACM device | acceptable |
| `t10` (`d6`) | upstream `wpa_supplicant`/`wpa_cli`/`wpa_passphrase`/hostapd binaries contain psk=%s format strings and /etc/hostapd.conf has commented #`wpa_psk`= examples, so the literal check can never pass; the reading still catches any baked PSK in a config/keyfile | acceptable |
| `t10` (`d7`) | image has no sudo; with root locked, wheel+run0 is the only admin path (e.g. run0 tailscale up, editing culture node.env); dropping it is one line | risky |
| `t19` (`d8`) | on the integrated image tailscaled contains the constant 'tskey-wrap' and sshd/gnutls/NetworkManager/mime databases embed bare PEM markers; gnutls embeds FIPS self-test EC keys. The narrowed checks still catch baked key files (they found libvirt's) and any real Tailscale key, binaries included. | acceptable |
| `t19` (`d9`) | libvirt-libvirtd ships pre-generated private keys in /etc/pki/libvirt/private, identical on every board built from the image (audit-image.sh finding); CultureOS runs no VMs; removes ~30 packages | acceptable |
| `t17` | the summary is no longer signed: `ostree summary --sign` can only take the key on argv. Downgrade protection moved to the board's `--timestamp-check`. No record covers this. | acceptable |
| `t15` / `t19` | the health checks t19 was meant to install landed in t15's recipe during the #7 review | acceptable |
| `t20`–`t22` | not started: the NVMe is not installed (q7) | needs-follow-up |

## Evidence

- tests: the offline behavioral suite `tests/os` + `tests/test_os_status.py` at `aa5d23b`, 2026-11-01T17:43 — 382 passed, 1 skipped (the rootfs scan, which needs an image). The real-ostree tests were enabled through the image's own ostree 2026.5 (`CULTUREOS_TEST_OSTREE`).
- tests: `tests/os/test_provision_rootfs.py` on the extracted integrated image `cultureos-image-ventuno-q.rootfs-20261101140301` — pass
- tests: full suite `uv run pytest -n auto` on `main` at `aa5d23b` — 516 passed, 7 skipped
- evidence records `e1`–`e12` and behavioral deltas `b1`–`b7`: filed via `/validate-delivery`, all `proposed` and pending the operator's adjudication
- image: `cultureos-image` build exit 0 (11,656 tasks); `os/scripts/audit-image.sh` on `…rootfs-20261101140301.ostree.tar.zst` — "audit: OK (no data outside /var, secrets scan clean, root locked)"
- lint/CI: black, isort, flake8, bandit, markdownlint, scan-secrets, `teken cli doctor --strict`, harness-smoke, steward portability, version-check, SonarCloud quality gate, and the new SonarCloud no-unresolved-issues gate — all green on PRs #5, #6, #7
- commits: `597c291..aa5d23b` (squash merges `2f2d2ff` #5, `87d9c80` #6, `aa5d23b` #7)
- PRs / issues: #5, #6, #7; issues #3, #4; upstream culture-rules#132, colleague#502

## Delivery Claims

Evidence records `e1`–`e12` are `proposed`, not yet adjudicated, and almost all of them run against fakes or stubs. So no claim below is `high`. The board itself has not run CultureOS.

| Claim | Confidence | Evidence |
|-------|------------|----------|
| `c1` (pinned, reproducible image) — every layer is pinned by SHA with a lock file, and an offline rebuild from the mirror succeeds | medium | test `tests/os/test_meta_cultureos.py::test_kas_manifest_pins_every_repo_by_sha` (`e1`, proposed) · file `docs/os/reproducibility.md` · PR #7 |
| `c1` (installed on NVMe, reachable over Tailscale, needs only power) | unverified | t20–t22 blocked: not claimed done |
| `c29` — signed commits; unsigned or wrongly signed commits are refused | medium | test `tests/os/test_cultureos_security.py::test_unsigned_commit_is_refused` with the image's real ostree (`e2`, proposed); on-board refusal not run |
| `c29` — sshd key-only, no root login | medium | `tests/os/test_cultureos_security.py::test_dropin_wins_over_upstream_sshd_config` · audit of image `20261101140301` |
| `c11` — no recipe flashes MCU firmware | medium | `tests/os/test_arduino_router.py::test_no_stm32_firmware_installed_or_flashed` (`e3`, proposed) |
| `c27` — arduino-router packaged and owns the MCU tty (`/dev/ttySTM0`, d5) | low | `tests/os/test_arduino_router.py::test_only_arduino_router_recipe_touches_the_mcu_tty` (`e4`); the MCU link on the factory board has been down since its 06:53 factory update, so this is not observed end to end |
| `c26` — provisioning delivers Wi-Fi, the SSH key and the login user; no secrets in the image | medium | `tests/os/test_provision.py::test_valid_full_file` · `tests/os/test_provision_rootfs.py` on the real image (`e5`, proposed) |
| `c7` — supervised Culture node, state in `/var` | low | `tests/os/test_culture_node.py::test_unit_orders_after_network_online_and_restarts` (`e6`); approved lapse `l3` was on this claim; the node does not link to the mesh until r12 is decided |
| `c32` — `cultureos os status` reports version and outcome, exit codes 0/1/2 | high | `tests/test_os_status.py::test_outcomes` (`e7`) · pure CLI, faked inputs only for ostree and the state file, which is its tested contract |
| `c30` — the release bundle carries LICENSE.qcom-2, binary-only | medium | `tests/os/test_bundle_release.py::test_bundle_manifest_lists_license_and_no_source` (`e8`) · a real bundle built in t7 |
| `c36` — the culture-rules release workflow chain stops before the board on any failure | medium | `tests/os/test_publish_ostree.py::test_real_ostree_round_trip` (`e9`) · `tests/os/test_release_workflow.py::test_a_failed_step_stops_the_run_before_the_board_trigger` (culture-rules' in-memory engine); not imported, never run live |
| `c39` / `c25` — default changes only after a passing health check; failure rolls back | low | `tests/os/test_trialboot_helper.py::test_pass_promotes_after_health_check` (`e11`, `e12`) against fakes; LoaderEntryOneShot, the watchdog and panic reboot on the QCS UEFI are unverified (r5); approved lapse `l1` was on c25 |
| `c25` — one OTA over Tailscale, a broken one rolls back within 1 reboot | unverified | t22 blocked: not claimed done |
| `c5` — `/var` survives OTA and rollback | unverified | no test can exercise it before t22 |
| `c8` — atomic rootfs deployments with rollback via OSTree | unverified | OSTree is in the image (`e1` stack), but an atomic update has not happened on hardware; approved lapse `l2` was on c8 |
| `c12` — board joins the tailnet | unverified | tailscale is packaged and enabled (`tests/os/test_tailscale_recipe.py`), but CultureOS has not booted |
| `c13` — OS on NVMe, eMMC untouched | unverified | t20 blocked |
| `c28` — network-independent local access (login consoles) | low | `tests/os/test_local_access.py` and a real-rootfs check of the enabled units in t11; the gadget has not run on the board |

Lapse ledger evidence:

| Lapse | Code | What |
|-------|------|------|
| `l1` | `assumption-for-measurement` | h18 (on c25) prescribes 'greenboot/boot-count style check' for automatic rollback without verifying that any boot-counting mechanism exists for this stack — probe shows meta-qcom uses systemd-boot (`EFI_PROVIDER`, qcom-common.inc:67), not GRUB/U-Boot that meta-updater's rollback is usually wired to |
| `l2` | `provenance-missing` | c8 states OSTree is the only update framework in the Qualcomm layers and implies a working OTA path, but meta-updater's sota.conf.inc (which brings the update client and its server expectations) was never read — only the subagent's report and qcom-distro-sota.inc were |
| `l3` | `assumption-for-measurement` | c7 assumes culture can run on the image as 'uv tool install culture' without checking that a Yocto image can carry uv/PyPI wheels offline or that culture's deps build for aarch64 in Yocto |

Pending approval (not yet evidence): `l4`, `l5`, `l6`, `l7`, `l8`, `l9`.

## Remaining Work / Follow-up

- `t20` — write `os/scripts/install-nvme.sh` (t20 deliverable, not yet on disk), install CultureOS on the NVMe and set the UEFI order NVMe then eMMC. Next step: the operator installs the NVMe and gives the go-ahead (hardware).
- `t21` — the eMMC Ubuntu rescue agent. Next step: after `t20`. Resolve risk r7 (o13 wording against the rescue agent writing the Ubuntu rootfs) first.
- `t22` — end-to-end hardware validation with the procedures in `docs/os/*.md` ("Not verified on hardware" sections), filing `devague evidence` per obligation o1–o19. Next step: after `t21`.
- r12 — headless mesh link passwords for culture-node (keyring, env file, or an upstream culture secret backend). Operator decision. Blocks "appears on the mesh" (c7).
- r14 — system users added in a *later* release need `sysusers.d` entries (`docs/os/building.md`). Next step: before the first OTA that adds a user.
- Operator steps before the first release:
  - install an ed25519-capable ostree on the Spark;
  - run `os/scripts/publish-ostree.sh --print-keygen` and commit the `.pub`;
  - enable the repo's user unit;
  - import `os/release/culture-rules/` (dry run first).
- The factory board's STM32 has not enumerated since its 06:53 first-run update: no `1209:ca01` device, so arduino-router has nothing to talk to. Next step: re-run Arduino's MCU update (App Lab), or reflash the MCU. Operator. Outside this plan, but it blocks observing c27.
- Adjudicate the proposed records: evidence `e1`–`e12`, deltas `b1`–`b7`, lapses `l4`–`l9`.
- Upstream: culture-rules#132 and colleague#502, so the cited CI gates can be re-cited without local divergence.
