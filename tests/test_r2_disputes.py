"""Release 2 disputes (DSP-01 to DSP-05, DSP-07; ADR-042): cases on a visit, their evidence, letters drafted in the
application tier, the call script and log, follow-ups, deadlines and outcomes. Core cases (U) pin "today" to
2026-10-09; page cases (I, E) run against both apps through the `web` fixture, on the real date."""

import copy
import hashlib
import re
from datetime import date, timedelta

import pytest

from mhs.core import disputes, edits
from mhs.core.reconcile import build_report
from mhs.web import letters
from mhs.web.pages import attention_queue
from tests.conftest import SAMPLE, admin_sql
from tests.test_r1_reconcile import bill, claim
from tests.test_r1_reconcile_pages import import_data, text_of
from tests.test_r1_scenarios import EOB, STATEMENT, member  # noqa: F401 (fixture)
from tests.test_reconcile import TODAY, base, eob, pay, visit
from tests.test_web import import_sample, web  # noqa: F401 (fixture)

PCP = "v-2026-04-02-pcp"  # the sample's visit with a missed adjustment ($180.00 asked, $100.00 owed) that was paid


def run(ds, today=TODAY):
    return build_report(ds, 2026, today)


def findings_of(vr) -> list[dict]:
    return [{"code": c.code, "kind": c.kind, "amount": c.amount, "detail": c.detail} for c in vr.findings
            if c.code != "C6"]  # as the pages open a case: a balance owed isn't disputed


def overbilled(vid="v1", d="2026-03-01", paid=0):
    """A visit whose statement asks $180.00 while the EOB says $100.00 (a missed adjustment, REC-02), with lines."""
    v = visit(vid, d)
    items = [{"code": "99213", "description": "Office visit", "charge": 18000, "adjustment": 0, "patient_amount": 18000}]
    e = claim(vid, f"CLM-{vid}", [{"code": "99213", "billed": 18000, "allowed": 10000, "adjustment": 8000,
                                   "insurer_paid": 0, "deductible": 10000, "patient_responsibility": 10000}], d=d)
    s = bill(f"s-{vid}", (date.fromisoformat(d) + timedelta(days=14)).isoformat(),
             [{"visit_id": vid, "billed_charge": 18000, "adjustment": 0, "patient_amount": 18000, "items": items}])
    docs = [e, s] + ([pay(f"p-{vid}", (date.fromisoformat(d) + timedelta(days=20)).isoformat(), paid)] if paid else [])
    return v, docs


def opened(v, docs, today="2026-10-01", **kw):
    vr = run(base(visits=[v], documents=docs)).visit(v["id"])
    from mhs.web.pages import case_lines
    return edits.open_case(v, today, findings_of(vr), case_lines(vr.line_match), **kw)


def note(nid, vid, case_id, d, direction="sent", channel="email", **extra):
    return {"id": nid, "provider_id": "a", "visit_id": vid, "case_id": case_id, "date": d, "channel": channel,
            "direction": direction, "text": "x", **extra}


# ---------- DSP-01 a case with its evidence ----------

def test_tc_dsp_01_1_case_from_a_rec_02_finding_holds_bill_eob_payment_lines_and_amounts():
    v, docs = overbilled(paid=18000)
    v, case_id = opened(v, docs)
    case = next(c for c in v["cases"] if c["id"] == case_id)
    assert [(f["code"], f["kind"], f["amount"]) for f in case["findings"]] == [("C2", "missed_adjustment", 8000),
                                                                              ("C4", "overpayment", 8000)]
    assert case["lines"] == [{"code": "99213", "description": "Office visit", "charge": 18000, "billed": 18000,
                              "patient_amount": 18000, "patient_responsibility": 10000}]
    view = run(base(visits=[v], documents=docs)).visit("v1").cases[0]
    assert [(k, d["id"]) for k, d in view.evidence.documents] == [("bill", "s-v1"), ("eob", "eob-CLM-v1"),
                                                                  ("payment", "p-v1")]
    assert view.evidence.missing == [] and view.amount == 8000 and view.party == "provider"
    assert view.letter == "billing_correction"


def test_tc_dsp_01_3_missing_payment_proof_is_listed():
    v, docs = overbilled(paid=0)
    v, _ = opened(v, docs)
    vr = run(base(visits=[v], documents=docs)).visit("v1")
    assert vr.status == "in_dispute" and vr.cases[0].evidence.missing == ["Payment proof"]
    no_eob = run(base(visits=[v], documents=[d for d in docs if d["type"] != "eob"])).visit("v1")
    assert no_eob.cases[0].evidence.missing == ["Insurance decision (EOB)", "Payment proof"]


def test_tc_dsp_01_1_and_01_2_on_the_pages(web):
    """The case page lists the statement, EOB and payment with the finding and the lines; each original opens from
    the application tier unchanged (ING-10: the same SHA-256 as the file imported)."""
    import_sample(web)
    page = web.client.get(f"/visits/{PCP}").text
    assert 'name="finding" value="C2:8000"' in page
    r = web.client.post(f"/visits/{PCP}/cases", data={"finding": "C2:8000"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/visits/{PCP}/cases/case-1"
    case = text_of(web.client.get(r.headers["location"]).text)
    assert "Missed adjustment" in case and "$80.00" in case and "Statement Apr 28, 2026" in case
    assert "EOB Apr 16, 2026 · claim EX0000002" in case and "Payment May 2, 2026" in case
    assert "Missing evidence" not in case
    assert web.client.post(f"/visits/{PCP}/cases", data={"finding": "C2:8000"}).status_code == 400  # one open case


def test_tc_dsp_01_2_evidence_files_are_the_originals(web, tmp_path):
    """The case links each document's stored original, served by the application tier, with the same SHA-256 as
    the file that was imported (ING-10)."""
    from tests.pdfs import make_pdf as pdf
    from tests.test_r1_reconcile_pages import scenario

    statement = pdf("Alder Clinic\nStatement date: 03/05/2026\nAmount due: $180.00\n")
    (tmp_path / "statement.pdf").write_bytes(statement)
    data = scenario()
    data["documents"].append({"id": "s1", "type": "provider_bill", "date": "2026-03-05", "provider_id": "prov-a",
                              "file": "statement.pdf", "balance_due": 180,
                              "lines": [{"visit_id": "A", "patient_amount": 180}]})
    import_data(web, tmp_path, data)
    r = web.client.post("/visits/A/cases", data={"finding": "all"}, follow_redirects=False)
    page = web.client.get(r.headers["location"]).text
    doc = web.store.get("document", "s1")
    assert 'href="/files/s1"' in page and f"SHA-256 {doc['file_sha256'][:12]}" in page
    served = web.client.get("/files/s1").content
    assert hashlib.sha256(served).hexdigest() == doc["file_sha256"] == hashlib.sha256(statement).hexdigest()


def test_tc_dsp_01_3_on_the_pages(web, tmp_path):
    from tests.test_r1_reconcile_pages import scenario

    data = scenario()
    data["documents"].append({"id": "s1", "type": "provider_bill", "date": "2026-03-05", "provider_id": "prov-a",
                              "balance_due": 180, "lines": [{"visit_id": "A", "patient_amount": 180,
                                                             "billed_charge": 200, "adjustment": 20}]})
    import_data(web, tmp_path, data)
    r = web.client.post("/visits/A/cases", data={"finding": "all"}, follow_redirects=False)
    assert r.status_code == 303
    assert "Missing evidence: Payment proof" in text_of(web.client.get(r.headers["location"]).text)


# ---------- DSP-02 letters ----------

IDS = {"name": "Pat Example", "address": "12 Elm St, Springfield", "account_number": "556677",
       "member_number": "W123-456-789"}


def test_tc_dsp_02_1_each_draft_has_the_claim_dates_amounts_and_request():
    v, docs = overbilled(paid=18000)
    v, _ = opened(v, docs)
    r = run(base(visits=[v], documents=docs))
    vr = r.visit("v1")
    plan = {"insurer": "Example Health"}
    expect = {
        "itemized_bill": ["itemized bill", "procedure code"],
        "billing_correction": ["asks me to pay $180.00", "my responsibility is $100.00", "correct the bill to $100.00"],
        "refund": ["I have paid $180.00", "overpayment of $80.00", "refund $80.00"],
        "claim_resubmission": ["resubmit it to Example Health", "member ID W123-456-789"],
        "appeal": ["internal appeal of claim CLM-v1", "corrected Explanation of Benefits", "Member ID: W123-456-789"],
    }
    for kind, phrases in expect.items():
        letter = letters.draft(kind, vr, vr.cases[0], plan, IDS)
        for phrase in ["CLM-v1", "March 1, 2026", "Pat Example", "12 Elm St, Springfield", *phrases]:
            assert phrase in letter.text, (kind, phrase)
        if kind != "appeal":
            assert "Account number: 556677" in letter.text, kind
        assert letter.blanks == [] and "[" not in letter.text, (kind, letter.text)
    blank = letters.draft("appeal", vr, vr.cases[0], plan, {})
    assert "[your member ID]" in blank.text and "member_number" in blank.blanks and "Me" in blank.text


def test_tc_dsp_02_1_balance_billing_duplicate_and_estimate_letters():
    v, docs = overbilled()
    docs[1]["lines"][0]["adjustment"] = 8000  # the discount is applied, but they still ask $180.00: balance billing
    v, _ = opened(v, docs)
    vr = run(base(visits=[v], documents=docs)).visit("v1")
    assert vr.cases[0].findings[0]["kind"] == "balance_billing"
    text = letters.draft("billing_correction", vr, vr.cases[0], None, IDS).text
    assert "agreed to accept the plan's allowed amount ($100.00)" in text

    dup_items = [{"code": "80053", "charge": 4000, "patient_amount": 4000}] * 2
    v2 = {**visit("v2", "2026-05-01"), "payment_path": "self_pay"}
    s2 = bill("s2", "2026-05-10", [{"visit_id": "v2", "patient_amount": 8000, "items": dup_items}])
    v2, _ = edits.open_case(v2, "2026-10-01", findings_of(run(base(visits=[v2], documents=[s2])).visit("v2")))
    vr2 = run(base(visits=[v2], documents=[s2])).visit("v2")
    text = letters.draft("billing_correction", vr2, vr2.cases[0], None, IDS).text
    assert "The same service is charged twice: 80053 appears twice" in text

    v3 = {**visit("v3", "2026-06-01"), "payment_path": "self_pay", "good_faith_estimate": 30000}
    s3 = bill("s3", "2026-06-10", [{"visit_id": "v3", "patient_amount": 80000}])
    v3, _ = edits.open_case(v3, "2026-10-01", findings_of(run(base(visits=[v3], documents=[s3])).visit("v3")))
    vr3 = run(base(visits=[v3], documents=[s3])).visit("v3")
    text = letters.draft("billing_correction", vr3, vr3.cases[0], None, IDS).text
    assert "good-faith estimate for this care was $300.00; the bill is $500.00 more" in text
    assert "No Surprises Act" in text


def test_tc_dsp_02_1_identifiers_only_in_the_application_tier(member, pgdb):
    """The draft carries the real account number, re-identified from the vault in the application tier; the records
    the worker reads, the job queue and the access log hold tokens only, and the draft is not stored anywhere."""
    for name, text in (("s.pdf", STATEMENT), ("e.pdf", EOB)):
        uid = member.upload_id(member.upload(name, make_pdf(text)))
        member.work()
        assert member.confirm(uid, member.review(uid)[1]).status_code == 303
    vid = "v-2026-09-28-example-dermatology"
    r = member.client.post(f"/visits/{vid}/cases", data={"finding": "all"}, follow_redirects=False)
    assert r.status_code == 303
    case_url = r.headers["location"]
    assert "556677" in member.client.get(case_url).text  # the call script has it ready
    jobs_before = admin_sql(pgdb, "SELECT count(*) FROM app.jobs WHERE household_id = %s", (member.who.household_id,))
    draft = member.client.post(f"{case_url}/letter", data={"kind": "billing_correction",
                                                            "member_number": "W123-456-789"})
    assert draft.status_code == 200 and draft.headers["cache-control"] == "no-store"
    text = text_of(draft.text)
    for phrase in ("Account number: 556677", "Claim number: C-2026-0042", "September 28, 2026", "$320.00", "$45.00",
                   "Pat Example"):
        assert phrase in text, phrase
    appeal = text_of(member.client.post(f"{case_url}/letter", data={"kind": "appeal", "member_number":
                                                                    "W123-456-789"}).text)
    assert "Member ID: W123-456-789" in appeal
    hid = member.who.household_id
    records = " ".join(r[0] for r in admin_sql(pgdb, "SELECT data::text FROM app.records WHERE household_id = %s", (hid,)))
    jobs = " ".join(r[0] for r in admin_sql(pgdb, "SELECT payload::text FROM app.jobs WHERE household_id = %s", (hid,)))
    log = " ".join(" ".join(map(str, r)) for r in admin_sql(pgdb, "SELECT * FROM app.access_log WHERE household_id = %s",
                                                             (hid,)))
    for value in ("556677", "W123-456-789", "W123456789", "Dear Example Dermatology"):
        assert value not in records and value not in jobs and value not in log, value
    assert admin_sql(pgdb, "SELECT count(*) FROM app.jobs WHERE household_id = %s", (hid,)) == jobs_before
    assert "letter" in log  # the member's draft is logged as a view, without its text (PRV-10)


def test_tc_dsp_02_2_a_draft_is_never_sent_without_the_member(web):
    """Drafting changes nothing and sends nothing; "I sent it" only logs the contact, without the letter's text."""
    import_sample(web)
    web.client.post(f"/visits/{PCP}/cases", data={"finding": "all"})
    url = f"/visits/{PCP}/cases/case-1"
    before = (web.store.get("visit", PCP), web.store.all("provider_note"))
    page = web.client.post(f"{url}/letter", data={"kind": "billing_correction"})
    assert page.status_code == 200 and "not saved" in page.text and "not legal or financial advice" in page.text
    assert 'action="' + url + '/sent"' in page.text and "never sends anything" in page.text
    download = web.client.post(f"{url}/letter", data={"kind": "refund", "format": "text"})
    assert download.headers["content-type"].startswith("text/plain")
    assert "attachment" in download.headers["content-disposition"] and "Refund request" in download.text
    assert (web.store.get("visit", PCP), web.store.all("provider_note")) == before
    assert web.client.post(f"{url}/sent", data={"kind": "billing_correction", "channel": "letter"},
                           follow_redirects=False).status_code == 303
    [sent] = [n for n in web.store.all("provider_note") if n.get("case_id") == "case-1"]
    assert sent["text"] == "Sent the billing correction" and sent["direction"] == "sent" and sent["channel"] == "letter"
    assert web.store.get("visit", PCP)["cases"][0]["status"] == "contacted"
    assert web.client.post(f"{url}/letter", data={"kind": "nope"}).status_code == 400


# ---------- DSP-03 call script and log ----------

def test_tc_dsp_03_1_call_script_for_a_refund_case():
    v, docs = overbilled(paid=18000)
    vr = run(base(visits=[v], documents=docs)).visit("v1")
    v, _ = edits.open_case(v, "2026-10-01", [f for f in findings_of(vr) if f["kind"] == "overpayment"])
    vr = run(base(visits=[v], documents=docs)).visit("v1")
    assert vr.cases[0].letter == "refund"
    script = letters.call_script(vr, vr.cases[0], {"insurer": "Example Health"}, {"account_number": "556677"})
    assert "Refund the overpayment of $80.00" in script.ask[0]
    assert ("Account number", "556677") in script.ready and ("Claim number", "CLM-v1") in script.ready
    assert "The call reference number (ask for one)" in script.record
    assert "The name of the person you spoke with" in script.record


def test_tc_dsp_03_2_and_03_3_log_a_call(web):
    import_sample(web)
    web.client.post(f"/visits/{PCP}/cases", data={"finding": "all"})
    url = f"/visits/{PCP}/cases/case-1"
    bad = web.client.post(f"{url}/contacts", data={"channel": "phone", "person": "Dana", "reference": "R-77",
                                                   "date": "2026-10-10"})
    assert bad.status_code == 400 and "Say how the call ended" in bad.text
    assert 'value="Dana"' in bad.text  # what was typed comes back
    assert [n for n in web.store.all("provider_note") if n.get("case_id")] == []  # TC-DSP-03-3: nothing saved
    ok = web.client.post(f"{url}/contacts", data={"channel": "phone", "direction": "sent", "date": "2026-10-10",
                                                  "person": "Dana", "reference": "R-77",
                                                  "outcome": "Will send a corrected bill"}, follow_redirects=False)
    assert ok.status_code == 303
    [n] = [n for n in web.store.all("provider_note") if n.get("case_id") == "case-1"]
    assert (n["person"], n["reference"], n["outcome"], n["visit_id"]) == ("Dana", "R-77", "Will send a corrected bill",
                                                                          PCP)
    page = text_of(web.client.get(url).text)
    assert "Spoke with Dana · Ref. R-77" in page and "Will send a corrected bill" in page and "Contacted" in page
    visit_page = text_of(web.client.get(f"/visits/{PCP}").text)
    assert "Will send a corrected bill (Dana, ref. R-77)" in visit_page and "Case: contacted" in visit_page
    ledger = text_of(web.client.get("/providers/prov-pcp?year=2026").text)
    assert "Spoke with Dana" in ledger  # the provider's log shows it too


# ---------- DSP-04 status and follow-ups ----------

def test_tc_dsp_04_1_status_changes_are_dated():
    v, docs = overbilled(paid=10000)
    v, cid = opened(v, docs, today="2026-09-01")
    v = edits.set_case_status(v, cid, "waiting", "2026-09-05", "They will reprocess")
    v = edits.resolve_case(v, cid, "2026-09-20", "corrected", 8000)
    case = v["cases"][0]
    assert [(h["date"], h["status"]) for h in case["history"]] == [("2026-09-01", "open"), ("2026-09-05", "waiting"),
                                                                   ("2026-09-20", "resolved")]
    assert case["history"][1]["note"] == "They will reprocess"
    with pytest.raises(edits.EditError):
        edits.set_case_status(v, cid, "contacted", "2026-09-21")  # reopen first
    with pytest.raises(edits.EditError):
        edits.set_case_status(v, cid, "resolved", "2026-09-21")
    vr = run(base(visits=[v], documents=docs)).visit("v1")
    assert vr.status == "resolved" and vr.cases[0].label == "Resolved"


def test_tc_dsp_04_2_reminders_at_30_and_10_days_rise_in_the_queue():
    v1, d1 = overbilled("v1", "2026-03-01")
    v2, d2 = overbilled("v2", "2026-03-02")
    v3, d3 = overbilled("v3", "2026-01-05")  # an older visit with the same dollars and nothing due
    v1, c1 = opened(v1, d1)
    v2, c2 = opened(v2, d2)
    v2 = edits.set_follow_up(v2, c2, 10)
    notes = [note("n1", "v1", c1, (TODAY - timedelta(days=30)).isoformat()),
             note("n2", "v2", c2, (TODAY - timedelta(days=10)).isoformat())]
    r = run(base(visits=[v1, v2, v3], documents=d1 + d2 + d3, notes=notes))
    assert [c.reminder for c in r.visit("v1").cases + r.visit("v2").cases] == [True, True]
    assert r.visit("v1").due[0].kind == "follow_up" and r.visit("v1").due[0].since == notes[0]["date"]
    queue = [v.id for v in attention_queue(r.visits)]
    assert sorted(queue[:2]) == ["v1", "v2"] and queue[2] == "v3"  # both due today: ahead of v3
    early = [note("n1", "v1", c1, (TODAY - timedelta(days=29)).isoformat()),
             note("n2", "v2", c2, (TODAY - timedelta(days=9)).isoformat())]
    r = run(base(visits=[v1, v2, v3], documents=d1 + d2 + d3, notes=early))
    assert not r.visit("v1").due and not r.visit("v2").due
    assert r.visit("v1").cases[0].follow_up.days_left == 1
    queue = [v.id for v in attention_queue(r.visits)]
    assert queue.index("v3") < queue.index("v1")  # back to dollars, then the oldest


def test_tc_dsp_04_3_a_reply_clears_the_reminder():
    v, docs = overbilled()
    v, cid = opened(v, docs)
    sent = note("n1", "v1", cid, "2026-08-01")
    assert run(base(visits=[v], documents=docs, notes=[sent])).visit("v1").cases[0].reminder
    reply = note("n2", "v1", cid, "2026-08-20", direction="received")
    vr = run(base(visits=[v], documents=docs, notes=[sent, reply])).visit("v1")
    assert not vr.cases[0].reminder and vr.cases[0].follow_up is None and not vr.due
    again = note("n3", "v1", cid, "2026-09-01", channel="phone", direction=None)  # a call: sent by the member
    del again["direction"]
    vr = run(base(visits=[v], documents=docs, notes=[sent, reply, again])).visit("v1")
    assert vr.cases[0].follow_up.due == "2026-10-01" and vr.cases[0].reminder  # a new clock from the call
    with pytest.raises(edits.EditError):
        edits.set_follow_up(v, cid, 0)
    assert "follow_up_days" not in edits.set_follow_up(edits.set_follow_up(v, cid, 10), cid, None)["cases"][0]


def test_tc_dsp_04_on_the_pages(web):
    """Status and follow-up forms; a reply moves a contacted case to waiting."""
    import_sample(web)
    web.client.post(f"/visits/{PCP}/cases", data={"finding": "all"})
    url = f"/visits/{PCP}/cases/case-1"
    web.client.post(f"{url}/sent", data={"kind": "billing_correction", "date": "2026-09-01"})
    assert web.store.get("visit", PCP)["cases"][0]["status"] == "contacted"
    page = text_of(web.client.get(url).text)
    assert "Follow up due" in page and "Oct 1, 2026" in page  # 30 days after Sep 1, already passed on the real date
    home = text_of(web.client.get("/?year=2026").text)
    assert "Follow up with Example Family Medicine: nothing back since Sep 1, 2026" in home
    assert web.client.post(f"{url}/follow-up", data={"days": "400"}).status_code == 400
    web.client.post(f"{url}/follow-up", data={"days": "10"})
    assert web.store.get("visit", PCP)["cases"][0]["follow_up_days"] == 10
    web.client.post(f"{url}/contacts", data={"channel": "email", "direction": "received", "text": "Will reprocess",
                                             "date": "2026-09-05"})
    case = web.store.get("visit", PCP)["cases"][0]
    assert case["status"] == "waiting" and [h["status"] for h in case["history"]] == ["open", "contacted", "waiting"]
    assert "Follow up with" not in text_of(web.client.get("/?year=2026").text)
    web.client.post(f"{url}/status", data={"status": "contacted", "party": "insurer", "note": "Asked the insurer"})
    case = web.store.get("visit", PCP)["cases"][0]
    assert case["status"] == "contacted" and case["party"] == "insurer" and case["history"][-1]["note"] == \
        "Asked the insurer"
    assert web.client.post(f"{url}/status", data={"status": "resolved"}).status_code == 400


# ---------- DSP-05 deadlines ----------

def insurer_finding(vid, eob_date):
    e = eob(vid, 4521, billed=133200, d=eob_date)
    e.update(adjustment=0, not_covered=123000, patient_responsibility=127521)  # C1: the EOB doesn't add up
    return e


def test_tc_dsp_05_1_appeal_deadline_from_the_eob_date():
    v = visit("v1", "2026-02-10")
    docs = [insurer_finding("v1", "2026-03-01")]
    vr = run(base(visits=[v], documents=docs)).visit("v1")
    assert [(d.kind, d.due) for d in vr.deadlines] == [("appeal", "2026-08-28")]  # 180 days, real dates
    v, cid = edits.open_case(v, "2026-03-05", findings_of(vr))
    vr = run(base(visits=[v], documents=docs)).visit("v1")
    assert vr.cases[0].party == "insurer" and vr.cases[0].letter == "appeal"
    assert vr.cases[0].deadlines[0].due == "2026-08-28" and vr.cases[0].deadlines[0].passed
    plans = [{"id": "plan", "plan_year": 2026, "insurer": "X", "limits": [], "appeal_days": 60}]
    assert run(base(visits=[v], documents=docs, plans=plans)).visit("v1").deadlines[0].due == "2026-04-30"
    # A provider-side finding (a missed adjustment) has no appeal deadline to chase.
    v2, d2 = overbilled("v2")
    assert run(base(visits=[v2], documents=d2)).visit("v2").deadlines == []


def test_tc_dsp_05_2_no_surprises_act_deadline_for_a_self_pay_bill_over_the_estimate():
    v = {**visit("v1", "2026-08-01"), "payment_path": "self_pay", "good_faith_estimate": 50000}
    first = bill("s1", "2026-08-10", [{"visit_id": "v1", "patient_amount": 95000}])
    later = bill("s2", "2026-09-10", [{"visit_id": "v1", "patient_amount": 95000}])
    vr = run(base(visits=[v], documents=[first, later])).visit("v1")
    est = next(c for c in vr.checks if c.code == "estimate")
    assert (est.result, est.kind, est.amount) == ("fail", "over_estimate", 45000) and vr.status == "discrepancy"
    assert [(d.kind, d.due) for d in vr.deadlines] == [("nsa", "2026-12-08")]  # 120 days from the first bill
    small = run(base(visits=[{**v, "good_faith_estimate": 80000}], documents=[first])).visit("v1")
    assert next(c for c in small.checks if c.code == "estimate").amount == 15000 and small.deadlines == []
    assert "starts at $400.00" in next(c for c in small.checks if c.code == "estimate").detail
    within = run(base(visits=[{**v, "good_faith_estimate": 95000}], documents=[first])).visit("v1")
    assert next(c for c in within.checks if c.code == "estimate").result == "pass"


def test_tc_dsp_05_3_a_deadline_within_14_days_rises_in_the_queue():
    near = visit("v1", "2026-04-12")  # the same dollars as v2 and the newer visit: last on dollars and age alone
    far = visit("v2", "2026-04-10")
    docs = [insurer_finding("v1", (TODAY - timedelta(days=180 - 10)).isoformat()),
            insurer_finding("v2", (TODAY - timedelta(days=180 - 20)).isoformat())]
    r = run(base(visits=[near, far], documents=docs))
    assert r.visit("v1").due[0].kind == "appeal" and r.visit("v1").due[0].days_left == 10
    assert not r.visit("v2").due and r.visit("v2").deadlines[0].days_left == 20
    assert [v.id for v in attention_queue(r.visits)] == ["v1", "v2"]
    later = run(base(visits=[near, far], documents=docs), today=TODAY - timedelta(days=5))  # 15 days left
    assert [v.id for v in attention_queue(later.visits)] == ["v2", "v1"]


def test_tc_dsp_05_on_the_pages(web, tmp_path):
    """The good-faith estimate on a self-pay visit, the finding and the No Surprises Act deadline on the case."""
    from tests.test_r1_reconcile_pages import scenario

    data = scenario()
    data["visits"][0]["payment_path"] = "self_pay"
    data["documents"] = [d for d in data["documents"] if d.get("visit_id") != "A"]
    data["documents"].append({"id": "s1", "type": "provider_bill", "date": "2026-02-10", "provider_id": "prov-a",
                              "balance_due": 950, "lines": [{"visit_id": "A", "patient_amount": 950}]})
    import_data(web, tmp_path, data)
    assert "Good-faith estimate" in web.client.get("/visits/A").text
    assert web.client.post("/visits/A/estimate", data={"good_faith_estimate": "abc"}).status_code == 400
    web.client.post("/visits/A/estimate", data={"good_faith_estimate": "500"})
    assert web.store.get("visit", "A")["good_faith_estimate"] == 50000
    page = text_of(web.client.get("/visits/A").text)
    assert "Bill exceeds the good-faith estimate" in page and "Start a No Surprises Act dispute by Jun 10, 2026" in page
    r = web.client.post("/visits/A/cases", data={"finding": "estimate:45000"}, follow_redirects=False)
    case = text_of(web.client.get(r.headers["location"]).text)
    assert "Start a No Surprises Act dispute" in case and "by Jun 10, 2026" in case
    web.client.post("/visits/A/estimate", data={"good_faith_estimate": ""})
    assert "good_faith_estimate" not in web.store.get("visit", "A")


# ---------- DSP-07 outcomes and savings ----------

def resolved(v, docs, result, amount, today="2026-09-01"):
    v, cid = opened(v, docs)
    return edits.resolve_case(v, cid, today, result, amount), cid


def test_tc_dsp_07_1_refunded_75_adds_75():
    v, docs = overbilled(paid=18000)
    before = run(base(visits=[v], documents=docs)).recovered_lifetime
    v, _ = resolved(v, docs, "refunded", 7500)
    r = run(base(visits=[v], documents=docs))
    assert r.recovered_lifetime - before == 7500 and r.visit("v1").cases[0].recovered == 7500


def test_tc_dsp_07_2_written_off_and_denied():
    v1, d1 = overbilled("v1")
    v2, d2 = overbilled("v2", "2026-03-05")
    v1, _ = resolved(v1, d1, "written_off", 20000)
    v2, _ = resolved(v2, d2, "denied", 9999)  # denied counts nothing, whatever was typed
    assert v2["cases"][0]["outcome"]["recovered"] == 0
    assert disputes.recovered([v1]) == 20000 and disputes.recovered([v2]) == 0
    assert run(base(visits=[v1, v2], documents=d1 + d2)).recovered_lifetime == 20000
    with pytest.raises(edits.EditError):
        edits.resolve_case(v1, "case-1", "2026-09-02", "refunded", 100)  # already resolved
    with pytest.raises(edits.EditError):
        edits.resolve_case(overbilled()[0], "case-1", "2026-09-02", "refunded", 100)  # no such case


def test_tc_dsp_07_3_reopened_and_closed_again_counts_once():
    v, docs = overbilled(paid=18000)
    v, cid = resolved(v, docs, "corrected", 8000)
    assert [c.result for c in run(base(visits=[v], documents=docs)).visit("v1").checks
            if c.code in ("C2", "C4")] == ["closed", "closed"]  # the case's findings close with it
    v = edits.reopen_case(v, cid, "2026-09-05")
    vr = run(base(visits=[v], documents=docs)).visit("v1")
    assert disputes.recovered([v]) == 0 and vr.status == "in_dispute" and len(vr.findings) == 2  # reopened too
    assert v["cases"][0]["history"][-1]["note"] == "Reopened (was corrected)"
    v = edits.resolve_case(v, cid, "2026-09-10", "refunded", 7500)
    assert disputes.recovered([v]) == 7500
    assert run(base(visits=[v], documents=docs)).recovered_lifetime == 7500


def test_tc_dsp_07_on_the_pages(web):
    """Resolving on the case page: the outcome, the dollars, the findings closed; Cases adds up every year."""
    import_sample(web)
    web.client.post(f"/visits/{PCP}/cases", data={"finding": "C4:8000"})
    url = f"/visits/{PCP}/cases/case-1"
    assert 'name="recovered" inputmode="decimal" value="80.00"' in web.client.get(url).text
    assert web.client.post(f"{url}/resolve", data={"result": "refunded", "recovered": "x"}).status_code == 400
    web.client.post(f"{url}/resolve", data={"result": "refunded", "recovered": "75.00", "note": "Check received"})
    page = text_of(web.client.get(url).text)
    assert "Resolved" in page and "Refunded" in page and "$75.00 recovered" in page and "Check received" in page
    cases = text_of(web.client.get("/cases").text)
    assert "Recovered so far $75.00" in cases and "Recovered in" in cases and "No open cases" in cases
    assert "$75.00 recovered so far" in text_of(web.client.get("/?year=2026").text)
    web.client.post(f"{url}/reopen")
    assert "Recovered so far $0.00" in text_of(web.client.get("/cases").text)
    assert "In dispute" in text_of(web.client.get(f"/visits/{PCP}").text)
    web.client.post(f"{url}/resolve", data={"result": "refunded", "recovered": "75"})
    assert "Recovered so far $75.00" in text_of(web.client.get("/cases").text)


# ---------- ADR-042: storage, old disputes, merges, isolation ----------

def test_an_old_minimal_dispute_reads_as_a_case():
    v, docs = overbilled()
    old = {**v, "dispute": {"status": "open", "opened": "2026-09-01", "note": "Called billing"}}
    vr = run(base(visits=[old], documents=docs)).visit("v1")
    assert vr.status == "in_dispute" and vr.cases[0].id == "dispute" and vr.cases[0].case["note"] == "Called billing"
    changed = edits.resolve_case(old, "dispute", "2026-09-10", "corrected", 8000)
    assert "dispute" not in changed and changed["cases"][0]["status"] == "resolved"
    closed = {**v, "dispute": {"status": "closed", "opened": "2026-09-01", "closed": "2026-09-03",
                               "outcome": "accepted"}}
    vr = run(base(visits=[closed], documents=docs)).visit("v1")
    assert vr.cases[0].status == "resolved" and vr.status == "discrepancy"  # it didn't close the finding
    v2, cid = edits.open_case(old, "2026-10-01", [])
    assert [c["id"] for c in v2["cases"]] == ["dispute", "case-2"] and "dispute" not in v2


def test_cases_survive_reimport_and_move_on_merge(web, tmp_path):
    """ADR-011: a case is the member's edit, so importing the same file again keeps it; merging visits moves the
    dropped visit's cases and their notes."""
    from tests.test_r1_reconcile_pages import scenario

    data = scenario()
    data["documents"] += [{"id": f"s-{v}", "type": "provider_bill", "date": "2026-03-05", "provider_id": "prov-a",
                           "balance_due": 180, "lines": [{"visit_id": v, "patient_amount": 180}]} for v in "AB"]
    import_data(web, tmp_path, data)
    web.client.post("/visits/A/cases", data={"finding": "all"})
    web.client.post("/visits/B/cases", data={"finding": "all"})
    web.client.post("/visits/B/cases/case-1/contacts", data={"channel": "phone", "outcome": "Promised a fix",
                                                             "date": "2026-10-01"})
    import_data(web, tmp_path, copy.deepcopy(data))
    assert [c["id"] for c in web.store.get("visit", "A")["cases"]] == ["case-1"]
    assert web.client.post("/visits/A/merge", data={"other": "B"}, follow_redirects=False).status_code == 303
    assert [c["id"] for c in web.store.get("visit", "A")["cases"]] == ["case-1", "case-2"]
    [n] = [n for n in web.store.all("provider_note") if n.get("case_id")]
    assert (n["visit_id"], n["case_id"]) == ("A", "case-2")
    assert "Promised a fix" in text_of(web.client.get("/visits/A/cases/case-2").text)


@pytest.mark.postgres
def test_another_household_cannot_reach_a_case(household, app_db, tmp_path):
    """PRV-11: every case route is household-scoped."""
    from tests.test_r1_reconcile_pages import scenario
    from tests.test_web import ReleaseOne

    a, b = ReleaseOne(household, app_db), ReleaseOne(household, app_db)
    import_data(a, tmp_path, scenario())
    a.client.post("/visits/A/cases", data={"finding": "all"})
    before = a.store.get("visit", "A")
    assert b.client.get("/visits/A/cases/case-1").status_code == 404
    for path, data in [("", {"finding": "all"}), ("/case-1/status", {"status": "waiting"}),
                       ("/case-1/follow-up", {"days": "5"}), ("/case-1/contacts", {"outcome": "x"}),
                       ("/case-1/letter", {"kind": "refund"}), ("/case-1/sent", {"kind": "refund"}),
                       ("/case-1/resolve", {"result": "refunded"}), ("/case-1/reopen", {})]:
        assert b.client.post(f"/visits/A/cases{path}", data=data).status_code == 404, path
    assert a.store.get("visit", "A") == before and "No open cases" in b.client.get("/cases").text


def make_pdf(text):
    from tests.pdfs import make_pdf as pdf

    return pdf(text)


def test_schema_accepts_a_case_and_the_new_note_fields():
    from mhs.data import importer
    from mhs.data.money import to_dollars

    v, docs = overbilled(paid=18000)
    v, cid = resolved(v, docs, "refunded", 7500)
    v["good_faith_estimate"] = 10000
    assert importer.record_errors("visit", to_dollars(v)) == []
    n = note("n1", "v1", cid, "2026-09-01", channel="phone", party="insurer", person="Dana", reference="R-1",
             outcome="ok")
    assert importer.record_errors("provider_note", n) == []
    assert re.search(r"appeal_days", (SAMPLE.parent.parent / "schema" / "mhs-ingest.schema.json").read_text())
