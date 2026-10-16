"""Release 1 stack: runtime settings for the app, worker and vault, and the `mhs-stack` setup commands.

Settings come from environment variables. Any secret can be given directly (MHS_X) or as a file (MHS_X_FILE);
on the Docker Compose stack the `setup` job writes the files into a volume and each service mounts only its own
folder of it (ADR-031).
"""

import argparse
import base64
import os
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

APP_PORT = 3063  # registered in ~/Projects/app-registry as my-health-spend-r1; Release 0 keeps 3062
VAULT_PORT = 8100  # inside the compose network only, never published


def secret(name: str, default: str | None = None) -> str | None:
    """Read MHS_<name>, or the file named by MHS_<name>_FILE."""
    value = os.environ.get(f"MHS_{name}")
    if value:
        return value
    path = os.environ.get(f"MHS_{name}_FILE")
    if path:
        return Path(path).read_text().strip()
    return default


def database_url(user_env: str = "DB_USER") -> str:
    """MHS_DATABASE_URL, or one built from MHS_DB_HOST, MHS_DB_NAME, MHS_DB_USER and the DB_PASSWORD secret."""
    url = os.environ.get("MHS_DATABASE_URL")
    if url:
        return url
    host = os.environ.get("MHS_DB_HOST", "localhost")
    name = os.environ.get("MHS_DB_NAME", "mhs")
    user = os.environ.get(f"MHS_{user_env}")
    password = secret("DB_PASSWORD")
    if not user or not password:
        raise SystemExit("Set MHS_DATABASE_URL, or MHS_DB_USER and MHS_DB_PASSWORD(_FILE).")
    return f"postgresql://{quote(user)}:{quote(password)}@{host}:5432/{quote(name)}"


@dataclass(frozen=True)
class AppConfig:
    database_url: str
    objects_dir: Path
    key_file: Path
    vault_url: str
    vault_token: str
    host: str = "127.0.0.1"
    port: int = APP_PORT
    cookie_secure: bool = False  # True once served over TLS (staging, production)
    session_idle_minutes: int = 15
    session_max_hours: int = 12


def load_app_config() -> AppConfig:
    return AppConfig(
        database_url=database_url(),
        objects_dir=Path(os.environ.get("MHS_OBJECTS_DIR", "/srv/objects")),
        key_file=Path(os.environ.get("MHS_KEY_FILE", "/run/secrets/mhs/kek")),
        vault_url=os.environ.get("MHS_VAULT_URL", f"http://vault:{VAULT_PORT}"),
        vault_token=secret("VAULT_TOKEN") or "",
        host=os.environ.get("MHS_HOST", "127.0.0.1"),
        port=int(os.environ.get("MHS_APP_PORT", str(APP_PORT))),
        cookie_secure=os.environ.get("MHS_COOKIE_SECURE", "") == "1",
        session_idle_minutes=int(os.environ.get("MHS_SESSION_IDLE_MINUTES", "15")),
        session_max_hours=int(os.environ.get("MHS_SESSION_MAX_HOURS", "12")),
    )


# --- setup: secrets for the local stack -------------------------------------------------------

# Each logical secret and the service folders that get a copy of it.
SECRET_LAYOUT = {
    "pg_admin": [("postgres", "admin_password"), ("migrate", "admin_password")],
    "db_app": [("migrate", "db_app_password"), ("app", "db_password")],
    "db_worker": [("migrate", "db_worker_password"), ("worker", "db_password")],
    "db_vault": [("migrate", "db_vault_password"), ("vault", "db_password")],
    "vault_token": [("app", "vault_token"), ("vault", "vault_token")],
    "app_kek": [("app", "kek")],
    "vault_kek": [("vault", "kek")],
}
# Owner uid of each folder: postgres runs as uid 70 in the alpine image, the mhs image as 10001.
FOLDER_UID = {"postgres": 70, "migrate": 10001, "app": 10001, "worker": 10001, "vault": 10001}


def _new_value(name: str) -> str:
    if name.endswith("_kek"):
        return base64.b64encode(secrets.token_bytes(32)).decode()
    return secrets.token_urlsafe(32)


def init_secrets(root: Path, chown: bool = True) -> list[str]:
    """Create any missing secret files under root; existing values are kept. Returns the files written."""
    written = []
    for name, copies in SECRET_LAYOUT.items():
        existing = [root / d / f for d, f in copies if (root / d / f).exists()]
        value = existing[0].read_text().strip() if existing else _new_value(name)
        for folder, filename in copies:
            path = root / folder / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(value + "\n")
                written.append(str(path.relative_to(root)))
    for folder, uid in FOLDER_UID.items():
        path = root / folder
        path.mkdir(parents=True, exist_ok=True)
        for f in path.iterdir():
            f.chmod(0o400)
            if chown:
                os.chown(f, uid, uid)
        path.chmod(0o500)
        if chown:
            os.chown(path, uid, uid)
    return written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mhs-stack", description="Set up the Release 1 Docker Compose stack.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init-secrets", help="generate missing database passwords, the vault token and key files")
    p.add_argument("root", type=Path)
    p.add_argument("--no-chown", action="store_true")
    sub.add_parser("migrate", help="create roles and apply database migrations (admin connection)")
    args = parser.parse_args(argv)

    if args.command == "init-secrets":
        written = init_secrets(args.root, chown=not args.no_chown)
        print(f"secrets: {len(written)} file(s) created" + (f": {', '.join(written)}" if written else ""))
    elif args.command == "migrate":
        from mhs.data.migrate import Roles, migrate

        host = os.environ.get("MHS_DB_HOST", "postgres")
        name = os.environ.get("MHS_DB_NAME", "mhs")
        admin = os.environ.get("MHS_DB_ADMIN_USER", "postgres")
        url = f"postgresql://{quote(admin)}:{quote(secret('DB_ADMIN_PASSWORD') or '')}@{host}:5432/{quote(name)}"
        passwords = {
            "app": secret("DB_APP_PASSWORD"),
            "worker": secret("DB_WORKER_PASSWORD"),
            "vault": secret("DB_VAULT_PASSWORD"),
        }
        if not all(passwords.values()):
            sys.exit("migrate: role passwords missing (MHS_DB_APP_PASSWORD, ..._WORKER_..., ..._VAULT_...)")
        applied = migrate(url, Roles(), passwords)
        print(f"migrate: {len(applied)} migration(s) applied" + (f": {', '.join(applied)}" if applied else ""))


if __name__ == "__main__":
    main()
