# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

`cultureos` hosts the **cultureos** agent: *CultureOS — an operating system
built on Culture, the AgentCulture agent mesh.*

The repo was scaffolded from
[`culture-agent-template`](https://github.com/agentculture/culture-agent-template)
(commit `d1c44cd`), so today it carries only the template's sibling-pattern
baseline: an agent-first CLI, a mesh identity, the canonical skill kit, four
harness prompt files, and a build/deploy pipeline. **No CultureOS-specific
domain code exists yet** — the CLI verbs below are the template's
self-describing verbs. When you add CultureOS functionality, update this file
(and the other three harness files) to describe what is actually on disk.

Siblings within the Organic Development framework:
[`guildmaster`](https://github.com/agentculture/guildmaster) (the **skills
supplier**), [`steward`](https://github.com/agentculture/steward)
(**alignment** — `steward doctor`, the sibling-pattern baseline), and
[`teken`](https://github.com/agentculture/teken) (the **afi-cli** "Agent First
Interface" scaffolder this CLI is cited from).

## Commands

```bash
uv sync                                           # install (runtime has zero deps; dev group adds pytest, linters, teken)
uv run pytest -n auto                             # full suite (what culture.yaml's gate.test runs)
uv run pytest tests/test_cli.py::test_whoami_json # a single test
uv run pytest -n auto --cov=cultureos             # with coverage (fail_under = 60)
uv run cultureos <verb> [--json]                  # run the CLI from the checkout

# Lint — the same set CI's `lint` job runs
uv run black --check cultureos tests
uv run isort --check-only cultureos tests
uv run flake8 cultureos tests
uv run bandit -c pyproject.toml -r cultureos
markdownlint-cli2 "**/*.md" "#node_modules" "#.local" "#.claude/skills" "#.teken"
python3 scripts/scan-secrets.py                   # committed-secret / non-localhost-endpoint gate
uv run teken cli doctor . --strict                # agent-first rubric gate

# Harness config check (all four harnesses; `config` stage is offline)
uv run python scripts/harness-smoke.py --stage config
```

Line length is 100 for black, isort, and flake8. Python ≥ 3.12.

## CLI architecture

The CLI is cited (cite-don't-import) from teken's `python-cli` reference, so
the runtime package has **no third-party dependencies**; `teken` is a dev
dependency only.

- `cultureos/cli/__init__.py` builds the argparse tree. Each verb lives in its
  own module under `cultureos/cli/_commands/` and exposes `register()`; new
  noun groups follow the same pattern and get wired into `_build_parser()`.
- **Error contract:** handlers raise `CliError` (`cli/_errors.py`); `main()`
  catches it and routes through `cli/_output.py`. Unknown exceptions are
  wrapped so no traceback leaks. Argparse errors also go through the
  structured path via `_CliArgumentParser.error()`, and JSON vs. text error
  rendering is decided by pre-scanning raw argv for `--json`.
- **Output contract:** every command supports `--json`; results go to stdout,
  errors/diagnostics to stderr (never mixed). Exit codes: `0` success, `1` user
  error, `2` environment error, `3+` reserved. `teken cli doctor --strict`
  enforces this rubric in CI.
- `cultureos/explain/catalog.py` holds the markdown served by
  `explain <path>`. Add an entry for each new verb so `explain` covers it;
  `test_every_catalog_path_resolves` checks that every catalog path
  resolves.

Verbs: `whoami` (identity from `culture.yaml`), `learn` (self-teaching
prompt), `explain <path>`, `overview`, `doctor` (agent-identity invariants),
`cli overview`.

Some CLI strings still describe the package as "a clonable template"
(`cli/__init__.py` description, `learn.py`, `explain/catalog.py`,
`whoami.py`); those are inherited from the scaffold and should be updated when
real CultureOS verbs land.

## Identity and the four harnesses

`culture.yaml` declares the mesh identity:

```yaml
agents:
- suffix: cultureos
  backend: claude
gate:
  setup: [[uv, sync]]
  test: [[uv, run, pytest, -n, auto]]
```

The repo root carries one prompt file per harness, each read by **exactly
one** harness. There is deliberately **no `AGENTS.md`** (a shared base was
considered and rejected; `scripts/harness-smoke.py` fails if one appears,
because it would shadow the Pi/colleague cascades):

| Harness | File(s) |
|---------|---------|
| Claude Code | `CLAUDE.md` (this file) |
| Pi / associate | `AGENTS.override.md` (context; replaces `AGENTS.md`/`CLAUDE.md` for this dir so Pi does **not** inherit this file) + `.pi/SYSTEM.md` (replaces Pi's system prompt with the non-coding read/find/summarize `associate` identity) |
| colleague | `AGENTS.colleague.md` (layer 2 of colleague's `AGENTS.md` → `AGENTS.colleague.md` → `AGENTS.colleague.<model>.md` cascade; only this layer ships) |
| Qwen Code | `QWEN.md` |

Skills reach every harness from one tree: `.qwen/skills`, `.colleague/skills`
and `.pi/skills` are relative symlinks onto `.claude/skills`.

There are **two separate selections** over one clone — don't conflate them:

1. **Interactive harness** — whichever binary you run (`claude`, `pi`,
   `colleague`, `qwen`). All four are live at once. Forcing one for automation
   is invocation-level only (flags to that process, per
   `docs/harness-invocations.yaml` / `docs/automation-contract.md`) — never
   rewrite `culture.yaml` or any tracked file to do it.
2. **Mesh resident** — the single `backend` in `culture.yaml`, which the
   Culture daemon starts and `steward doctor` / `cultureos doctor` check.
   `backend: claude` makes **this file** the resident prompt, satisfying
   **prompt-file-present** and **backend-consistency** (`claude` ↔
   `CLAUDE.md`). `guild harness use <name>` changes only this.

Full writeup: `docs/harness-selection.md`. When you change conventions here,
update `AGENTS.override.md`, `AGENTS.colleague.md`, and `QWEN.md` too — CI's
`harness-smoke` job checks that all four configs resolve, but not that their
prose agrees.

## Skills

`.claude/skills/` vendors the guildmaster skill kit **cite-don't-import**.
Provenance, per-skill notes, and the re-sync procedure live in
`docs/skill-sources.md`. Never reformat or edit vendored scripts — fix
upstream and re-vendor. Every vendored `SKILL.md` carries `type: command`,
which is load-bearing (`core.skill_loader` silently skips a skill without it).

Origins: most skills come from guildmaster; `think`, `spec-to-plan`,
`assign-to-workforce`, `scope`, `challenge`, `deviate`, `validate-delivery`,
`summarize-delivery` originate in `devague` (re-broadcast via guildmaster);
`ask-colleague` is vendored directly from `colleague`, and `recall` /
`remember` directly from `eidetic-cli` (guildmaster's copies were stale).

Tooling prerequisites: **`devex`** on PATH (`cicd` delegates to `devex pr`),
**`agtag`** on PATH (`communicate` wraps `agtag issue`), **`eidetic`** on PATH
(`recall` / `remember`), and optionally
**`colleague`** (only when `ask-colleague` is invoked). Per-machine skill
config goes in `.claude/skills.local.yaml` (git-ignored; copy from the
`.example`).

## Conventions

- **Every PR bumps the version** — even docs/config/CI. Use the
  `version-bump` skill (updates `pyproject.toml` + `CHANGELOG.md`); CI's
  `version-check` job blocks merge otherwise.
- **PRs** go through the `cicd` skill (`devex pr` + SonarCloud gating). Online
  posts sign as `- cultureos (Claude)`; the `cicd` / `communicate` scripts
  resolve the nick from `culture.yaml` and append it, so don't sign bodies by
  hand.
- **Reach for `ask-colleague` reflexively.** Before presenting or opening a PR
  on a non-trivial committed diff, run `review`; for a fresh read of an
  unfamiliar area, run `explore`. Both are read-only (throwaway worktree), so
  always safe; `write --apply` / `write --pr` need the user's go-ahead. Treat
  the output as a second opinion to verify, not authority.
- **Deploy:** push to `main` touching `pyproject.toml` or `cultureos/**`
  publishes to PyPI via Trusted Publishing (`.github/workflows/publish.yml`);
  same-repo PRs do a TestPyPI dry-run. Requires the `pypi` / `testpypi`
  GitHub environments and a PyPI Trusted Publisher.
- Keep this file grounded in what exists on disk; mark anything ahead of
  reality `(planned)` or move it under a `## Roadmap` heading.

### Worktrees

Worktrees you create by hand live in
`../.worktrees.cultureos/<name>/` — never a shared `../worktrees/`:

```bash
git worktree add ../.worktrees.cultureos/<name> -b <scoped-prefix>/<name>
```

Use a work-scoped branch prefix (`retire/t2`, not `agent/t2`) to avoid
collisions with leftover fan-out branches. The vendored `assign-to-workforce`
skill's example uses `../worktrees/` and `agent/<task-id>` — override both
when following it (the skill itself is not edited). `ask-colleague`'s own
throwaway worktrees under `${TMPDIR:-/tmp}` are exempt; they're deleted on
exit. Clean up with `git worktree remove <path>` (`prune` only clears
metadata); never `rm -rf` a worktree you didn't create.

### Memory — recall before, remember after

The `recall` / `remember` skills wrap the `eidetic` store (vendored directly
from eidetic-cli, not guildmaster — see `docs/skill-sources.md`). Both default
to `--scope cultureos --visibility public`, so a plain `/remember` lands
**in-repo** at `.eidetic/memory/` (committed, shared with the team and the
`claude`/`colleague` backends). Pass `--visibility private` to keep a record
in `$HOME/.eidetic/memory`; a private recall sees your private notes plus the
public pool.

- `/recall` before non-trivial work in an area — prior decisions and gotchas.
- `/remember` non-obvious decisions, constraints, and fixes with their *why*,
  as they happen. Don't store what the repo already records.
