"""Run the exported cultureos-release workflow in culture-rules' in-memory engine.

Not a test module: tests/os/test_release_workflow.py runs it in a subprocess with the
culture-rules checkout on PYTHONPATH (the engine is stdlib-only; the fake actor is the one
culture-rules' own tests use). Prints one JSON object: scenario -> status, steps run, outputs.
Usage: python -P release_sim.py <os/release/culture-rules dir>
"""

import json
import pathlib
import sys

from culture_rules.engine.runs import Executor
from culture_rules.node.actors import ActorRouter
from culture_rules.node.runner import BuiltinCodePort
from culture_rules.store.memory import MemoryStore

from tests.engine.run_helpers import Clock, FakeActor, enrol_online, machine

DIR = pathlib.Path(sys.argv[1])


def _load(rel: str) -> dict:
    return json.loads((DIR / rel).read_text())


def scenario(fail_step: str | None) -> dict:
    clock = Clock()
    store = MemoryStore(clock=clock)
    enrol_online(store, clock, machine("spark"))
    store.put("actors", _load("actors/spark-cultureos-release.json"))
    store.put("workflows", _load("workflows/cultureos-release.json"))
    actor = FakeActor(
        default=lambda inp, ctx: {"stdout": f"out:{inp['command']}", "stderr": "", "exit_code": 0}
    )
    if fail_step:
        actor.on(fail_step, ("fail", "exit code 1: boom", False))
    ports = {
        "action:machine.command": actor,
        "action:noop": FakeActor(),
        "code": BuiltinCodePort({}),
    }
    router = ActorRouter(store, ports=ports, clock=clock)
    ex = Executor(store, "spark", router, clock=clock)
    run = ex.start_workflow("cultureos-release", {"ref": "origin/main", "version": "0.12.0"})
    ex.run_until_idle()
    doc = ex.run(run["id"])
    return {
        "status": doc["status"],
        "ran": [c[2].step_id for c in actor.calls],
        "commands": [c[1]["command"] for c in actor.calls],
        "args": [c[1]["args"] for c in actor.calls],
        "hosts": [c[2].host for c in actor.calls],
        "outputs": doc.get("outputs"),
    }


STEPS = ["sync", "build", "bundle", "publish", "notify", "status"]
print(json.dumps({s or "ok": scenario(s) for s in [None, *STEPS]}))
