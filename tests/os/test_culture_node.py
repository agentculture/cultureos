"""Offline checks for the culture mesh node recipes (plan t13).

Acceptance 1: recipes-culture builds culture and cultureos from pinned PyPI
sdists, with no runtime network. Acceptance 2: the node unit orders after
network-online.target, restarts on failure and keeps identity/state in
/var/lib/culture. Acceptance 3 (node on the mesh after a reboot) is hardware
and is not tested here.
"""

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RECIPES = ROOT / "os" / "meta-cultureos" / "recipes-culture"
NODE = RECIPES / "culture-node"
UNIT = NODE / "files" / "culture-node.service"
START = NODE / "files" / "culture-node-start"
ENV_EXAMPLE = NODE / "files" / "node.env.example"
DOC = ROOT / "docs" / "os" / "culture-node.md"

PINS = {"python3-culture": "14.13.1", "python3-cultureos": "0.10.1"}

# Python recipes the culture tree uses that come from oe-core / meta-python at
# the pinned layer commits (see the audit in python3-culture_*.bb). Anything a
# recipes-culture recipe RDEPENDS on must be one of these, a python3 stdlib
# split package, or a recipe in recipes-culture itself.
UPSTREAM_PY = {
    "python3-aiohappyeyeballs",
    "python3-aiohttp",
    "python3-aiosignal",
    "python3-annotated-doc",
    "python3-annotated-types",
    "python3-anyio",
    "python3-attrs",
    "python3-certifi",
    "python3-cffi",
    "python3-click",
    "python3-cryptography",
    "python3-frozenlist",
    "python3-grpcio",
    "python3-h11",
    "python3-httpcore",
    "python3-httpx",
    "python3-idna",
    "python3-importlib-metadata",
    "python3-jinja2",
    "python3-jsonschema",
    "python3-markdown-it-py",
    "python3-multidict",
    "python3-packaging",
    "python3-portalocker",
    "python3-propcache",
    "python3-protobuf",
    "python3-pydantic",
    "python3-pydantic-core",
    "python3-pyjwt",
    "python3-python-dotenv",
    "python3-python-multipart",
    "python3-pyyaml",
    "python3-rich",
    "python3-starlette",
    "python3-tomlkit",
    "python3-typer",
    "python3-typing-extensions",
    "python3-typing-inspection",
    "python3-uvicorn",
    "python3-wrapt",
    "python3-yarl",
    "python3-zipp",
}
STDLIB = {"python3-core", "python3-modules"}


def _python_recipes() -> dict[str, Path]:
    out = {}
    for bb in RECIPES.glob("*/python3-*_*.bb"):
        pn = bb.name.split("_", 1)[0]
        out[pn] = bb
    return out


def _var(text: str, name: str) -> str:
    """Value of a (possibly line-continued) `NAME = "..."` / `NAME += "..."` assignment."""
    m = re.search(rf'^{re.escape(name)}\s*\+?=\s*"((?:[^"\\]|\\.|\\\n)*)"', text, re.M | re.S)
    assert m, f"{name} not set"
    return m.group(1).replace("\\\n", " ")


def _unit() -> dict[str, list[str]]:
    keys: dict[str, list[str]] = {}
    for line in UNIT.read_text().splitlines():
        if "=" in line and not line.startswith(("#", ";", "[")):
            k, v = line.split("=", 1)
            keys.setdefault(k.strip(), []).append(v.strip())
    return keys


# --- acceptance 1: pinned PyPI recipes, no runtime network ------------------


@pytest.mark.parametrize("pn,pv", sorted(PINS.items()))
def test_culture_and_cultureos_pinned(pn, pv):
    recipes = _python_recipes()
    assert recipes[pn].name == f"{pn}_{pv}.bb"


def test_every_python_recipe_is_a_sha256_pinned_pypi_sdist():
    recipes = _python_recipes()
    assert len(recipes) == 27
    for pn, bb in recipes.items():
        text = bb.read_text()
        assert re.search(r"^inherit pypi ", text, re.M), pn
        assert re.search(r'^SRC_URI\[sha256sum\] = "[0-9a-f]{64}"$', text, re.M), pn
        assert re.search(r"^LIC_FILES_CHKSUM = \"file://\S+;md5=[0-9a-f]{32}\"", text, re.M), pn
        assert re.search(r'^LICENSE = "\S+"$', text, re.M), pn


def test_no_recipe_fetches_or_installs_at_build_or_run_time():
    for bb in RECIPES.rglob("*"):
        if not bb.is_file():
            continue
        text = bb.read_text()
        assert "pip install" not in text, bb
        assert "pip download" not in text, bb
        assert "--index-url" not in text, bb
        assert "python3-pip" not in text, bb


def test_rdepends_closure_is_satisfied():
    recipes = _python_recipes()
    known = set(recipes) | UPSTREAM_PY | STDLIB
    missing = {}
    for pn, bb in recipes.items():
        for dep in _var(bb.read_text(), "RDEPENDS:${PN}").split():
            if dep not in known:
                missing.setdefault(pn, []).append(dep)
    assert not missing


def test_culture_rdepends_its_declared_requirements():
    rdeps = set(_var(_python_recipes()["python3-culture"].read_text(), "RDEPENDS:${PN}").split())
    for dep in (
        "python3-agentirc-cli",
        "python3-cultureagent",
        "python3-irc-lens",
        "python3-aiohttp",
        "python3-opentelemetry-sdk",
        "python3-modules",
    ):
        assert dep in rdeps


def test_packaging_route_recorded_in_recipe_header_and_doc():
    header = _python_recipes()["python3-culture"].read_text().split("SUMMARY", 1)[0]
    assert "PACKAGING ROUTE" in header
    assert "argon2-cffi-bindings" in header
    assert "Rejected: a build-time venv" in header
    assert "3.14" in header
    doc = DOC.read_text()
    assert "## Packaging route" in doc
    assert "argon2-cffi-bindings" in doc


def test_importlib_metadata_comes_from_meta_python():
    # Decision recorded in python3-culture: keep meta-python's 9.1.0.
    assert "python3-importlib-metadata" not in _python_recipes()


# --- acceptance 2: the systemd unit -----------------------------------------


def test_node_recipe_wires_unit_user_and_packages():
    bbs = list(NODE.glob("culture-node_*.bb"))
    assert len(bbs) == 1
    text = bbs[0].read_text()
    assert re.search(r"^inherit .*\bsystemd\b", text, re.M)
    assert re.search(r"^inherit .*\buseradd\b", text, re.M)
    assert _var(text, "SYSTEMD_SERVICE:${PN}") == "culture-node.service"
    useradd = _var(text, "USERADD_PARAM:${PN}")
    assert "--system" in useradd
    assert "--home-dir /var/lib/culture" in useradd
    assert "--no-create-home" in useradd
    rdeps = _var(text, "RDEPENDS:${PN}").split()
    assert "python3-culture" in rdeps
    assert "python3-cultureos" in rdeps
    # OSTree does not carry build-time /var content to a deployed system; the
    # state dir must come from systemd at runtime, never from do_install.
    do_install = text.split("do_install() {", 1)[1].split("\n}", 1)[0]
    assert "${localstatedir}" not in do_install
    assert "/var" not in do_install


def test_unit_orders_after_network_online_and_restarts():
    u = _unit()
    assert "network-online.target" in " ".join(u["After"])
    assert "network-online.target" in " ".join(u["Wants"])
    assert u["Restart"] == ["on-failure"]
    # culture's exit contract: 78 = permanent config error, park the unit
    assert u["RestartPreventExitStatus"] == ["78"]
    assert u["Type"] == ["simple"]
    assert u["WantedBy"] == ["multi-user.target"]


def test_unit_keeps_identity_and_state_in_var_lib_culture():
    u = _unit()
    assert u["User"] == ["culture"]
    assert u["StateDirectory"] == ["culture"]
    assert "HOME=/var/lib/culture" in u["Environment"]
    assert u["WorkingDirectory"] == ["/var/lib/culture"]
    assert u["EnvironmentFile"] == ["-/var/lib/culture/node.env"]
    assert u["ExecStart"] == ["/usr/libexec/culture-node/culture-node-start"]


def test_no_secrets_in_recipe_files():
    for f in NODE.rglob("*"):
        if f.is_file():
            text = f.read_text()
            assert not re.search(r"(?i)password\s*=\s*\S", text), f
            assert not re.search(r"--link\s+\S+:\S+:\d+:\S+", text), f
            assert "tskey-" not in text, f


# --- the start wrapper, with a stub culture binary --------------------------


# No tailnet in tests: a local-only node names its (loopback) host explicitly.
LOCAL = {"CULTURE_NODE_NAME": "node1", "CULTURE_NODE_HOST": "127.0.0.1"}


def _run_start(tmp_path, env_extra=None, mesh=False, stale_pid=False):
    home = tmp_path / "home"
    (home / ".culture" / "pids").mkdir(parents=True)
    if mesh:
        (home / ".culture" / "mesh.yaml").write_text("server: {}\n")
    if stale_pid:
        (home / ".culture" / "pids" / "server-node1.pid").write_text("1\n")
    stub = tmp_path / "culture"
    out = tmp_path / "argv"
    stub.write_text(f'#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done > "{out}"\n')
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "CULTURE_BIN": str(stub),
        # No tailnet in tests unless a test provides a stub; don't wait for one.
        "TAILSCALE_BIN": str(tmp_path / "no-tailscale"),
        "CULTURE_NODE_TAILNET_WAIT": "0",
    }
    env.update(env_extra or {})
    r = subprocess.run(["sh", str(START)], env=env, capture_output=True, text=True)
    argv = out.read_text().splitlines() if out.exists() else []
    return r, argv, home


def test_start_script_is_executable_posix_sh():
    assert START.read_text().startswith("#!/bin/sh\n")


def test_start_runs_foreground_server_with_state_under_home(tmp_path):
    r, argv, home = _run_start(tmp_path, LOCAL)
    assert r.returncode == 0, r.stderr
    assert argv[:3] == ["server", "start", "--foreground"]
    assert argv[argv.index("--name") + 1] == "node1"
    assert argv[argv.index("--port") + 1] == "6667"
    assert argv[argv.index("--data-dir") + 1] == f"{home}/.culture/data"
    assert "--mesh-config" not in argv


def test_start_uses_mesh_config_when_operator_provided_one(tmp_path):
    r, argv, home = _run_start(tmp_path, LOCAL, mesh=True)
    assert r.returncode == 0, r.stderr
    assert argv[argv.index("--mesh-config") + 1] == f"{home}/.culture/mesh.yaml"


def test_start_clears_stale_pid_file(tmp_path):
    r, _, home = _run_start(tmp_path, LOCAL, stale_pid=True)
    assert r.returncode == 0, r.stderr
    assert not (home / ".culture" / "pids" / "server-node1.pid").exists()


def test_start_defaults_name_to_hostname_and_passes_overrides(tmp_path):
    r, argv, _ = _run_start(
        tmp_path,
        {**LOCAL, "CULTURE_NODE_PORT": "6697", "CULTURE_NODE_EXTRA_ARGS": "--no-persist"},
    )
    assert r.returncode == 0, r.stderr
    assert argv[argv.index("--name") + 1]  # some hostname
    assert argv[argv.index("--port") + 1] == "6697"
    assert argv[-1] == "--no-persist"


def _tailscale_stub(tmp_path, ip):
    stub = tmp_path / "tailscale"
    stub.write_text(f'#!/bin/sh\n[ "$1 $2" = "ip -4" ] && echo {ip}\n')
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return str(stub)


def test_start_listens_on_the_tailnet_address_by_default(tmp_path):
    # r13: the IRC port must not be exposed beyond the tailnet.
    ts = _tailscale_stub(tmp_path, "100.97.170.7")
    r, argv, _ = _run_start(tmp_path, {"CULTURE_NODE_NAME": "node1", "TAILSCALE_BIN": ts})
    assert r.returncode == 0, r.stderr
    assert argv[argv.index("--host") + 1] == "100.97.170.7"


def test_start_exits_75_without_a_tailnet_address(tmp_path):
    r, argv, _ = _run_start(tmp_path, {"CULTURE_NODE_NAME": "node1"})
    assert r.returncode == 75
    assert argv == []  # culture was never started
    assert "no tailnet address" in r.stderr


def test_explicit_loopback_host_starts_without_a_tailnet(tmp_path):
    r, argv, _ = _run_start(
        tmp_path, {"CULTURE_NODE_NAME": "node1", "CULTURE_NODE_HOST": "127.0.0.1"}
    )
    assert r.returncode == 0, r.stderr
    assert argv[argv.index("--host") + 1] == "127.0.0.1"


def test_unit_retries_indefinitely():
    u = _unit()
    assert u["StartLimitIntervalSec"] == ["0"]
    assert u["RestartSec"] == ["30"]


def test_explicit_host_overrides_the_tailnet_default(tmp_path):
    ts = _tailscale_stub(tmp_path, "100.97.170.7")
    r, argv, _ = _run_start(
        tmp_path,
        {"CULTURE_NODE_NAME": "node1", "TAILSCALE_BIN": ts, "CULTURE_NODE_HOST": "10.0.0.5"},
    )
    assert r.returncode == 0, r.stderr
    assert argv[argv.index("--host") + 1] == "10.0.0.5"


def test_start_never_defaults_to_all_interfaces():
    assert "0.0.0.0" not in START.read_text()  # nosec B104 - asserting its absence


def test_start_rejects_unsafe_node_name(tmp_path):
    r, argv, _ = _run_start(tmp_path, {"CULTURE_NODE_NAME": "../evil"})
    assert r.returncode == 78
    assert argv == []


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
def test_start_script_passes_shellcheck():
    subprocess.run(["shellcheck", str(START)], check=True)


def test_env_example_has_no_values_for_secrets():
    text = ENV_EXAMPLE.read_text()
    for line in text.splitlines():
        if line.strip() and not line.startswith("#"):
            assert line.split("=", 1)[0].startswith("CULTURE_NODE_"), line


def test_argon2_bindings_build_without_x86_sse2():
    # Upstream CMake would pass -msse2 to the aarch64 cross compiler.
    text = _python_recipes()["python3-argon2-cffi-bindings"].read_text()
    assert 'export ARGON2_CFFI_USE_SSE2 = "0"' in text


def test_every_recipe_is_reachable_from_culture_node():
    # Catches a dependency lost on the way (e.g. one only named through an
    # extra such as agentfront[mcp]): it would build but never be installed.
    recipes = _python_recipes()
    node = next(NODE.glob("culture-node_*.bb")).read_text()
    seen: set[str] = set()
    todo = _var(node, "RDEPENDS:${PN}").split()
    while todo:
        pn = todo.pop()
        if pn in seen or pn not in recipes:
            continue
        seen.add(pn)
        todo += _var(recipes[pn].read_text(), "RDEPENDS:${PN}").split()
    assert set(recipes) - seen == set()


def test_extras_are_spelled_out():
    recipes = _python_recipes()
    irc_lens = _var(recipes["python3-irc-lens"].read_text(), "RDEPENDS:${PN}").split()
    assert {"python3-mcp", "python3-cryptography"} <= set(irc_lens)
    mcp = _var(recipes["python3-mcp"].read_text(), "RDEPENDS:${PN}").split()
    assert "python3-cryptography" in mcp


def test_build_time_requirements_are_provided():
    recipes = _python_recipes()
    # httpx-sse's sdist lists `wheel` in build-system.requires
    assert "python3-wheel-native" in _var(recipes["python3-httpx-sse"].read_text(), "DEPENDS")
    # mcp's git-tag versioning plugin is replaced by a PV pin
    mcp = recipes["python3-mcp"].read_text()
    assert "uv-dynamic-versioning-native" not in mcp
    assert 'version = "${PV}"' in mcp
