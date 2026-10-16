"""TC-PRV-11-2: two households; neither can reach the other's records, files, jobs or vault entries."""

import pytest

from tests.pdfs import make_pdf

from mhs.data.records import HouseholdRecords

pytestmark = pytest.mark.postgres

NOT_FOUND = {"detail": "Not found"}
A_PDF = make_pdf("household A only")


@pytest.fixture
def two(household, app_db):
    a, b = household.enrol("Household A"), household.enrol("Household B")
    ca, cb = household.sign_in(a), household.sign_in(b)
    HouseholdRecords(app_db, a.household_id).put("visit", {"id": "visit-a", "provider": "Clinic A"})
    HouseholdRecords(app_db, b.household_id).put("visit", {"id": "visit-b", "provider": "Clinic B"})
    r = ca.post("/uploads", files={"file": ("a-eob.pdf", A_PDF, "application/pdf")},
                data={"csrf_token": household.csrf(ca)}, follow_redirects=False)
    doc_a = r.headers["location"].split("uploaded=")[1]
    return household, a, b, ca, cb, doc_a


def test_visits_and_documents_of_another_household_are_not_found(two):
    household, a, b, ca, cb, doc_a = two
    # A sees its own.
    assert ca.get("/api/visits/visit-a").json()["provider"] == "Clinic A"
    assert ca.get(f"/api/uploads/{doc_a}").json()["filename"] == "a-eob.pdf"
    assert ca.get(f"/uploads/{doc_a}").content == A_PDF
    # B asks for A's ids: the same 404 as an id that doesn't exist, nothing of A's in the body.
    for path in (f"/api/uploads/{doc_a}", "/api/visits/visit-a", f"/uploads/{doc_a}"):
        r = cb.get(path)
        assert r.status_code == 404 and r.json() == NOT_FOUND, path
        missing = cb.get(path.replace(doc_a, "upl_000000000000000000000000").replace("visit-a", "visit-zz"))
        assert (missing.status_code, missing.json()) == (r.status_code, r.json())
    # Lists hold only the member's own household.
    assert [v["id"] for v in cb.get("/api/visits").json()] == ["visit-b"]
    assert cb.get("/api/uploads").json() == []
    assert "a-eob.pdf" not in cb.get("/uploads").text and "Household A" not in cb.get("/uploads").text


def test_jobs_of_another_household_are_not_found(two):
    household, a, b, ca, cb, doc_a = two
    job = ca.post("/api/jobs/ping", headers={"x-csrf-token": household.csrf(ca)}).json()["job_id"]
    assert ca.get(f"/api/jobs/{job}").json()["status"] == "queued"
    r = cb.get(f"/api/jobs/{job}")
    assert r.status_code == 404 and r.json() == NOT_FOUND


def test_bad_ids_leak_nothing(two):
    household, a, b, ca, cb, doc_a = two
    for path in ("/api/uploads/..%2F..%2Fetc", "/api/visits/" + "x" * 200, "/api/jobs/not-a-number"):
        r = cb.get(path)
        assert r.status_code in (400, 404) and set(r.json()) == {"detail"}, path
        assert "x" * 20 not in r.text and "etc" not in r.text


def test_original_files_are_stored_per_household(two):
    household, a, b, ca, cb, doc_a = two
    files = [p for p in household.objects_dir.rglob("*") if p.is_file()]
    assert [p.relative_to(household.objects_dir).parts[:2] for p in files] == [("households", a.household_id)]


def test_vault_entries_are_per_household(vault_client, accounts):
    a, b = accounts.create_household("A"), accounts.create_household("B")
    token_a = vault_client.tokenize(a, "name", "Pat Example")
    assert vault_client.tokenize(a, "name", "Pat Example") == token_a  # stable within a household
    assert vault_client.detokenize(a, token_a) == ("name", "Pat Example")
    assert vault_client.detokenize(b, token_a) is None  # B can't resolve A's token
    assert vault_client.tokenize(b, "name", "Pat Example") != token_a  # same value, different household


def test_vault_service_requires_its_token(vault_store):
    from fastapi.testclient import TestClient

    from mhs.vault.service import create_app

    c = TestClient(create_app(vault_store, "s" * 40))
    hid = "11111111-1111-1111-1111-111111111111"
    assert c.post(f"/v1/households/{hid}/tokens", json={"kind": "name", "value": "x"}).status_code == 401
    assert c.post(f"/v1/households/{hid}/tokens", json={"kind": "name", "value": "x"},
                  headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = {"Authorization": "Bearer " + "s" * 40}
    assert c.get("/v1/households/not-a-uuid/tokens/tok_x", headers=ok).status_code == 404
    assert c.post(f"/v1/households/{hid}/tokens", json={"kind": "Bad Kind", "value": "x"}, headers=ok).status_code == 422
    assert c.get("/health").json() == {"status": "ok"}
    with pytest.raises(RuntimeError):
        create_app(vault_store, "short")
