"""Tests for ``cultureos os status`` with faked ostree and state sources."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cultureos.cli import main
from cultureos.explain import known_paths

TEXT = """\
* cultureos 3f2a9c1d.0
    Version: 0.4.0
    origin refspec: cultureos:stable
  cultureos 9ab01e22.1 (rollback)
    Version: 0.3.0
"""
JSON_OUT = json.dumps(
    {
        "deployments": [
            {"osname": "cultureos", "checksum": "3f2a9c1d", "version": "0.4.0", "booted": True},
            {"osname": "cultureos", "checksum": "9ab01e22", "version": "0.3.0", "rollback": True},
        ]
    }
)


@pytest.fixture
def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def setup(ostree: str | None = TEXT, state: dict | str | None = None) -> Path:
        out = tmp_path / "ostree.out"
        if ostree is None:
            monkeypatch.setenv("CULTUREOS_OSTREE_STATUS_CMD", str(tmp_path / "no-such-ostree"))
        else:
            out.write_text(ostree)
            monkeypatch.setenv("CULTUREOS_OSTREE_STATUS_CMD", f"cat {out}")
        sp = tmp_path / "update-state.json"
        monkeypatch.setenv("CULTUREOS_UPDATE_STATE", str(sp))
        if state is not None:
            sp.write_text(state if isinstance(state, str) else json.dumps(state))
        return sp

    return setup


def _run(capsys, *extra: str):
    rc = main(["os", "status", *extra])
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


@pytest.mark.parametrize(
    "outcome,rc", [("applied", 0), ("none", 0), ("rolled-back", 1), ("failed", 1)]
)
def test_outcomes(fake, capsys, outcome, rc) -> None:
    fake(state={"schema_version": 1, "outcome": outcome, "timestamp": "t", "reason": "boom"})
    got, out, _ = _run(capsys, "--json")
    assert got == rc
    data = json.loads(out)
    assert data["outcome"] == outcome
    assert data["healthy"] == (rc == 0)
    assert data["booted"]["commit"] == "3f2a9c1d"
    assert data["version"] == "0.4.0"


def test_missing_state_is_none(fake, capsys) -> None:
    fake()
    rc, out, _ = _run(capsys, "--json")
    assert rc == 0 and json.loads(out)["outcome"] == "none"


def test_json_ostree_source(fake, capsys) -> None:
    fake(ostree=JSON_OUT, state={"outcome": "applied"})
    rc, out, _ = _run(capsys, "--json")
    data = json.loads(out)
    assert rc == 0 and data["booted"]["version"] == "0.4.0"
    assert data["deployments"][1]["rollback"] is True


def test_text_output_degraded(fake, capsys) -> None:
    fake(state={"outcome": "failed", "reason": "fetch error"})
    rc, out, err = _run(capsys)
    assert rc == 1 and err == ""
    assert "degraded" in out and "failed" in out and "fetch error" in out


def test_not_ostree_env_error(fake, capsys) -> None:
    fake(ostree=None)
    rc, out, err = _run(capsys)
    assert rc == 2 and out == ""
    assert "not an OSTree system" in err and "hint:" in err and "Traceback" not in err


def test_not_ostree_json_error(fake, capsys) -> None:
    fake(ostree="nothing useful here\n")
    rc, _, err = _run(capsys, "--json")
    assert rc == 2 and json.loads(err)["code"] == 2


def test_ostree_nonzero_exit(fake, monkeypatch, capsys) -> None:
    fake()
    monkeypatch.setenv("CULTUREOS_OSTREE_STATUS_CMD", "false")
    rc, _, err = _run(capsys)
    assert rc == 2 and "exited 1" in err


@pytest.mark.parametrize("bad", ["{not json", json.dumps({"outcome": "weird"}), "[]"])
def test_bad_state_file(fake, capsys, bad) -> None:
    fake(state=bad)
    rc, _, err = _run(capsys)
    assert rc == 2 and "update state" in err


@pytest.mark.parametrize("bad", ["{not json", json.dumps({"x": 1})])
def test_bad_ostree_json(fake, capsys, bad) -> None:
    fake(ostree=bad)
    rc, _, _ = _run(capsys)
    assert rc == 2


def test_bare_os_runs_status(fake, capsys) -> None:
    fake(state={"outcome": "applied"})
    assert main(["os"]) == 0
    assert "healthy" in capsys.readouterr().out


def test_explain_entry() -> None:
    assert ("os", "status") in known_paths()
