"""Export and delete (PRV-09, ADR-025): TC-PRV-09-1 to TC-PRV-09-3."""

import hashlib
import io
import json
import re
import time
import uuid
import zipfile

import pyotp
import pytest

from mhs.data.household_store import HouseholdStore
from mhs.data.importer import FolderSource, prepare
from tests.conftest import SAMPLE, admin_sql
from tests.pdfs import make_pdf
from tests.test_r1_scenarios import EOB, Member
from tests.test_web import CsrfClient

pytestmark = pytest.mark.postgres


@pytest.fixture
def full(household, app_db, worker_db):
    """A household with imported records, an attached file, an upload read by the worker, and vault entries."""
    m = Member(household, app_db, worker_db)
    preview = m.client.post("/import", files=[
        ("file", ("ingest.json", SAMPLE.read_bytes(), "application/json")),
        ("attachments", ("eob-2026-02-10-pcp.pdf", make_pdf("attached EOB"), "application/pdf"))])
    m.client.post("/import/confirm", data={"token": re.search(r'name="token" value="([^"]+)"', preview.text).group(1)})
    m.upload_id(m.upload("eob.pdf", make_pdf(EOB)))
    m.work()
    return m


def next_code(who) -> str:
    return pyotp.TOTP(who.totp_secret).at(time.time() + 30)  # the current step was used at sign-in


def test_tc_prv_09_1_export_has_every_record_and_file(full, tmp_path, app_db):
    r = full.client.post("/data/export", data={"password": full.who.password})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    manifest = json.loads(z.read("manifest.json"))
    store = full.store
    for kind in ("plan", "provider", "visit", "document", "member"):
        assert manifest["records"][kind] == len(store.all(kind)), kind  # compared with a store inventory
    assert manifest["records"]["original"] == len(store.all("original")) == 1
    for f in manifest["files"]:
        assert hashlib.sha256(z.read(f["path"])).hexdigest() == f["sha256"]
    assert z.read("files/documents/eob-2026-02-10-pcp-eob-2026-02-10-pcp.pdf") == make_pdf("attached EOB")
    upload = json.loads(z.read("uploads.json"))[0]
    assert z.read(upload["file"]) == make_pdf(EOB) and upload["extraction"]["doc_type"] == "eob"
    identifiers = json.loads(z.read("identifiers.json"))
    assert any(e["kind"] == "name" and e["value"] == "pat example" for e in identifiers)

    # The export imports again, with its files, into a fresh household.
    z.extractall(tmp_path / "export")
    hid = str(uuid.uuid4())
    with app_db.tx() as c:
        c.execute("INSERT INTO app.households (id, name) VALUES (%s, 'Restored')", (hid,))
    data = json.loads((tmp_path / "export" / "ingest.json").read_text())
    plan = prepare(data, HouseholdStore(app_db, hid), "export", FolderSource(tmp_path / "export"))
    assert plan.ok and plan.warnings == [] and plan.counts["visits"]["new"] == 6


def test_export_needs_the_password(full):
    assert full.client.post("/data/export", data={"password": "wrong-password-123"}).status_code == 401
    assert full.client.client.post("/data/export", data={"password": full.who.password}).status_code == 403


def test_tc_prv_09_2_and_3_deleting_the_last_member_deletes_the_household(full, pgdb, household):
    hid = full.who.household_id
    cookie = full.client.client.cookies["mhs_session"]
    stored = [p for p in household.objects_dir.rglob("*") if p.is_file()]
    assert stored and admin_sql(pgdb, "SELECT count(*) FROM vault.entries WHERE household_id = %s", (hid,))[0][0] > 0
    assert "deletes all of its data" in full.client.get("/data").text

    r = full.client.post("/data/delete", data={"password": full.who.password, "code": next_code(full.who),
                                               "confirm": "DELETE"})
    assert r.status_code == 200 and "Your account and data are deleted" in r.text and "Reference:" in r.text
    for table in ("app.households", "app.members", "app.records", "app.jobs", "app.household_keys",
                  "app.sessions", "app.imports", "app.owner_edits"):
        column = "id" if table == "app.households" else "household_id"
        assert admin_sql(pgdb, f"SELECT count(*) FROM {table} WHERE {column} = %s", (hid,))[0][0] == 0, table
    assert admin_sql(pgdb, "SELECT count(*) FROM vault.entries WHERE household_id = %s", (hid,))[0][0] == 0
    assert admin_sql(pgdb, "SELECT count(*) FROM vault.household_keys WHERE household_id = %s", (hid,))[0][0] == 0
    assert not any(p.exists() for p in stored)  # originals and attached files gone at once
    [(event,)] = admin_sql(pgdb, "SELECT event FROM app.security_log WHERE household_id = %s "
                                 "AND event = 'household_deleted'", (hid,))
    assert event == "household_deleted"

    # TC-PRV-09-3: no way back in.
    stale = household.client()
    stale.cookies.set("mhs_session", cookie)
    assert stale.get("/api/visits").status_code == 401
    r = household.client().post("/signin", data={"email": full.who.email, "password": full.who.password})
    assert r.status_code == 401


def test_deleting_one_member_keeps_the_household(household, app_db, worker_db, pgdb):
    first = Member(household, app_db, worker_db)
    second = household.enrol(household_id=first.who.household_id)
    raw = household.sign_in(second)
    other = CsrfClient(raw, household.csrf(raw))
    assert "deletes your account only" in other.get("/data").text
    r = other.post("/data/delete", data={"password": second.password, "code": next_code(second), "confirm": "DELETE"})
    assert r.status_code == 200 and "Your account is deleted" in r.text
    assert admin_sql(pgdb, "SELECT count(*) FROM app.members WHERE id = %s", (second.member_id,))[0][0] == 0
    assert first.client.get("/api/session").status_code == 200  # the first member and the data stay
    assert first.store.all("member")  # household records untouched


def test_deletion_needs_confirmation_and_both_factors(full, pgdb):
    hid = full.who.household_id
    assert full.client.post("/data/delete", data={"password": full.who.password, "code": next_code(full.who),
                                                  "confirm": "yes"}).status_code == 400
    assert full.client.post("/data/delete", data={"password": full.who.password, "code": "000000",
                                                  "confirm": "DELETE"}).status_code == 401
    assert full.client.post("/data/delete", data={"password": "wrong-password-123", "code": next_code(full.who),
                                                  "confirm": "DELETE"}).status_code == 401
    assert admin_sql(pgdb, "SELECT count(*) FROM app.households WHERE id = %s", (hid,))[0][0] == 1


def test_deleting_one_household_leaves_another(household, app_db, worker_db, pgdb):
    a = Member(household, app_db, worker_db, "A")
    b = Member(household, app_db, worker_db, "B")
    b.upload_id(b.upload("eob.pdf", make_pdf(EOB)))
    b.work()
    a.client.post("/data/delete", data={"password": a.who.password, "code": next_code(a.who), "confirm": "DELETE"})
    assert admin_sql(pgdb, "SELECT count(*) FROM app.households WHERE id = %s", (b.who.household_id,))[0][0] == 1
    assert b.client.get("/api/uploads").json() and b.store.all("extraction")


def test_security_log_keeps_a_year(app_db, pgdb):
    from mhs.web.household.privacy import log_event

    admin_sql(pgdb, "INSERT INTO app.security_log (event, at) VALUES ('old_event', now() - interval '400 days')")
    log_event(app_db, None, None, "new_event")
    events = [r[0] for r in admin_sql(pgdb, "SELECT event FROM app.security_log")]
    assert "old_event" not in events and "new_event" in events
