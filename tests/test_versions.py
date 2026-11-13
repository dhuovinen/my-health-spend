"""MAT-08 claim versions, ALC-05 secondary insurance and ALC-08 refunds (ADR-052)."""

from datetime import date

from mhs.core import edits
from mhs.core.reconcile import build_report
from tests.test_reconcile import base, eob, pay, visit

TODAY = date(2026, 10, 9)


def run(**ds):
    return build_report(base(**ds), 2026, TODAY)


def version(original, doc_id, d, owed, **extra):
    out = {**original, "id": doc_id, "date": d, "allowed": owed, "adjustment": original["billed"] - owed,
           "deductible": owed, "patient_responsibility": owed, "version_of": original["id"]}
    out.update(extra)
    return out


# ---- MAT-08 ----

def test_tc_mat_08_1_latest_is_current_and_original_in_history():
    first = {**eob("v1", 20000), "claim_number": "C1"}
    newer = version(first, "eob-v1-v2", "2026-03-01", 15000, version_reason="reprocessed")
    r = run(visits=[visit("v1", "2026-01-15")], documents=[first, newer])
    v = r.visit("v1")
    assert [c["id"] for c in v.claims] == ["eob-v1-v2"] and [e["id"] for e in v.versions] == ["eob-v1"]
    assert v.insurer_owed == 15000


def test_tc_mat_08_2_lower_responsibility_after_payment_is_an_overpayment():
    first = {**eob("v1", 20000), "claim_number": "C1"}
    newer = version(first, "eob-v1-v2", "2026-04-01", 5000)
    r = run(visits=[visit("v1", "2026-01-15")], documents=[first, newer, pay("p1", "2026-02-15", 20000)])
    c4 = next(c for c in r.visit("v1").checks if c.code == "C4")
    assert (c4.result, c4.amount, c4.kind) == ("fail", 15000, "overpayment")


def test_tc_mat_08_3_order_by_processed_date_not_arrival():
    first = {**eob("v1", 20000, d="2026-02-01"), "claim_number": "C1"}
    corrected = {**first, "id": "eob-arrived-first", "date": "2026-03-01", "patient_responsibility": 9000,
                 "deductible": 9000, "allowed": 9000, "adjustment": 1000}
    r = run(visits=[visit("v1", "2026-01-15")], documents=[corrected, first])
    assert r.visit("v1").claims[0]["id"] == "eob-arrived-first"


def test_tc_mat_08_5_member_edit_waits_for_the_member():
    first = {**eob("v1", 20000), "claim_number": "C1", "member_edited": True}
    newer = version(first, "eob-v1-v2", "2026-03-01", 5000, version_reason="corrected")
    newer.pop("member_edited")
    r = run(visits=[visit("v1", "2026-01-15")], documents=[first, newer])
    v = r.visit("v1")
    assert v.claims[0]["id"] == "eob-v1" and v.status == "needs_review"
    assert v.version_conflicts == [(first, newer)]
    accepted = edits.choose_version(newer, "use_newer")
    r = run(visits=[visit("v1", "2026-01-15")], documents=[first, accepted])
    assert r.visit("v1").claims[0]["id"] == "eob-v1-v2" and not r.visit("v1").version_conflicts
    kept = edits.choose_version(newer, "keep_mine")
    r = run(visits=[visit("v1", "2026-01-15")], documents=[first, kept])
    assert r.visit("v1").claims[0]["id"] == "eob-v1" and r.visit("v1").status != "needs_review"


# ---- ALC-05 ----

PLANS = [{"id": "plan", "plan_year": 2026, "insurer": "X", "coverage_order": "primary", "limits": [],
          "member_ids": ["me"]},
         {"id": "plan2", "plan_year": 2026, "insurer": "Y", "coverage_order": "secondary", "limits": [],
          "member_ids": ["me"]}]


def primary():
    return {"id": "eob-p", "type": "eob", "date": "2026-02-01", "plan_id": "plan", "provider_id": "a",
            "visit_id": "v1", "claim_number": "P1", "billed": 20000, "allowed": 10000, "adjustment": 10000,
            "insurer_paid": 8000, "deductible": 0, "coinsurance": 2000, "patient_responsibility": 2000}


def secondary():
    return {"id": "eob-s", "type": "eob", "date": "2026-02-20", "plan_id": "plan2", "provider_id": "a",
            "visit_id": "v1", "claim_number": "S1", "billed": 20000, "allowed": 2000, "insurer_paid": 1500,
            "patient_responsibility": 500}


def test_tc_alc_05_1_all_parts_shown_and_identity_holds():
    v = run(visits=[visit("v1", "2026-01-15")], documents=[primary(), secondary()], plans=PLANS).visit("v1")
    assert v.insurer_owed == 500 and v.insurer_paid == 9500 and v.total_billed == 20000
    assert v.buckets["secondary_paid"] == 1500 and v.buckets["member_unspecified"] == 500
    assert sum(v.buckets.values()) == 20000
    cob = next(c for c in v.checks if c.code == "cob")
    assert cob.result == "pass"


def test_tc_alc_05_2_waiting_for_the_second_insurer():
    v = build_report(base(visits=[visit("v1", "2026-09-20")], documents=[{**primary(), "date": "2026-09-30"}],
                          plans=PLANS), 2026, TODAY).visit("v1")
    assert v.secondary_expected and v.status == "awaiting_eob"
    assert any(d.kind == "secondary_eob" and d.state == "expected" for d in v.documents)


def test_tc_alc_05_3_coverage_order_decides():
    plans = [{**PLANS[0], "coverage_order": "secondary"}, {**PLANS[1], "coverage_order": "primary"}]
    v = run(visits=[visit("v1", "2026-01-15")], documents=[primary(), secondary()], plans=plans).visit("v1")
    assert v.insurer_owed == 2000  # plan2's EOB is now the primary, plan's the secondary


def test_second_insurer_charging_more_than_was_left():
    s = {**secondary(), "patient_responsibility": 1500, "insurer_paid": 1500}
    v = run(visits=[visit("v1", "2026-01-15")], documents=[primary(), s], plans=PLANS).visit("v1")
    cob = next(c for c in v.checks if c.code == "cob")
    assert (cob.result, cob.amount, cob.kind) == ("fail", 1000, "cob_excess")


# ---- ALC-08 ----

def overpaid(refund_account, amount=4500, refund_of=None):
    refund = pay("r1", "2026-03-01", amount, account=refund_account, kind="refund")
    if refund_of:
        refund["refund_of"] = refund_of
    return run(visits=[visit("v1", "2026-01-15")],
               documents=[eob("v1", 10000), pay("p1", "2026-02-10", 14500), refund]).visit("v1")


def test_tc_alc_08_1_refund_to_the_hsa_card():
    v = overpaid("hsa", refund_of=["p1"])
    assert v.overpaid == 0 and next(c for c in v.checks if c.code == "refund").result == "pass"
    assert v.status == "resolved"


def test_tc_alc_08_2_refund_by_check_for_an_hsa_charge():
    v = overpaid("card")
    refund = next(c for c in v.checks if c.code == "refund")
    assert (refund.result, refund.amount, refund.kind) == ("fail", 4500, "refund_to_hsa")


def test_tc_alc_08_3_partial_refund_leaves_the_rest_owed():
    v = overpaid("hsa", amount=2000)
    c4 = next(c for c in v.checks if c.code == "C4")
    assert v.overpaid == 2500 and "$25.00 is still owed to you" in c4.detail
