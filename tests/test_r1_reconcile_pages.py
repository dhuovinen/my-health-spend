"""Phase 1.4 on the pages: the member's matches, splits, merges, disputes and document checklist (MAT-07, ALC-04,
MAT-10, REC-11; ADR-011, ADR-035). Run against both apps through the `web` fixture, like Appendix A."""

import copy
import json
import re

import pytest

from mhs.core.reconcile import STATUS_LABELS
from tests.conftest import SAMPLE
from tests.test_r1_scenarios import member  # noqa: F401 (fixture)
from tests.test_web import import_sample, web  # noqa: F401 (fixture)

pytestmark = []


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).replace("&#39;", "'")


def import_data(web, tmp_path, data: dict, **confirm):
    path = tmp_path / f"ingest-{len(list(tmp_path.glob('ingest-*.json')))}.json"
    path.write_text(json.dumps(data))
    preview = web.import_preview(path)
    assert preview.status_code == 200 and "What will change" in preview.text, preview.text[:2000]
    token = preview.text.split('name="token" value="')[1].split('"')[0]
    done = web.client.post("/import/confirm", data={"token": token, **confirm}, follow_redirects=False)
    assert done.status_code == 303
    return preview


SETTINGS = {"plans": [{"id": "plan", "plan_year": 2026, "insurer": "X"}],
            "accounts": [{"id": "hsa", "name": "HSA", "type": "hsa"}],
            "members": [{"id": "me", "name": "Me"}],
            "providers": [{"id": "prov-a", "name": "Alder Clinic", "network_status": "in_network"}]}


def eob(vid, owed, billed=200, number=None, **extra):
    return {"id": f"eob-{number or vid}", "type": "eob", "date": "2026-03-01", "plan_id": "plan",
            "provider_id": "prov-a", "visit_id": vid, "claim_number": number or vid, "billed": billed,
            "allowed": owed, "adjustment": billed - owed, "insurer_paid": 0, "deductible": owed,
            "patient_responsibility": owed, **extra}


def scenario(**extra) -> dict:
    """Two visits at one provider: A on Feb 1 and B on Feb 3, $100.00 owed on each."""
    data = {"schema_version": "0.1", **copy.deepcopy(SETTINGS),
            "visits": [{"id": vid, "date": d, "provider_id": "prov-a", "member_id": "me", "plan_id": "plan",
                        "category": "provider_visit"} for vid, d in (("A", "2026-02-01"), ("B", "2026-02-03"))],
            "documents": [eob("A", 100), eob("B", 100)]}
    for k, v in extra.items():
        data[k] = data.get(k, []) + v
    return data


def payment(amount=150, **extra):
    return {"id": "pay-1", "type": "payment", "date": "2026-03-10", "provider_id": "prov-a", "account_id": "hsa",
            "amount": amount, **extra}


def test_mat_05_5_and_mat_07_1_proposed_match_is_confirmed(web, tmp_path):
    """TC-MAT-05-5: a proposed match shows its reasons beside the score. TC-MAT-07-1: confirming it saves it as the
    member's decision, and the visit leaves Needs review."""
    match = {"status": "proposed", "score": 0.75, "reasons": ["same provider", "dates of service 2 days apart"]}
    data = scenario()
    data["documents"][1]["match"] = match
    import_data(web, tmp_path, data)
    page = text_of(web.client.get("/visits/B").text)
    assert "Needs review" in page and "matched to this visit with a score of 75%: same provider, dates of " \
                                      "service 2 days apart" in page
    assert web.client.post("/visits/B/documents/eob-B/confirm", follow_redirects=False).status_code == 303
    assert web.store.get("document", "eob-B")["match"]["status"] == "confirmed"
    assert "eob-B" in web.store.edited_ids("document")
    assert "Needs review" not in text_of(web.client.get("/visits/B").text)


def test_mat_07_2_rejected_match_stays_rejected_on_reimport(web, tmp_path):
    """TC-MAT-07-2 (I): "not this visit" moves the EOB to a new visit; importing the same file again keeps the
    member's version (ADR-011), so the rejected pair isn't proposed again."""
    data = scenario()
    data["documents"][1]["match"] = {"status": "proposed", "score": 0.7, "reasons": ["same provider"]}
    import_data(web, tmp_path, data)
    r = web.client.post("/visits/B/documents/eob-B/move", data={"target": "new", "reject": "1"},
                        follow_redirects=False)
    assert r.status_code == 303
    moved = web.store.get("document", "eob-B")
    new_visit = moved["visit_id"]
    assert r.headers["location"] == f"/visits/{new_visit}" and new_visit not in ("A", "B")
    assert moved["match"]["rejected"] == ["B"] and moved["match"]["status"] == "confirmed"
    preview = import_data(web, tmp_path, data)
    assert "eob-B" in preview.text  # listed as a member edit the file would overwrite
    assert web.store.get("document", "eob-B")["visit_id"] == new_visit


def test_claims_export_matches_by_score_and_keeps_rejections(member):
    """MAT-05 on the insurer's claims export: a claim on the same provider, date and person links automatically; a
    near one is proposed (the visit is Needs review); a claim the member moved stays where they put it."""
    member.client.post("/settings/plans", data={"plan_year": "2026", "insurer": "Example Health", "plan_name": "Medical"})
    head = ("Patient,Provided By,Claim Type,Claim Number,Service Date,Processed Date,Status,Billed,Plan Discount,"
            "Allowed,Plan Paid,Deductible,Your Cost\n")
    row = ("Pat Example,Example Family Medicine,Medical,{n},{d},2026-04-20,Approved,${b}.00,$100.00,${a}.00,$0.00,"
           "${a}.00,${a}.00\n")
    member.import_export("one.csv", (head + row.format(n="C-1", d="2026-04-02", b=250, a=150)).encode())
    visit_id = member.store.get("document", "eob-c-1")["visit_id"]
    # A second claim (another claim number) for the same visit, and one two days later.
    preview = member.import_export("two.csv", (head + row.format(n="C-2", d="2026-04-02", b=250, a=150)
                                               + row.format(n="C-3", d="2026-04-04", b=180, a=80)).encode())
    c2, c3 = member.store.get("document", "eob-c-2"), member.store.get("document", "eob-c-3")
    assert c2["visit_id"] == visit_id and c2["match"]["status"] == "auto" and c2["match"]["score"] >= 0.9
    assert c3["visit_id"] == visit_id and c3["match"]["status"] == "proposed" and "confirm it on the visit" in preview.text
    page = text_of(member.client.get(f"/visits/{visit_id}").text)
    assert "Needs review" in page and "2 days apart" in page and "3 claims" in page
    member.client.post(f"/visits/{visit_id}/documents/eob-c-3/move", data={"target": "new", "reject": "1"})
    moved_to = member.store.get("document", "eob-c-3")["visit_id"]
    member.import_export("again.csv", (head + row.format(n="C-3", d="2026-04-04", b=180, a=80) + "\n").encode())
    assert member.store.get("document", "eob-c-3")["visit_id"] == moved_to != visit_id


def test_mat_07_3_split_a_statement_and_merge_visits(web, tmp_path):
    """TC-MAT-07-3 (I): lines and allocations move; totals don't change."""
    items = [{"code": "99214", "service_date": "2026-02-01", "charge": 200, "patient_amount": 100, "balance": 100},
             {"code": "99213", "service_date": "2026-02-03", "charge": 200, "patient_amount": 100, "balance": 100}]
    statement = {"id": "bill-1", "type": "provider_bill", "date": "2026-02-20", "provider_id": "prov-a",
                 "balance_due": 200, "lines": [{"visit_id": "A", "patient_amount": 200, "balance": 200,
                                                "billed_charge": 400, "items": items}]}
    import_data(web, tmp_path, scenario(documents=[statement, payment(200)]))
    home_before = text_of(web.client.get("/?year=2026").text)
    r = web.client.post("/visits/A/documents/bill-1/move", data={"target": "B", "items": "1"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/visits/B"
    lines = {l["visit_id"]: l for l in web.store.get("document", "bill-1")["lines"]}
    assert (lines["A"]["patient_amount"], lines["B"]["patient_amount"]) == (10000, 10000)
    assert [i["code"] for i in lines["B"]["items"]] == ["99213"]
    assert text_of(web.client.get("/visits/B").text).count("99213") >= 1
    assert re.search(r"Paid \(allocated\) \$100\.00", text_of(web.client.get("/visits/B").text))
    home_after = text_of(web.client.get("/?year=2026").text)
    for tile in ("Total billed $400.00", "Insurer paid $0.00", "You paid $200.00"):
        assert tile in home_before and tile in home_after
    # Both lines were on A, so A looked billed for B too; split, each bill matches its EOB.
    assert "$ at stake $200.00" in home_before and "$ at stake $0.00" in home_after
    # Merge B into A: everything moves back, B is gone, totals unchanged.
    r = web.client.post("/visits/A/merge", data={"other": "B"}, follow_redirects=False)
    assert r.status_code == 303 and web.store.get("visit", "B") is None
    assert web.store.get("document", "eob-B")["visit_id"] == "A"
    [line] = web.store.get("document", "bill-1")["lines"]
    assert (line["visit_id"], line["patient_amount"], len(line["items"])) == ("A", 20000, 2)
    page = text_of(web.client.get("/visits/A").text)
    assert "2 claims" in page and re.search(r"Paid \(allocated\) \$200\.00", page)


def test_mat_01_4_a_visit_with_documents_cannot_be_deleted(web, tmp_path):
    """TC-MAT-01-4 (I): blocked with a message; an empty visit can be deleted; no orphans either way."""
    data = scenario()
    data["visits"].append({"id": "C", "date": "2026-02-05", "provider_id": "prov-a", "category": "provider_visit"})
    import_data(web, tmp_path, data)
    r = web.client.post("/visits/A/delete", follow_redirects=False)
    assert r.status_code == 400 and "Move them to another visit, or merge the visits" in text_of(r.text)
    assert web.store.get("visit", "A")
    assert web.client.post("/visits/C/delete", follow_redirects=False).headers["location"] == "/visits"
    assert web.store.get("visit", "C") is None
    import_data(web, tmp_path, data)
    assert web.store.get("visit", "C") is None  # deleted in the app, so the import doesn't bring it back


def test_alc_04_2_members_split_is_saved_used_and_kept(web, tmp_path):
    """TC-ALC-04-2 (I): the member changes the default split on the ledger; it is used, and kept on re-import."""
    data = scenario(documents=[payment(150)])
    import_data(web, tmp_path, data)
    ledger = text_of(web.client.get("/providers/prov-a?year=2026").text)
    assert "Payments and how they're split" in ledger
    bad = web.client.post("/payments/pay-1/split", data={"split-A": "50", "split-B": "50"})
    assert bad.status_code == 400 and "add up to $100.00; the payment was $150.00" in text_of(bad.text)
    other = web.client.post("/payments/pay-1/split", data={"split-A": "50", "split-nope": "100"})
    assert other.status_code == 400 and "only be split across this provider" in text_of(other.text)
    r = web.client.post("/payments/pay-1/split", data={"split-A": "50.00", "split-B": "100.00"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/providers/prov-a?year=2026#pay-pay-1"
    saved = web.store.get("document", "pay-1")
    assert saved["allocations"] == [{"visit_id": "A", "amount": 5000}, {"visit_id": "B", "amount": 10000}]
    assert "split by you" in text_of(web.client.get("/visits/A").text)
    assert "$50.00 still unpaid" in text_of(web.client.get("/visits/A").text)
    import_data(web, tmp_path, data)  # the file has no split: the member's is kept
    assert web.store.get("document", "pay-1")["allocations"][0]["amount"] == 5000
    web.client.post("/payments/pay-1/split", data={"action": "reset"})
    assert "allocations" not in web.store.get("document", "pay-1")
    assert "$50.00 still unpaid" in text_of(web.client.get("/visits/B").text)  # oldest first again


def test_mat_10_3_and_4_document_checklist(web, tmp_path):
    """TC-MAT-10-3 (I): marking a document not applicable counts as satisfied. TC-MAT-10-4 (E): the visit card and
    page show completeness per document kind."""
    import_data(web, tmp_path, scenario(documents=[payment(200)]))
    cards = text_of(web.client.get("/visits?year=2026").text)
    assert "2 of 2 documents ✓ Insurance decision (EOB) ✓ Payment proof" in cards
    web.client.post("/visits/A/expected", data={"kind": "itemized_bill", "state": "expected"})
    page = text_of(web.client.get("/visits/A").text)
    assert "Awaiting documents" in page and "Itemized bill Expected you asked for it" in page
    assert "… Itemized bill" in text_of(web.client.get("/visits?year=2026").text)
    web.client.post("/visits/A/expected", data={"kind": "itemized_bill", "state": "not_applicable"})
    assert "Complete" in text_of(web.client.get("/visits/A").text)
    web.client.post("/visits/A/expected", data={"kind": "itemized_bill", "state": "default"})
    assert "documents" not in web.store.get("visit", "A")
    assert web.client.post("/visits/A/expected", data={"kind": "x", "state": "expected"}).status_code == 400


def test_rec_11_dispute_lifecycle_and_findings_on_the_pages(web):
    """REC-11 In dispute and Resolved on the pages; a finding the member deals with; status badges say the status
    in words (TC-REC-11-5)."""
    import_sample(web)
    page = text_of(web.client.get("/visits/v-2026-04-02-pcp").text)
    assert "Discrepancy found" in page and "Missed adjustment" in page and "Open a dispute" in page
    web.client.post("/visits/v-2026-04-02-pcp/dispute", data={"action": "open", "note": "Called billing"})
    page = text_of(web.client.get("/visits/v-2026-04-02-pcp").text)
    assert "In dispute since" in page and "Called billing" in page
    web.client.post("/visits/v-2026-04-02-pcp/dispute", data={"action": "close", "outcome": "accepted"})
    page = text_of(web.client.get("/visits/v-2026-04-02-pcp").text)
    assert "Resolved" in page and "Closed by you on" in page
    assert web.store.get("visit", "v-2026-04-02-pcp")["dispute"]["status"] == "closed"
    # Reopen one finding: the visit is a discrepancy again.
    closed = web.store.get("visit", "v-2026-04-02-pcp")["closed_findings"]
    for f in closed:
        web.client.post("/visits/v-2026-04-02-pcp/findings", data={"code": f["code"], "amount": f["amount"],
                                                                   "action": "reopen"})
    assert "Discrepancy found" in text_of(web.client.get("/visits/v-2026-04-02-pcp").text)
    web.client.post("/visits/v-2026-04-02-pcp/findings", data={"code": "C2", "amount": "8000"})
    web.client.post("/visits/v-2026-04-02-pcp/findings", data={"code": "C4", "amount": "8000"})
    assert "Resolved" in text_of(web.client.get("/visits/v-2026-04-02-pcp").text)
    assert web.client.post("/visits/v-2026-04-02-pcp/dispute", data={"action": "close"}).status_code == 400
    listing = web.client.get("/visits?year=2026").text
    for status in ("resolved", "complete", "balance_outstanding", "awaiting_eob"):
        assert f'<span class="badge s-{status}">{STATUS_LABELS[status]}</span>' in listing


def test_rec_11_4_waiting_threshold_setting(web):
    """TC-REC-11-4 (I): the threshold is a household setting; the derm visit waits or is missing its EOB."""
    import_sample(web)
    assert "Awaiting EOB" in text_of(web.client.get("/visits/v-2026-09-28-derm").text)
    assert web.client.post("/settings/reconciliation", data={"waiting_days": "5"},
                           follow_redirects=False).status_code == 303
    assert "Missing documents" in text_of(web.client.get("/visits/v-2026-09-28-derm").text)
    assert 'value="5"' in web.client.get("/settings").text
    assert web.client.post("/settings/reconciliation", data={"waiting_days": "0"}).status_code == 400


def test_payment_path_and_home_year_buckets(web):
    """A visit can be marked self-pay (REC-05): no EOB is expected. Home shows where the year's billed dollars went
    (ALC-01 per year)."""
    import_sample(web)
    web.client.post("/visits/v-2026-09-28-derm/payment-path", data={"path": "self_pay"})
    assert web.store.get("visit", "v-2026-09-28-derm")["payment_path"] == "self_pay"
    assert "Awaiting documents" in text_of(web.client.get("/visits/v-2026-09-28-derm").text)
    web.client.post("/visits/v-2026-09-28-derm/payment-path", data={"path": "default"})
    assert "payment_path" not in web.store.get("visit", "v-2026-09-28-derm")
    home = text_of(web.client.get("/?year=2026").text)
    assert "Where 2026's billed dollars went" in home and "Plan discount $305.00" in home


def test_decisions_on_another_visit_or_unknown_records_are_refused(web, tmp_path):
    import_data(web, tmp_path, scenario())
    assert web.client.post("/visits/A/documents/eob-B/confirm").status_code == 404
    assert web.client.post("/visits/nope/dispute", data={"action": "open"}).status_code == 404
    assert web.client.post("/payments/eob-A/split", data={}).status_code == 404
    r = web.client.post("/visits/A/documents/eob-A/move", data={"target": "nowhere"})
    assert r.status_code == 400 and "Choose the visit it belongs to" in r.text
    assert web.client.post("/visits/A/merge", data={"other": "A"}).status_code == 400
    assert web.client.post("/visits/A/findings", data={"code": "C2", "amount": "8.00"}).status_code == 400


@pytest.mark.postgres
def test_another_household_cannot_change_these_records(household, app_db, tmp_path):
    """PRV-11: every decision route is household-scoped; another household gets Not found and changes nothing."""
    from tests.test_web import ReleaseOne

    a, b = ReleaseOne(household, app_db), ReleaseOne(household, app_db)
    import_data(a, tmp_path, scenario(documents=[payment(150)]))
    before = (a.store.get("visit", "A"), a.store.get("document", "pay-1"), a.store.get("document", "eob-A"))
    for url, data in [("/visits/A/dispute", {"action": "open"}), ("/visits/A/findings", {"code": "C2", "amount": "1"}),
                      ("/visits/A/expected", {"kind": "eob", "state": "not_applicable"}),
                      ("/visits/A/payment-path", {"path": "self_pay"}), ("/visits/A/merge", {"other": "B"}),
                      ("/visits/A/delete", {}), ("/visits/A/documents/eob-A/confirm", {}),
                      ("/visits/A/documents/eob-A/move", {"target": "new"}),
                      ("/payments/pay-1/split", {"split-A": "150"})]:
        assert b.client.post(url, data=data).status_code == 404, url
    assert (a.store.get("visit", "A"), a.store.get("document", "pay-1"), a.store.get("document", "eob-A")) == before
