"""Fake `ostree`, `bootctl` and `systemctl` for the cultureos-trialboot tests (t15).

Run as ``python3 trialboot_fake.py <tool> <args...>``. The simulated machine lives in
the JSON file named by ``TB_WORLD``:

- ``deployments``: OSTree deployments in boot order (index 0 is the default), each
  ``{checksum, serial, stateroot, version, blessed, kargs}``
- ``booted``: ``{checksum, serial}`` of the booted deployment
- ``refs``: refspec -> commit checksum
- ``oneshot``: the LoaderEntryOneShot EFI variable (an entry id) or null
- ``efivars_writable``: false makes ``bootctl set-oneshot`` fail
- ``default_override``: an entry index systemd-boot treats as default instead of 0
- ``calls``: every invocation, in order
- ``reboots``: how many reboots were requested
- ``set_default_audit``: for every ``ostree admin set-default``, the trial state's
  health record and the boot id at the time of the call

Entry ids follow libostree 2026.5 (``ostree-<n - index>.conf``) and systemd 262 (the
boot-counting suffix is not part of the id); an unblessed entry reports ``triesLeft``.
"""

import json
import os
import sys
from pathlib import Path


def _load() -> dict:
    return json.loads(Path(os.environ["TB_WORLD"]).read_text())


def _save(world: dict) -> None:
    Path(os.environ["TB_WORLD"]).write_text(json.dumps(world, indent=2))


def _is_booted(world: dict, dep: dict) -> bool:
    b = world["booted"]
    return dep["checksum"] == b["checksum"] and dep["serial"] == b["serial"]


def _rev_parse(world: dict, ref: str) -> str | None:
    if ref in world["refs"]:
        return world["refs"][ref]
    if ref in world["refs"].values():
        return ref
    return None


def _ostree(world: dict, args: list[str]) -> int:
    if args[:1] == ["rev-parse"]:
        csum = _rev_parse(world, args[1])
        if csum is None:
            print(f"error: Refspec '{args[1]}' not found", file=sys.stderr)
            return 1
        print(csum)
        return 0
    if args[:2] == ["admin", "status"] and "--json" in args:
        out = []
        for i, d in enumerate(world["deployments"]):
            out.append(
                {
                    "checksum": d["checksum"],
                    "stateroot": d["stateroot"],
                    "refspec": "cultureos:ventuno-q",
                    "serial": d["serial"],
                    "index": i,
                    "booted": _is_booted(world, d),
                    "pending": False,
                    "rollback": False,
                    "staged": False,
                    "pinned": False,
                    "unlocked": "none",
                    "version": d["version"],
                }
            )
        print(json.dumps({"deployments": out}))
        return 0
    if args[:2] == ["admin", "deploy"]:
        opts = [a for a in args[2:] if a.startswith("--")]
        ref = [a for a in args[2:] if not a.startswith("--")][-1]
        csum = _rev_parse(world, ref)
        if csum is None:
            print(f"error: Refspec '{ref}' not found", file=sys.stderr)
            return 1
        booted = next(d for d in world["deployments"] if _is_booted(world, d))
        kargs = booted["kargs"].split()
        for o in opts:
            if o.startswith("--karg="):
                key = o[len("--karg=") :].split("=", 1)[0]
                kargs = [k for k in kargs if k.split("=", 1)[0] != key] + [o[len("--karg=") :]]
        serial = 1 + max(
            [d["serial"] for d in world["deployments"] if d["checksum"] == csum], default=-1
        )
        new = {
            "checksum": csum,
            "serial": serial,
            "stateroot": "cultureos",
            "version": world.get("versions", {}).get(csum, "unknown"),
            "blessed": False,
            "kargs": " ".join(kargs),
        }
        # libostree simple_write_deployment without --retain*: keep the booted
        # deployment, drop the others; --not-as-default puts the new one after it.
        if "--not-as-default" in opts:
            world["deployments"] = [booted, new]
        else:
            world["deployments"] = [new, booted]
        return 0
    if args[:2] == ["admin", "set-default"]:
        idx = int(args[2])
        state_path = Path(os.environ["CULTUREOS_TRIALBOOT_STATE"])
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        boot_id = Path(os.environ["CULTUREOS_TRIALBOOT_BOOT_ID_FILE"]).read_text().strip()
        world["set_default_audit"].append({"health": state.get("health"), "boot_id": boot_id})
        dep = world["deployments"].pop(idx)
        world["deployments"].insert(0, dep)
        return 0
    if args[:2] == ["admin", "undeploy"]:
        idx = int(args[2])
        if _is_booted(world, world["deployments"][idx]):
            print("error: Cannot undeploy currently booted deployment", file=sys.stderr)
            return 1
        world["deployments"].pop(idx)
        return 0
    print(f"fake ostree: unsupported {args}", file=sys.stderr)
    return 99


def entry_id(world: dict, index: int) -> str:
    return f"ostree-{len(world['deployments']) - index}.conf"


def _bootctl(world: dict, args: list[str]) -> int:
    if args[:1] == ["list"]:
        default = world.get("default_override")
        default = 0 if default is None else default
        out = []
        for i, d in enumerate(world["deployments"]):
            e = {
                "type": "type1",
                "source": "esp",
                "id": entry_id(world, i),
                "options": f"{d['kargs']} ostree=/ostree/boot.1/cultureos/x/{d['serial']}",
                "isReported": True,
                "isDefault": i == default,
                "isSelected": _is_booted(world, d),
            }
            if not d["blessed"]:
                e["triesLeft"] = 2
                e["triesDone"] = 1
            out.append(e)
        print(json.dumps(out))
        return 0
    if args[:1] == ["set-oneshot"]:
        if not world.get("efivars_writable", True):
            print(
                "Failed to set EFI variable LoaderEntryOneShot: Read-only file system",
                file=sys.stderr,
            )
            return 1
        world["oneshot"] = args[1]
        return 0
    print(f"fake bootctl: unsupported {args}", file=sys.stderr)
    return 99


def _systemctl(world: dict, args: list[str]) -> int:
    if args[:1] == ["reboot"]:
        world["reboots"] += 1
        return 0
    print(f"fake systemctl: unsupported {args}", file=sys.stderr)
    return 99


def main() -> int:
    tool, args = sys.argv[1], sys.argv[2:]
    world = _load()
    world["calls"].append([tool, *args])
    rc = {"ostree": _ostree, "bootctl": _bootctl, "systemctl": _systemctl}[tool](world, args)
    _save(world)
    return rc


if __name__ == "__main__":
    sys.exit(main())
