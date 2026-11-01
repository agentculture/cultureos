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
    assert rc == 0
    assert json.loads(out)["outcome"] == "none"


def test_booted_selected_by_marker_not_position(fake, capsys) -> None:
    # During a one-shot trial boot ostree lists the staged deployment above
    # the booted one; the booted entry must come from the '*' marker.
    staged_first = """\
  cultureos 77aa11bb.0 (pending)
    Version: 0.5.0
* cultureos 3f2a9c1d.0
    Version: 0.4.0
"""
    fake(ostree=staged_first, state={"outcome": "none"})
    rc, out, _ = _run(capsys, "--json")
    data = json.loads(out)
    assert rc == 0
    assert data["booted"]["commit"] == "3f2a9c1d"
    assert data["version"] == "0.4.0"


def test_json_ostree_source(fake, capsys) -> None:
    fake(ostree=JSON_OUT, state={"outcome": "applied"})
    rc, out, _ = _run(capsys, "--json")
    data = json.loads(out)
    assert rc == 0
    assert data["booted"]["version"] == "0.4.0"
    assert data["deployments"][1]["rollback"] is True


def test_text_output_degraded(fake, capsys) -> None:
    fake(state={"outcome": "failed", "reason": "fetch error"})
    rc, out, err = _run(capsys)
    assert rc == 1
    assert err == ""
    assert "degraded" in out
    assert "failed" in out
    assert "fetch error" in out


def test_not_ostree_env_error(fake, capsys) -> None:
    fake(ostree=None)
    rc, out, err = _run(capsys)
    assert rc == 2
    assert out == ""
    assert "not an OSTree system" in err
    assert "hint:" in err
    assert "Traceback" not in err


def test_not_ostree_json_error(fake, capsys) -> None:
    fake(ostree="nothing useful here\n")
    rc, _, err = _run(capsys, "--json")
    assert rc == 2
    assert json.loads(err)["code"] == 2


def test_ostree_nonzero_exit(fake, monkeypatch, capsys) -> None:
    fake()
    monkeypatch.setenv("CULTUREOS_OSTREE_STATUS_CMD", "false")
    rc, _, err = _run(capsys)
    assert rc == 2
    assert "exited 1" in err


@pytest.mark.parametrize("bad", ["{not json", json.dumps({"outcome": "weird"}), "[]"])
def test_bad_state_file(fake, capsys, bad) -> None:
    fake(state=bad)
    rc, _, err = _run(capsys)
    assert rc == 2
    assert "update state" in err


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


# --- review fixes (PR #5) -------------------------------------------------


@pytest.mark.parametrize(
    "cmd",
    ["", "   ", "cat 'unbalanced"],
    ids=["empty", "blank", "unbalanced-quote"],
)
def test_bad_status_command_is_env_error(monkeypatch, capsys, cmd) -> None:
    monkeypatch.setenv("CULTUREOS_OSTREE_STATUS_CMD", cmd)
    rc, out, err = _run(capsys, "--json")
    assert rc == 2, err
    assert out == ""
    assert "unexpected" not in err


def test_non_utf8_ostree_output_is_env_error(tmp_path, monkeypatch, capsys) -> None:
    raw = tmp_path / "raw.out"
    raw.write_bytes(b"* cultureos \xff\xfe.0\n")
    monkeypatch.setenv("CULTUREOS_OSTREE_STATUS_CMD", f"cat {raw}")
    rc, _, err = _run(capsys, "--json")
    assert rc == 2, err
    assert "unexpected" not in err


def test_version_not_taken_from_failed_update_target(fake, capsys) -> None:
    # Rolled back to a commit without Version metadata: the version the update
    # aimed for (deployed_version) is NOT what is running.
    fake(
        ostree="* cultureos 3f2a9c1d.0\n  cultureos 77aa11bb.0 (rollback)\n",
        state={
            "outcome": "rolled-back",
            "deployed_commit": "77aa11bb",
            "deployed_version": "0.5.0",
        },
    )
    _, out, _ = _run(capsys, "--json")
    assert json.loads(out)["version"] is None


def test_version_falls_back_when_state_names_booted_commit(fake, capsys) -> None:
    fake(
        ostree="* cultureos 3f2a9c1d.0\n",
        state={"outcome": "applied", "deployed_commit": "3f2a9c1d", "deployed_version": "0.4.0"},
    )
    _, out, _ = _run(capsys, "--json")
    assert json.loads(out)["version"] == "0.4.0"


def test_json_flag_on_noun_survives_verb(fake, capsys) -> None:
    fake(state={"outcome": "applied"})
    rc = main(["os", "--json", "status"])
    out = capsys.readouterr().out
    assert rc == 0
    assert json.loads(out)["outcome"] == "applied"


def test_staged_text_deployment_is_reported(fake, capsys) -> None:
    fake(ostree="  cultureos 77aa11bb.0 (staged)\n* cultureos 3f2a9c1d.0\n", state=None)
    _, out, _ = _run(capsys, "--json")
    staged = json.loads(out)["deployments"][0]
    assert staged["staged"] is True
    assert staged["pending"] is True


def test_staged_json_deployment_is_reported(fake, capsys) -> None:
    fake(
        ostree=json.dumps(
            {
                "deployments": [
                    {"osname": "cultureos", "checksum": "77aa11bb", "staged": True},
                    {"osname": "cultureos", "checksum": "3f2a9c1d", "booted": True},
                ]
            }
        )
    )
    _, out, _ = _run(capsys, "--json")
    staged = json.loads(out)["deployments"][0]
    assert staged["staged"] is True
    assert staged["pending"] is True


def test_no_booted_deployment_is_env_error(fake, capsys) -> None:
    fake(ostree=json.dumps({"deployments": [{"osname": "cultureos", "checksum": "3f2a9c1d"}]}))
    rc, out, err = _run(capsys, "--json")
    assert rc == 2, err
    assert out == ""
