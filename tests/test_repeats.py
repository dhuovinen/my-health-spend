"""Repeat services across visits (REC-14, ADR-045), the matching rule it depends on (ADR-046), and the Visits rows."""

import re

from mhs.core import edits, matching
from mhs.core.reconcile import build_report
from tests.test_r1_reconcile import bill, claim
from tests.test_r1_reconcile_pages import import_data, scenario, text_of
from tests.test_reconcile import TODAY, base, visit
from tests.test_web import web  # noqa: F401 (fixture)


def line(code="99214", billed=50000, allowed=40000, share=40000, deductible=None, **extra):
    deductible = share if deductible is None else deductible
    return {"code": code, "billed": billed, "allowed": allowed, "insurer_paid": allowed - share,
            "adjustment": billed - allowed, "deductible": deductible, "patient_responsibility": share, **extra}


def seen(*visits, plans=None, members=None, providers=None, year=2026):
    """visits: (id, date, lines) or (id, date, lines, changes to the visit). Returns the report."""
    vs, docs = [], []
    for spec in visits:
        vid, d, lines, *more = spec
        v = visit(vid, d)
        v.update(more[0] if more else {})
        vs.append(v)
        if lines is not None:
            docs.append({**claim(vid, f"C-{vid}", lines, d=d), "plan_id": v["plan_id"], "provider_id": v["provider_id"]})
    ds = base(visits=vs, documents=docs)
    if plans:
        ds.plans = plans
    if members:
        ds.members = members
    return build_report(ds, year, TODAY)


def flags(r, vid):
    return [(c.code, c.amount) for c in r.visit(vid).repeat_flags]


def test_tc_rec_14_1_changed_allowed_amount():
    r = seen(("v1", "2026-02-01", [line()]), ("v2", "2026-03-01", [line(allowed=25000, share=25000)]))
    assert flags(r, "v1") == [] and flags(r, "v2") == [("R14-allowed", 15000)]
    [f] = r.visit("v2").repeat_flags
    assert "$400.00 on Feb 1, 2026" in f.detail and "$250.00 on Mar 1, 2026" in f.detail and "$150.00" in f.detail
    assert "Worth a closer look" in f.detail and "a new contract" in f.detail and f.earlier_visit == "v1"
    alone = seen(("v2", "2026-03-01", [line(allowed=25000, share=25000)])).visit("v2")
    assert (r.visit("v2").status, r.visit("v2").at_stake) == (alone.status, alone.at_stake)  # status and dollars unchanged


def test_tc_rec_14_2_a_ten_cent_price_change_is_flagged():
    r = seen(("v1", "2026-02-01", [line(billed=15000, allowed=9000, share=9000)]),
             ("v2", "2026-03-01", [line(billed=15010, allowed=9000, share=9000)]))
    assert flags(r, "v2") == [("R14-billed", 10)]


def test_tc_rec_14_3_the_deductible_explains_a_lower_share():
    r = seen(("v1", "2026-02-01", [line()]), ("v2", "2026-03-01", [line(share=8000, deductible=0, coinsurance=8000)]))
    assert flags(r, "v2") == []
    [note] = [c for c in r.visit("v2").checks if c.code == "R14-share"]
    assert note.result == "info" and "deductible" in note.detail


def test_tc_rec_14_4_a_lower_share_the_deductible_does_not_explain():
    r = seen(("v1", "2026-02-01", [line()]), ("v2", "2026-03-01", [line(share=25000)]))
    assert flags(r, "v2") == [("R14-share", 15000)]


def test_the_share_keeps_the_dollar_tolerance():
    r = seen(("v1", "2026-02-01", [line()]), ("v2", "2026-03-01", [line(share=39950)]))
    assert flags(r, "v2") == []


def test_tc_rec_14_5_another_person_group_plan_or_year_is_not_compared():
    changed = [line(allowed=25000, share=25000)]
    plans = [{"id": "plan", "plan_year": 2026, "insurer": "X", "limits": []},
             {"id": "plan2", "plan_year": 2026, "insurer": "Y", "limits": []}]
    two = [{"id": "me", "name": "Me"}, {"id": "you", "name": "You"}]
    for change in ({"member_id": "you"}, {"provider_id": "b"}, {"plan_id": "plan2"}):
        r = seen(("v1", "2026-02-01", [line()]), ("v2", "2026-03-01", changed, change), plans=plans, members=two)
        assert flags(r, "v2") == [], change
    r = seen(("v1", "2025-12-01", [line()]), ("v2", "2026-01-15", changed))
    assert flags(r, "v2") == []


def test_tc_rec_14_6_compared_per_unit_and_with_the_same_modifiers():
    r = seen(("v1", "2026-02-01", [line(billed=20000, allowed=20000, share=20000, units=2)]),
             ("v2", "2026-03-01", [line(billed=10000, allowed=10000, share=10000, units=1)]))
    assert flags(r, "v2") == []
    r = seen(("v1", "2026-02-01", [line()]), ("v2", "2026-03-01", [line(code="99214-25", allowed=25000, share=25000)]))
    assert flags(r, "v2") == []


def test_tc_rec_14_7_changed_codes_in_a_series():
    pair = [line("A", 100, 100, 100), line("B", 100, 100, 100)]
    with_c = pair + [line("C", 100, 100, 100)]
    r = seen(*[(f"v{i}", f"2026-0{i}-01", pair) for i in range(1, 5)], ("v5", "2026-05-01", with_c))
    assert flags(r, "v5") == [("R14-codes", 0)] and "added C" in r.visit("v5").repeat_flags[0].detail
    r = seen(("v1", "2026-01-01", pair), ("v2", "2026-02-01", pair), ("v3", "2026-03-01", with_c))
    assert flags(r, "v3") == []  # only two earlier visits


def test_tc_rec_14_8_no_line_detail_or_unconfirmed_documents_are_not_compared():
    r = seen(("v1", "2026-02-01", [line()]), ("v2", "2026-03-01", None))
    assert flags(r, "v2") == []  # an extraction waiting for review isn't a document yet
    no_lines = base(visits=[visit("v1", "2026-02-01"), visit("v2", "2026-03-01")], documents=[
        claim("v1", "C1", d="2026-02-01", billed=50000, allowed=40000, insurer_paid=0, patient_responsibility=40000),
        bill("s2", "2026-03-10", [{"visit_id": "v2", "billed_charge": 30000, "patient_amount": 30000}])])
    assert flags(build_report(no_lines, 2026, TODAY), "v2") == []


def test_a_billed_change_on_statement_lines_is_compared_without_an_eob():
    item = lambda charge: [{"code": "96413", "description": "Infusion", "charge": charge, "patient_amount": charge}]  # noqa: E731
    ds = base(visits=[visit("v1", "2026-02-01"), visit("v2", "2026-03-01")], documents=[
        bill("s1", "2026-02-10", [{"visit_id": "v1", "billed_charge": 40000, "patient_amount": 40000, "items": item(40000)}]),
        bill("s2", "2026-03-10", [{"visit_id": "v1", "billed_charge": 40000, "patient_amount": 40000, "items": item(40000)},
                                  {"visit_id": "v2", "billed_charge": 25000, "patient_amount": 25000, "items": item(25000)}])])
    assert flags(build_report(ds, 2026, TODAY), "v2") == [("R14-billed", 15000)]


def test_tc_rec_14_9_one_flag_and_it_stays_closed():
    low = [line(allowed=25000, share=25000)]
    specs = [("v1", "2026-01-01", [line()]), ("v2", "2026-02-01", [line()]), ("v3", "2026-03-01", low),
             ("v4", "2026-04-01", low), ("v5", "2026-05-01", low)]
    r = seen(*specs)
    assert [v for v in ("v1", "v2", "v3", "v4", "v5") if flags(r, v)] == ["v3"]
    closing = edits.close_finding(visit("v3", "2026-03-01"), "R14-allowed", 15000, "2026-10-01", "marked wrong", "wrong",
                                  kind="repeat_allowed")["closed_findings"]
    r = seen(*specs[:2], ("v3", "2026-03-01", low, {"closed_findings": closing}), *specs[3:])
    assert flags(r, "v3") == [] and [c.result for c in r.visit("v3").checks if c.code == "R14-allowed"] == ["closed"]


def repeat_data():
    def eob_doc(vid, d, allowed):
        return {"id": f"eob-{vid}", "type": "eob", "date": d, "plan_id": "plan", "provider_id": "prov-a", "visit_id": vid,
                "claim_number": f"C-{vid}", "claim_status": "processed", "billed": 500, "allowed": allowed,
                "adjustment": 500 - allowed, "insurer_paid": 0, "deductible": allowed, "copay": 0, "coinsurance": 0,
                "not_covered": 0, "patient_responsibility": allowed,
                "lines": [{"code": "96413", "description": "Infusion", "billed": 500, "allowed": allowed,
                           "adjustment": 500 - allowed, "insurer_paid": 0, "deductible": allowed,
                           "patient_responsibility": allowed}]}
    data = scenario()
    data["documents"] = [eob_doc("A", "2026-02-01", 400), eob_doc("B", "2026-02-03", 250)]
    return data


def test_tc_rec_14_10_a_flagged_visit_on_the_pages_and_finding_accuracy(web, tmp_path):
    import_data(web, tmp_path, repeat_data())
    page = web.client.get("/visits/B").text
    words = text_of(page)
    assert "Allowed amount changed" in words and "Worth a closer look" in words and "a new contract" in words
    assert "Feb 1, 2026" in words and "Feb 3, 2026" in words and 'href="/visits/A"' in page
    assert 'style="' not in page and "onclick" not in page
    assert "Worth a closer look: 1" in text_of(web.client.get("/visits?year=2026").text)
    only = web.client.get("/visits?year=2026&repeat=1").text
    assert 'href="/visits/B"' in only and 'href="/visits/A"' not in only
    r = web.client.post("/visits/B/findings", data={"code": "R14-allowed", "amount": "15000", "verdict": "wrong"})
    assert r.status_code in (200, 303)
    assert web.store.get("visit", "B")["closed_findings"][0]["verdict"] == "wrong"
    assert "Repeat service" in text_of(web.client.get("/accuracy").text)
    assert "Worth a closer look: 1" not in text_of(web.client.get("/visits?year=2026").text)


# ---------- ADR-046: repeat treatment stays separate visits ----------

def test_a_far_off_date_does_not_propose_a_visit_however_alike():
    v = visit("v1", "2026-03-18")
    far = matching.Facts("a", "2026-04-15", "me", None, 21000)
    assert matching.score(far, v, amounts={21000}).decision == "none"
    weekly = matching.Facts("a", "2026-03-25", "me", None, 21000)
    assert matching.score(weekly, v, amounts={21000}).decision == "none"  # weekly treatment stays apart
    near = matching.Facts("a", "2026-03-20", "me", None, 21000)
    assert matching.score(near, v, amounts={21000}).decision != "none"
    same_claim = matching.Facts("a", "2026-04-15", "me", "C1", 21000)
    assert matching.score(same_claim, v, claim_numbers={"C1"}, amounts={21000}).decision != "none"


# ---------- ADR-046: visits as rows, filters and sort ----------

def order(html: str) -> list[str]:
    return re.findall(r'class="visit-row s-edge[^"]*" href="/visits/([^"]+)"', html)


def test_visits_are_rows_sorted_by_date_with_filters(web, tmp_path):
    import_data(web, tmp_path, scenario())
    newest = web.client.get("/visits?year=2026").text
    assert order(newest) == ["B", "A"] and "card visit-card" not in newest
    assert "sort=oldest" in newest  # the Date heading turns the order round, keeping the filters
    assert order(web.client.get("/visits?year=2026&sort=oldest").text) == ["A", "B"]
    assert order(web.client.get("/visits?year=2026&sort=nonsense").text) == ["B", "A"]
    assert order(web.client.get("/visits?year=2026&start=2026-02-02").text) == ["B"]
    assert order(web.client.get("/visits?year=2026&end=2026-02-02").text) == ["A"]
    kept = web.client.get("/visits?year=2026&start=2026-02-01&sort=oldest").text
    assert "start=2026-02-01&amp;sort=newest" in kept
    home = web.client.get("/?year=2026").text
    assert order(home) == ["B", "A"] and 'action="/visits"' in home
