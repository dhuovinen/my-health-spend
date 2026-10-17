"""Phase 1.4: matching and reconciliation in core (TEST_PLAN 3.2 to 3.4; ADR-035). Unit level, "today" pinned.

Each test names the TEST_PLAN cases it covers. Money in cents.
"""

import random
from datetime import date, timedelta

import pytest

from mhs.core import edits, matching
from mhs.core.lines import BUCKETS, buckets, pair_lines
from mhs.core.reconcile import STATUS_ORDER, Dataset, build_report
from mhs.data.importer import commit, prepare
from mhs.data.repository import load_dataset
from tests.test_reconcile import TODAY, base, eob, pay, visit


def bill(bid, d, lines, provider="a", **extra):
    return {"id": bid, "type": "provider_bill", "date": d, "provider_id": provider,
            "balance_due": sum(l.get("balance", l["patient_amount"]) for l in lines), "lines": lines, **extra}


def claim(vid, number, lines=(), d="2026-02-01", **amounts):
    """An EOB claim; header amounts default to the sum of its lines."""
    keys = ("billed", "allowed", "adjustment", "insurer_paid", "deductible", "copay", "coinsurance", "not_covered",
            "patient_responsibility", "additional_savings", "secondary_paid")
    head = {k: sum(l[k] for l in lines if k in l) for k in keys if any(k in l for l in lines)}
    head.update(amounts)
    return {"id": f"eob-{number}", "type": "eob", "date": d, "plan_id": "plan", "provider_id": "a", "visit_id": vid,
            "claim_number": number, "claim_status": "processed", **head, "lines": list(lines)}


def run(ds, today=TODAY):
    return build_report(ds, 2026, today)


def check(v, code):
    return next(c for c in v.checks if c.code == code)


def docs_state(v):
    return {d.kind: d.state for d in v.documents}


LINE_250 = {"code": "99214", "billed": 25000, "adjustment": 12500, "insurer_paid": 8000, "patient_responsibility": 4500,
            "deductible": 2000, "copay": 2500}


# ---------- MAT-01 data model ----------

def test_mat_01_1_visit_with_two_claims_three_lines_each_round_trips(store, config):
    """TC-MAT-01-1: two claims of three lines each, with the member's allocation, through the store and back."""
    def lines(prefix):
        return [{"code": f"{prefix}{i}", "service_date": "2026-03-01", "billed": 100, "allowed": 60,
                 "insurer_paid": 40, "patient_responsibility": 20} for i in range(3)]
    data = {"schema_version": "0.1",
            "plans": [{"id": "plan", "plan_year": 2026, "insurer": "X"}],
            "accounts": [{"id": "hsa", "name": "HSA", "type": "hsa"}],
            "providers": [{"id": "a", "name": "A"}],
            "visits": [{"id": "v1", "date": "2026-03-01", "provider_id": "a", "plan_id": "plan",
                        "category": "service"}],
            "documents": [
                {**claim("v1", "F-1", lines("8000")), "date": "2026-03-20"},
                {**claim("v1", "P-2", lines("9921")), "date": "2026-03-21"},
                {"id": "pay1", "type": "payment", "date": "2026-04-01", "provider_id": "a", "account_id": "hsa",
                 "amount": 1.20, "allocations": [{"visit_id": "v1", "amount": 1.20}], "allocation_source": "member"},
            ]}
    for d in data["documents"]:
        if d["type"] == "eob":  # ingest files are in dollars
            for rec in [d, *d["lines"]]:
                for k in ("billed", "allowed", "adjustment", "insurer_paid", "patient_responsibility"):
                    if k in rec:
                        rec[k] = rec[k] / 100
    plan = prepare(data, store, "test", None)
    assert plan.ok, plan.errors
    commit(plan, store, config.documents_dir)
    v = build_report(load_dataset(store), 2026, TODAY).visit("v1")
    assert [c["claim_number"] for c in v.claims] == ["F-1", "P-2"]
    assert [len(c["lines"]) for c in v.claims] == [3, 3]
    assert v.total_billed == 600 and v.insurer_owed == 120
    assert [(a.amount, a.source) for a in v.allocations] == [(120, "member")]
    assert check(v, "C1").result == "pass" and v.status == "complete"
    assert edits.references("v1", store.all("document")) == ["eob-F-1", "eob-P-2", "pay1"]


def test_mat_01_2_one_payment_across_three_open_visits():
    """TC-MAT-01-2: a $300.00 payment to a provider with three open visits."""
    ds = base(visits=[visit("v1", "2026-01-05"), visit("v2", "2026-02-05"), visit("v3", "2026-03-05")],
              documents=[eob("v1", 12000), eob("v2", 10000), eob("v3", 15000), pay("p", "2026-04-01", 30000)])
    r = run(ds)
    parts = {vid: r.visit(vid).paid for vid in ("v1", "v2", "v3")}
    assert parts == {"v1": 12000, "v2": 10000, "v3": 8000} and sum(parts.values()) == 30000
    assert r.visit("v3").remaining == 7000 and r.group("a").paid == 30000


def test_mat_01_3_one_visit_paid_by_hsa_and_card():
    """TC-MAT-01-3."""
    ds = base(visits=[visit("v1", "2026-01-05")],
              documents=[eob("v1", 10000), pay("p1", "2026-02-01", 6000), pay("p2", "2026-02-02", 4000, account="card")])
    v = run(ds).visit("v1")
    assert sorted(a.payment["id"] for a in v.allocations) == ["p1", "p2"]
    assert (v.settlement.paid_hsa, v.settlement.paid_other, v.remaining) == (6000, 4000, 0)
    assert v.status == "complete"


def test_mat_01_5_account_transactions_stay_out_of_visit_totals():
    """TC-MAT-01-5: contributions, interest and fees have no visit and change no visit total."""
    txns = [{"id": f"t{i}", "type": "account_transaction", "date": "2026-02-01", "account_id": "hsa", "kind": kind,
             "amount": 5000} for i, kind in enumerate(("contribution_employee", "interest", "fee"))]
    ds = base(visits=[visit("v1", "2026-01-05")], documents=[eob("v1", 10000), *txns])
    r = run(ds)
    assert r.totals["you_paid"] == 0 and r.visit("v1").remaining == 10000
    assert edits.references("v1", ds.documents) == ["eob-v1"]


# ---------- MAT-05 document-to-visit matching ----------

VISITS = [{"id": "v-me", "date": "2026-03-10", "provider_id": "a", "member_id": "me"},
          {"id": "v-you", "date": "2026-03-10", "provider_id": "a", "member_id": "you"}]


def test_mat_05_1_same_person_provider_date_and_claim_links_with_reasons():
    """TC-MAT-05-1."""
    docs = [{"type": "eob", "visit_id": "v-me", "claim_number": "C9", "billed": 25000}]
    top, what = matching.best(matching.Facts("a", "2026-03-10", "me", "C9", 25000), VISITS, docs)
    assert (top.visit_id, top.score, what) == ("v-me", 1.0, "link")
    assert top.reasons == ["same provider", "same date of service", "same person", "same claim number C9",
                           "same billed amount $250.00"]


def test_mat_05_2_score_bands():
    """TC-MAT-05-2: 0.95 links (and can be undone: see TC-MAT-07-2), 0.75 is proposed, 0.5 stays unmatched."""
    assert [matching.decision(s) for s in (0.95, 0.75, 0.5)] == ["link", "propose", "none"]
    # Same provider and person, two days apart: proposed; three weeks apart: unmatched.
    near, what = matching.best(matching.Facts("a", "2026-03-12", "me"), VISITS[:1])
    assert (near.score, what) == (0.75, "propose") and "dates of service 2 days apart" in near.reasons
    assert matching.best(matching.Facts("a", "2026-03-31", "me"), VISITS[:1]) == (None, "none")
    # A near tie between two visits is only proposed, never linked.
    twins = [{**VISITS[0], "member_id": None}, {**VISITS[0], "id": "v-twin", "member_id": None}]
    assert matching.best(matching.Facts("a", "2026-03-10", "me"), twins)[1] == "propose"


def test_mat_05_3_two_members_same_provider_same_day():
    """TC-MAT-05-3: each document goes to its own member's visit."""
    assert matching.best(matching.Facts("a", "2026-03-10", "you"), VISITS)[0].visit_id == "v-you"
    assert matching.best(matching.Facts("a", "2026-03-10", "me"), VISITS)[0].visit_id == "v-me"


def test_mat_05_4_same_amount_and_date_other_provider_never_matches():
    """TC-MAT-05-4."""
    docs = [{"type": "eob", "visit_id": "v-me", "billed": 25000}]
    assert matching.best(matching.Facts("b", "2026-03-10", "me", billed=25000), VISITS, docs) == (None, "none")
    assert matching.best(matching.Facts("b", "2026-03-10", "me"), VISITS, same_group={"a"})[1] == "link"


def test_mat_07_2_rejected_visit_is_never_proposed_again():
    """TC-MAT-07-2 (core): a visit the member rejected for a document drops out of its candidates."""
    facts = matching.Facts("a", "2026-03-10", "me", rejected={"v-me"})
    assert matching.best(facts, VISITS) == (None, "none")
    doc = {"id": "e", "type": "eob", "visit_id": "v-me", "match": {"status": "auto", "score": 0.9}}
    moved = edits.move_document(doc, "v-me", "v-new", reject=True)
    assert moved["visit_id"] == "v-new" and moved["match"] == {"status": "confirmed", "score": 0.9,
                                                               "rejected": ["v-me"]}


# ---------- MAT-06 line pairing ----------

def test_mat_06_1_lines_pair_by_code():
    """TC-MAT-06-1."""
    items = [{"code": c, "charge": 100 * n} for n, c in enumerate(("99214", "85025", "80053"), 1)]
    lines = [{"code": c, "billed": 100 * n} for n, c in enumerate(("80053", "99214", "85025"), 1)]
    m = pair_lines(items, lines)
    assert m.complete and [(p.bill[0]["code"], p.eob[0]["code"]) for p in m.pairs] == [
        ("99214", "99214"), ("85025", "85025"), ("80053", "80053")]


def test_mat_06_2_bundled_component_pairs_one_to_many():
    """TC-MAT-06-2: 80053 on the bill; 80053 plus a component denied as bundled (CARC 97) on the EOB."""
    m = pair_lines([{"code": "80053", "charge": 12000}],
                   [{"code": "80053", "billed": 12000}, {"code": "82947", "billed": 0, "remark_codes": ["CO-97"]}])
    [p] = m.pairs
    assert m.complete and p.how == "bundled" and [e["code"] for e in p.eob] == ["80053", "82947"]
    assert "82947 bundled into 80053" in p.notes[0]


def test_mat_06_3_separate_bill_lines_one_panel_line():
    """TC-MAT-06-3: three lab lines on the bill, one panel line on the EOB."""
    items = [{"code": c, "charge": a} for c, a in (("82947", 3000), ("84132", 2500), ("82565", 4500))]
    m = pair_lines(items, [{"code": "80048", "billed": 10000}])
    [p] = m.pairs
    assert m.complete and p.how == "panel" and len(p.bill) == 3 and "3 bill lines processed as one" in p.notes[0]


def test_mat_06_4_unmatched_bill_line_is_reported_with_its_amount():
    """TC-MAT-06-4, and how it shows on the visit."""
    m = pair_lines([{"code": "99214", "charge": 15000}, {"code": "36415", "charge": 1500}],
                   [{"code": "99214", "billed": 15000}])
    assert [i["code"] for i in m.bill_only] == ["36415"] and not m.eob_only
    ds = base(visits=[visit("v1", "2026-02-01")],
              documents=[claim("v1", "C1", [{"code": "99214", "billed": 15000, "adjustment": 5000,
                                             "insurer_paid": 0, "patient_responsibility": 10000}]),
                         bill("s", "2026-02-20", [{"visit_id": "v1", "patient_amount": 10000, "billed_charge": 16500,
                                                   "adjustment": 6500, "items": [{"code": "99214", "charge": 15000},
                                                                                 {"code": "36415", "charge": 1500}]}])])
    lines = check(run(ds).visit("v1"), "lines")
    assert lines.result == "info" and "on the bill only: 36415 $15.00" in lines.detail


def test_mat_06_5_modifier_difference_is_noted():
    """TC-MAT-06-5."""
    [p] = pair_lines([{"code": "99214", "charge": 15000}], [{"code": "99214-25", "billed": 15000}]).pairs
    assert p.how == "modifier" and p.notes == ["modifier differs: 99214 on the bill, 99214-25 on the EOB"]


# ---------- MAT-10 document completeness ----------

def test_mat_10_1_bill_and_eob_without_payment():
    """TC-MAT-10-1."""
    ds = base(visits=[visit("v1", "2026-02-01")],
              documents=[eob("v1", 4500), bill("s", "2026-02-20", [{"visit_id": "v1", "patient_amount": 4500}])])
    v = run(ds).visit("v1")
    assert docs_state(v) == {"eob": "present", "bill": "present", "itemized_bill": "not_applicable",
                             "receipt": "not_applicable", "payment": "expected"}


def test_mat_10_3_member_marks_a_document_not_applicable_or_expected():
    """TC-MAT-10-3 (core): the member's choice counts; asking for an itemized bill makes the visit wait for it."""
    paid = [eob("v1", 4500), pay("p", "2026-02-21", 4500)]
    v = visit("v1", "2026-02-01")
    asked = edits.set_expectation(v, "itemized_bill", "expected", "2026-10-01")
    r = run(base(visits=[asked], documents=paid))
    assert docs_state(r.visit("v1"))["itemized_bill"] == "expected" and r.visit("v1").status == "awaiting_documents"
    assert r.visit("v1").missing == ["Itemized bill"]
    later = run(base(visits=[asked], documents=paid), today=date(2026, 11, 15))
    assert later.visit("v1").status == "missing_documents"
    not_needed = edits.set_expectation(asked, "itemized_bill", "not_applicable", "2026-11-15")
    assert run(base(visits=[not_needed], documents=paid)).visit("v1").status == "complete"
    no_eob = edits.set_expectation(visit("v2", "2026-01-01"), "eob", "not_applicable", "2026-10-01")
    assert run(base(visits=[no_eob])).visit("v2").status == "complete"
    with pytest.raises(edits.EditError):
        edits.set_expectation(v, "x-ray", "expected", "2026-10-01")


def test_mat_10_5_self_pay_visit():
    """TC-MAT-10-5: EOB not applicable; a bill or receipt and payment proof are expected."""
    v = {**visit("v1", "2026-10-01"), "payment_path": "self_pay"}
    r = run(base(visits=[v]))
    s = docs_state(r.visit("v1"))
    assert s["eob"] == "not_applicable" and s["bill"] == "expected" and s["receipt"] == "expected"
    assert r.visit("v1").missing == ["Receipt or bill"] and r.visit("v1").status == "awaiting_documents"


# ---------- REC-01 identities 1 and 2, ALC-01 buckets ----------

def test_rec_01_1_and_alc_01_1_line_identity_and_buckets():
    """TC-REC-01-1 and TC-ALC-01-1: billed $250.00 = adjustment $125.00 + insurer $80.00 + member $45.00."""
    assert buckets(LINE_250) == {"plan_adjustment": 12500, "primary_paid": 8000, "deductible": 2000, "copay": 2500}
    ds = base(visits=[visit("v1", "2026-02-01")], documents=[claim("v1", "C1", [LINE_250])])
    v = run(ds).visit("v1")
    assert check(v, "C1").result == "pass" and "each of its 1 line" in check(v, "C1").detail
    assert sum(v.buckets.values()) == 25000 and v.line_buckets == [("99214", buckets(LINE_250))]


def test_rec_01_3_lines_pass_but_claim_totals_differ():
    """TC-REC-01-3: claim-level failure with the difference."""
    c = claim("v1", "C1", [LINE_250, {**LINE_250, "code": "85025"}])
    c["billed"] += 2000
    c["adjustment"] += 2000  # header identity still holds; the lines don't add up to it
    v = run(base(visits=[visit("v1", "2026-02-01")], documents=[c])).visit("v1")
    c1 = check(v, "C1")
    assert c1.result == "fail" and c1.amount == 2000 and "the lines' billed add up to $500.00" in c1.detail


def test_rec_01_4_cost_sharing_identity():
    """TC-REC-01-4: $45.00 = deductible $20.00 + copay $25.00; with copay $30.00 it fails by $5.00."""
    ok = run(base(visits=[visit("v1", "2026-02-01")], documents=[claim("v1", "C1", [LINE_250])])).visit("v1")
    assert check(ok, "C1").result == "pass"
    bad = claim("v1", "C1", [{**LINE_250, "copay": 3000}])
    c1 = check(run(base(visits=[visit("v1", "2026-02-01")], documents=[bad])).visit("v1"), "C1")
    assert c1.result == "fail" and c1.amount == 500 and "by -$5.00" in c1.detail


def test_rec_01_5_other_savings_and_secondary_payer():
    """TC-REC-01-5."""
    line = {"billed": 25000, "adjustment": 12500, "additional_savings": 1000, "insurer_paid": 6500,
            "secondary_paid": 1500, "patient_responsibility": 3500, "coinsurance": 3500}
    v = run(base(visits=[visit("v1", "2026-02-01")], documents=[claim("v1", "C1", [line])])).visit("v1")
    assert check(v, "C1").result == "pass"
    assert v.buckets["other_savings"] == 1000 and v.buckets["secondary_paid"] == 1500
    assert sum(v.buckets.values()) == 25000


def test_rec_01_6_self_pay_visit_adds_up_without_an_eob():
    """TC-REC-01-6: billed $250.00, self-pay discount $145.00, member $105.00; no EOB expected."""
    v = {**visit("v1", "2026-02-01"), "payment_path": "self_pay"}
    line = {"visit_id": "v1", "billed_charge": 25000, "self_pay_discount": 14500, "patient_amount": 10500,
            "balance": 10500}
    r = run(base(visits=[v], documents=[bill("s", "2026-02-01", [line]), pay("p", "2026-02-01", 10500)]))
    vr = r.visit("v1")
    assert check(vr, "self_pay").result == "pass" and "no EOB expected" in check(vr, "self_pay").detail
    assert vr.buckets == {"self_pay_discount": 14500, "member_responsibility": 10500}
    assert docs_state(vr)["eob"] == "not_applicable" and vr.status == "complete"
    bad = run(base(visits=[v], documents=[bill("s", "2026-02-01", [{**line, "self_pay_discount": 12500}])]))
    assert check(bad.visit("v1"), "self_pay").amount == 2000


def test_alc_01_2_fully_denied_line_is_all_not_covered():
    """TC-ALC-01-2."""
    line = {"billed": 40000, "allowed": 40000, "insurer_paid": 0, "patient_responsibility": 40000,
            "not_covered": 40000}
    assert buckets(line) == {"not_covered": 40000}


def test_alc_01_3_write_off_is_a_settlement_item_not_a_bucket():
    """TC-ALC-01-3: $45.00 owed, $30.00 paid, then a $5.00 prompt-pay write-off."""
    line = {"visit_id": "v1", "patient_amount": 4500, "write_off": 500, "balance": 1000}
    ds = base(visits=[visit("v1", "2026-02-01")],
              documents=[claim("v1", "C1", [LINE_250]), pay("p", "2026-02-25", 3000),
                         bill("s", "2026-03-01", [line])])
    v = run(ds).visit("v1")
    assert sum(v.buckets.values()) == 25000 and set(v.buckets) <= set(BUCKETS)
    s = v.settlement
    assert (s.paid, s.write_offs, s.still_owed, s.unexplained) == (3000, 500, 1000, 0) and s.balanced


def test_alc_01_4_every_cent_lands_in_exactly_one_bucket():
    """TC-ALC-01-4: 1,000 random valid EOB lines (and some that don't add up)."""
    rng = random.Random(14)
    settlement = {"paid", "refunds", "write_offs", "still_owed", "write_off"}
    for _ in range(1000):
        billed = rng.randint(0, 500000)
        adj = rng.randint(0, billed)
        rest = billed - adj
        paid = rng.randint(0, rest)
        resp = rest - paid
        shares = sorted(rng.randint(0, resp) for _ in range(3))
        line = {"billed": billed, "adjustment": adj, "insurer_paid": paid, "patient_responsibility": resp,
                "deductible": shares[0], "copay": shares[1] - shares[0], "coinsurance": shares[2] - shares[1],
                "not_covered": resp - shares[2]}
        if rng.random() < 0.1:
            line["insurer_paid"] += rng.randint(-500, 500)
        b = buckets(line)
        assert sum(b.values()) == billed and set(b) <= set(BUCKETS) and not set(b) & settlement


# ---------- REC-02 provider asks more than the EOB ----------

def bill_vs_eob(asks, adjustment=0, billed_charge=10000, owed=10000, eob_billed=18000):
    e = eob("v1", owed, billed=eob_billed)
    line = {"visit_id": "v1", "patient_amount": asks, "billed_charge": billed_charge, "adjustment": adjustment}
    return run(base(visits=[visit("v1", "2026-02-01")], documents=[e, bill("s", "2026-03-01", [line])])).visit("v1")


def test_rec_02_1_two_finding_types():
    """TC-REC-02-1: EOB says $100.00, the provider asks $180.00: $80.00, a missed adjustment or balance billing."""
    missed = check(bill_vs_eob(18000, adjustment=0, billed_charge=18000), "C2")
    assert (missed.result, missed.amount, missed.kind) == ("fail", 8000, "missed_adjustment")
    assert "statement of 2026-03-01 asks $180.00, EOB says you owe $100.00" in missed.detail
    assert "doesn't apply the plan's $80.00 discount" in missed.detail
    billing = check(bill_vs_eob(18000, adjustment=8000, billed_charge=18000), "C2")
    assert (billing.amount, billing.kind, billing.kind_label) == (8000, "balance_billing", "Balance billing")


def test_rec_02_2_and_4_asks_exactly_or_less():
    """TC-REC-02-2: no finding. TC-REC-02-4: asking less is a note, not an overcharge."""
    assert check(bill_vs_eob(10000, 8000, 18000), "C2").result == "pass"
    less = bill_vs_eob(9000, 8000, 18000)
    assert check(less, "C2").result == "info" and "$10.00 less than the EOB" in check(less, "C2").detail
    assert less.status == "balance_outstanding" and less.remaining == 9000  # owes what the provider asks
    assert check(less, "settlement").result == "pass"


def test_estimate_sent_before_the_eob_is_not_a_write_off():
    """A statement dated before the EOB that asks less (an estimate) leaves the EOB's amount owed."""
    line = {"visit_id": "v1", "patient_amount": 2500, "billed_charge": 18000}
    ds = base(visits=[visit("v1", "2026-02-01")],
              documents=[bill("s", "2026-02-01", [line]), eob("v1", 10000, billed=18000, d="2026-02-20")])
    v = run(ds).visit("v1")
    assert v.write_off == 0 and v.remaining == 10000 and v.status == "balance_outstanding"


def test_rec_02_3_bill_before_the_eob_waits():
    """TC-REC-02-3: no finding while the EOB is pending; the visit is Awaiting EOB, not Balance outstanding."""
    line = {"visit_id": "v1", "patient_amount": 18000, "billed_charge": 18000}
    v = run(base(visits=[visit("v1", "2026-09-25")], documents=[bill("s", "2026-10-01", [line])])).visit("v1")
    assert v.status == "awaiting_eob" and not v.findings
    assert check(v, "C2").result == "na" and check(v, "C6").result == "info"
    assert v.hsa_flags == ["Statement asks $180.00; wait for the EOB before paying from the HSA"]


def test_rec_02_5_statement_charges_differ_from_the_claim():
    """TC-REC-02-5: charges sent to the insurer not shown to the member."""
    c2 = check(bill_vs_eob(10000, 8000, billed_charge=15000), "C2")
    assert (c2.result, c2.amount, c2.kind) == ("fail", 3000, "billed_mismatch")
    assert "insurer was billed $180.00, statement shows $150.00 in charges" in c2.detail


# ---------- REC-03 overpayment ----------

def test_rec_03_1_paid_twice_by_two_methods():
    """TC-REC-03-1: $45.00 owed, paid $45.00 by HSA and $45.00 by card."""
    ds = base(visits=[visit("v1", "2026-02-01")],
              documents=[eob("v1", 4500), pay("p1", "2026-03-01", 4500), pay("p2", "2026-03-05", 4500, account="card")])
    r = run(ds)
    v = r.visit("v1")
    assert r.group("a").overpaid == 4500 and v.overpaid == 4500
    assert check(v, "C4").result == "fail" and check(v, "C4").amount == 4500 and v.status == "discrepancy"
    assert v.settlement.still_owed == -4500  # a credit due from the provider


def test_rec_03_3_three_methods_summing_exactly():
    """TC-REC-03-3."""
    ds = base(visits=[visit("v1", "2026-02-01")],
              documents=[eob("v1", 9000), pay("p1", "2026-03-01", 3000), pay("p2", "2026-03-02", 2500, account="card"),
                         pay("p3", "2026-03-03", 3500, account="card")])
    v = run(ds).visit("v1")
    assert check(v, "C4").result == "pass" and v.status == "complete" and not v.findings


def test_rec_03_4_and_rec_13_3_refund_resolves_the_overpayment():
    """TC-REC-03-4, TC-REC-13-3: $100.00 owed, $120.00 paid: a $20.00 credit; after a $20.00 refund, Resolved."""
    docs = [eob("v1", 10000), pay("p1", "2026-03-01", 12000)]
    before = run(base(visits=[visit("v1", "2026-02-01")], documents=docs)).visit("v1")
    assert before.overpaid == 2000 and before.settlement.still_owed == -2000 and before.status == "discrepancy"
    after = run(base(visits=[visit("v1", "2026-02-01")],
                     documents=docs + [pay("r1", "2026-04-01", 2000, kind="refund")])).visit("v1")
    assert after.overpaid == 0 and after.settlement.still_owed == 0 and after.settlement.balanced
    assert check(after, "C4").detail == "A refund of $20.00 cleared the overpayment" and after.status == "resolved"


def test_rec_03_5_small_overpayment_clears_within_tolerance():
    """TC-REC-03-5: $0.40 clears, is recorded, and counts toward the provider's $5.00 cap."""
    ds = base(visits=[visit("v1", "2026-02-01")], documents=[eob("v1", 4500), pay("p1", "2026-03-01", 4540)])
    r = run(ds)
    v = r.visit("v1")
    assert check(v, "C4").result == "cleared" and v.cleared == [check(v, "C4")] and v.status == "complete"
    assert r.group("a").cleared_total == 40 and "tolerance" not in r.group("a").flags


def test_tolerance_cap_flags_the_provider():
    """TC-REC-10-5 (the cap TC-REC-03-5 counts toward): six $0.90 differences in a year flag the provider."""
    visits = [visit(f"v{i}", f"2026-0{i + 1}-01") for i in range(6)]
    docs = [eob(f"v{i}", 1000) for i in range(6)] + [pay(f"p{i}", f"2026-0{i + 1}-02", 1090) for i in range(6)]
    g = run(base(visits=visits, documents=docs)).group("a")
    assert g.cleared_total == 540 and "tolerance" in g.flags


def test_alc_04_4_lump_sum_beyond_everything_owed_is_a_credit():
    """TC-ALC-04-4."""
    ds = base(visits=[visit("v1", "2026-01-05"), visit("v2", "2026-02-05")],
              documents=[eob("v1", 5000), eob("v2", 5000), pay("p", "2026-03-01", 15000)])
    r = run(ds)
    assert r.group("a").overpaid == 5000 and r.visit("v2").overpaid == 5000
    assert r.group("a").settlement.still_owed == -5000


# ---------- REC-04 duplicate charges ----------

ITEM = {"code": "99214", "service_date": "2026-02-01", "charge": 15000}


def dup_visit(items, statements=1):
    docs = [bill(f"s{n}", f"2026-0{n + 2}-01", [{"visit_id": "v1", "patient_amount": 15000, "items": items}])
            for n in range(statements)]
    return run(base(visits=[visit("v1", "2026-02-01")], documents=[eob("v1", 15000, billed=30000), *docs])).visit("v1")


def test_rec_04_1_same_code_date_and_provider_twice():
    """TC-REC-04-1: a duplicate-charge finding for the second line's amount."""
    v = dup_visit([ITEM, {**ITEM, "charge": 15500}])
    d = check(v, "duplicate")
    assert (d.result, d.amount, d.kind) == ("fail", 15500, "duplicate_charge") and v.status == "discrepancy"


def test_rec_04_2_same_charge_on_successive_statements_is_not_a_duplicate():
    """TC-REC-04-2."""
    assert check(dup_visit([ITEM], statements=2), "duplicate").result == "pass"


def test_same_code_on_two_visits_of_one_statement_is_not_a_duplicate():
    """Items without their own date take their visit's date, so two visits' 99214s aren't one charge twice."""
    item = {"code": "99214", "charge": 15000}
    s = bill("s", "2026-04-01", [{"visit_id": "v1", "patient_amount": 15000, "items": [item]},
                                 {"visit_id": "v2", "patient_amount": 15000, "items": [item]}])
    r = run(base(visits=[visit("v1", "2026-02-01"), visit("v2", "2026-03-01")], documents=[s]))
    assert check(r.visit("v2"), "duplicate").result == "pass"


@pytest.mark.parametrize("second", [{**ITEM, "code": "99214-76"}, {**ITEM, "code": "99214-77"}, {**ITEM, "units": 2}])
def test_rec_04_4_repeat_modifiers_and_units_are_not_duplicates(second):
    """TC-REC-04-4."""
    assert check(dup_visit([ITEM, second]), "duplicate").result == "pass"


# ---------- REC-05 bills without claims, claim-free visits ----------

def test_rec_05_1_bill_with_no_claim_past_the_threshold():
    """TC-REC-05-1: "provider may not have filed with insurance" (a missing-document finding)."""
    line = {"visit_id": "v1", "patient_amount": 18000, "billed_charge": 18000}
    v = run(base(visits=[visit("v1", "2026-07-01")], documents=[bill("s", "2026-07-20", [line])])).visit("v1")
    f = check(v, "claim_filed")
    assert f.result == "fail" and f.amount == 18000 and "may not have filed with your insurance" in f.detail
    assert v.status == "balance_outstanding"  # TC-REC-11-2: balance owed + missing EOB
    paid = run(base(visits=[visit("v1", "2026-07-01")],
                    documents=[bill("s", "2026-07-20", [line]), pay("p", "2026-07-25", 18000)])).visit("v1")
    assert paid.status == "missing_documents" and check(paid, "claim_filed").result == "fail"


def test_rec_05_2_eob_without_a_bill_is_not_an_error():
    """TC-REC-05-2: no finding; Complete when nothing is owed, Balance outstanding when it's unpaid."""
    nothing = run(base(visits=[visit("v1", "2026-02-01")], documents=[eob("v1", 0)])).visit("v1")
    assert nothing.status == "complete" and not nothing.findings and docs_state(nothing)["bill"] == "not_applicable"
    owed = run(base(visits=[visit("v1", "2026-02-01")], documents=[eob("v1", 4500)])).visit("v1")
    assert owed.status == "balance_outstanding" and [c.code for c in owed.findings] == ["C6"]


@pytest.mark.parametrize("category,path", [("provider_visit", "self_pay"), ("supplements", None), ("rx", None)])
def test_rec_05_3_claim_free_visits_are_complete_with_receipt_and_payment(category, path):
    """TC-REC-05-3: self-pay visits, supplements and cash-price prescriptions need no claim."""
    v = {**visit("v1", "2026-06-01", category=category), **({"payment_path": path} if path else {})}
    receipt = {"id": "r", "type": "receipt", "date": "2026-06-01", "provider_id": "a", "visit_id": "v1", "total": 2500}
    r = run(base(visits=[v], documents=[receipt, pay("p", "2026-06-01", 2500, account="card")])).visit("v1")
    assert r.status == "complete" and not r.findings and docs_state(r)["eob"] == "not_applicable"


# ---------- REC-11 the nine statuses ----------

def nine_statuses() -> Dataset:
    def v(vid, d="2026-02-01", **extra):
        return {**visit(vid, d), **extra}
    line = {"visit_id": "x", "patient_amount": 10000}
    proposed = {**eob("review", 4500), "match": {"status": "proposed", "score": 0.75, "reasons": ["same provider"]}}
    return base(
        visits=[v("dispute", dispute={"status": "open", "opened": "2026-09-01"}), v("discrepancy"), v("review"),
                v("balance"), v("eob-wait", "2026-10-01"),
                v("docs-wait", documents={"itemized_bill": {"state": "expected", "since": "2026-10-01"}}),
                v("missing", "2026-06-01"),
                v("resolved", closed_findings=[{"code": "C2", "amount": 8000, "closed": "2026-09-01"}]),
                v("complete")],
        documents=[eob("dispute", 10000), eob("discrepancy", 10000), proposed, eob("balance", 4500),
                   eob("docs-wait", 0), eob("resolved", 10000), eob("complete", 0),
                   bill("s1", "2026-03-01", [{**line, "visit_id": "discrepancy", "patient_amount": 18000},
                                             {**line, "visit_id": "dispute", "patient_amount": 18000},
                                             {**line, "visit_id": "resolved", "patient_amount": 18000}]),
                   edits.set_split(pay("p2", "2026-03-02", 10000), {"resolved": 10000})])


def test_rec_11_1_every_status_is_reachable():
    """TC-REC-11-1."""
    r = run(nine_statuses())
    got = {v.id: v.status for v in r.visits}
    assert got == {"dispute": "in_dispute", "discrepancy": "discrepancy", "review": "needs_review",
                   "balance": "balance_outstanding", "eob-wait": "awaiting_eob", "docs-wait": "awaiting_documents",
                   "missing": "missing_documents", "resolved": "resolved", "complete": "complete"}
    assert set(got.values()) == set(STATUS_ORDER)
    assert r.visit("resolved").checks[1].result == "closed"


def test_rec_11_2_first_status_in_the_order_wins():
    """TC-REC-11-2: open case + failed check; failed check + balance owed; balance owed + missing EOB."""
    r = run(nine_statuses())
    assert r.visit("dispute").findings and r.visit("dispute").status == "in_dispute"
    assert r.visit("discrepancy").remaining and r.visit("discrepancy").status == "discrepancy"
    line = {"visit_id": "v1", "patient_amount": 9000}
    v = run(base(visits=[visit("v1", "2026-05-01")], documents=[bill("s", "2026-05-20", [line])])).visit("v1")
    assert v.missing == ["EOB"] and v.status == "balance_outstanding"


def test_rec_11_3_lifecycle():
    """TC-REC-11-3: Awaiting EOB → Discrepancy found → In dispute → Resolved, each on its own event."""
    v = visit("v1", "2026-09-20")
    asks = bill("s1", "2026-09-25", [{"visit_id": "v1", "patient_amount": 18000, "billed_charge": 18000}])
    assert run(base(visits=[v], documents=[asks])).visit("v1").status == "awaiting_eob"
    docs = [asks, eob("v1", 10000, billed=18000, d="2026-10-01")]
    r = run(base(visits=[v], documents=docs))
    assert r.visit("v1").status == "discrepancy"
    v = edits.open_dispute(v, "2026-10-02", "Called billing")
    assert run(base(visits=[v], documents=docs)).visit("v1").status == "in_dispute"
    fixed = docs + [bill("s2", "2026-10-05", [{"visit_id": "v1", "patient_amount": 10000, "billed_charge": 18000,
                                               "adjustment": 8000}]), pay("p", "2026-10-06", 10000)]
    assert run(base(visits=[v], documents=fixed)).visit("v1").status == "in_dispute"  # until the member closes it
    closed = edits.close_dispute(v, "2026-10-07", [], "Corrected bill")
    assert run(base(visits=[closed], documents=fixed)).visit("v1").status == "resolved"
    # Accepting the difference instead closes the finding with the dispute.
    findings = [(c.code, c.amount) for c in r.visit("v1").findings]
    accepted = edits.close_dispute(v, "2026-10-07", findings, "Accepted")
    after = run(base(visits=[accepted], documents=docs + [pay("p", "2026-10-06", 18000)])).visit("v1")
    assert after.status == "discrepancy"  # paying the inflated bill is a new finding (an overpayment)
    assert [c.code for c in after.checks if c.result == "closed"] == ["C2"]


def test_rec_11_4_waiting_threshold_is_configurable():
    """TC-REC-11-4: an insured visit 40 days old with no EOB."""
    v = visit("v1", (TODAY - timedelta(days=40)).isoformat())
    assert run(base(visits=[v])).visit("v1").status == "missing_documents"
    assert run(base(visits=[v], waiting_days=45)).visit("v1").status == "awaiting_eob"


# ---------- REC-13 settlement ----------

def test_rec_13_1_still_owed_after_payment_and_write_off():
    """TC-REC-13-1: $100.00 owed, $60.00 paid, $10.00 written off: $30.00 still owed."""
    line = {"visit_id": "v1", "patient_amount": 10000, "write_off": 1000, "balance": 3000}
    ds = base(visits=[visit("v1", "2026-02-01")],
              documents=[eob("v1", 10000), pay("p", "2026-03-01", 6000), bill("s", "2026-03-05", [line])])
    v = run(ds).visit("v1")
    s = v.settlement
    assert (s.responsibility, s.paid, s.write_offs, s.still_owed, s.unexplained) == (10000, 6000, 1000, 3000, 0)
    assert s.balanced and v.remaining == 3000 and check(v, "settlement").result == "pass"


def test_rec_13_2_statement_balance_lower_than_explained():
    """TC-REC-13-2 (the second way): a statement shows less owed than payments and write-offs explain."""
    line = {"visit_id": "v1", "patient_amount": 10000, "balance": 2000}
    ds = base(visits=[visit("v1", "2026-02-01")],
              documents=[eob("v1", 10000), pay("p", "2026-03-01", 6000), bill("s", "2026-03-05", [line])])
    v = run(ds).visit("v1")
    f = check(v, "settlement")
    assert (f.result, f.amount, f.kind) == ("fail", 2000, "unexplained") and v.remaining == 2000
    assert "shows $20.00 still owed" in f.detail and v.status == "discrepancy"


def test_rec_13_4_provider_settlement_is_the_sum_of_its_visits():
    """TC-REC-13-4: a provider with four visits."""
    visits = [visit(f"v{i}", f"2026-0{i + 1}-05") for i in range(4)]
    docs = [eob(f"v{i}", 2500 * (i + 1)) for i in range(4)] + [pay("p1", "2026-03-01", 6000),
                                                               pay("p2", "2026-06-01", 10000)]
    g = run(base(visits=visits, documents=docs)).group("a")
    total = g.settlement
    assert total.responsibility == 25000 and total.paid == 16000 and total.still_owed == 9000
    for k in ("responsibility", "paid", "refunds", "write_offs", "still_owed", "unexplained"):
        assert getattr(total, k) == sum(getattr(v.settlement, k) for v in g.visits)
    assert total.balanced


# ---------- ALC-04 lump sums ----------

def test_alc_04_1_statement_split_wins_over_oldest_first():
    """TC-ALC-04-1: $300.00 lump sum; the statement credits $200.00 to visit A and $100.00 to B."""
    ds = base(visits=[visit("A", "2026-01-05"), visit("B", "2026-02-05")],
              documents=[eob("A", 25000), eob("B", 15000), pay("p", "2026-03-01", 30000),
                         bill("s", "2026-03-10", [{"visit_id": "A", "patient_amount": 25000, "patient_paid": 20000,
                                                   "balance": 5000},
                                                  {"visit_id": "B", "patient_amount": 15000, "patient_paid": 10000,
                                                   "balance": 5000}])])
    r = run(ds)
    assert (r.visit("A").paid, r.visit("B").paid) == (20000, 10000)
    assert {a.source for v in r.visits for a in v.allocations} == {"statement"}
    no_split = run(base(visits=ds.visits, documents=ds.documents[:3]))
    assert (no_split.visit("A").paid, no_split.visit("B").paid) == (25000, 5000)  # oldest first


def test_alc_04_2_members_split_is_used():
    """TC-ALC-04-2 (core): the member's split wins over the statement and oldest-first; it must add up."""
    p = pay("p", "2026-03-01", 30000)
    with pytest.raises(edits.EditError):
        edits.set_split(p, {"A": 10000, "B": 10000})
    split = edits.set_split(p, {"A": 5000, "B": 25000})
    ds = base(visits=[visit("A", "2026-01-05"), visit("B", "2026-02-05")],
              documents=[eob("A", 25000), eob("B", 15000), split])
    r = run(ds)
    assert (r.visit("A").paid, r.visit("B").paid, r.visit("B").overpaid) == (5000, 25000, 10000)
    assert r.visit("A").remaining == 20000 and r.group("a").overpaid == 0  # the provider is even; B holds a credit
    assert edits.clear_split(split) == p


def test_merge_and_split_keep_totals():
    """TC-MAT-07-3 (core): splitting a statement across two visits and merging two visits move lines and
    allocations without changing any total."""
    items = [{"code": "99214", "charge": 15000, "patient_amount": 6000, "balance": 6000},
             {"code": "73562", "charge": 9000, "patient_amount": 3000, "balance": 3000}]
    s = bill("s", "2026-02-20", [{"visit_id": "v1", "patient_amount": 9000, "balance": 9000, "billed_charge": 24000,
                                  "items": items}])
    v1, v2 = visit("v1", "2026-02-01"), visit("v2", "2026-02-03")
    split = edits.move_document(s, "v1", "v2", items=[1])
    assert [(l["visit_id"], l["patient_amount"], l["billed_charge"]) for l in split["lines"]] == [
        ("v1", 6000, 15000), ("v2", 3000, 9000)]
    before = run(base(visits=[v1, v2], documents=[s, pay("p", "2026-03-01", 9000)]))
    after = run(base(visits=[v1, v2], documents=[split, pay("p", "2026-03-01", 9000)]))
    assert (after.visit("v1").paid, after.visit("v2").paid) == (6000, 3000)
    assert before.totals == after.totals
    changed = edits.merge_visits("v1", "v2", [split, edits.set_split(pay("p", "2026-03-01", 9000),
                                                                     {"v1": 6000, "v2": 3000})])
    merged = {r["id"]: r for _, r in changed}
    [line] = merged["s"]["lines"]
    assert (line["visit_id"], line["patient_amount"], line["billed_charge"], len(line["items"])) == ("v1", 9000, 24000, 2)
    assert merged["p"]["allocations"] == [{"visit_id": "v1", "amount": 9000}]
    once = run(base(visits=[v1], documents=list(merged.values())))
    assert once.totals == before.totals and once.visit("v1").paid == 9000
    assert edits.references("v2", list(merged.values())) == []
