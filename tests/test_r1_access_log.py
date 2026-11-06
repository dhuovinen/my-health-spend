"""Access log (PRV-10, ADR-040): TC-PRV-10-1 and TC-PRV-10-2."""

import re

import psycopg
import pytest

from tests.conftest import SAMPLE, admin_sql
from tests.pdfs import make_pdf
from tests.test_r1_scenarios import EOB, Member

pytestmark = pytest.mark.postgres


def entries(pgdb, hid: str) -> list[tuple]:
    return admin_sql(pgdb, "SELECT member_id::text, action, kind, record_id FROM app.access_log WHERE household_id = %s "
                           "ORDER BY id", (hid,))


def test_tc_prv_10_1_reads_and_changes_are_logged(household, app_db, worker_db, pgdb):
    m = Member(household, app_db, worker_db)
    who, c = m.who, m.client
    preview = c.post("/import", files=[("file", ("i.json", SAMPLE.read_bytes(), "application/json")),
                                       ("attachments", ("eob-2026-02-10-pcp.pdf", make_pdf("attached"), "application/pdf"))])
    c.post("/import/confirm", data={"token": re.search(r'name="token" value="([^"]+)"', preview.text).group(1)})
    c.get("/visits/v-2026-04-02-pcp")
    c.get("/files/eob-2026-02-10-pcp")
    c.post("/settings/providers/prov-pcp", data={"name": "Example Family Medicine", "kind": "physician_practice",
                                                 "network_status": "in_network"})
    c.post("/notes", data={"provider_id": "prov-pcp", "text": "Called billing"})
    [note] = m.store.all("provider_note")
    c.post(f"/notes/{note['id']}/delete", data={})
    uid = m.upload_id(m.upload("eob.pdf", make_pdf(EOB)))
    m.work()
    c.get(f"/uploads/{uid}/review")
    c.get(f"/uploads/{uid}")
    c.post("/data/export", data={"password": who.password})

    log = entries(pgdb, who.household_id)
    assert all(member == who.member_id for member, *_ in log)  # every entry names the member
    seen = {(action, kind, rid) for _, action, kind, rid in log}
    for expected in [("create", "visit", "v-2026-04-02-pcp"), ("view", "visit", "v-2026-04-02-pcp"),
                     ("download", "document", "eob-2026-02-10-pcp"), ("change", "provider", "prov-pcp"),
                     ("create", "provider_note", note["id"]), ("delete", "provider_note", note["id"]),
                     ("create", "original", uid), ("view", "original", uid), ("download", "original", uid),
                     ("export", "household", who.household_id)]:
        assert expected in seen, expected
    [(at,)] = admin_sql(pgdb, "SELECT max(at) FROM app.access_log WHERE household_id = %s", (who.household_id,))
    assert at is not None  # and when


def test_tc_prv_10_2_members_see_the_log_and_cannot_edit_it(household, app_db, worker_db, pgdb):
    m = Member(household, app_db, worker_db)
    m.client.post("/settings/members", data={"name": "Jordan Example", "relationship": "spouse"})
    page = m.client.get("/data").text
    assert "Access log" in page and "Test Member" in page and "mbr-jordan-example" in page
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with app_db.tx(m.who.household_id) as c:
            c.execute("UPDATE app.access_log SET action = 'view' WHERE household_id = %s", (m.who.household_id,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with app_db.tx(m.who.household_id) as c:
            c.execute("DELETE FROM app.access_log WHERE household_id = %s", (m.who.household_id,))


def test_the_log_stays_in_its_household(household, app_db, worker_db, pgdb):
    a = Member(household, app_db, worker_db, "A")
    b = Member(household, app_db, worker_db, "B")
    a.client.post("/settings/accounts", data={"name": "HSA", "type": "hsa"})
    assert "acct-hsa" in a.client.get("/data").text
    assert "acct-hsa" not in b.client.get("/data").text
    with app_db.tx(b.who.household_id) as c:  # row-level security: B's transaction can't see A's entries
        assert c.execute("SELECT count(*) AS n FROM app.access_log WHERE household_id = %s",
                         (a.who.household_id,)).fetchone()["n"] == 0


def test_background_work_is_not_logged_as_a_member(household, app_db, worker_db, pgdb):
    m = Member(household, app_db, worker_db)
    uid = m.upload_id(m.upload("eob.pdf", make_pdf(EOB)))
    m.work()  # the worker writes the extraction: not a member's action
    kinds = [(action, kind) for _, action, kind, rid in entries(pgdb, m.who.household_id) if rid == uid]
    assert kinds == [("create", "original")]
