import json
import uuid
from pathlib import Path

import pytest

from mhs.config import ROOT, Config
from mhs.data.importer import commit, prepare
from mhs.data.store import Store

SAMPLE = ROOT / "samples" / "example-ingest.json"


@pytest.fixture
def sample_data() -> dict:
    return json.loads(SAMPLE.read_text())


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(data_dir=tmp_path / "data")


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def store(request, config: Config):
    """Release 0's SQLite store, and a household's Postgres store with the same interface (ADR-032)."""
    if request.param == "sqlite":
        return Store(config.db_path)
    from mhs.data.household_store import HouseholdStore

    db = request.getfixturevalue("app_db")
    hid = str(uuid.uuid4())
    with db.tx() as c:
        c.execute("INSERT INTO app.households (id, name) VALUES (%s, 'Importer test')", (hid,))
    return HouseholdStore(db, hid)


@pytest.fixture
def loaded_store(store: Store, config: Config, sample_data: dict) -> Store:
    plan = prepare(sample_data, store, str(SAMPLE), SAMPLE.parent)
    assert plan.ok, plan.errors
    commit(plan, store, config.documents_dir)
    return store


# --- Release 1 fixtures (Postgres, keys, vault, application tier) ---------------------------

import secrets  # noqa: E402
from dataclasses import dataclass  # noqa: E402

import psycopg  # noqa: E402
import pyotp  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from mhs.data.db import Database  # noqa: E402
from mhs.data.keys import LocalKeyFile, db_keyring  # noqa: E402
from mhs.data.objects import LocalObjectStore  # noqa: E402
from mhs.stack import AppConfig  # noqa: E402
from mhs.vault.client import VaultClient  # noqa: E402
from mhs.vault.service import create_app as create_vault_app  # noqa: E402
from mhs.vault.store import VaultStore  # noqa: E402
from mhs.web.household.app import create_app as create_household_app  # noqa: E402
from mhs.web.household.auth import Accounts  # noqa: E402
from tests.pg import PgServer, TestDatabase  # noqa: E402

VAULT_TOKEN = secrets.token_urlsafe(32)


@pytest.fixture(scope="session")
def pg_server():
    if not PgServer.available():
        pytest.skip("no Postgres: set MHS_TEST_DATABASE_ADMIN_URL, or start Docker for a throwaway server")
    server = PgServer()
    yield server
    server.close()


@pytest.fixture(scope="session")
def pgdb(pg_server) -> TestDatabase:
    return pg_server.create_database()


@pytest.fixture(scope="session")
def tier_dbs(pgdb):
    dbs = {tier: Database(pgdb.url(tier), max_size=4) for tier in ("app", "worker", "vault")}
    yield dbs
    for db in dbs.values():
        db.close()


def admin_sql(pgdb: TestDatabase, query: str, params=()):
    """Run a query as the admin (owner) role, outside row-level security. Returns rows."""
    with psycopg.connect(pgdb.admin_url, autocommit=True) as c:
        cur = c.execute(query, params)
        return cur.fetchall() if cur.description else []


@pytest.fixture
def clean_db(pgdb, tier_dbs):
    admin_sql(pgdb, "TRUNCATE app.households, vault.household_keys, vault.entries CASCADE")
    return tier_dbs


@pytest.fixture
def app_db(clean_db) -> Database:
    return clean_db["app"]


@pytest.fixture
def worker_db(clean_db) -> Database:
    return clean_db["worker"]


@pytest.fixture
def vault_db(clean_db) -> Database:
    return clean_db["vault"]


@pytest.fixture
def app_keys(tmp_path) -> LocalKeyFile:
    return LocalKeyFile.create(tmp_path / "keys" / "app.kek")


@pytest.fixture
def vault_keys(tmp_path) -> LocalKeyFile:
    return LocalKeyFile.create(tmp_path / "keys" / "vault.kek")


@pytest.fixture
def app_keyring(app_db, app_keys):
    return db_keyring(app_db, app_keys, "app.household_keys")


@pytest.fixture
def vault_store(vault_db, vault_keys) -> VaultStore:
    return VaultStore(vault_db, db_keyring(vault_db, vault_keys, "vault.household_keys"))


@pytest.fixture
def vault_client(vault_store) -> VaultClient:
    return VaultClient("http://vault", VAULT_TOKEN, http=TestClient(create_vault_app(vault_store, VAULT_TOKEN)))


@pytest.fixture
def accounts(app_db, app_keyring) -> Accounts:
    return Accounts(app_db, app_keyring)


@dataclass
class Enrolled:
    household_id: str
    member_id: str
    email: str
    password: str
    totp_secret: str

    def code(self) -> str:
        return pyotp.TOTP(self.totp_secret).now()


class Household:
    """The application tier under test, with helpers to enrol members and sign them in."""

    def __init__(self, app, accounts: Accounts, objects_dir: Path):
        self.app = app
        self.accounts = accounts
        self.objects_dir = objects_dir

    def enrol(self, household_name: str = "Household", household_id: str | None = None) -> Enrolled:
        hid = household_id or self.accounts.create_household(household_name)
        email = f"member-{uuid.uuid4().hex[:8]}@example.test"
        password = secrets.token_urlsafe(18)
        member, totp_secret = self.accounts.add_member(hid, email, "Test Member", password)
        return Enrolled(hid, member.id, email, password, totp_secret)

    def client(self) -> TestClient:
        return TestClient(self.app)

    def sign_in(self, who: Enrolled) -> TestClient:
        c = self.client()
        r = c.post("/signin", data={"email": who.email, "password": who.password}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/signin/mfa", r.text
        r = c.post("/signin/mfa", data={"code": who.code(), "csrf_token": csrf_from(c.get("/signin/mfa").text)},
                   follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/", r.text
        return c

    def csrf(self, client: TestClient) -> str:
        return client.get("/api/session").json()["csrf_token"]


def csrf_from(html: str) -> str:
    import re

    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert m, "no csrf token in page"
    return m.group(1)


@pytest.fixture
def household(tmp_path, app_db, app_keyring, vault_client, accounts) -> Household:
    objects_dir = tmp_path / "objects"
    config = AppConfig(database_url="unused", objects_dir=objects_dir, key_file=tmp_path / "unused",
                       vault_url="http://vault", vault_token=VAULT_TOKEN)
    app = create_household_app(config, db=app_db, keyring=app_keyring, objects=LocalObjectStore(objects_dir),
                               vault=vault_client)
    return Household(app, accounts, objects_dir)
