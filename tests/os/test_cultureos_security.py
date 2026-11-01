"""Offline checks for the cultureos-security recipe (plan task t12, covers h24).

Acceptance 1: an sshd_config drop-in with PasswordAuthentication no and
PermitRootLogin no. Acceptance 2: the OSTree remote sets sign-verify=true
with the release public key, and an unsigned commit is refused with a logged
reason (the ostree pull test below; it runs only where an ostree with
ed25519 support is available, see docs/os/security.md).
"""

import base64
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RECIPE_DIR = ROOT / "os" / "meta-cultureos" / "recipes-core" / "cultureos-security"
RECIPE = RECIPE_DIR / "cultureos-security_1.0.bb"
DROPIN = RECIPE_DIR / "files" / "01-cultureos-hardening.conf"
REMOTE_TEMPLATE = RECIPE_DIR / "files" / "ostree-remote.conf.in"
OSTREE_BBAPPEND = RECIPE_DIR / "ostree_%.bbappend"

# The first lines of the upstream /etc/ssh/sshd_config in cultureos-image
# (openssh 10.6p1 from oe-core, plus allow-root-login / allow-empty-password
# image features): the Include comes first, then the permissive values.
UPSTREAM_SSHD_CONFIG = """\
Include {dropin_dir}/*.conf
PermitRootLogin yes
AuthorizedKeysFile .ssh/authorized_keys
PermitEmptyPasswords yes
KbdInteractiveAuthentication no
UsePAM yes
"""


def _sshd_keywords(text: str) -> dict[str, str]:
    """First value of each keyword, lower-cased (sshd: first match wins)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(" ")
        out.setdefault(key.lower(), value.strip())
    return out


def _bb_value(text: str, name: str) -> str:
    m = re.search(rf'^{re.escape(name)}\s*\??=\s*"(.*)"\s*$', text, re.M)
    assert m, f"{name} not set in recipe"
    return m.group(1)


# --- acceptance 1: sshd drop-in -------------------------------------------------


def test_recipe_files_exist():
    assert RECIPE.is_file()
    assert DROPIN.is_file()
    assert REMOTE_TEMPLATE.is_file()
    assert OSTREE_BBAPPEND.is_file()


def test_dropin_is_key_only_and_no_root():
    kw = _sshd_keywords(DROPIN.read_text())
    assert kw["passwordauthentication"] == "no"
    assert kw["permitrootlogin"] == "no"
    assert kw["permitemptypasswords"] == "no"
    assert kw["kbdinteractiveauthentication"] == "no"
    assert kw["authenticationmethods"] == "publickey"


def test_dropin_sorts_before_other_dropins():
    # sshd reads sshd_config.d/*.conf in lexical order and keeps the first
    # value; the image already ships 20-systemd-userdb.conf.
    assert DROPIN.name < "20-systemd-userdb.conf"


def test_recipe_installs_dropin_and_remote():
    text = RECIPE.read_text()
    assert "${sysconfdir}/ssh/sshd_config.d" in text
    assert "01-cultureos-hardening.conf" in text
    assert "${sysconfdir}/ostree/remotes.d" in text
    assert re.search(r'^RDEPENDS:\$\{PN\} = ".*openssh-sshd.*"', text, re.M)


@pytest.mark.skipif(not Path("/usr/sbin/sshd").exists(), reason="no OpenSSH sshd on this host")
def test_dropin_wins_over_upstream_sshd_config(tmp_path):
    """sshd -T on the upstream main config plus the drop-in: the drop-in wins."""
    dropin_dir = tmp_path / "sshd_config.d"
    dropin_dir.mkdir()
    shutil.copy(DROPIN, dropin_dir / DROPIN.name)
    main = tmp_path / "sshd_config"
    main.write_text(UPSTREAM_SSHD_CONFIG.format(dropin_dir=dropin_dir))
    hostkey = tmp_path / "hostkey"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(hostkey)],
        check=True,
        capture_output=True,
    )
    proc = subprocess.run(
        ["/usr/sbin/sshd", "-T", "-f", str(main), "-h", str(hostkey)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    eff = _sshd_keywords(proc.stdout)
    assert eff["permitrootlogin"] == "no"
    assert eff["passwordauthentication"] == "no"
    assert eff["permitemptypasswords"] == "no"
    assert eff["authenticationmethods"] == "publickey"


# --- acceptance 2: signed OSTree remote ----------------------------------------


def test_remote_template_requires_ed25519_signature():
    text = REMOTE_TEMPLATE.read_text()
    assert re.search(r'^\[remote "@REMOTE@"\]$', text, re.M)
    keys = dict(line.split("=", 1) for line in text.splitlines() if "=" in line and line[0] != "#")
    assert keys["url"] == "@URL@"
    assert keys["sign-verify"] == "true"
    assert keys["gpg-verify"] == "false"
    assert keys["verification-ed25519-file"] == "@PUBKEY_PATH@"


def test_recipe_url_and_key_are_configurable():
    text = RECIPE.read_text()
    # placeholder default: the Spark over MagicDNS; t17 defines the real one
    assert _bb_value(text, "CULTUREOS_OSTREE_URL").startswith(
        "http://spark.tail0be7e0.ts.net:8650/"
    )
    assert "keys/" in _bb_value(text, "CULTUREOS_OSTREE_PUBKEY_FILE")
    assert _bb_value(text, "CULTUREOS_OSTREE_PUBKEY_PATH").startswith("${datadir}/")
    # the remote is named after the OSTree stateroot (ota-ext4 deploys
    # ${OSTREE_OSNAME}:${OSTREE_BRANCHNAME})
    assert _bb_value(text, "CULTUREOS_OSTREE_REMOTE") == "${OSTREE_OSNAME}"
    for name in ("CULTUREOS_OSTREE_URL", "CULTUREOS_OSTREE_PUBKEY_PATH"):
        assert re.search(rf"^{name} \?=", text, re.M), f"{name} must be a weak default"


def test_no_key_material_in_recipe_dir():
    for path in RECIPE_DIR.rglob("*"):
        if path.is_file():
            text = path.read_text()
            assert "PRIVATE KEY" not in text, path
            assert not re.search(r"[A-Za-z0-9+/]{43}=", text), f"key-like blob in {path}"


def test_ostree_bbappend_enables_ed25519():
    text = OSTREE_BBAPPEND.read_text()
    assert re.search(r'^PACKAGECONFIG:append = ".*\bed25519-libsodium\b.*"$', text, re.M)


# --- acceptance 2: refusal of an unsigned commit (needs an ostree binary) -----


def _ostree_cmd() -> list[str] | None:
    """The ostree to test with: $CULTUREOS_TEST_OSTREE (a command line) or PATH."""
    env = os.environ.get("CULTUREOS_TEST_OSTREE")
    if env:
        return shlex.split(env)
    found = shutil.which("ostree")
    return [found] if found else None


def _ostree_skip_reason() -> str | None:
    cmd = _ostree_cmd()
    if cmd is None:
        return "no ostree binary (install ostree or set CULTUREOS_TEST_OSTREE)"
    if shutil.which("openssl") is None:
        return "no openssl to make a throwaway ed25519 key"
    proc = subprocess.run([*cmd, "--version"], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return f"{cmd} --version failed: {proc.stderr.strip()}"
    if "sign-ed25519" not in proc.stdout:
        return f"{cmd} has no sign-ed25519 feature (built without libsodium/openssl)"
    return None


def _ed25519_keypair(tmp_path: Path, name: str) -> tuple[str, Path]:
    """A throwaway key: (base64 secret for `ostree sign`, file with base64 public)."""
    pem = tmp_path / f"{name}.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "ed25519", "-out", str(pem)],
        check=True,
        capture_output=True,
    )
    priv_der = subprocess.run(
        ["openssl", "pkey", "-in", str(pem), "-outform", "DER"],
        check=True,
        capture_output=True,
    ).stdout
    pub_der = subprocess.run(
        ["openssl", "pkey", "-in", str(pem), "-pubout", "-outform", "DER"],
        check=True,
        capture_output=True,
    ).stdout
    seed, pub = priv_der[-32:], pub_der[-32:]
    pub_file = tmp_path / f"{name}.pub"
    pub_file.write_text(base64.b64encode(pub).decode() + "\n")
    # libsodium secret key = seed || public key
    return base64.b64encode(seed + pub).decode(), pub_file


class _Ostree:
    def __init__(self, cmd: list[str]):
        self.cmd = cmd

    def __call__(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        proc = subprocess.run([*self.cmd, *args], capture_output=True, text=True, check=False)
        if check and proc.returncode != 0:
            raise AssertionError(f"ostree {' '.join(args)} failed: {proc.stderr}")
        return proc


@pytest.fixture
def signed_remote(tmp_path):
    """A server repo with signed and unsigned refs, and a client using the template."""
    reason = _ostree_skip_reason()
    if reason:
        pytest.skip(reason)
    ostree = _Ostree(_ostree_cmd())
    secret, pub_file = _ed25519_keypair(tmp_path, "release")
    other_secret, _ = _ed25519_keypair(tmp_path, "other")

    srv = tmp_path / "srv"
    ostree("init", f"--repo={srv}", "--mode=archive")
    commits = {}
    for ref, key in (("signed", secret), ("unsigned", None), ("wrongkey", other_secret)):
        tree = tmp_path / f"tree-{ref}"
        (tree / "usr").mkdir(parents=True)
        (tree / "usr" / "marker").write_text(ref + "\n")
        out = ostree("commit", f"--repo={srv}", f"--branch={ref}", f"--tree=dir={tree}")
        commits[ref] = out.stdout.strip()
        if key:
            ostree("sign", f"--repo={srv}", "--sign-type=ed25519", commits[ref], key)
    ostree("summary", f"--repo={srv}", "--update")

    cli = tmp_path / "cli"
    ostree("init", f"--repo={cli}", "--mode=bare-user")
    remote = (
        REMOTE_TEMPLATE.read_text()
        .replace("@REMOTE@", "cultureos")
        .replace("@URL@", f"file://{srv}")
        .replace("@PUBKEY_PATH@", str(pub_file))
    )
    with (cli / "config").open("a") as fh:
        fh.write("\n" + remote)
    return ostree, cli, commits, pub_file


def _refused(proc: subprocess.CompletedProcess) -> None:
    assert proc.returncode != 0, "pull was accepted"
    # the reason ostree logs (on the device the update agent forwards it to
    # the journal)
    assert re.search(r"sign|signature", proc.stderr, re.I), proc.stderr


def test_unsigned_commit_is_refused(signed_remote):
    ostree, cli, commits, _ = signed_remote
    _refused(ostree("pull", f"--repo={cli}", "cultureos", "unsigned", check=False))
    assert ostree("rev-parse", f"--repo={cli}", "cultureos:unsigned", check=False).returncode


def test_commit_signed_with_other_key_is_refused(signed_remote):
    ostree, cli, _, _ = signed_remote
    _refused(ostree("pull", f"--repo={cli}", "cultureos", "wrongkey", check=False))


def test_signed_commit_is_accepted(signed_remote):
    ostree, cli, commits, _ = signed_remote
    ostree("pull", f"--repo={cli}", "cultureos", "signed")
    rev = ostree("rev-parse", f"--repo={cli}", "cultureos:signed").stdout.strip()
    assert rev == commits["signed"]


def test_missing_key_file_fails_closed(signed_remote):
    ostree, cli, _, pub_file = signed_remote
    pub_file.unlink()
    proc = ostree("pull", f"--repo={cli}", "cultureos", "signed", check=False)
    assert proc.returncode != 0, "pull accepted without a key file"
    assert re.search(r"key", proc.stderr, re.I), proc.stderr
