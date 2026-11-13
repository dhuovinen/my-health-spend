"""PRE-01, PRE-02, PRE-04, PRE-05, PRE-07: planned visits and the pre-visit estimate (ADR-053)."""

from datetime import date

from mhs.core import estimate, tax
from mhs.core.reconcile import build_report
from mhs.data.reference import load_tables
from tests.test_reconcile import base, eob

TODAY = date(2026, 10, 9)
TABLES = load_tables()


def plan(**extra):
    p = {"id": "plan", "plan_year": 2026, "insurer": "Example Health", "coinsurance_rate": 0.2,
         "hsa_eligible_plan": True, "limits": [
             {"type": "deductible", "network": "in_network", "level": "individual", "amount": 150000},
             {"type": "out_of_pocket_max", "network": "in_network", "level": "individual", "amount": 300000}]}
    p.update(extra)
    return p


def planned(**extra):
    v = {"id": "plan-1", "date": "2026-11-20", "provider_id": "a", "member_id": "me", "plan_id": "plan",
         "category": "provider_visit", "planned": True, "expected_allowed": 80000}
    v.update(extra)
    return v


def used(deductible, oop=None):
    """An earlier claim that used part of the deductible."""
    e = {**eob("v0", deductible, d="2026-02-01"), "network_status": "in_network"}
    if oop is not None:
        e.update(coinsurance=oop - deductible, patient_responsibility=oop)
    return e


def ds_with(visit, docs=(), **plan_extra):
    return base(plans=[plan(**plan_extra)], visits=[{"id": "v0", "date": "2026-01-20", "provider_id": "a",
                                                      "member_id": "me", "plan_id": "plan",
                                                      "category": "provider_visit"}, visit],
                documents=list(docs))


def est(visit, docs=(), **plan_extra):
    return estimate.estimate(visit, ds_with(visit, docs, **plan_extra), TODAY, TABLES)


def test_tc_pre_02_1_deductible_then_coinsurance_with_the_math():
    e = est(planned(), [used(100000)])
    assert e.total == 56000
    assert e.expected.steps == ["Deductible: $500.00 of the $500.00 left",
                                "Coinsurance: 20% of the $300.00 left after the deductible = $60.00"]


def test_tc_pre_02_2_capped_at_the_out_of_pocket_maximum():
    e = est(planned(expected_allowed=200000), [used(150000, oop=280000)])
    assert e.total == 20000 and "Capped" in e.expected.steps[-1]


def test_tc_pre_02_3_copay_only_service():
    e = est(planned(service_type="specialist"), [], hsa_eligible_plan=False, copays={"specialist": 6000})
    assert e.total == 6000


def test_preventive_is_free():
    assert est(planned(service_type="preventive")).total == 0


def test_tc_pre_01_1_planned_visit_is_not_reconciled():
    ds = ds_with(planned())
    assert [v["id"] for v in estimate.planned_visits(ds)] == ["plan-1"]
    assert build_report(ds, 2026, TODAY).visit("plan-1") is None


def test_tc_pre_01_2_documents_turn_it_into_a_visit():
    doc = {**eob("plan-1", 50000, d="2026-11-30")}
    ds = ds_with(planned(), [doc])
    assert estimate.planned_visits(ds) == []
    assert build_report(ds, 2026, date(2026, 12, 5)).visit("plan-1") is not None


def test_tc_pre_01_3_past_date_asks_if_it_happened():
    assert est(planned(date="2026-10-01")).past_due
    assert not est(planned()).past_due


def test_tc_pre_04_cash_or_insurance_and_the_deductible():
    yes = est(planned(cash_price=40000), cash_counts_toward_deductible="yes")
    assert yes.cash.cheaper == "cash" and "counts a cash payment toward the deductible" in yes.cash.text
    no = est(planned(cash_price=40000), cash_counts_toward_deductible="no")
    assert "doesn't count a cash payment" in no.cash.text
    unknown = est(planned(cash_price=40000))
    assert "Ask the plan whether" in unknown.cash.text


def test_tc_pre_05_questions_by_network():
    in_net = estimate.questions({"network_status": "in_network"}, plan(), True, False)
    assert any("in network" in q for q in in_net) and any("itemized bill" in q for q in in_net)
    assert not any("balance billing" in q for q in in_net)
    out = estimate.questions({"network_status": "out_of_network"}, plan(), True, False)
    assert any("balance billing" in q for q in out) and any("good-faith estimate" in q for q in out)


def test_tc_pre_07_account_matches_tax_03():
    v = planned()
    ds = ds_with(v)
    e = estimate.estimate(v, ds, TODAY, TABLES)
    expected = tax.recommend(tax.tag_visit(v, ds.providers[0], [], TABLES), ds.members[0], v["date"], ds.accounts,
                             ds.documents, "pay_now", TODAY, TABLES)
    assert e.recommendation == expected and e.disclaimer == tax.DISCLAIMER


def test_missing_allowed_amount_says_what_to_enter():
    e = est(planned(expected_allowed=None))
    assert e.total is None and "allow" in e.missing
