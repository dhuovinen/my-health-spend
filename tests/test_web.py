"""Release 0 web tests (TEST_PLAN Appendix A), run against both apps: Release 0 over SQLite, and the Release 1
application tier over a signed-in household's Postgres store (ADR-032)."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mhs.data.household_store import HouseholdStore
from mhs.data.store import Store
from mhs.web.app import create_app
from tests.conftest import SAMPLE


class ReleaseZero:
    """The Release 0 app: imports by path, settings written to data/settings.json."""

    def __init__(self, config):
        self.client = TestClient(create_app(config))
        self.store = Store(config.db_path)
        self.config = config

    def import_preview(self, path: Path):
        return self.client.post("/import", data={"path": str(path)})

    def settings_json(self) -> dict:
        return json.loads(self.config.settings_file.read_text())


class CsrfClient:
    """A signed-in member's browser: every post carries the session's CSRF token, as the pages' forms do."""

    def __init__(self, client: TestClient, token: str):
        self.client, self.token = client, token

    def get(self, *args, **kwargs):
        return self.client.get(*args, **kwargs)

    def post(self, url, data=None, **kwargs):
        return self.client.post(url, data={**(data or {}), "csrf_token": self.token}, **kwargs)


class ReleaseOne:
    """The Release 1 application tier: a signed-in member; imports by upload; settings by download."""

    def __init__(self, household, app_db):
        who = household.enrol()
        client = household.sign_in(who)
        self.client = CsrfClient(client, household.csrf(client))
        self.store = HouseholdStore(app_db, who.household_id)

    def import_preview(self, path: Path):
        data = json.loads(path.read_text())
        names = [d["file"] for d in data.get("documents", []) if "file" in d and (path.parent / d["file"]).is_file()]
        files = [("file", (path.name, path.read_bytes(), "application/json"))]
        files += [("attachments", (Path(n).name, (path.parent / n).read_bytes(), "application/pdf")) for n in names]
        return self.client.post("/import", files=files)

    def settings_json(self) -> dict:
        r = self.client.get("/settings/export")
        assert r.headers["content-disposition"] == 'attachment; filename="settings.json"'
        return r.json()


@pytest.fixture(params=["release0", pytest.param("release1", marks=pytest.mark.postgres)])
def web(request, config):
    if request.param == "release0":
        return ReleaseZero(config)
    return ReleaseOne(request.getfixturevalue("household"), request.getfixturevalue("app_db"))


def import_sample(web, **confirm):
    preview = web.import_preview(SAMPLE)
    assert preview.status_code == 200 and "What will change" in preview.text
    token = preview.text.split('name="token" value="')[1].split('"')[0]
    done = web.client.post("/import/confirm", data={"token": token, **confirm}, follow_redirects=False)
    assert done.status_code == 303
    return preview


def test_empty_home_has_hero_help_and_settings(web):
    client = web.client
    page = client.get("/")
    assert page.status_code == 200
    assert "My Health Spend" in page.text and "No visits yet" in page.text
    assert 'href="/help"' in page.text and 'href="/settings"' in page.text
    assert client.get("/help").status_code == 200
    assert client.get("/health").json() == {"ok": True}
    assert client.get("/static/favicon.svg").status_code == 200


def test_every_page_renders_after_import(web):
    client = web.client
    import_sample(web)
    home = client.get("/")
    assert "$80.00" in home.text  # at stake
    for url in ["/visits", "/visits?status=discrepancy&flagged=1", "/visits/v-2026-04-02-pcp", "/visits/v-2026-09-28-derm",
                "/providers", "/providers/prov-pcp", "/import", "/settings"]:
        assert client.get(url).status_code == 200, url
    assert "Bill matches EOB" in client.get("/visits/v-2026-04-02-pcp").text
    assert client.get("/visits/nope").status_code == 404


def test_import_with_errors_saves_nothing(web, tmp_path):
    client = web.client
    bad = json.loads(SAMPLE.read_text())
    bad["visits"][0]["category"] = "vitamins"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    page = web.import_preview(path)
    assert "Nothing was saved" in page.text and "vitamins" in page.text
    assert "No visits yet" in client.get("/").text


def test_settings_edits_are_saved_and_written_to_settings_json(web):
    client = web.client
    import_sample(web)
    client.post("/settings/plans/plan-2026", data={"insurer": "Example Health", "plan_name": "HDHP", "plan_year": "2026",
                                                    "coverage_order": "primary", "coinsurance_pct": "20"})
    r = client.post("/settings/plans/plan-2026/limits",
                    data={"type": "out_of_pocket_max", "network": "in_network", "level": "family", "amount": "9,000"},
                    follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/settings")
    assert "Primary insurer" in page.text and "Example Health" in page.text and "$9,000.00" in page.text
    exported = web.settings_json()
    plan = next(p for p in exported["plans"] if p["id"] == "plan-2026")
    assert plan["coverage_order"] == "primary" and plan["coinsurance_rate"] == 0.2
    assert plan["limits"][-1] == {"type": "out_of_pocket_max", "network": "in_network", "level": "family", "amount": 9000}

    bad = client.post("/settings/plans/plan-2026/limits", data={"type": "deductible", "network": "in_network",
                                                                "level": "family", "amount": "lots"})
    assert bad.status_code == 400 and "not an amount" in bad.text


def test_provider_notes_can_be_added_edited_and_deleted(web):
    client, store = web.client, web.store
    import_sample(web)
    ledger = "/providers/prov-derm?year=2026"
    r = client.post("/notes", data={"provider_id": "prov-derm", "date": "2026-10-09", "channel": "email",
                                    "direction": "sent", "visit_id": "v-2026-09-28-derm",
                                    "text": "Good day,\nAsked for the itemized bill.", "next": ledger},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == ledger + "#notes"
    [note] = store.all("provider_note")
    assert note["channel"] == "email" and note["visit_id"] == "v-2026-09-28-derm"

    page = client.get(ledger).text
    assert "Asked for the itemized bill." in page and "I sent" in page
    assert "Asked for the itemized bill." in client.get("/visits/v-2026-09-28-derm").text
    assert '#notes">1</a>' in client.get("/providers").text

    client.post(f"/notes/{note['id']}", data={"provider_id": "prov-derm", "date": "2026-10-10",
                                              "text": "Called instead.", "next": ledger})
    edited = store.get("provider_note", note["id"])
    assert edited["text"] == "Called instead." and "channel" not in edited and "visit_id" not in edited

    assert client.post("/notes", data={"provider_id": "prov-derm", "text": "  "}).status_code == 400
    assert client.post("/notes", data={"provider_id": "nobody", "text": "x"}).status_code == 400
    r = client.post("/notes", data={"provider_id": "prov-derm", "text": "x", "next": "https://evil.example"},
                    follow_redirects=False)
    assert r.headers["location"].startswith("/providers")

    client.post(f"/notes/{note['id']}/delete", data={"next": ledger})
    assert store.get("provider_note", note["id"]) is None


def test_reimport_does_not_touch_notes(web):
    client, store = web.client, web.store
    import_sample(web)
    client.post("/notes", data={"provider_id": "prov-pcp", "text": "Keep me"})
    import_sample(web)
    assert [n["text"] for n in store.all("provider_note")] == ["Keep me"]


def test_reimport_keeps_settings_edits_unless_replaced(web):
    client, store = web.client, web.store
    import_sample(web)
    client.post("/settings/providers/prov-pcp", data={"name": "Example Family Medicine", "kind": "physician_practice",
                                                      "network_status": "out_of_network"})
    preview = import_sample(web)
    assert "Your edits" in preview.text and "network_status" in preview.text
    assert store.get("provider", "prov-pcp")["network_status"] == "out_of_network"
    exported = web.settings_json()["providers"]
    assert next(p for p in exported if p["id"] == "prov-pcp")["network_status"] == "out_of_network"
    assert "1 of your edits kept" in client.get("/import").text

    import_sample(web, replace_edits="1")
    assert store.get("provider", "prov-pcp")["network_status"] == "in_network"
    assert store.edited_ids("provider") == set()
    assert "Your edits" not in import_sample(web).text


def test_home_hsa_counts_link_to_filtered_lists(web):
    client = web.client
    import_sample(web)
    home = client.get("/").text
    assert 'href="/visits?year=2026&amp;hsa=unpaid"' in home and "1 visit<" in home
    unpaid = client.get("/visits?year=2026&hsa=unpaid").text
    assert "1 of 6" in unpaid and "Example Imaging" in unpaid
    assert "1 of 6" in client.get("/visits?year=2026&hsa=outside_hsa").text
    assert "Showing providers flagged" in client.get("/providers?year=2026&flag=unpaid").text
    ledger = client.get("/providers/prov-imaging?year=2026").text
    assert re.search(r"first billed \d+ days ago", ledger)  # the app ages balances from the real date
