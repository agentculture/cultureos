"""``cultureos os status`` — OSTree deployment, version and last update outcome.

Two inputs, both injectable so tests never need ostree:

* the OSTree source: the command in ``CULTUREOS_OSTREE_STATUS_CMD`` (default
  ``ostree admin status``). Its stdout is parsed as JSON when it looks like
  JSON (``{"deployments": [...]}``), otherwise as the classic text format
  (``* osname checksum.serial`` plus indented ``Version:`` lines), because
  ``ostree admin status --json`` is not available on every ostree version.
* the update-agent state file: the path in ``CULTUREOS_UPDATE_STATE`` (default
  ``/var/lib/cultureos/update-state.json``); schema in ``docs/os/update-state.md``.

Exit codes: 0 healthy (outcome ``applied`` or ``none``), 1 degraded (outcome
``rolled-back`` or ``failed``; the report is still printed to stdout), 2 not an
OSTree system / unreadable source or state.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess  # nosec B404 - runs a fixed, operator-configured status command
from pathlib import Path
from typing import Any

from cultureos.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, CliError
from cultureos.cli._output import emit_result

DEFAULT_OSTREE_CMD = "ostree admin status"
DEFAULT_STATE_PATH = "/var/lib/cultureos/update-state.json"
OUTCOMES = ("applied", "rolled-back", "failed", "none")
DEGRADED_OUTCOMES = ("rolled-back", "failed")

_DEPLOY_RE = re.compile(r"^(?P<marker>[ *])\s*(?P<osname>\S+)\s+(?P<commit>[0-9a-f]{6,})(\.\d+)?")


def _not_ostree(detail: str) -> CliError:
    return CliError(
        code=EXIT_ENV_ERROR,
        message=f"not an OSTree system: cannot read deployment status ({detail})",
        remediation="run on an OSTree host, or set CULTUREOS_OSTREE_STATUS_CMD",
    )


def _run_ostree() -> str:
    # Every failure to obtain status is an environment error (exit 2): exit 1 is
    # reserved for "degraded", which a health gate may act on.
    raw = os.environ.get("CULTUREOS_OSTREE_STATUS_CMD", DEFAULT_OSTREE_CMD)
    try:
        cmd = shlex.split(raw)
    except ValueError as err:
        raise _not_ostree(f"cannot parse CULTUREOS_OSTREE_STATUS_CMD: {err}") from err
    if not cmd:
        raise _not_ostree("CULTUREOS_OSTREE_STATUS_CMD is empty")
    try:
        proc = subprocess.run(  # nosec B603 - no shell, argv from operator config
            cmd, capture_output=True, check=False, timeout=30
        )
    except (OSError, subprocess.SubprocessError) as err:
        raise _not_ostree(f"{cmd[0]}: {err}") from err
    if proc.returncode != 0:
        raise _not_ostree(f"{' '.join(cmd)} exited {proc.returncode}")
    try:
        return proc.stdout.decode("utf-8")
    except UnicodeDecodeError as err:
        raise _not_ostree(f"output is not UTF-8: {err}") from err


def _parse_json(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except ValueError as err:
        raise CliError(EXIT_ENV_ERROR, f"ostree status is not valid JSON: {err}") from err
    raw = data.get("deployments") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raise CliError(EXIT_ENV_ERROR, "ostree status JSON has no 'deployments' list")
    return [
        {
            "osname": d.get("osname") or d.get("stateroot"),
            "commit": d.get("checksum") or d.get("commit"),
            "version": d.get("version"),
            "booted": bool(d.get("booted")),
            "pending": bool(d.get("pending") or d.get("staged")),
            "staged": bool(d.get("staged")),
            "rollback": bool(d.get("rollback")),
        }
        for d in raw
        if isinstance(d, dict)
    ]


def _parse_text(text: str) -> list[dict[str, Any]]:
    deployments: list[dict[str, Any]] = []
    for line in text.splitlines():
        m = _DEPLOY_RE.match(line)
        if m and not line.startswith("    "):
            deployments.append(
                {
                    "osname": m["osname"],
                    "commit": m["commit"],
                    "version": None,
                    "booted": m["marker"] == "*",
                    # "(staged)" = queued by `ostree admin deploy --stage` for next boot
                    "pending": "(pending)" in line or "(staged)" in line,
                    "staged": "(staged)" in line,
                    "rollback": "(rollback)" in line,
                }
            )
        elif deployments and line.strip().lower().startswith("version:"):
            deployments[-1]["version"] = line.split(":", 1)[1].strip()
    return deployments


def read_deployments() -> list[dict[str, Any]]:
    text = _run_ostree()
    deployments = _parse_json(text) if text.lstrip().startswith(("{", "[")) else _parse_text(text)
    if not deployments:
        raise CliError(
            EXIT_ENV_ERROR,
            "not an OSTree system: no deployments found in ostree status output",
            "run on an OSTree host, or set CULTUREOS_OSTREE_STATUS_CMD",
        )
    return deployments


def read_state() -> dict[str, Any]:
    """Read the update-agent state file; a missing file means outcome ``none``."""
    path = Path(os.environ.get("CULTUREOS_UPDATE_STATE", DEFAULT_STATE_PATH))
    if not path.exists():
        return {"outcome": "none"}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise CliError(
            EXIT_ENV_ERROR,
            f"cannot read update state {path}: {err}",
            "see docs/os/update-state.md for the schema",
        ) from err
    if not isinstance(state, dict) or state.get("outcome") not in OUTCOMES:
        raise CliError(
            EXIT_ENV_ERROR,
            f"update state {path} has missing or invalid 'outcome' (want one of {OUTCOMES})",
            "see docs/os/update-state.md for the schema",
        )
    return state


def build_status() -> dict[str, Any]:
    deployments = read_deployments()
    booted = next((d for d in deployments if d["booted"]), None)
    if booted is None:
        raise CliError(
            EXIT_ENV_ERROR,
            "not booted into an OSTree deployment: no deployment is marked booted",
            "run on the booted OSTree host, not a chroot or container",
        )
    state = read_state()
    outcome = state["outcome"]
    version = booted.get("version")
    if version is None and state.get("deployed_commit") == booted["commit"]:
        # The state file describes the commit that is actually running.
        version = state.get("deployed_version")
    return {
        "healthy": outcome not in DEGRADED_OUTCOMES,
        "booted": booted,
        "deployments": deployments,
        "version": version,
        "outcome": outcome,
        "last_update": {
            k: state.get(k) for k in ("timestamp", "deployed_commit", "previous_commit", "reason")
        },
    }


def _render_text(s: dict[str, Any]) -> str:
    b = s["booted"]
    lu = s["last_update"]
    lines = [
        f"status: {'healthy' if s['healthy'] else 'degraded'}",
        f"booted: {b.get('osname')} {b.get('commit')}",
        f"version: {s['version']}",
        f"last update outcome: {s['outcome']}",
    ]
    if lu.get("timestamp"):
        lines.append(f"last update at: {lu['timestamp']}")
    if lu.get("reason"):
        lines.append(f"reason: {lu['reason']}")
    return "\n".join(lines)


def cmd_os_status(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    status = build_status()
    emit_result(status if json_mode else _render_text(status), json_mode=json_mode)
    return 0 if status["healthy"] else EXIT_USER_ERROR


def _no_verb(args: argparse.Namespace) -> int:
    return cmd_os_status(args)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("os", help="OS deployment state (see 'cultureos os status').")
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=_no_verb, json=False)
    noun_sub = p.add_subparsers(dest="os_command", parser_class=type(p))
    st = noun_sub.add_parser(
        "status", help="Report OSTree deployment, version and last update outcome."
    )
    # SUPPRESS: an unset verb-level --json must not overwrite `os --json status`.
    st.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="Emit structured JSON."
    )
    st.set_defaults(func=cmd_os_status)
