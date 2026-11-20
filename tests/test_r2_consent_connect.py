"""Release 1 parts of ADR-054 and ADR-055: consent before collection (CMP-02), the privacy notice (CMP-03), and the
insurer connection end to end against a fake payer (ING-09)."""

import io
import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from mhs.data.household_store import HouseholdStore
from mhs.ingest import fhir
from mhs.web.household import connect
from mhs.web.household.features import REQUIRE_CONSENT, Features
from tests.fhir_fixtures import bundle, eob

pytestmark = pytest.mark.postgres

PAYER = fhir.Payer("examplehealth", "Example Health", "https://fhir.example.test/r4", "https://auth.example.test/a",
                   "https://auth.example.test/t", "client-1")


def csrf(household, client):
    return household.csrf(client)


def give(household, client, collection=True, ai=False):
    data = {"csrf_token": csrf(household, client)}
    if collection:
        data["collection"] = "on"
    if ai:
        data["ai_sharing"] = "on"
    return client.post("/consent", data=data, follow_redirects=False)


def upload(household, client):
    return client.post("/uploads", data={"csrf_token": csrf(household, client), "kind": "auto"},
                       files={"file": ("eob.txt", io.BytesIO(b"x"), "text/plain")}, follow_redirects=False)


def test_privacy_notice_is_public(household):
    r = household.client().get("/privacy-notice")
    assert r.status_code == 200 and "Who else sees it" in r.text and "draft" in r.text


def test_tc_cmp_02_1_nothing_collected_before_opt_in(household, app_db):
    who = household.enrol()
    Features(app_db).set(REQUIRE_CONSENT, True)
    c = household.sign_in(who)
    form = c.get("/consent").text.split('action="/consent"')[1].split("</form>")[0]
    assert "checked" not in form  # both boxes start unticked
    r = upload(household, c)
    assert r.status_code == 400 and "consent" in r.text
    r = c.post("/import", data={"csrf_token": csrf(household, c)},
               files={"file": ("x.json", io.BytesIO(b"{}"), "application/json")})
    assert r.status_code == 403
    assert give(household, c).status_code == 303
    assert "without your consent" not in upload(household, c).text
    r = c.post("/import", data={"csrf_token": csrf(household, c)},
               files={"file": ("x.json", io.BytesIO(json.dumps({"schema_version": "0.1"}).encode()),
                               "application/json")})
    assert r.status_code == 200


def test_tc_cmp_02_2_withdrawing_stops_collection_and_ai(household, app_db):
    who = household.enrol()
    household.accounts.set_ai_extraction(who.household_id, True)
    c = household.sign_in(who)
    give(household, c, collection=True, ai=True)
    assert household.accounts.ai_extraction(who.household_id)
    give(household, c, collection=False)
    assert not household.accounts.ai_extraction(who.household_id)
    r = upload(household, c)
    assert r.status_code == 400 and "consent" in r.text  # refused even with the toggle off
    assert "withdrawn consent" in c.get("/consent").text
    rec = HouseholdStore(app_db, who.household_id).get("consent", f"consent-{who.member_id}")
    assert [h["collection"] for h in rec["history"]] == [True, False]


def test_admin_toggle_for_consent(household, app_db):
    who = household.enrol()
    household.accounts.set_owner(who.email, True)
    c = household.sign_in(who)
    r = c.post("/admin/require-consent", data={"state": "on", "csrf_token": csrf(household, c)},
               follow_redirects=False)
    assert r.status_code == 303 and Features(app_db).require_consent()


# --- insurer connection against a fake payer ---

@pytest.fixture
def payer_app(make_household, monkeypatch):
    responses = {"token": {"access_token": "tok-1", "patient": "p-777"},
                 "eobs": [bundle([eob(), eob(claim="CLM-1002", when="2026-04-02", provider="Bennett Radiology")])]}

    def handler(request: httpx.Request):
        if request.url.path == "/t":
            return httpx.Response(200, json=responses["token"])
        assert request.headers["authorization"] == "Bearer tok-1"
        return httpx.Response(200, json=responses["eobs"].pop(0))

    monkeypatch.setattr(connect, "TRANSPORT", httpx.MockTransport(handler))
    monkeypatch.setattr(connect, "SLEEP", lambda s: None)
    return make_household(fhir_payers=(PAYER,), public_url="http://testserver")


def plan_for(app_db, who):
    store = HouseholdStore(app_db, who.household_id)
    store.upsert("member", {"id": "mem-1", "name": "Jordan"})
    store.upsert("plan", {"id": "plan-2026", "plan_year": 2026, "insurer": "Example Health", "limits": []})


def test_tc_ing_09_1_connect_pull_review_confirm(payer_app, app_db):
    who = payer_app.enrol()
    plan_for(app_db, who)
    c = payer_app.sign_in(who)
    assert "Example Health" in c.get("/connect").text
    r = c.get("/connect/examplehealth?who=mem-1", follow_redirects=False)
    assert r.status_code == 303
    q = parse_qs(urlsplit(r.headers["location"]).query)
    assert q["aud"] == [PAYER.fhir_base] and q["code_challenge_method"] == ["S256"]
    # The payer sends the browser back without the Strict session cookie: a fresh client with only the flow cookie.
    back = payer_app.client()
    back.cookies.set(connect.FLOW_COOKIE, c.cookies.get(connect.FLOW_COOKIE), path="/connect")
    done = back.get(f"/connect/examplehealth/callback?code=abc&state={q['state'][0]}")
    assert done.status_code == 200 and "Read 2 claims" in done.text
    token = done.text.split("/connect/review/")[1].split('"')[0]
    preview = c.get(f"/connect/review/{token}")
    assert preview.status_code == 200 and "Save import" in preview.text, preview.text[preview.text.find("<main"):][:1500]
    form_token = preview.text.split('name="token" value="')[1].split('"')[0]
    assert c.post("/import/confirm", data={"token": form_token, "csrf_token": csrf(payer_app, c)},
                  follow_redirects=False).status_code == 303
    docs = HouseholdStore(app_db, who.household_id).all("document")
    assert sorted(d["claim_number"] for d in docs) == ["CLM-1001", "CLM-1002"]
    assert all(d["extensions"]["feed"] == "fhir" for d in docs)
    assert "p-777" not in json.dumps(docs)


def test_state_mismatch_imports_nothing(payer_app, app_db):
    who = payer_app.enrol()
    c = payer_app.sign_in(who)
    c.get("/connect/examplehealth", follow_redirects=False)
    r = c.get("/connect/examplehealth/callback?code=abc&state=wrong")
    assert r.status_code == 400 and "Nothing was imported" in r.text


def test_unknown_payer_is_404(payer_app):
    c = payer_app.sign_in(payer_app.enrol())
    assert c.get("/connect/nobody", follow_redirects=False).status_code == 404
