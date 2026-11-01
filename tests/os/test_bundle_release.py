"""Offline tests for os/scripts/bundle-release.sh on a fixture deploy dir."""

import io
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "os" / "scripts" / "bundle-release.sh"


def _flash_tar(path: Path, names: list[str]) -> None:
    with tarfile.open(path, "w:gz") as tf:
        for n in names:
            info = tarfile.TarInfo(n)
            info.size = 3
            tf.addfile(info, io.BytesIO(b"bin"))


def _fixture(tmp_path: Path, *, license_file=True, flash=("aop.mbn", "xbl.elf")) -> Path:
    deploy = tmp_path / "deploy"
    img = deploy / "images" / "ventuno-q"
    img.mkdir(parents=True)
    _flash_tar(img / "cultureos-image-ventuno-q.rootfs-1.qcomflash.tar.gz", list(flash))
    (img / "cultureos-image-ventuno-q.rootfs-1.ostreecommit.tar.zst").write_bytes(b"zst")
    fw = deploy / "licenses" / "allarch" / "firmware-qcom-boot-qcs8300"
    fw.mkdir(parents=True)
    (fw / "recipeinfo").write_text("LICENSE: LicenseRef-LICENSE.qcom-2\n")
    if license_file:
        (fw / "LICENSE.qcom-2").write_text("QUALCOMM LICENSE\n")
    other = deploy / "licenses" / "aarch64" / "glib-2.0-native"
    other.mkdir(parents=True)
    (other / "glib.h").write_text("/* unrelated native recipe */\n")
    return deploy


def _run(tmp_path: Path, deploy: Path) -> tuple[subprocess.CompletedProcess, Path]:
    out = tmp_path / "out"
    proc = subprocess.run(
        ["bash", str(SCRIPT), str(deploy), str(out), "t"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc, out


def test_bundle_manifest_lists_license_and_no_source(tmp_path):
    proc, out = _run(tmp_path, _fixture(tmp_path))
    assert proc.returncode == 0, proc.stderr
    tarball = out / "cultureos-release-t.tar"
    assert tarball.is_file()
    with tarfile.open(tarball) as tf:
        names = tf.getnames()
        manifest = tf.extractfile("cultureos-release-t/MANIFEST.sha256").read().decode()
    assert any(n.endswith("/LICENSE.qcom-2") for n in names)
    assert "LICENSE.qcom-2" in manifest
    assert "images/cultureos-image-ventuno-q.rootfs-1.qcomflash.tar.gz" in manifest
    assert not any(n.endswith((".c", ".h", ".S", ".patch")) for n in names)
    assert not list(out.glob(".stage.*"))


def test_missing_license_fails_and_leaves_no_tarball(tmp_path):
    proc, out = _run(tmp_path, _fixture(tmp_path, license_file=False))
    assert proc.returncode != 0
    assert "LICENSE.qcom-2" in proc.stderr
    assert not list(out.glob("*.tar"))


def test_firmware_source_in_flash_bundle_fails(tmp_path):
    proc, out = _run(tmp_path, _fixture(tmp_path, flash=("aop.mbn", "fw/src/main.c")))
    assert proc.returncode != 0
    assert "source-like" in proc.stderr
    assert not list(out.glob("*.tar"))
