"""Fake `ostree`, `systemctl` and `systemd-run` for the cultureos-update tests (t16).

Run as ``python3 update_fake.py <tool> <args...>``. Extends the t15 world of
tests/os/trialboot_fake.py (same ``TB_WORLD`` JSON file; the real cultureos-trialboot
helper runs against it) with:

- ``remote``: ``{url, branches: {branch: commit}, bad_signature: [commit],
  pull_error: str|null, content_error: str|null, pull_sleep: float}``.
  ``pull_error`` fails every pull with that stderr text; ``content_error`` fails only
  the full (content) pull.
- ``partial``: commits pulled with ``--commit-metadata-only`` and not yet in full;
  ``ostree admin deploy`` of one fails, like libostree does.
- ``scheduled``: every ``systemd-run`` call.
- ``unit_starts``: every ``systemctl start`` call (the push path).

``systemctl start cultureos-update.service`` runs the agent's ``run`` (the command
named by ``UPD_AGENT_CMD``) with the caller's environment, as the unit would.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import trialboot_fake  # noqa: E402  (t15's fake, reused for everything else)


def _load() -> dict:
    return json.loads(Path(os.environ["TB_WORLD"]).read_text())


def _save(world: dict) -> None:
    Path(os.environ["TB_WORLD"]).write_text(json.dumps(world, indent=2))


def _pull(world: dict, args: list[str]) -> int:
    metadata_only = "--commit-metadata-only" in args
    remote, branch = [a for a in args if not a.startswith("--")]
    r = world["remote"]
    if r.get("pull_sleep"):
        _save(world)
        time.sleep(r["pull_sleep"])
        world = _load()
        r = world["remote"]
    if r.get("pull_error"):
        print(f"error: {r['pull_error']}", file=sys.stderr)
        return 1, world
    commit = r["branches"].get(branch)
    if commit is None:
        print(
            f"error: While fetching {r['url']}refs/heads/{branch}: Server returned HTTP 404",
            file=sys.stderr,
        )
        return 1, world
    if commit in r.get("bad_signature", []):
        print(
            f"error: Commit {commit}: Can't verify commit: ed25519: Signature couldn't be "
            "verified with: key 'abc'",
            file=sys.stderr,
        )
        return 1, world
    if not metadata_only and r.get("content_error"):
        print(f"error: {r['content_error']}", file=sys.stderr)
        return 1, world
    world["refs"][f"{remote}:{branch}"] = commit
    partial = set(world.setdefault("partial", []))
    if metadata_only:
        if commit not in world.setdefault("pulled", []):
            partial.add(commit)
    else:
        partial.discard(commit)
        world.setdefault("pulled", []).append(commit)
    world["partial"] = sorted(partial)
    return 0, world


def _ostree(world: dict, args: list[str]):
    if args[:1] == ["pull"]:
        return _pull(world, args[1:])
    if args[:2] == ["remote", "show-url"]:
        if args[2] != "cultureos":
            print(f'error: Remote "{args[2]}" not found', file=sys.stderr)
            return 1, world
        print(world["remote"]["url"])
        return 0, world
    if args[:1] == ["show"]:
        ref = args[-1]
        csum = trialboot_fake._rev_parse(world, ref)
        if csum is None:
            print(f"error: Refspec '{ref}' not found", file=sys.stderr)
            return 1, world
        print(f"'{world.get('versions', {}).get(csum, '')}'")
        return 0, world
    if args[:2] == ["admin", "deploy"]:
        ref = [a for a in args[2:] if not a.startswith("--")][-1]
        csum = trialboot_fake._rev_parse(world, ref)
        if csum in world.get("partial", []):
            print(f"error: Commit {csum} is partial", file=sys.stderr)
            return 1, world
    return trialboot_fake._ostree(world, args), world


def _systemctl(world: dict, args: list[str]):
    args = [a for a in args if a != "--no-ask-password"]
    if args[:1] == ["start"]:
        world.setdefault("unit_starts", []).append(args[1])
        _save(world)
        cmd = json.loads(os.environ["UPD_AGENT_CMD"])
        r = subprocess.run([*cmd, "run"], capture_output=True, text=True)
        sys.stderr.write(r.stderr)
        world = _load()
        if r.returncode not in (0, 3):  # SuccessExitStatus=3
            print(
                f"Job for {args[1]} failed because the control process exited with error code.",
                file=sys.stderr,
            )
            return 1, world
        return 0, world
    return trialboot_fake._systemctl(world, args), world


def _systemd_run(world: dict, args: list[str]):
    world.setdefault("scheduled", []).append(args)
    print(f"Running timer as unit: {args[0].split('=', 1)[1]}.timer", file=sys.stderr)
    return 0, world


def main() -> int:
    tool, args = sys.argv[1], sys.argv[2:]
    world = _load()
    world["calls"].append([tool, *args])
    handler = {"ostree": _ostree, "systemctl": _systemctl, "systemd-run": _systemd_run}[tool]
    rc, world = handler(world, args)
    _save(world)
    return rc


if __name__ == "__main__":
    sys.exit(main())
