"""REC-06 (plan cost sharing) and REC-09 (claim codes), ADR-050."""

from datetime import date

from mhs.core import costshare
from mhs.core.reconcile import build_report
from mhs.data.reference import load_claim_codes
from tests.test_reconcile import base, visit

TODAY = date(2026, 10, 9)
CODES = load_claim_codes()


def plan(**extra):
    p = {"id": "plan", "plan_year": 2026, "insurer": "X", "coinsurance_rate": 0.2, "terms_confirmed": True,
         "copays": {"specialist": 6000}, "limits": [
             {"type": "deductible", "network": "in_network", "level": "individual", "amount": 600000},
             {"type": "deductible", "network": "in_network", "level": "family", "amount": 1200000},
             {"type": "out_of_pocket_max", "network": "in_network", "level": "individual", "amount": 800000}]}
    p.update(extra)
    return p


def claim(vid, allowed, d="2026-03-01", number="", **share):
    out = {"id": f"eob-{vid}", "type": "eob", "date": d, "plan_id": "plan", "provider_id": "a", "visit_id": vid,
           "claim_status": "processed", "network_status": "in_network", "billed": allowed + 10000,
           "allowed": allowed, "adjustment": 10000, "deductible": 0, "copay": 0, "coinsurance": 0}
    out.update(share)
    out["patient_responsibility"] = out["deductible"] + out["copay"] + out["coinsurance"] + out.get("not_covered", 0)
    out["insurer_paid"] = allowed - out["patient_responsibility"] + out.get("not_covered", 0)
    if number:
        out["claim_number"] = number
    return out


def run(visits, docs, **plan_extra):
    ds = base(visits=visits, documents=docs, plans=[plan(**plan_extra)], claim_codes=CODES)
    return build_report(ds, 2026, TODAY)


def check(r, vid, code="plan"):
    return [c for c in r.visit(vid).checks if c.code == code]


def test_tc_rec_06_1_specialist_copay_too_high():
    v = {**visit("v1", "2026-03-01"), "service_type": "specialist"}
    r = run([v], [claim("v1", 20000, copay=7500)], hsa_eligible_plan=False)
    [c] = check(r, "v1")
    assert (c.result, c.amount, c.kind) == ("fail", 1500, "cost_share")
    assert "copay $75.00 (plan says $60.00)" in c.detail
    assert r.visit("v1").status == "discrepancy"


def test_tc_rec_06_2_coinsurance_after_deductible_met():
    early = claim("v0", 600000, d="2026-01-10", deductible=600000)
    later = claim("v1", 50000, d="2026-03-01", coinsurance=15000)
    r = run([visit("v0", "2026-01-05"), visit("v1", "2026-03-01")], [early, later])
    [c] = check(r, "v1")
    assert (c.result, c.amount) == ("fail", 5000)
    assert "Deductible already met" in c.detail and "20% of the $500.00" in c.detail


def test_tc_rec_06_3_deductible_nearly_met():
    early = claim("v0", 580000, d="2026-01-10", deductible=580000)
    right = claim("v1", 50000, d="2026-03-01", deductible=20000, coinsurance=6000)
    r = run([visit("v0", "2026-01-05"), visit("v1", "2026-03-01")], [early, right])
    [c] = check(r, "v1")
    assert c.result == "pass" and "$260.00" in c.detail


def test_tc_rec_06_4_processing_order_not_service_order():
    """The later service was processed first, so it took the deductible; the earlier service is coinsurance only."""
    later_service = claim("v2", 600000, d="2026-02-01", deductible=600000)
    earlier_service = claim("v1", 50000, d="2026-03-15", coinsurance=10000)
    r = run([visit("v1", "2026-01-20"), visit("v2", "2026-01-25")], [later_service, earlier_service])
    assert check(r, "v1")[0].result == "pass"
    assert check(r, "v2")[0].result == "pass"


def test_tc_rec_06_5_preventive_visit_charged():
    v = {**visit("v1", "2026-03-01"), "service_type": "preventive"}
    r = run([v], [claim("v1", 20000, copay=3000)])
    [c] = check(r, "v1")
    assert c.result == "fail" and c.amount == 3000 and "preventive care should cost you $0.00" in c.detail


def test_unconfirmed_terms_are_a_flag_not_a_finding():
    v = {**visit("v1", "2026-03-01"), "service_type": "preventive"}
    r = run([v], [claim("v1", 20000, copay=3000)], terms_confirmed=False)
    [c] = check(r, "v1")
    assert c.result == "flag" and r.visit("v1").status != "discrepancy" and r.visit("v1").at_stake == 0


def test_missing_terms_say_what_to_add():
    early = claim("v0", 600000, d="2026-01-10", deductible=600000)
    r = run([visit("v0", "2026-01-05"), visit("v1", "2026-03-01")], [early, claim("v1", 20000, coinsurance=3000)],
            coinsurance_rate=None)
    [c] = check(r, "v1")
    assert c.result == "na" and "coinsurance rate" in c.detail


def test_charged_less_than_terms_is_not_a_finding():
    r = run([visit("v1", "2026-03-01")], [claim("v1", 20000, deductible=10000)])
    [c] = check(r, "v1")
    assert c.result == "info" and "less" in c.detail


def test_out_of_pocket_cap():
    t = costshare.terms_of(plan())
    acc = costshare.Accumulators()
    acc.add("me", 600000, 790000)
    e = costshare.expected_share(t, 100000, None, acc, "me")
    assert e.total == 10000 and "Capped" in e.steps[-1]


def test_tc_rec_09_1_codes_in_plain_language():
    for code in ("CO-45", "PR-1", "PR-2", "PR-3", "CO-97", "CO-16", "CO-50"):
        note = costshare.explain(code, CODES)
        assert note.known and note.text, code
    assert "deductible" in costshare.explain("PR-1", CODES).text
    assert "don't owe" in costshare.explain("CO-45", CODES).text


def test_tc_rec_09_2_appealable_codes():
    assert costshare.explain("CO-16", CODES).appealable
    assert not costshare.explain("CO-45", CODES).appealable
    c = claim("v1", 20000, not_covered=20000, number="EX1")
    c["lines"] = [{"code": "99213", "billed": 30000, "allowed": 20000, "not_covered": 20000,
                   "patient_responsibility": 20000, "insurer_paid": 0, "remark_codes": ["PR-50"]}]
    r = run([visit("v1", "2026-03-01")], [c])
    [d] = check(r, "v1", "denial")
    assert (d.result, d.kind, d.amount) == ("fail", "appealable_denial", 20000)
    assert any(n.code == "PR-50" and n.appealable for n in r.visit("v1").code_notes)


def test_contractual_denial_is_explained_not_flagged():
    c = claim("v1", 20000, number="EX1")
    c["remark_codes"] = ["CO-16"]
    c["claim_status"] = "denied"
    r = run([visit("v1", "2026-03-01")], [c])
    assert check(r, "v1", "denial") == []
    assert [n.code for n in r.visit("v1").code_notes] == ["CO-16"]


def test_tc_rec_09_3_unknown_code():
    note = costshare.explain("ZZ-999", CODES)
    assert not note.known and "Unknown code" in note.text
    assert not costshare.explain("garbage!", CODES).known
