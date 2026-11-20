"""Records database and job queue on Postgres: migrations, roles, row-level security, the worker."""

import secrets
import threading
import uuid

import psycopg
import pytest
from psycopg import sql

from mhs.data.migrate import MIGRATIONS, RoleError, Roles, migrate
from mhs.data.queue import JobQueue
from mhs.data.records import HouseholdRecords
from mhs.ingest.worker import run_once
from tests.conftest import admin_sql
from tests.pg import with_db

pytestmark = pytest.mark.postgres


def new_household(pgdb, name="H") -> str:
    hid = str(uuid.uuid4())
    admin_sql(pgdb, "INSERT INTO app.households (id, name) VALUES (%s, %s)", (hid, name))
    return hid


def test_migrations_are_applied_once(pgdb, clean_db):
    assert migrate(pgdb.admin_url, pgdb.roles, pgdb.passwords) == []
    names = [r[0] for r in admin_sql(pgdb, "SELECT name FROM public.schema_migrations")]
    assert names == sorted(p.stem for p in MIGRATIONS.glob("*.sql"))
    assert names[:2] == ["001_foundation", "002_release0_port"]


def test_migrations_rerun_as_an_admin_that_is_not_superuser(pg_server):
    """Cloud SQL's `postgres` has CREATEROLE and CREATEDB but isn't a superuser: a second run must still work, and a
    tier role that gained rights stops it rather than being silently trusted."""
    admin, password = "t" + secrets.token_hex(4) + "_admin", secrets.token_urlsafe(16)
    db = "mhs_test_" + secrets.token_hex(4)
    roles = Roles(app=f"{admin}_app", worker=f"{admin}_worker", vault=f"{admin}_vault")
    passwords = {k: secrets.token_urlsafe(16) for k in ("app", "worker", "vault")}
    with psycopg.connect(pg_server.server_url, autocommit=True) as c:
        c.execute(sql.SQL("CREATE ROLE {} LOGIN CREATEROLE CREATEDB PASSWORD {}").format(
            sql.Identifier(admin), sql.Literal(password)))
        c.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(db), sql.Identifier(admin)))
    pg_server.databases.append(db)
    url = with_db(pg_server.server_url, db, admin, password)
    assert migrate(url, roles, passwords)  # first run: creates the roles and applies everything
    passwords["app"] = secrets.token_urlsafe(16)
    assert migrate(url, roles, passwords) == []  # second run: only sets the passwords
    with psycopg.connect(with_db(pg_server.server_url, db, roles.app, passwords["app"])) as c:
        assert c.execute("SELECT current_user").fetchone()[0] == roles.app
    with psycopg.connect(pg_server.server_url, autocommit=True) as c:
        c.execute(sql.SQL("ALTER ROLE {} BYPASSRLS").format(sql.Identifier(roles.worker)))
    with pytest.raises(RoleError, match=roles.worker):
        migrate(url, roles, passwords)


def test_records_crud_scoped_to_household(pgdb, app_db):
    a, b = new_household(pgdb, "A"), new_household(pgdb, "B")
    ra, rb = HouseholdRecords(app_db, a), HouseholdRecords(app_db, b)
    ra.put("visit", {"id": "v1", "total": 12345})
    ra.put("visit", {"id": "v1", "total": 100})  # upsert
    rb.put("visit", {"id": "v1", "total": 999})  # same id in another household is a different record
    assert ra.get("visit", "v1") == {"id": "v1", "total": 100}
    assert rb.get("visit", "v1") == {"id": "v1", "total": 999}
    assert ra.count("visit") == 1 and [v["id"] for v in ra.all("visit")] == ["v1"]
    assert ra.delete("visit", "v1") and not ra.delete("visit", "v1")
    assert rb.get("visit", "v1") is not None


def test_row_level_security_hides_other_households(pgdb, app_db):
    """Even a query with no household filter sees only the household set on the transaction (PRV-11)."""
    a, b = new_household(pgdb), new_household(pgdb)
    HouseholdRecords(app_db, a).put("visit", {"id": "va"})
    HouseholdRecords(app_db, b).put("visit", {"id": "vb"})
    with app_db.tx(b) as c:
        assert [r["id"] for r in c.execute("SELECT id FROM app.records")] == ["vb"]
    with app_db.tx() as c:  # no household set: nothing
        assert c.execute("SELECT count(*) AS n FROM app.records").fetchone()["n"] == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege):  # can't write into another household
        with app_db.tx(b) as c:
            c.execute("INSERT INTO app.records (household_id, kind, id, data) VALUES (%s, 'visit', 'x', '{}')", (a,))


@pytest.mark.parametrize("table", ["vault.entries", "vault.household_keys"])
def test_app_role_cannot_read_the_vault(app_db, table):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with app_db.tx() as c:
            c.execute(f"SELECT * FROM {table}")


@pytest.mark.parametrize("table", ["vault.entries", "vault.household_keys", "app.household_keys", "app.members",
                                   "app.sessions", "app.households"])
def test_worker_role_cannot_read_keys_accounts_or_vault(worker_db, table):
    """TC-PRV-06-3: the back-end tier can't reach the vault, the wrapped keys, or member credentials."""
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with worker_db.tx() as c:
            c.execute(f"SELECT * FROM {table}")


@pytest.mark.parametrize("table", ["app.records", "app.members", "app.household_keys"])
def test_vault_role_cannot_read_app_tables(vault_db, table):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with vault_db.tx() as c:
            c.execute(f"SELECT * FROM {table}")


def test_queue_enqueue_claim_complete(pgdb, app_db, worker_db):
    a, b = new_household(pgdb), new_household(pgdb)
    app_q, worker_q = JobQueue(app_db), JobQueue(worker_db)
    job_a = app_q.enqueue(a, "ping", {"n": 1})
    app_q.enqueue(b, "ping")
    assert app_q.status(a, job_a) == "queued"
    assert app_q.status(b, job_a) is None  # another household's job doesn't exist for b
    claimed = worker_q.claim()
    assert (claimed.id, claimed.household_id, claimed.payload, claimed.attempts) == (job_a, a, {"n": 1}, 1)
    worker_q.complete(claimed)
    assert app_q.status(a, job_a) == "done"


def test_queue_retries_then_fails(pgdb, app_db, worker_db):
    hid = new_household(pgdb)
    job_id = JobQueue(app_db).enqueue(hid, "ping", max_attempts=2)
    q = JobQueue(worker_db)
    q.fail(q.claim(), "boom")
    assert JobQueue(app_db).status(hid, job_id) == "queued"
    assert q.claim() is None  # backed off
    admin_sql(pgdb, "UPDATE app.jobs SET run_after = now() WHERE id = %s", (job_id,))
    job = q.claim()
    assert job.attempts == 2
    q.fail(job, "boom again")
    assert JobQueue(app_db).status(hid, job_id) == "failed"
    assert admin_sql(pgdb, "SELECT last_error FROM app.jobs WHERE id = %s", (job_id,))[0][0] == "boom again"


def test_concurrent_claims_never_share_a_job(pgdb, app_db, worker_db):
    hid = new_household(pgdb)
    for _ in range(20):
        JobQueue(app_db).enqueue(hid, "ping")
    claimed, lock = [], threading.Lock()

    def drain():
        q = JobQueue(worker_db)
        while (job := q.claim()) is not None:
            with lock:
                claimed.append(job.id)

    threads = [threading.Thread(target=drain) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(claimed) == 20 and len(set(claimed)) == 20


def test_worker_runs_ping_and_records_failures(pgdb, app_db, worker_db):
    hid = new_household(pgdb)
    ping = JobQueue(app_db).enqueue(hid, "ping")
    unknown = JobQueue(app_db).enqueue(hid, "nope", max_attempts=1)
    q = JobQueue(worker_db)
    assert run_once(q, worker_db).id == ping
    assert run_once(q, worker_db).id == unknown
    assert run_once(q, worker_db) is None
    assert JobQueue(app_db).status(hid, ping) == "done"
    assert JobQueue(app_db).status(hid, unknown) == "failed"
    assert HouseholdRecords(app_db, hid).get("job_result", f"job-{ping}")["kind"] == "ping"
