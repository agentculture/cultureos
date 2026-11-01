"""Markdown catalog for ``cultureos explain <path>``.

Each entry is verbatim markdown. Keys are command-path tuples. The empty tuple
and ``("cultureos",)`` both resolve to the root entry.

Keep bodies self-contained: an agent reading one entry should get enough
context without chaining reads.
"""

from __future__ import annotations

_ROOT = """\
# cultureos

A clonable template for AgentCulture mesh agents. It carries an agent-first CLI
(cited from the teken `python-cli` reference), a mesh identity (`culture.yaml` +
`CLAUDE.md`), the canonical guildmaster skill kit under `.claude/skills/`, and a
buildable/deployable package baseline. Clone it, rename the package, edit
`culture.yaml`, and you have a new agent.

## Verbs

- `cultureos whoami` — identity probe from `culture.yaml`.
- `cultureos learn` — structured self-teaching prompt.
- `cultureos explain <path>` — markdown docs for any noun/verb.
- `cultureos overview` — descriptive snapshot of the agent.
- `cultureos doctor` — check the agent-identity invariants.
- `cultureos cli overview` — describe the CLI surface.

## Exit-code policy

- `0` success
- `1` user-input error
- `2` environment / setup error
- `3+` reserved

## See also

- `cultureos explain whoami`
- `cultureos explain doctor`
"""

_WHOAMI = """\
# cultureos whoami

Reports the agent's identity from `culture.yaml`: nick (`suffix`), backend,
served model, and the package version. Read-only.

## Usage

    cultureos whoami
    cultureos whoami --json
"""

_LEARN = """\
# cultureos learn

Prints a structured self-teaching prompt covering purpose, command map,
exit-code policy, `--json` support, and the `explain` pointer.

## Usage

    cultureos learn
    cultureos learn --json
"""

_EXPLAIN = """\
# cultureos explain <path>

Prints markdown documentation for any noun/verb path. Unlike `--help` (terse,
positional), `explain` is global and addressable by path.

## Usage

    cultureos explain cultureos
    cultureos explain whoami
    cultureos explain --json <path>
"""

_OVERVIEW = """\
# cultureos overview

Read-only descriptive snapshot of the agent: identity (from `culture.yaml`), the
verb surface, and the sibling-pattern artifacts the template carries. Accepts an
ignored `target` so a stray path never hard-fails.

## Usage

    cultureos overview
    cultureos overview --json
"""

_DOCTOR = """\
# cultureos doctor

Checks the agent-identity invariants `steward doctor` verifies:
prompt-file-present and backend-consistency (`claude` → `CLAUDE.md`), plus a
skills-present check. Exits 1 when unhealthy.

prompt-file-present requires the *resident* prompt the declared backend
actually reads. Other harness prompt files recognized under the same backend
name (`AGENTS.override.md`, `.pi/SYSTEM.md`, `QWEN.md`) belong to
interactively available harnesses the mesh daemon never loads; they are
reported by the informational harness-prompts check and never substituted.

## Usage

    cultureos doctor
    cultureos doctor --json
"""

_CLI = """\
# cultureos cli

Noun group for CLI-surface introspection. `cli overview` describes the CLI
itself (distinct from the global `overview`, which describes the agent).

## Usage

    cultureos cli overview
    cultureos cli overview --json
"""


_OS = """\
# cultureos os status

Report the OSTree deployment, version and last update outcome.

Sources: `ostree admin status` (override with `CULTUREOS_OSTREE_STATUS_CMD`;
JSON or classic text output is accepted) and the update agent's state file
`/var/lib/cultureos/update-state.json` (override with `CULTUREOS_UPDATE_STATE`;
schema in `docs/os/update-state.md`). A missing state file means outcome `none`.

Outcome is one of `applied`, `rolled-back`, `failed`, `none`.

`version` is the booted deployment's `Version` metadata; it falls back to the
state file's `deployed_version` only when `deployed_commit` is the booted
commit. Each deployment carries `booted`, `pending`, `staged` and `rollback`
flags; a deployment queued with `ostree admin deploy --stage` is `staged` (and
`pending`).

Exit codes: 0 healthy (`applied` / `none`); 1 degraded (`rolled-back` /
`failed`; the report is still written to stdout); 2 not an OSTree system,
no booted deployment, or an unreadable/invalid status source or state file.

## Usage

    cultureos os status
    cultureos os status --json
"""


ENTRIES: dict[tuple[str, ...], str] = {
    (): _ROOT,
    ("cultureos",): _ROOT,
    ("whoami",): _WHOAMI,
    ("learn",): _LEARN,
    ("explain",): _EXPLAIN,
    ("overview",): _OVERVIEW,
    ("doctor",): _DOCTOR,
    ("cli",): _CLI,
    ("cli", "overview"): _CLI,
    ("os",): _OS,
    ("os", "status"): _OS,
}
