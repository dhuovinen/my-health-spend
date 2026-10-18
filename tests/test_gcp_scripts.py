"""The Google Cloud scripts in tools/gcp (docs/GCP_SETUP.md), run with --dry-run: no network, no account. A fake
gcloud, curl, docker and openssl on PATH record any call, and the dry runs must make none. The commands they print
are checked against DEPLOYMENT.md "Identities and access" and against the settings the code reads."""

import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GCP = ROOT / "tools" / "gcp"
PROJECT = "mhs-staging-test"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash")


@pytest.fixture
def fake_bin(tmp_path: Path) -> Path:
    """gcloud, curl, docker and openssl that only log their arguments and fail."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("gcloud", "curl", "docker", "openssl"):
        path = bin_dir / tool
        path.write_text(f'#!/bin/sh\necho "{tool} $*" >> "{tmp_path}/calls.log"\nexit 1\n')
        path.chmod(0o755)
    return bin_dir


def run_script(fake_bin: Path, name: str, *args: str, stdin: str = "", **env: str) -> subprocess.CompletedProcess:
    environ = {"PATH": f"{fake_bin}:/usr/bin:/bin", "HOME": str(fake_bin.parent), "PROJECT_ID": PROJECT,
               "TAG": "testtag", **env}
    return subprocess.run([BASH, str(GCP / name), *args], capture_output=True, text=True, env=environ,
                          input=stdin, cwd=ROOT, timeout=60)


def dry_run(fake_bin: Path, name: str, *args: str, **env: str) -> list[list[str]]:
    """The commands a script prints under --dry-run, each split into words. Fails if it called anything."""
    result = run_script(fake_bin, name, "--dry-run", *args, **env)
    assert result.returncode == 0, result.stdout + result.stderr
    calls = fake_bin.parent / "calls.log"
    assert not calls.exists(), f"dry run called: {calls.read_text()}"
    return [shlex.split(line[2:]) for line in result.stdout.splitlines() if line.startswith("+ ")]


def flag(cmd: list[str], name: str) -> str | None:
    prefix = f"--{name}="
    return next((a[len(prefix):] for a in cmd if a.startswith(prefix)), None)


def find(cmds: list[list[str]], *words: str) -> list[list[str]]:
    return [c for c in cmds if c[:len(words)] == list(words)]


def one(cmds: list[list[str]], *words: str) -> list[str]:
    found = find(cmds, *words)
    assert len(found) == 1, f"{' '.join(words)}: {found}"
    return found[0]


def pairs(value: str) -> dict[str, str]:
    return dict(item.split("=", 1) for item in value.split(","))


def sa(name: str) -> str:
    return f"serviceAccount:{name}@{PROJECT}.iam.gserviceaccount.com"


# --- setup.sh ----------------------------------------------------------------------------------------------

def test_setup_enables_the_apis(fake_bin):
    cmd = one(dry_run(fake_bin, "setup.sh"), "gcloud", "services", "enable")
    for api in ("run", "sqladmin", "secretmanager", "cloudkms", "storage", "documentai", "artifactregistry",
                "servicenetworking", "compute"):
        assert f"{api}.googleapis.com" in cmd
    assert f"--project={PROJECT}" in cmd


def test_setup_creates_private_postgres_17_with_backups(fake_bin):
    cmds = dry_run(fake_bin, "setup.sh")
    sql = one(cmds, "gcloud", "sql", "instances", "create")
    assert flag(sql, "database-version") == "POSTGRES_17"
    assert flag(sql, "region") == "us-east4"
    assert flag(sql, "network") == f"projects/{PROJECT}/global/networks/mhs-vpc"
    assert flag(sql, "ssl-mode") == "ENCRYPTED_ONLY"
    for f in ("--no-assign-ip", "--enable-point-in-time-recovery", "--deletion-protection"):
        assert f in sql
    assert flag(sql, "backup-start-time")
    one(cmds, "gcloud", "services", "vpc-peerings", "connect")
    assert flag(one(cmds, "gcloud", "compute", "addresses", "create"), "purpose") == "VPC_PEERING"
    # The admin password is set from Secret Manager, never shown.
    pw = one(cmds, "gcloud", "sql", "users", "set-password")
    assert flag(pw, "password") == "<SECRET mhs-db-admin-password>"


def test_setup_region_comes_from_the_environment(fake_bin):
    sql = one(dry_run(fake_bin, "setup.sh", "sql", REGION="europe-west3"), "gcloud", "sql", "instances", "create")
    assert flag(sql, "region") == "europe-west3"


def test_setup_locks_down_the_bucket_and_makes_both_keys(fake_bin):
    cmds = dry_run(fake_bin, "setup.sh")
    bucket = one(cmds, "gcloud", "storage", "buckets", "create")
    assert bucket[4] == f"gs://{PROJECT}-originals"
    assert "--uniform-bucket-level-access" in bucket and "--public-access-prevention" in bucket
    assert "--versioning" in one(cmds, "gcloud", "storage", "buckets", "update")
    assert [c[4] for c in find(cmds, "gcloud", "kms", "keys", "create")] == ["app", "vault"]


def test_setup_grants_exactly_the_roles_in_deployment_md(fake_bin):
    cmds = dry_run(fake_bin, "setup.sh")
    accounts = [c[4] for c in find(cmds, "gcloud", "iam", "service-accounts", "create")]
    assert accounts == ["mhs-app", "mhs-vault", "mhs-worker", "mhs-worker-ai", "mhs-migrate"]

    project_roles = {(flag(c, "member"), flag(c, "role")) for c in find(cmds, "gcloud", "projects",
                                                                         "add-iam-policy-binding")}
    assert project_roles == {(sa(a), "roles/cloudsql.client") for a in accounts} | {
        (sa("mhs-app"), "roles/documentai.apiUser")}
    bucket_roles = {(flag(c, "member"), flag(c, "role")) for c in find(cmds, "gcloud", "storage", "buckets",
                                                                        "add-iam-policy-binding")}
    assert bucket_roles == {(sa("mhs-app"), "roles/storage.objectUser")}
    key_roles = {(c[4], flag(c, "member"), flag(c, "role")) for c in find(cmds, "gcloud", "kms", "keys",
                                                                           "add-iam-policy-binding")}
    assert key_roles == {("app", sa("mhs-app"), "roles/cloudkms.cryptoKeyEncrypterDecrypter"),
                         ("vault", sa("mhs-vault"), "roles/cloudkms.cryptoKeyEncrypterDecrypter")}
    secret_access = {(c[3], flag(c, "member")) for c in find(cmds, "gcloud", "secrets", "add-iam-policy-binding")}
    assert secret_access == {
        ("mhs-db-admin-password", sa("mhs-migrate")),
        ("mhs-db-app-password", sa("mhs-migrate")), ("mhs-db-worker-password", sa("mhs-migrate")),
        ("mhs-db-vault-password", sa("mhs-migrate")),
        ("mhs-db-app-password", sa("mhs-app")), ("mhs-vault-token", sa("mhs-app")),
        ("mhs-member-password", sa("mhs-app")),
        ("mhs-db-vault-password", sa("mhs-vault")), ("mhs-vault-token", sa("mhs-vault")),
        ("mhs-db-worker-password", sa("mhs-worker")), ("mhs-db-worker-password", sa("mhs-worker-ai")),
    }
    # The worker holds no bucket or key access (TC-PRV-06-3).
    assert all(sa("mhs-worker") not in (flag(c, "member") or "") for c in cmds if "storage" in c or "kms" in c)


def test_setup_generates_secret_values_without_showing_them(fake_bin):
    result = run_script(fake_bin, "setup.sh", "--dry-run", "secrets")
    adds = [line for line in result.stdout.splitlines() if "secrets versions add" in line]
    assert len(adds) == 6
    assert all(line.startswith("+ openssl rand -hex 32 | gcloud secrets versions add mhs-") for line in adds)
    assert "--data-file=-" in adds[0]


def test_setup_makes_the_registry_and_the_ocr_processor(fake_bin):
    cmds = dry_run(fake_bin, "setup.sh")
    assert flag(one(cmds, "gcloud", "artifacts", "repositories", "create"), "repository-format") == "docker"
    docai = one(cmds, "docai_curl", "-X", "POST")
    assert '"type": "OCR_PROCESSOR"' in docai[docai.index("-d") + 1]
    assert docai[-1] == f"https://us-documentai.googleapis.com/v1/projects/{PROJECT}/locations/us/processors"


def test_setup_checks_before_creating(fake_bin):
    lines = run_script(fake_bin, "setup.sh", "--dry-run").stdout.splitlines()
    creates = [i for i, line in enumerate(lines) if re.match(r"\+ (gcloud .* create |gcloud services vpc-peerings "
                                                             r"connect|openssl .* versions add )", line)]
    assert len(creates) > 20
    assert all(lines[i - 1].startswith("? ") for i in creates), [lines[i] for i in creates if lines[i - 1][0] != "?"]


def test_setup_rejects_an_unknown_step(fake_bin):
    result = run_script(fake_bin, "setup.sh", "--dry-run", "everything")
    assert result.returncode != 0 and "unknown step" in result.stderr


# --- deploy.sh ---------------------------------------------------------------------------------------------

def settings_the_code_reads() -> set[str]:
    """Every MHS_ name in src/mhs, plus MHS_X and MHS_X_FILE for each secret("X")."""
    names: set[str] = set()
    for path in (ROOT / "src" / "mhs").rglob("*.py"):
        text = path.read_text()
        names |= set(re.findall(r"\b(MHS_[A-Z0-9_]+)\b", text))
        for name in re.findall(r"""secret\(["']([A-Z0-9_]+)["']""", text):
            names |= {f"MHS_{name}", f"MHS_{name}_FILE"}
    return names


def deploys(fake_bin, *args, **env) -> dict[str, list[str]]:
    cmds = dry_run(fake_bin, "deploy.sh", *args, **env)
    out = {}
    for c in cmds:
        if c[:3] == ["gcloud", "run", "deploy"] or c[:4] in (["gcloud", "run", "jobs", "deploy"],
                                                            ["gcloud", "run", "worker-pools", "deploy"]):
            out[c[c.index("deploy") + 1]] = c
    return out


def test_deploy_uses_only_settings_the_code_reads(fake_bin):
    known = settings_the_code_reads()
    for name, cmd in deploys(fake_bin, "--with-ai", MHS_AI_PROXY="http://proxy.internal:3128").items():
        env = pairs(flag(cmd, "set-env-vars"))
        assert set(env) <= known, f"{name}: {set(env) - known} not read by the code"
        mounts = pairs(flag(cmd, "set-secrets"))
        for key, value in env.items():
            if key.endswith("_FILE"):
                assert value in mounts, f"{name}: {key}={value} has no secret mounted there"
        assert all(v.endswith(":latest") for v in mounts.values())
        # Cloud Run mounts each secret as its own folder.
        folders = [str(Path(p).parent) for p in mounts]
        assert len(folders) == len(set(folders)), name


def test_deploy_services_and_jobs(fake_bin):
    d = deploys(fake_bin)
    assert set(d) == {"mhs-migrate", "mhs-vault", "mhs-app", "mhs-worker", "mhs-admin"}
    image = f"us-east4-docker.pkg.dev/{PROJECT}/mhs/mhs:testtag"
    assert all(flag(c, "image") == image for c in d.values())

    app = d["mhs-app"]
    env = pairs(flag(app, "set-env-vars"))
    assert flag(app, "ingress") == "all" and "--allow-unauthenticated" in app
    assert flag(app, "service-account") == sa("mhs-app").split(":")[1]
    assert env["MHS_COOKIE_SECURE"] == "1"
    assert env["MHS_PUBLIC_URL"] == "https://mhs-app-<PROJECT_NUMBER>.us-east4.run.app"
    assert env["MHS_VAULT_URL"] == "https://mhs-vault-<PROJECT_NUMBER>.us-east4.run.app"
    assert env["MHS_KEYS"] == "kms" and env["MHS_KMS_KEY"].endswith("/keyRings/mhs/cryptoKeys/app")
    assert env["MHS_OBJECT_STORE"] == "gcs" and env["MHS_GCS_BUCKET"] == f"{PROJECT}-originals"
    assert env["MHS_OCR_ENGINE"] == "documentai" and env["MHS_DOCAI_PROCESSOR"] == "<DOCAI_PROCESSOR>"
    assert env["MHS_DB_USER"] == "mhs_app"
    assert "--proxy-headers" in flag(app, "args")

    vault = d["mhs-vault"]
    env = pairs(flag(vault, "set-env-vars"))
    assert flag(vault, "ingress") == "internal" and "--allow-unauthenticated" not in vault
    assert env["MHS_KMS_KEY"].endswith("/cryptoKeys/vault") and env["MHS_DB_USER"] == "mhs_vault"
    assert flag(vault, "port") == "8100" and env["MHS_HOST"] == "0.0.0.0"

    worker = d["mhs-worker"]
    env = pairs(flag(worker, "set-env-vars"))
    assert worker[:4] == ["gcloud", "run", "worker-pools", "deploy"]
    assert flag(worker, "network-tags") == "mhs-no-egress" and flag(worker, "vpc-egress") == "all-traffic"
    assert env["MHS_DB_USER"] == "mhs_worker" and env["MHS_EXTRACTOR"] == "rules"
    assert not {"MHS_KMS_KEY", "MHS_GCS_BUCKET", "MHS_VAULT_URL"} & set(env)
    assert list(pairs(flag(worker, "set-secrets")).values()) == ["mhs-db-worker-password:latest"]

    migrate = d["mhs-migrate"]
    assert migrate[:4] == ["gcloud", "run", "jobs", "deploy"] and flag(migrate, "args") == "migrate"
    assert flag(migrate, "service-account") == sa("mhs-migrate").split(":")[1]
    assert pairs(flag(migrate, "set-env-vars"))["MHS_DB_ADMIN_USER"] == "postgres"

    admin = d["mhs-admin"]
    assert flag(admin, "service-account") == sa("mhs-app").split(":")[1]
    assert "MHS_PUBLIC_URL" in pairs(flag(admin, "set-env-vars"))


def test_deploy_runs_migrate_before_the_services(fake_bin):
    cmds = dry_run(fake_bin, "deploy.sh")
    migrate = cmds.index(one(cmds, "gcloud", "run", "jobs", "execute", "mhs-migrate"))
    assert migrate < cmds.index(one(cmds, "gcloud", "run", "deploy", "mhs-vault"))


def test_deploy_builds_from_committed_files_for_cloud_run(fake_bin):
    result = run_script(fake_bin, "deploy.sh", "--dry-run", "image")
    assert ("+ git archive --format=tar HEAD | docker buildx build --platform=linux/amd64 --target=runtime "
            f"--tag=us-east4-docker.pkg.dev/{PROJECT}/mhs/mhs:testtag --push -") in result.stdout


def test_ai_worker_needs_its_proxy(fake_bin):
    assert "mhs-worker-ai" not in deploys(fake_bin)
    result = run_script(fake_bin, "deploy.sh", "--dry-run", "worker-ai")
    assert result.returncode != 0 and "MHS_AI_PROXY" in result.stderr
    ai = deploys(fake_bin, "worker-ai", MHS_AI_PROXY="http://proxy.internal:3128")["mhs-worker-ai"]
    env = pairs(flag(ai, "set-env-vars"))
    assert env["MHS_EXTRACTOR"] == "claude" and env["MHS_AI_PROXY"] == "http://proxy.internal:3128"
    assert pairs(flag(ai, "set-secrets"))[env["MHS_ANTHROPIC_API_KEY_FILE"]] == "mhs-anthropic-api-key:latest"


# --- admin.sh, check.sh, teardown.sh -----------------------------------------------------------------------

def test_admin_runs_the_job_and_reads_its_output(fake_bin):
    cmds = dry_run(fake_bin, "admin.sh", "create-household", "Staging household")
    execute = one(cmds, "gcloud", "run", "jobs", "execute", "mhs-admin")
    assert flag(execute, "args") == '^|^-c|exec mhs-admin "$@"|mhs-admin|create-household|Staging household'
    assert "--wait" in execute
    one(cmds, "gcloud", "logging", "read")


def test_admin_add_member_reads_a_generated_password(fake_bin):
    result = run_script(fake_bin, "admin.sh", "--dry-run", "add-member", "--household", "h1", "--email",
                        "a@example.com", "--name", "A Member")
    assert "+ openssl rand -base64 18 | gcloud secrets versions add mhs-member-password" in result.stdout
    assert "--password-stdin < /secrets/member/password|mhs-admin|add-member|--household|h1" in result.stdout


def test_admin_refuses_the_argument_delimiter(fake_bin):
    result = run_script(fake_bin, "admin.sh", "--dry-run", "create-household", "a|b")
    assert result.returncode != 0


def test_check_lists_the_staging_checks(fake_bin):
    result = run_script(fake_bin, "check.sh", "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "expect: refused" in result.stdout and "absent_from mhs-worker" in result.stdout
    assert not (fake_bin.parent / "calls.log").exists()


def test_teardown_deletes_everything_in_dry_run(fake_bin):
    cmds = dry_run(fake_bin, "teardown.sh")
    assert "--no-deletion-protection" in one(cmds, "gcloud", "sql", "instances", "patch")
    one(cmds, "gcloud", "sql", "instances", "delete")
    assert "--all-versions" in one(cmds, "gcloud", "storage", "rm")
    assert len(find(cmds, "gcloud", "secrets", "delete")) == 7
    assert len(find(cmds, "gcloud", "iam", "service-accounts", "delete")) == 5
    one(cmds, "gcloud", "compute", "networks", "delete")
    assert len(find(cmds, "gcloud", "kms", "keys", "versions", "destroy")) == 2
    assert not find(cmds, "gcloud", "projects", "delete")
    assert one(dry_run(fake_bin, "teardown.sh", "--delete-project"), "gcloud", "projects", "delete")[3] == PROJECT


def test_teardown_needs_the_project_id_typed(fake_bin):
    result = run_script(fake_bin, "teardown.sh", stdin="yes\n")
    assert result.returncode != 0 and "nothing was deleted" in result.stderr
    assert not (fake_bin.parent / "calls.log").exists()


@pytest.mark.parametrize("script", ["setup.sh", "deploy.sh", "check.sh", "teardown.sh"])
def test_scripts_refuse_production_and_need_a_project(fake_bin, script):
    result = run_script(fake_bin, script, "--dry-run", PROJECT_ID="mhs-production")
    assert result.returncode != 0 and "staging" in result.stderr
    result = run_script(fake_bin, script, "--dry-run", PROJECT_ID="")
    assert result.returncode != 0 and "PROJECT_ID" in result.stderr


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck isn't installed")
def test_shellcheck():
    scripts = sorted(str(p) for p in GCP.glob("*.sh"))
    result = subprocess.run(["shellcheck", "-x", "-P", str(GCP), *scripts], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout
