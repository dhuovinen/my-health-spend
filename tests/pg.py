"""Throwaway Postgres for the Release 1 tests.

Uses MHS_TEST_DATABASE_ADMIN_URL (or MHS_TEST_DB_HOST plus MHS_TEST_DB_ADMIN_PASSWORD_FILE, as the compose
`tests` runner sets) when given; otherwise starts a postgres container with Docker for the test session.
Each session gets fresh databases and its own tier roles, so it never touches a stack's own data or roles.
"""

import os
import secrets
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from psycopg import sql

from mhs.data.migrate import Roles, migrate

IMAGE = "postgres:17-alpine"


def with_db(url: str, db: str, user: str | None = None, password: str | None = None) -> str:
    u = urlsplit(url)
    netloc = u.netloc
    if user is not None:
        host = netloc.split("@", 1)[-1]
        netloc = f"{quote(user)}:{quote(password or '')}@{host}"
    return urlunsplit((u.scheme, netloc, "/" + db, u.query, u.fragment))


def _wait(url: str, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            with psycopg.connect(url, connect_timeout=2) as c:
                c.execute("SELECT 1")
            return
        except psycopg.OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.3)


@dataclass
class TestDatabase:
    __test__ = False
    admin_url: str
    roles: Roles
    passwords: dict[str, str]

    def url(self, tier: str) -> str:
        return with_db(self.admin_url, urlsplit(self.admin_url).path.lstrip("/"),
                       self.roles.as_dict()[tier], self.passwords[tier])


class PgServer:
    def __init__(self):
        self.container = None
        url = os.environ.get("MHS_TEST_DATABASE_ADMIN_URL")
        if not url and os.environ.get("MHS_TEST_DB_HOST"):
            password = Path(os.environ["MHS_TEST_DB_ADMIN_PASSWORD_FILE"]).read_text().strip()
            url = f"postgresql://postgres:{quote(password)}@{os.environ['MHS_TEST_DB_HOST']}:5432/postgres"
        if not url:
            url = self._start_container()
        self.server_url = url
        _wait(url)
        prefix = "t" + secrets.token_hex(4)
        self.roles = Roles(app=f"{prefix}_app", worker=f"{prefix}_worker", vault=f"{prefix}_vault")
        self.passwords = {k: secrets.token_urlsafe(16) for k in ("app", "worker", "vault")}
        self.databases: list[str] = []

    @staticmethod
    def available() -> bool:
        if os.environ.get("MHS_TEST_DATABASE_ADMIN_URL") or os.environ.get("MHS_TEST_DB_HOST"):
            return True
        if not shutil.which("docker"):
            return False
        return subprocess.run(["docker", "info"], capture_output=True).returncode == 0

    def _start_container(self) -> str:
        password = secrets.token_urlsafe(16)
        out = subprocess.run(
            ["docker", "run", "-d", "--rm", "-e", f"POSTGRES_PASSWORD={password}", "-p", "127.0.0.1::5432",
             "--label", "mhs-tests=1", IMAGE],
            check=True, capture_output=True, text=True,
        )
        self.container = out.stdout.strip()
        mapping = subprocess.run(["docker", "port", self.container, "5432/tcp"], check=True, capture_output=True,
                                 text=True).stdout.strip().splitlines()[0]
        return f"postgresql://postgres:{quote(password)}@127.0.0.1:{mapping.rsplit(':', 1)[1]}/postgres"

    def create_database(self) -> TestDatabase:
        name = "mhs_test_" + secrets.token_hex(4)
        with psycopg.connect(self.server_url, autocommit=True) as c:
            c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        self.databases.append(name)
        admin_url = with_db(self.server_url, name)
        migrate(admin_url, self.roles, self.passwords)
        return TestDatabase(admin_url, self.roles, self.passwords)

    def close(self) -> None:
        if self.container:
            subprocess.run(["docker", "rm", "-f", self.container], capture_output=True)
            return
        with psycopg.connect(self.server_url, autocommit=True) as c:
            for name in self.databases:
                c.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
            for role in self.roles.as_dict().values():
                c.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
