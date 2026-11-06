from datetime import date

from mhs.core.reconcile import Dataset, build_report
from mhs.data.repository import load_dataset

TODAY = date(2026, 10, 9)


def report(store, year=2026):
    return build_report(load_dataset(store), year, TODAY)


def test_sample_statuses_match_the_notes_in_the_sample_file(loaded_store):
    """The nine REC-11 statuses (ADR-009) replace Release 0's five: Matched is Complete, Waiting is Awaiting EOB."""
    r = report(loaded_store)
    status = {v.id: v.status for v in r.visits}
    assert status == {
        "v-2026-02-10-pcp": "complete",
        "v-2026-04-02-pcp": "discrepancy",
        "v-2026-04-02-lab": "complete",
        "v-2026-06-15-vitamins": "complete",
        "v-2026-07-20-imaging": "balance_outstanding",  # TC-REC-11-2: balance owed + missing EOB
        "v-2026-09-28-derm": "awaiting_eob",
    }


def test_bill_vs_eob_discrepancy_and_provider_overpayment(loaded_store):
    r = report(loaded_store)
    follow_up = r.visit("v-2026-04-02-pcp")
    c2 = next(c for c in follow_up.checks if c.code == "C2")
    assert c2.result == "fail" and c2.amount == 8000
    assert follow_up.at_stake == 8000
    pcp = r.group("prov-pcp")
    assert (pcp.should_owe, pcp.paid, pcp.overpaid) == (24000, 32000, 8000)


def test_hsa_flags(loaded_store):
    r = report(loaded_store)
    assert r.visit("v-2026-04-02-lab").hsa_flags == []  # card payment reimbursed from the HSA
    assert any("outside the HSA" in f for f in r.visit("v-2026-06-15-vitamins").hsa_flags)
    assert any("pay from HSA" in f for f in r.visit("v-2026-07-20-imaging").hsa_flags)
    assert r.totals["outside_hsa"] == 4250
    assert r.totals["unpaid"] == 90000


def test_limit_progress_uses_eob_deductible(loaded_store):
    r = report(loaded_store)
    deductibles = [l for l in r.limits if l.limit["type"] == "deductible"]
    assert {l.limit["level"] for l in deductibles} == {"individual", "family"}
    assert all(l.used == 14000 + 10000 + 9500 for l in deductibles)


# --- synthetic cases ---------------------------------------------------------------------------

def base(**extra) -> Dataset:
    ds = Dataset(
        plans=[{"id": "plan", "plan_year": 2026, "insurer": "X", "limits": []}],
        accounts=[{"id": "hsa", "name": "HSA", "type": "hsa"}, {"id": "card", "name": "Card", "type": "credit_card"}],
        members=[{"id": "me", "name": "Me"}],
        providers=[{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
    )
    for k, v in extra.items():
        setattr(ds, k, v)
    return ds


def visit(vid, d, provider="a", category="provider_visit"):
    return {"id": vid, "date": d, "provider_id": provider, "member_id": "me", "plan_id": "plan", "category": category}


def eob(vid, owed, billed=10000, provider="a", d="2026-02-01", status="processed"):
    return {"id": f"eob-{vid}", "type": "eob", "date": d, "plan_id": "plan", "provider_id": provider, "visit_id": vid,
            "claim_status": status, "billed": billed, "allowed": owed, "adjustment": billed - owed, "insurer_paid": 0,
            "deductible": owed, "patient_responsibility": owed}


def pay(pid, d, amount, provider="a", account="hsa", kind="payment"):
    return {"id": pid, "type": "payment", "date": d, "provider_id": provider, "account_id": account, "amount": amount, "kind": kind}


def test_payment_with_no_claim_is_flagged():
    ds = base(documents=[pay("p1", "2026-03-01", 5000, provider="b")])
    r = build_report(ds, 2026, TODAY)
    assert r.group("b").no_claim_payments == 5000
    assert "no_claim" in r.group("b").flags


def test_suspected_relationship_joins_ledgers_and_flags_until_confirmed():
    rel = {"id": "r", "provider_id": "a", "related_provider_id": "b", "relationship": "same_organization", "status": "suspected"}
    ds = base(relationships=[rel], visits=[visit("v1", "2026-02-01")],
              documents=[eob("v1", 2000), pay("p1", "2026-02-02", 2000, provider="b")])
    r = build_report(ds, 2026, TODAY)
    g = r.group("a")
    assert [p["id"] for p in g.providers] == ["a", "b"]
    assert g.unconfirmed == [rel] and "unconfirmed" in g.flags
    assert r.visit("v1").status == "complete"

    rel_rejected = {**rel, "status": "rejected"}
    r2 = build_report(base(relationships=[rel_rejected], visits=ds.visits, documents=ds.documents), 2026, TODAY)
    assert r2.visit("v1").status == "balance_outstanding"
    assert r2.group("b").no_claim_payments == 2000


def test_visit_that_drops_off_a_later_statement_is_settled():
    def bill(bid, d, lines):
        return {"id": bid, "type": "provider_bill", "date": d, "provider_id": "a", "balance_due": sum(l["balance"] for l in lines),
                "lines": lines}
    line = {"visit_id": "v1", "patient_amount": 3000, "balance": 3000, "billed_charge": 10000}
    ds = base(visits=[visit("v1", "2026-01-10"), visit("v2", "2026-03-01")],
              documents=[eob("v1", 3000), eob("v2", 1000),
                         bill("s1", "2026-02-01", [line]),
                         bill("s2", "2026-04-01", [{"visit_id": "v2", "patient_amount": 1000, "balance": 1000, "billed_charge": 10000}])])
    r = build_report(ds, 2026, TODAY)
    v1 = r.visit("v1")
    assert v1.settled and v1.remaining == 0 and v1.unexplained == 3000
    assert any("no matching payment" in f for f in v1.hsa_flags)
    assert r.visit("v2").status == "balance_outstanding"
    assert r.group("a").provider_says_owed == 1000


def test_prior_year_visit_on_a_current_statement_is_carried_in():
    line = {"visit_id": "v0", "patient_amount": 4000, "balance": 4000}
    ds = base(visits=[visit("v0", "2025-12-15")],
              documents=[{"id": "s1", "type": "provider_bill", "date": "2026-01-20", "provider_id": "a",
                          "balance_due": 4000, "lines": [line]},
                         pay("p1", "2026-02-01", 4000)])
    r = build_report(ds, 2026, TODAY)
    assert r.visits == []  # carry-ins are not counted as this year's visits
    g = r.group("a")
    assert g.visits[0].carry_in and g.visits[0].paid == 4000 and g.overpaid == 0


def test_hsa_counts_include_carry_in_visits_like_the_totals():
    line = {"visit_id": "v0", "patient_amount": 4000, "balance": 4000}
    ds = base(visits=[visit("v0", "2025-12-15")],
              documents=[{"id": "s1", "type": "provider_bill", "date": "2026-01-20", "provider_id": "a",
                          "balance_due": 4000, "lines": [line]}])
    r = build_report(ds, 2026, TODAY)
    assert r.totals["unpaid"] == 4000 and r.hsa_counts["unpaid"] == 1
    assert [v.id for v in r.ledger_visits] == ["v0"]


def test_possible_duplicate_payments():
    ds = base(visits=[visit("v1", "2026-01-01")],
              documents=[eob("v1", 1853), pay("p1", "2026-01-15", 1853), pay("p2", "2026-01-18", 1853)])
    g = build_report(ds, 2026, TODAY).group("a")
    assert len(g.duplicates) == 1 and g.overpaid == 1853


def test_eob_that_does_not_add_up_fails_c1():
    e = eob("v1", 4521, billed=133200)
    e["adjustment"] = 0
    e["not_covered"] = 123000
    e["patient_responsibility"] = 127521
    ds = base(visits=[visit("v1", "2026-01-21")], documents=[e])
    c1 = next(c for c in build_report(ds, 2026, TODAY).visit("v1").checks if c.code == "C1")
    assert c1.result == "fail" and c1.amount == 5679


def test_missing_eob_waits_then_becomes_missing():
    ds = base(visits=[visit("new", "2026-10-01"), visit("old", "2026-06-01")])
    r = build_report(ds, 2026, TODAY)
    assert r.visit("new").status == "awaiting_eob"
    assert r.visit("old").status == "missing_documents"


def test_individual_and_family_limits():
    plan = {"id": "plan", "plan_year": 2026, "insurer": "X", "member_ids": ["me"], "limits": [
        {"type": "out_of_pocket_max", "network": "in_network", "level": "individual", "member_id": "me", "amount": 450000},
        {"type": "deductible", "network": "in_network", "level": "family", "amount": 600000}]}
    denied = eob("v3", 0, status="denied")
    ds = base(plans=[plan], visits=[visit("v1", "2026-01-01"), visit("v2", "2026-02-01"), visit("v3", "2026-03-01")],
              documents=[eob("v1", 10000), eob("v2", 5000), denied])
    limits = build_report(ds, 2026, TODAY).limits
    assert [(l.label, l.used) for l in limits] == [
        ("Me in-network out-of-pocket max", 15000), ("Family in-network deductible", 15000)]


def test_open_balance_is_aged_and_repeat_notices_counted():
    def bill(bid, d, notice=None):
        b = {"id": bid, "type": "provider_bill", "date": d, "provider_id": "a", "balance_due": 3000,
             "lines": [{"visit_id": "v1", "patient_amount": 3000, "balance": 3000}]}
        return {**b, "notice": notice} if notice else b
    ds = base(visits=[visit("v1", "2026-06-01")],
              documents=[eob("v1", 3000, d="2026-06-20"), bill("s1", "2026-07-01"), bill("s2", "2026-08-01", "Past due")])
    v = build_report(ds, 2026, TODAY).visit("v1")
    assert v.status == "balance_outstanding"
    assert (v.balance_age, v.notices, v.notice_label) == (100, 2, "Past due")
    c6 = next(c for c in v.checks if c.code == "C6")
    assert "first billed 100 days ago" in c6.detail and "on 2 statements" in c6.detail and '"Past due"' in c6.detail

    eob_only = build_report(base(visits=[visit("v1", "2026-06-01")], documents=[eob("v1", 3000, d="2026-06-20")]),
                            2026, TODAY).visit("v1")
    assert (eob_only.balance_age, eob_only.notices) == (111, 0)
    assert "second notice" not in next(c for c in eob_only.checks if c.code == "C6").detail


def test_hsa_counts_sit_behind_the_hsa_totals(loaded_store):
    r = report(loaded_store)
    assert r.hsa_counts == {"unpaid": 1, "gap": 0, "outside_hsa": 1, "unexplained": 0, "no_claim": 0}
    assert r.visit("v-2026-07-20-imaging").balance_age == 55
