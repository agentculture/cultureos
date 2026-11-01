"""Offline checks for the meta-cultureos layer skeleton and the pinned kas manifest (t5)."""

import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LAYER = ROOT / "os" / "meta-cultureos"
KAS = ROOT / "os" / "kas" / "cultureos.yml"
LOCK = ROOT / "os" / "kas" / "cultureos.lock.yml"
SHA = re.compile(r"^[0-9a-f]{40}$")

# Acceptance 2: the repos the plan names explicitly, plus everything the
# upstream ci includes pull in (they would otherwise float on a branch).
REQUIRED_REPOS = {
    "meta-qcom",
    "meta-qcom-arduino",
    "meta-qcom-distro",
    "meta-updater",
    "oe-core",
    "bitbake",
    "meta-openembedded",
    "meta-security",
    "meta-selinux",
    "meta-virtualization",
    "meta-audioreach",
    "meta-ai",
}


def _bb_assignments(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        m = re.match(r'^([A-Za-z0-9_:\-\[\]]+)\s*=\s*"(.*)"\s*$', line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def test_layer_files_exist():
    assert (LAYER / "conf" / "layer.conf").is_file()
    assert (LAYER / "conf" / "distro" / "cultureos.conf").is_file()
    assert (LAYER / "recipes-core" / "images" / "cultureos-image.bb").is_file()


def test_layer_conf_declares_collection():
    text = (LAYER / "conf" / "layer.conf").read_text()
    assert 'BBFILE_COLLECTIONS += "cultureos"' in text
    assert "LAYERSERIES_COMPAT_cultureos" in text
    for dep in ("qcom", "qcom-distro", "sota"):
        assert re.search(rf"^\s+{re.escape(dep)} \\$", text, re.M), dep


def test_distro_requires_sota_and_drops_uptane_client():
    text = (LAYER / "conf" / "distro" / "cultureos.conf").read_text()
    assert "require conf/distro/qcom-distro-sota.conf" in text
    vals = _bb_assignments(text)
    # decision c35: no Uptane client, no aktualizr provisioning
    assert vals["SOTA_CLIENT"] == ""
    assert vals["SOTA_CLIENT_PROV"] == ""
    assert vals["SOTA_DEPLOY_CREDENTIALS"] == "0"
    # decision c39: keep upstream systemd-boot, never override it here
    assert not any(k.startswith(("EFI_PROVIDER", "OSTREE_BOOTLOADER")) for k in vals)


def test_image_recipe_has_integration_slot():
    # t19 fills the slot; tests/os/test_image_integration.py checks its contents.
    text = (LAYER / "recipes-core" / "images" / "cultureos-image.bb").read_text()
    assert re.search(r"^CULTUREOS_PACKAGES = ", text, re.M)
    assert "${CULTUREOS_PACKAGES}" in text
    assert "aktualizr" not in text


def test_kas_manifest_pins_every_repo_by_sha():
    cfg = yaml.safe_load(KAS.read_text())
    assert cfg["distro"] == "cultureos"
    assert cfg["target"] == ["cultureos-image"]
    includes = {(i["repo"], i["file"]) for i in cfg["header"]["includes"]}
    assert ("meta-qcom-arduino", "ci/ventuno-q.yml") in includes
    assert ("meta-qcom", "ci/qcom-distro-sota.yml") in includes
    repos = cfg["repos"]
    assert REQUIRED_REPOS <= set(repos)
    for name, repo in repos.items():
        if name == "cultureos":  # this repo: local, no url
            assert "url" not in repo
            assert "os/meta-cultureos" in repo["layers"]
            continue
        assert SHA.match(str(repo.get("commit", ""))), f"{name} not pinned by commit"


def test_lock_file_agrees_with_manifest():
    cfg = yaml.safe_load(KAS.read_text())
    lock = yaml.safe_load(LOCK.read_text())
    assert lock["header"]["version"] >= 14
    locked = lock["overrides"]["repos"]
    for name, repo in cfg["repos"].items():
        if name == "cultureos":
            continue
        assert locked[name]["commit"] == repo["commit"], name


def test_kas_manifest_caps_build_threads():
    cfg = yaml.safe_load(KAS.read_text())
    conf = "\n".join(cfg["local_conf_header"].values())
    assert 'BB_NUMBER_THREADS = "8"' in conf
    assert 'PARALLEL_MAKE = "-j 8"' in conf


def test_no_rollout_cli_under_os():
    # acceptance 4: plain OSTree pull, no rollout-cli anywhere under os/
    proc = subprocess.run(
        ["grep", "-rIl", "rollout-cli", str(ROOT / "os")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1, proc.stdout
