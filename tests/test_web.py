import json

import pytest
from fastapi.testclient import TestClient

from mhs.web.app import create_app
from tests.conftest import SAMPLE


@pytest.fixture
def client(config):
    return TestClient(create_app(config))


def import_sample(client):
    preview = client.post("/import", data={"path": str(SAMPLE)})
    assert preview.status_code == 200 and "What will change" in preview.text
    token = preview.text.split('name="token" value="')[1].split('"')[0]
    done = client.post("/import/confirm", data={"token": token}, follow_redirects=False)
    assert done.status_code == 303


def test_empty_home_has_hero_help_and_settings(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "My Health Spend" in page.text and "No visits yet" in page.text
    assert 'href="/help"' in page.text and 'href="/settings"' in page.text
    assert client.get("/help").status_code == 200
    assert client.get("/health").json() == {"ok": True}
    assert client.get("/static/favicon.svg").status_code == 200


def test_every_page_renders_after_import(client, config):
    import_sample(client)
    home = client.get("/")
    assert "$80.00" in home.text  # at stake
    for url in ["/visits", "/visits?status=discrepancy&flagged=1", "/visits/v-2026-04-02-pcp", "/visits/v-2026-09-28-derm",
                "/providers", "/providers/prov-pcp", "/import", "/settings"]:
        assert client.get(url).status_code == 200, url
    assert "Bill matches EOB" in client.get("/visits/v-2026-04-02-pcp").text
    assert client.get("/visits/nope").status_code == 404


def test_import_with_errors_saves_nothing(client, tmp_path):
    bad = json.loads(SAMPLE.read_text())
    bad["visits"][0]["category"] = "vitamins"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    page = client.post("/import", data={"path": str(path)})
    assert "Nothing was saved" in page.text and "vitamins" in page.text
    assert "No visits yet" in client.get("/").text


def test_settings_edits_are_saved_and_written_to_settings_json(client, config):
    import_sample(client)
    client.post("/settings/plans/plan-2026", data={"insurer": "Example Health", "plan_name": "HDHP", "plan_year": "2026",
                                                    "coverage_order": "primary", "coinsurance_pct": "20"})
    r = client.post("/settings/plans/plan-2026/limits",
                    data={"type": "out_of_pocket_max", "network": "in_network", "level": "family", "amount": "9,000"},
                    follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/settings")
    assert "Primary insurer" in page.text and "Example Health" in page.text and "$9,000.00" in page.text
    exported = json.loads(config.settings_file.read_text())
    plan = next(p for p in exported["plans"] if p["id"] == "plan-2026")
    assert plan["coverage_order"] == "primary" and plan["coinsurance_rate"] == 0.2
    assert plan["limits"][-1] == {"type": "out_of_pocket_max", "network": "in_network", "level": "family", "amount": 9000}

    bad = client.post("/settings/plans/plan-2026/limits", data={"type": "deductible", "network": "in_network",
                                                                "level": "family", "amount": "lots"})
    assert bad.status_code == 400 and "not an amount" in bad.text


def test_provider_notes_can_be_added_edited_and_deleted(client, store):
    import_sample(client)
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


def test_reimport_does_not_touch_notes(client, store):
    import_sample(client)
    client.post("/notes", data={"provider_id": "prov-pcp", "text": "Keep me"})
    import_sample(client)
    assert [n["text"] for n in store.all("provider_note")] == ["Keep me"]
