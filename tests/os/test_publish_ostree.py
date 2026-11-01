"""Offline tests for os/scripts/publish-ostree.sh and the release-repo serving unit.

The publish flow runs against a stub `ostree` that keeps its "repos" as plain
directories, so the all-or-nothing contract (a failure at any step leaves the
published ref and summary unchanged) is checked without ostree or any key
material. A real-ostree round trip runs only where an ed25519-capable ostree
is installed, and is skipped with a reason otherwise.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "os" / "scripts" / "publish-ostree.sh"
UNIT = ROOT / "os" / "systemd" / "cultureos-ostree-http.service"
KEYS = ROOT / "os" / "keys"

STUB = r"""#!/usr/bin/env bash
# Stub ostree. A "repo" is a directory; STUB_FAIL names the step to fail.
echo "$*" >> "$STUB_LOG"
[ "$1" = "--version" ] && { printf 'libostree:\n Features:\n  - ed25519-libsodium\n'; exit 0; }
repo="${1#--repo=}"; shift
fail() {
  [ "${STUB_FAIL:-}" = "$1" ] && { echo "stub: injected failure: $1" >&2; exit 1; }
  return 0
}
case "$1" in
  init) mkdir -p "$repo/objects" "$repo/refs/heads" ;;
  rev-parse) cat "$repo/refs/heads/$2" 2>/dev/null || exit 1 ;;
  pull-local) fail pull-local; mkdir -p "$repo/objects"; touch "$repo/objects/$3" ;;
  sign)
    fail sign
    kf=""; rev=""
    for a in "$@"; do
      case "$a" in --keys-file=*) kf="${a#--keys-file=}" ;; sign|-*) ;; *) rev="$a" ;; esac
    done
    [ -f "$kf" ] || { echo "stub: no readable --keys-file" >&2; exit 1; }
    [ -n "$rev" ] || exit 1
    touch "$repo/objects/$rev.sig" ;;
  remote) echo "$*" > "$repo/remote" ;;
  pull)
    fail verify-commit
    rel="$(sed -n 's#.*file://##p' "$repo/remote" | head -1)"
    [ -f "$rel/objects/$3.sig" ] || exit 1 ;;
  refs)
    case "$2" in
      --delete) rm -f "$repo/refs/heads/$3" ;;
      --create=*) fail refs; ref="${2#--create=}"; printf '%s' "$4" > "$repo/refs/heads/$ref" ;;
    esac ;;
  summary)
    echo partial > "$repo/summary"
    fail summary
    echo "summary-for-$(cat "$repo/refs/heads/ventuno-q")" > "$repo/summary" ;;
  *) exit 1 ;;
esac
"""

OLD, NEW = "a" * 64, "b" * 64


@pytest.fixture
def world(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "ostree").write_text(STUB)
    (bindir / "ostree").chmod(0o755)
    build = tmp_path / "build" / "ostree_repo"
    (build / "refs" / "heads").mkdir(parents=True)
    (build / "refs" / "heads" / "ventuno-q").write_text(NEW)
    keydir = tmp_path / "keys"
    keydir.mkdir()
    key = keydir / "secret"
    key.write_text("c2VjcmV0\n")
    key.chmod(0o600)
    pub = tmp_path / "pub"
    pub.write_text("cHVi\n")
    rel = tmp_path / "rel"
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "OSTREE": "ostree",
        "STUB_LOG": str(tmp_path / "stub.log"),
        "CULTUREOS_RELEASE_CONF": str(tmp_path / "nonexistent.env"),
        "CULTUREOS_BUILD_REPO": str(build),
        "CULTUREOS_RELEASE_REPO": str(rel),
        "CULTUREOS_SIGN_KEY": str(key),
        "CULTUREOS_PUBKEY": str(pub),
    }
    env.pop("STUB_FAIL", None)
    return {"env": env, "rel": rel, "log": tmp_path / "stub.log", "key": key, "tmp": tmp_path}


def run(world, **extra):
    env = {**world["env"], **extra}
    return subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )


def publish_old(world):
    """Establish a previously published state (ref=OLD, a summary)."""
    rel = world["rel"]
    (rel / "refs" / "heads").mkdir(parents=True)
    (rel / "objects").mkdir()
    (rel / "refs" / "heads" / "ventuno-q").write_text(OLD)
    (rel / "summary").write_text("old-summary")
    (rel / "summary.sig").write_text("old-sig")


def calls(world):
    return world["log"].read_text().splitlines()


def test_publish_success_orders_steps(world):
    r = run(world)
    assert r.returncode == 0, r.stderr
    rel = world["rel"]
    assert (rel / "refs" / "heads" / "ventuno-q").read_text() == NEW
    assert (rel / "summary").read_text() == f"summary-for-{NEW}\n"
    log = [c for c in calls(world) if "sign" in c or "refs" in c or "summary" in c or "pull" in c]
    idx = {k: next(i for i, c in enumerate(log) if k in c) for k in ("pull-local", "sign", "refs")}
    assert idx["pull-local"] < idx["sign"] < idx["refs"]
    # the commit is verified before the ref moves
    assert any("pull release " + NEW in c for c in log[: idx["refs"]])


def test_secret_key_never_appears_on_any_command_line(world):
    secret = world["key"].read_text().strip()
    assert run(world).returncode == 0
    for line in calls(world):
        assert secret not in line
    sign = next(c for c in calls(world) if " sign " in c)
    assert f"--keys-file={world['key']}" in sign
    # the summary is updated but never signed (its only option takes the key inline)
    summary = next(c for c in calls(world) if " summary " in c)
    assert "--sign" not in summary


def test_second_run_is_a_noop(world):
    assert run(world).returncode == 0
    world["log"].write_text("")
    r = run(world)
    assert r.returncode == 0
    assert "already at" in r.stderr
    assert not any("sign" in c for c in calls(world))


@pytest.mark.parametrize("step", ["pull-local", "sign", "verify-commit", "refs", "summary"])
def test_failure_leaves_published_state_unchanged(world, step):
    publish_old(world)
    r = run(world, STUB_FAIL=step)
    assert r.returncode != 0
    rel = world["rel"]
    assert (rel / "refs" / "heads" / "ventuno-q").read_text() == OLD
    assert (rel / "summary").read_text() == "old-summary"
    assert (rel / "summary.sig").read_text() == "old-sig"


@pytest.mark.parametrize("step", ["sign", "summary"])
def test_failure_on_first_publish_leaves_no_ref(world, step):
    r = run(world, STUB_FAIL=step)
    assert r.returncode != 0
    assert not (world["rel"] / "refs" / "heads" / "ventuno-q").exists()
    assert not (world["rel"] / "summary").exists()


def test_key_inside_repo_is_refused(world):
    inside = ROOT / "os" / "keys" / "zz-test-secret"
    try:
        inside.write_text("c2VjcmV0\n")
        r = run(world, CULTUREOS_SIGN_KEY=str(inside))
    finally:
        inside.unlink(missing_ok=True)
    assert r.returncode != 0
    assert "outside the git repo" in r.stderr
    assert not world["log"].exists() or not any("pull-local" in c for c in calls(world))


def test_key_inside_other_git_tree_is_refused(world):
    tree = world["tmp"] / "other"
    tree.mkdir()
    subprocess.run(["git", "init", "-q", str(tree)], check=True)
    key = tree / "secret"
    key.write_text("c2VjcmV0\n")
    r = run(world, CULTUREOS_SIGN_KEY=str(key))
    assert r.returncode != 0
    assert "git work tree" in r.stderr


def test_missing_key_points_at_keygen(world):
    r = run(world, CULTUREOS_SIGN_KEY=str(world["tmp"] / "nope"))
    assert r.returncode != 0
    assert "--print-keygen" in r.stderr


def test_missing_ostree_reports_install_hint(world):
    r = run(world, OSTREE="definitely-not-ostree")
    assert r.returncode == 2
    assert "apt install ostree" in r.stderr


def test_ostree_without_ed25519_is_refused(world):
    (world["tmp"] / "bin" / "ostree").write_text(
        "#!/usr/bin/env bash\n[ \"$1\" = --version ] && echo 'Features: libarchive'\n"
    )
    r = run(world)
    assert r.returncode == 2
    assert "ed25519" in r.stderr


def test_print_keygen_prints_without_generating(world, tmp_path):
    r = subprocess.run(
        ["bash", str(SCRIPT), "--print-keygen"],
        env={**world["env"], "HOME": str(tmp_path / "home")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert "openssl genpkey -algorithm ed25519" in r.stdout
    assert "os/keys/cultureos-ostree.pub" in r.stdout
    # the secret is written as one base64 line, newline-terminated, for --keys-file
    assert "base64 -w 0" in r.stdout
    assert 'echo >> "$KEYDIR/ostree-ed25519.secret"' in r.stdout
    assert not (tmp_path / "home").exists()


def test_no_private_key_material_committed():
    # Check git-tracked files only: test_key_inside_repo_is_refused briefly writes
    # a scratch file into os/keys/, which a parallel (xdist) directory listing sees.
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "os/keys"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    names = {Path(t).name for t in tracked}
    assert "README.md" in names
    assert names <= {"README.md", "cultureos-ostree.pub"}
    for name in names - {"README.md"}:
        assert len((KEYS / name).read_text().strip()) == 44  # base64 of 32 bytes


def test_unit_binds_tailscale_address_only():
    text = UNIT.read_text()
    assert "tailscale ip -4" in text
    assert "--bind" in text
    assert '"$$ip"' in text
    exec_line = next(ln for ln in text.splitlines() if ln.startswith("ExecStart="))
    assert "0.0.0.0" not in exec_line
    assert "[::]" not in exec_line
    assert "WantedBy=default.target" in text
    assert "http.server" in text


def _real_ostree_ed25519():
    exe = os.environ.get("CULTUREOS_TEST_OSTREE") or shutil.which("ostree")
    if not exe:
        return None
    out = subprocess.run([exe, "--version"], capture_output=True, text=True, check=False).stdout
    return exe if "ed25519" in out.lower() else None


@pytest.mark.skipif(
    _real_ostree_ed25519() is None,
    reason="no ostree with ed25519 support on PATH (operator: sudo apt install ostree)",
)
def test_real_ostree_round_trip(tmp_path):  # pragma: no cover - needs host ostree
    import base64

    exe = _real_ostree_ed25519()
    pem = tmp_path / "k.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "ed25519", "-outform", "PEM", "-out", str(pem)],
        check=True,
    )

    def tail32(*args):
        der = subprocess.run(
            ["openssl", "pkey", "-outform", "DER", *args], capture_output=True, check=True
        ).stdout
        return der[-32:]

    pub = tail32("-pubout", "-in", str(pem))
    seed = tail32("-in", str(pem))
    (tmp_path / "secret").write_text(base64.b64encode(seed + pub).decode() + "\n")
    (tmp_path / "secret").chmod(0o600)
    (tmp_path / "pub").write_text(base64.b64encode(pub).decode() + "\n")
    build = tmp_path / "build"
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "f").write_text("x")
    subprocess.run([exe, f"--repo={build}", "init", "--mode=archive"], check=True)
    subprocess.run(
        [exe, f"--repo={build}", "commit", "-b", "ventuno-q", f"--tree=dir={tree}"],
        check=True,
        capture_output=True,
    )
    env = {
        **os.environ,
        "OSTREE": exe,
        "CULTUREOS_RELEASE_CONF": str(tmp_path / "none.env"),
        "CULTUREOS_BUILD_REPO": str(build),
        "CULTUREOS_RELEASE_REPO": str(tmp_path / "rel"),
        "CULTUREOS_SIGN_KEY": str(tmp_path / "secret"),
        "CULTUREOS_PUBKEY": str(tmp_path / "pub"),
    }
    r = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
