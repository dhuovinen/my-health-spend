"""The Release 0 pages on the Release 1 application tier (phase 1.2, ADR-032): household isolation on every
page, imports by upload with encrypted attachments, and the mhs-admin import migration path."""

import copy
import hashlib
import json

import pytest

from mhs.data.household_store import HouseholdStore
from tests.conftest import SAMPLE, admin_sql
from tests.test_web import CsrfClient

pytestmark = pytest.mark.postgres

MARKER = b"%PDF-1.4 SYNTHETIC-EOB-MARKER-41c2"
DOC_WITH_FILE = "eob-2026-02-10-pcp"


def member(household, name="Household"):
    who = household.enrol(name)
    client = household.sign_in(who)
    return who, CsrfClient(client, household.csrf(client))


def upload_import(client, data: dict, attachments: dict[str, bytes] | None = None, confirm=True, **extra):
    files = [("file", ("ingest.json", json.dumps(data).encode(), "application/json"))]
    files += [("attachments", (name, body, "application/pdf")) for name, body in (attachments or {}).items()]
    preview = client.post("/import", files=files)
    assert preview.status_code == 200, preview.text
    token = preview.text.split('name="token" value="')[1].split('"')[0]
    if confirm:
        r = client.post("/import/confirm", data={"token": token, **extra}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/import?done=1"
    return preview, token


@pytest.fixture
def two(household, app_db):
    a, ca = member(household, "Household A")
    b, cb = member(household, "Household B")
    upload_import(ca, json.loads(SAMPLE.read_text()), {"eob-2026-02-10-pcp.pdf": MARKER})
    ca.post("/notes", data={"provider_id": "prov-pcp", "text": "A's private note"})
    [note] = HouseholdStore(app_db, a.household_id).all("provider_note")
    return household, a, ca, b, cb, note


def test_pages_of_another_household_are_not_found(two):
    household, a, ca, b, cb, note = two
    assert "Bill matches EOB" in ca.get("/visits/v-2026-04-02-pcp").text
    assert ca.get("/providers/prov-pcp?year=2026").status_code == 200
    assert ca.get(f"/files/{DOC_WITH_FILE}").content == MARKER
    for path in ("/visits/v-2026-04-02-pcp", "/providers/prov-pcp?year=2026", f"/files/{DOC_WITH_FILE}"):
        r = cb.get(path)
        assert r.status_code == 404 and r.json() == {"detail": "Not found"}, path
    for path in ("/", "/visits", "/providers", "/settings", "/import"):
        text = cb.get(path).text
        assert "Example Family Medicine" not in text and "prov-pcp" not in text and "A&#39;s private note" not in text
    assert "No visits yet" in cb.get("/").text
    assert cb.get("/settings/export").json()["providers"] == []


def test_another_households_records_cannot_be_changed(two, app_db):
    household, a, ca, b, cb, note = two
    assert cb.post(f"/notes/{note['id']}", data={"provider_id": "prov-pcp", "text": "B was here"}).status_code == 404
    assert cb.post(f"/notes/{note['id']}/delete", data={}).status_code == 404
    assert cb.post("/settings/providers/prov-pcp", data={"name": "Renamed by B"}).status_code == 404
    assert cb.post("/settings/plans/plan-2026", data={"insurer": "B"}).status_code == 404
    assert cb.post("/notes", data={"provider_id": "prov-pcp", "text": "x"}).status_code == 400  # unknown provider
    store_a = HouseholdStore(app_db, a.household_id)
    assert store_a.get("provider_note", note["id"])["text"] == "A's private note"
    assert store_a.get("provider", "prov-pcp")["name"] != "Renamed by B"
    assert HouseholdStore(app_db, b.household_id).edited_ids("provider_note") == set()


def test_import_preview_belongs_to_its_household(household, app_db):
    a, ca = member(household, "A")
    b, cb = member(household, "B")
    _, token = upload_import(ca, json.loads(SAMPLE.read_text()), confirm=False)
    r = cb.post("/import/confirm", data={"token": token}, follow_redirects=False)
    assert r.headers["location"] == "/import"  # B can't confirm A's preview
    assert HouseholdStore(app_db, a.household_id).all("visit") == []
    assert HouseholdStore(app_db, b.household_id).all("visit") == []
    ca.post("/import/confirm", data={"token": token})  # still A's to confirm
    assert len(HouseholdStore(app_db, a.household_id).all("visit")) == 6


def test_owner_edits_and_import_history_are_per_household(household, app_db, pgdb):
    a, ca = member(household, "A")
    b, cb = member(household, "B")
    for c in (ca, cb):
        upload_import(c, json.loads(SAMPLE.read_text()))
    ca.post("/settings/providers/prov-pcp", data={"name": "A's name", "kind": "physician_practice",
                                                  "network_status": "out_of_network"})
    preview_b, _ = upload_import(cb, json.loads(SAMPLE.read_text()), confirm=False)
    assert "Your edits" not in preview_b.text  # A's edit doesn't protect B's records
    preview_a, _ = upload_import(ca, json.loads(SAMPLE.read_text()), confirm=False)
    assert "Your edits" in preview_a.text
    assert admin_sql(pgdb, "SELECT count(*) FROM app.imports WHERE household_id = %s", (b.household_id,))[0][0] == 1
    assert len(HouseholdStore(app_db, a.household_id).imports()) == 1


def test_attachments_are_stored_encrypted_and_hashed(two, app_db):
    household, a, ca, b, cb, note = two
    doc = HouseholdStore(app_db, a.household_id).get("document", DOC_WITH_FILE)
    assert doc["stored_file"] == f"households/{a.household_id}/documents/{DOC_WITH_FILE}"
    assert doc["file_sha256"] == hashlib.sha256(MARKER).hexdigest()  # ING-10
    on_disk = (household.objects_dir / doc["stored_file"]).read_bytes()
    assert MARKER not in on_disk and b"%PDF" not in on_disk
    r = ca.get(f"/files/{DOC_WITH_FILE}")
    assert r.content == MARKER and r.headers["content-disposition"].startswith("attachment;")
    # Re-importing without the attachment keeps the stored file.
    upload_import(ca, json.loads(SAMPLE.read_text()))
    assert HouseholdStore(app_db, a.household_id).get("document", DOC_WITH_FILE)["file_sha256"] == doc["file_sha256"]


def test_missing_attachments_are_warned(household):
    _, c = member(household)
    preview, _ = upload_import(c, json.loads(SAMPLE.read_text()), confirm=False)
    assert "not attached" in preview.text
    preview, _ = upload_import(c, json.loads(SAMPLE.read_text()), {"other.pdf": b"%PDF"}, confirm=False)
    assert "not among the attached files" in preview.text


def test_an_ingest_file_cannot_point_at_stored_files(two, app_db):
    """A file can't set stored_file itself, e.g. to reach another household's object."""
    household, a, ca, b, cb, note = two
    data = json.loads(SAMPLE.read_text())
    target = copy.deepcopy(next(d for d in data["documents"] if d["id"] == DOC_WITH_FILE))
    target.update(id="doc-smuggled", stored_file=f"households/{a.household_id}/documents/{DOC_WITH_FILE}")
    target.pop("file", None)
    data["documents"].append(target)
    files = [("file", ("ingest.json", json.dumps(data).encode(), "application/json"))]
    preview = cb.post("/import", files=files)
    if 'name="token"' in preview.text:  # the schema let the field through: the importer must drop it
        token = preview.text.split('name="token" value="')[1].split('"')[0]
        cb.post("/import/confirm", data={"token": token})
        assert "stored_file" not in HouseholdStore(app_db, b.household_id).get("document", "doc-smuggled")
    assert cb.get("/files/doc-smuggled").status_code == 404


def test_import_by_path_is_not_offered_on_the_server(household):
    _, c = member(household)
    page = c.get("/import").text
    assert 'name="path"' not in page and 'name="attachments"' in page
    r = c.post("/import", data={"path": str(SAMPLE)})
    assert r.status_code == 400 and "Choose a file." in r.text


def test_admin_import_previews_then_saves(household, app_db, pgdb, tmp_path, monkeypatch, capsys):
    """mhs-admin import: the path for migrating Release 0 data into a household."""
    from mhs.web.household import admin

    folder = tmp_path / "export"
    (folder / "files").mkdir(parents=True)
    (folder / "files" / "eob-2026-02-10-pcp.pdf").write_bytes(MARKER)
    (folder / "ingest.json").write_text(SAMPLE.read_text())
    hid = household.accounts.create_household("Migrated")
    monkeypatch.setenv("MHS_DATABASE_URL", pgdb.url("app"))
    monkeypatch.setenv("MHS_KEY_FILE", str(tmp_path / "keys" / "app.kek"))  # the app_keys fixture's file
    monkeypatch.setenv("MHS_OBJECTS_DIR", str(household.objects_dir))

    admin.main(["import", "--household", hid, str(folder / "ingest.json")])
    out = capsys.readouterr().out
    assert "visits: 6 new" in out and "Preview only" in out
    assert HouseholdStore(app_db, hid).all("visit") == []

    admin.main(["import", "--household", hid, str(folder / "ingest.json"), "--yes"])
    assert "saved:" in capsys.readouterr().out
    assert len(HouseholdStore(app_db, hid).all("visit")) == 6
    who = household.enrol(household_id=hid)
    c = household.sign_in(who)
    assert "Example Family Medicine" in c.get("/providers?year=2026").text
    assert c.get(f"/files/{DOC_WITH_FILE}").content == MARKER

    with pytest.raises(SystemExit, match="No such household"):
        admin.main(["import", "--household", "00000000-0000-0000-0000-000000000000", str(folder / "ingest.json")])
    bad = json.loads(SAMPLE.read_text())
    bad["visits"][0]["category"] = "vitamins"
    (folder / "bad.json").write_text(json.dumps(bad))
    with pytest.raises(SystemExit, match="Nothing was saved"):
        admin.main(["import", "--household", hid, str(folder / "bad.json"), "--yes"])
