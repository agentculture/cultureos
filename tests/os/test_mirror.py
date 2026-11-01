"""Offline tests for the local mirror config and os/scripts/refresh-mirror.sh."""

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
KAS = ROOT / "os" / "kas"
SCRIPT = ROOT / "os" / "scripts" / "refresh-mirror.sh"


def _conf(name: str) -> str:
    data = yaml.safe_load((KAS / name).read_text())
    return "\n".join(data["local_conf_header"].values())


def test_mirror_yml_sets_premirrors_and_sstate_mirrors():
    conf = _conf("mirror.yml")
    assert "PREMIRRORS:prepend" in conf
    assert "SSTATE_MIRRORS:prepend" in conf
    assert "file:///repo-ref/downloads/" in conf
    assert "file:///repo-ref/sstate-cache/PATH" in conf
    # https covers softwarecenter.qualcomm.com (QCS8300 boot binaries)
    assert "https?://.*/.*" in conf


def test_mirror_yml_has_no_host_paths():
    text = (KAS / "mirror.yml").read_text()
    assert "/home/" not in text


def test_offline_yml_sets_bb_no_network():
    assert 'BB_NO_NETWORK = "1"' in _conf("offline.yml")


def test_mirror_refresh_yml_generates_tarballs():
    assert 'BB_GENERATE_MIRROR_TARBALLS = "1"' in _conf("mirror-refresh.yml")


def test_refresh_mirror_copies_and_tars_git(tmp_path):
    cache = tmp_path / "cache"
    (cache / "downloads" / "git2" / "host.org.repo.git").mkdir(parents=True)
    (cache / "downloads" / "git2" / "host.org.repo.git" / "HEAD").write_text("ref")
    (cache / "downloads" / "git2" / "old.host.repo").symlink_to("/downloads/git2/host.org.repo.git")
    (cache / "downloads" / "a.tar.gz").write_text("a")
    (cache / "sstate-cache" / "ab").mkdir(parents=True)
    (cache / "sstate-cache" / "ab" / "x.tar.zst").write_text("s")
    mirror = tmp_path / "mirror"
    env = dict(os.environ, CULTUREOS_CACHE_DIR=str(cache), CULTUREOS_MIRROR_DIR=str(mirror))
    for _ in range(2):  # second run must be idempotent
        subprocess.run([str(SCRIPT)], env=env, check=True, capture_output=True)
    assert (mirror / "downloads" / "a.tar.gz").read_text() == "a"
    assert (mirror / "sstate-cache" / "ab" / "x.tar.zst").exists()
    assert not (mirror / "downloads" / "git2").exists()
    assert (mirror / "downloads" / "git2_host.org.repo.git.tar.gz").exists()
    assert (mirror / "downloads" / "git2_host.org.repo.git.tar.gz.done").exists()
    alias = mirror / "downloads" / "git2_old.host.repo.tar.gz"
    assert alias.is_symlink()
    assert alias.resolve().exists()


def test_refresh_mirror_dry_run_writes_nothing(tmp_path):
    cache = tmp_path / "cache"
    (cache / "downloads").mkdir(parents=True)
    (cache / "sstate-cache").mkdir()
    mirror = tmp_path / "mirror"
    env = dict(os.environ, CULTUREOS_CACHE_DIR=str(cache), CULTUREOS_MIRROR_DIR=str(mirror))
    out = subprocess.run([str(SCRIPT), "--dry-run"], env=env, check=True, capture_output=True)
    assert b"dry-run" in out.stdout
    assert not mirror.exists()


def test_refresh_mirror_missing_cache_exits_2(tmp_path):
    env = dict(os.environ, CULTUREOS_CACHE_DIR=str(tmp_path / "none"))
    r = subprocess.run([str(SCRIPT)], env=env, capture_output=True)
    assert r.returncode == 2
