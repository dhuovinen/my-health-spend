"""REC-15: the plan's terms from the household's own EOBs (ADR-056), TC-REC-15-1 to 5 at the core level."""

from mhs.core import costshare, plan_inference as pi
from mhs.core.costshare import Accumulators, Terms, expected_share


def generate(terms: Terms, visits: list[tuple[str, str, int]], start: int = 1):
    """A plan year of EOBs produced by the given terms: (member, service type, allowed in cents) in processing order."""
    acc, claims, visit_map = Accumulators(), [], {}
    for i, (member, kind, allowed) in enumerate(visits, start):
        e = expected_share(terms, allowed, kind, acc, member)
        assert not e.missing
        vid = f"v{i}"
        visit_map[vid] = {"id": vid, "member_id": member, "service_type": kind}
        claims.append(claim(i, allowed, e.deductible, e.copay, e.coinsurance))
        acc.add(member, e.deductible, e.total)
    return claims, visit_map


def claim(i, allowed, deductible=0, copay=0, coinsurance=0, **extra):
    c = {"id": f"eob-{i}", "visit_id": f"v{i}", "plan_id": "plan", "date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
         "claim_number": f"C{i:03d}", "claim_status": "processed", "network_status": "in_network", "allowed": allowed,
         "deductible": deductible, "copay": copay, "coinsurance": coinsurance}
    c.update(extra)
    return c


def infer(claims, visits):
    return pi.infer(claims, visits, "plan")


def state(t, key):
    f = t.get(key)
    return f.state, f.value


# TC-REC-15-1: plan years generated from known terms come back as known.

def test_tc_rec_15_1_embedded_deductible_and_coinsurance():
    terms = Terms(deductible=150000, family_deductible=300000, oop=400000, family_oop=800000, rate=0.2)
    claims, visits = generate(terms, [("a", "other", 60000), ("b", "other", 40000), ("a", "other", 70000),
                                      ("a", "other", 80000), ("a", "other", 50000), ("a", "other", 50000),
                                      ("b", "other", 30000), ("a", "other", 50000)])
    t = infer(claims, visits)
    assert state(t, "coinsurance") == ("known", 0.2)
    assert state(t, "deductible") == ("known", 150000)
    assert state(t, "family_deductible") == ("at_least", 220000)  # a's 1,500 and b's 700: not reached
    assert t.get("deductible").anchor == "eob-4"  # where a's deductible ran out
    assert set(t.get("coinsurance").claims) == {"eob-4", "eob-5", "eob-6", "eob-8"}


def test_tc_rec_15_1_copay_plan():
    terms = Terms(deductible=150000, rate=0.2, copays={"specialist": 6000, "primary_care": 3000})
    claims, visits = generate(terms, [("a", "specialist", 25000), ("a", "primary_care", 15000),
                                      ("a", "specialist", 25000), ("a", "primary_care", 15000),
                                      ("a", "specialist", 25000), ("a", "primary_care", 15000),
                                      ("a", "other", 50000)])
    t = infer(claims, visits)
    assert state(t, "copay:specialist") == ("known", 6000)
    assert state(t, "copay:primary_care") == ("known", 3000)
    assert state(t, "copays_after_deductible") == ("known", False)
    assert state(t, "deductible") == ("at_least", 50000)


def test_tc_rec_15_1_hsa_plan_copays_after_deductible():
    terms = Terms(deductible=100000, oop=500000, rate=0.2, copays={"specialist": 5000}, hdhp=True)
    claims, visits = generate(terms, [("a", "specialist", 25000)] * 4 + [("a", "specialist", 25000)] * 3
                              + [("a", "other", 10000)] * 2)
    t = infer(claims, visits)
    assert state(t, "copays_after_deductible") == ("known", True)
    assert state(t, "copay:specialist") == ("known", 5000)
    assert state(t, "deductible") == ("known", 100000)


def test_tc_rec_15_1_out_of_pocket_maximum_reached():
    terms = Terms(deductible=100000, oop=200000, rate=0.2)
    claims, visits = generate(terms, [("a", "other", 100000)] + [("a", "other", 90000)] * 6
                              + [("a", "other", 100000)] * 2)
    assert claims[6]["coinsurance"] == 10000  # $180.00 cut to the $100.00 left
    t = infer(claims, visits)
    assert state(t, "oop") == ("known", 200000)
    assert t.get("oop").anchor == "eob-7"  # the claim the cap cut short isn't a coinsurance outlier
    assert state(t, "coinsurance") == ("known", 0.2) and not t.get("coinsurance").outliers
    assert state(t, "deductible") == ("known", 100000)


# TC-REC-15-2: one insurer mistake is an outlier and doesn't move the term.

def test_tc_rec_15_2_one_mistake_is_an_outlier():
    claims = [claim(i, 50000, coinsurance=10000) for i in range(1, 13)] + [claim(13, 50000, coinsurance=15000)]
    visits = {c["visit_id"]: {"member_id": "a", "service_type": "other"} for c in claims}
    f = infer(claims, visits).get("coinsurance")
    assert (f.state, f.value, len(f.claims)) == ("known", 0.2, 12)
    assert [cid for cid, _ in f.outliers] == ["eob-13"] and "30.0%" in f.outliers[0][1]


def test_tc_rec_15_2_deductible_charged_again_after_it_ran_out_is_no_answer():
    """The walkthrough's mistake: the deductible runs out at $1,000.00, then a later EOB charges $300.00 more. A
    $1,300.00 deductible with an early stop would look the same, so the EOBs give no answer and nothing is flagged."""
    claims = [claim(1, 160000, deductible=100000, coinsurance=12000), claim(2, 30000, deductible=30000)]
    claims += [claim(i, 50000, coinsurance=10000) for i in range(3, 8)]
    visits = {f"v{i}": {"member_id": "a", "service_type": "other"} for i in range(1, 8)}
    t = infer(claims, visits)
    f = t.get("deductible")
    assert (f.state, f.value, f.text) == ("conflicting", None, "No single answer")
    assert {cid for cid, _ in f.outliers} == {"eob-1", "eob-2"}
    plan = {"id": "plan", "limits": [{"type": "deductible", "network": "in_network", "level": "individual",
                                      "amount": 100000}]}
    assert pi.mismatches(plan, t) == []
    # Without the mistake the same EOBs know it, and the later charge would be the outlier.
    t = infer([claims[0]] + claims[2:], visits)
    assert (t.get("deductible").state, t.get("deductible").value) == ("known", 100000)


# TC-REC-15-3: before the deductible is met, only a lower bound, never used.

def test_tc_rec_15_3_deductible_not_met_is_a_lower_bound():
    claims = [claim(i, 40000, deductible=40000) for i in range(1, 4)]
    visits = {c["visit_id"]: {"member_id": "a", "service_type": "other"} for c in claims}
    t = infer(claims, visits)
    f = t.get("deductible")
    assert (f.state, f.value, f.text) == ("at_least", 120000, "at least $1,200.00")
    filled, used = pi.fill(Terms(rate=0.2), t, "other")
    assert filled.deductible is None and not used


# TC-REC-15-4: too few claims, or claims that disagree, say nothing usable.

def test_tc_rec_15_4_unknown_and_conflicting():
    two = [claim(i, 20000, copay=4000) for i in (1, 2)]
    visits = {f"v{i}": {"member_id": "a", "service_type": "specialist"} for i in range(1, 5)}
    assert infer(two, visits).get("copay:specialist").state == "unknown"
    four = [claim(i, 20000, copay=amount) for i, amount in enumerate((4000, 4000, 6000, 7500), 1)]
    f = infer(four, visits).get("copay:specialist")
    assert f.state == "conflicting" and not f.usable
    filled, used = pi.fill(Terms(), infer(four, visits), "specialist")
    assert "specialist" not in filled.copays and not used


# TC-REC-15-5 (core part): denied and out-of-network claims and other plans are left out.

def test_tc_rec_15_5_denied_out_of_network_and_other_plans_left_out():
    claims = [claim(i, 50000, coinsurance=10000) for i in range(1, 4)]
    noise = [claim(4, 50000, coinsurance=25000, claim_status="denied"),
             claim(5, 50000, coinsurance=25000, network_status="out_of_network"),
             claim(6, 50000, coinsurance=25000, plan_id="other-plan")]
    visits = {f"v{i}": {"member_id": "a", "service_type": "other"} for i in range(1, 7)}
    f = infer(claims + noise, visits).get("coinsurance")
    assert (f.state, f.value, f.shown, f.outliers) == ("known", 0.2, 3, [])


def test_leave_one_out_and_fill_never_override():
    claims = [claim(i, 50000, coinsurance=10000) for i in range(1, 4)]
    visits = {f"v{i}": {"member_id": "a", "service_type": "other"} for i in range(1, 4)}
    assert pi.infer(claims, visits, "plan", without="eob-1").get("coinsurance").state == "unknown"
    t = infer(claims, visits)
    filled, used = pi.fill(Terms(rate=0.3, confirmed=True), t, "other")
    assert (filled.rate, used, filled.confirmed) == (0.3, [], True)
    filled, used = pi.fill(Terms(confirmed=True), t, "other")
    assert (filled.rate, used, filled.confirmed) == (0.2, ["coinsurance 20%"], False)


def test_mismatches_name_both_values():
    claims = [claim(i, 50000, coinsurance=15000) for i in range(1, 5)]
    visits = {f"v{i}": {"member_id": "a", "service_type": "other"} for i in range(1, 5)}
    plan = {"id": "plan", "coinsurance_rate": 0.2, "limits": []}
    [m] = pi.mismatches(plan, infer(claims, visits))
    assert m.key == "coinsurance" and m.amount == 0
    assert "coinsurance of 30%" in m.detail and "says 20%" in m.detail
    assert pi.mismatches({**plan, "coinsurance_rate": 0.3}, infer(claims, visits)) == []
    assert costshare  # the generator and the check share one rule


# ---------- through the report (TC-REC-15-5 to 7) ----------

from datetime import date  # noqa: E402

from mhs.core.reconcile import build_report  # noqa: E402
from tests.test_costshare import CODES, claim as eob, plan as base_plan  # noqa: E402
from tests.test_reconcile import base, visit as base_visit  # noqa: E402

TODAY = date(2026, 10, 9)


def year_at(rate_charged: float, n: int = 5, **plan_extra):
    """n visits, deductible already met by a first claim, each charged coinsurance at rate_charged."""
    visits = [base_visit("v0", "2026-01-05")] + [base_visit(f"v{i}", f"2026-02-{i:02d}") for i in range(1, n + 1)]
    docs = [eob("v0", 600000, d="2026-01-10", deductible=600000)]
    docs += [eob(f"v{i}", 50000, d=f"2026-03-{i:02d}", number=f"C{i}", coinsurance=round(40000 * rate_charged / 0.8))
             for i in range(1, n + 1)]
    plans = [base_plan(**plan_extra)]
    return visits, docs, plans


def report(visits, docs, plans):
    return build_report(base(visits=visits, documents=docs, plans=plans, claim_codes=CODES), 2026, TODAY)


def flags(r, prefix="terms-"):
    return [(v.id, c) for v in r.visits for c in v.checks if c.code.startswith(prefix)]


def test_tc_rec_15_6_entered_term_differs_is_a_flag():
    visits, docs, plans = year_at(0.3)  # the plan says 20%; every EOB charges 30% of $500.00 = $150.00
    for confirmed in (True, False):
        r = report(visits, docs, [{**plans[0], "terms_confirmed": confirmed}])
        assert r.plan_terms["plan"].get("coinsurance").value == 0.3
        [(vid, c)] = flags(r)
        assert (vid, c.result, c.kind, c.code) == ("v3", "flag", "terms_mismatch", "terms-coinsurance")
        assert "coinsurance of 30%" in c.detail and "says 20%" in c.detail
        assert c.name == "Coinsurance matches your EOBs"
    # Statuses and dollars at stake come from REC-06 alone: the mismatch adds nothing.
    without = report(visits, docs, [{**plans[0], "coinsurance_rate": 0.3, "terms_confirmed": True}])
    assert not flags(without)


def test_tc_rec_15_6_closing_the_flag_keeps_it_closed():
    visits, docs, plans = year_at(0.3)
    visits[3] = {**visits[3], "closed_findings": [{"code": "terms-coinsurance", "amount": 0, "closed": "2026-10-01",
                                                   "verdict": "wrong", "kind": "terms_mismatch"}]}
    [(_, c)] = flags(report(visits, docs, plans))
    assert c.result == "closed"


def test_tc_rec_15_7_empty_term_filled_from_the_other_eobs():
    visits, docs, plans = year_at(0.2, n=5, coinsurance_rate=None, terms_confirmed=True)
    docs.append(eob("v6", 50000, d="2026-04-01", number="C6", coinsurance=15000))
    visits.append(base_visit("v6", "2026-03-20"))
    r = report(visits, docs, plans)
    ok = [c for c in r.visit("v2").checks if c.code == "plan"]
    assert ok[0].result == "pass" and "using what your EOBs show for coinsurance 20%" in ok[0].detail
    [bad] = [c for c in r.visit("v6").checks if c.code == "plan"]
    assert (bad.result, bad.amount) == ("flag", 5000)
    assert "uses terms read from your other EOBs" in bad.detail
    assert r.visit("v6").status != "discrepancy"
    # An entered rate always wins.
    r = report(visits, docs, [{**plans[0], "coinsurance_rate": 0.3}])
    assert "using what your EOBs show" not in [c for c in r.visit("v2").checks if c.code == "plan"][0].detail


def test_tc_rec_15_7_checked_claim_never_sets_its_own_term():
    """Three claims: each is checked against the other two, which aren't enough to know the rate."""
    visits, docs, plans = year_at(0.2, n=3, coinsurance_rate=None)
    r = report(visits, docs, plans)
    assert r.plan_terms["plan"].get("coinsurance").state == "known"
    [c] = [c for c in r.visit("v1").checks if c.code == "plan"]
    assert c.result == "na" and "coinsurance rate" in c.detail


def test_tc_rec_15_5_secondary_and_superseded_eobs_change_nothing():
    visits, docs, plans = year_at(0.2)
    before = report(visits, docs, plans).plan_terms["plan"].get("coinsurance")
    second = {"id": "plan2", "plan_year": 2026, "insurer": "Y", "coverage_order": "secondary", "limits": []}
    noisy = docs + [
        {**eob("v1", 50000, d="2026-03-20", number="S1", coinsurance=25000), "id": "eob-v1-sec", "plan_id": "plan2"},
        {**eob("v2", 50000, d="2026-02-15", number="C2", coinsurance=25000), "id": "eob-v2-old"},
    ]
    after = report(visits, noisy, plans + [second]).plan_terms["plan"].get("coinsurance")
    assert (after.state, after.value, after.shown, after.outliers) == (before.state, before.value, before.shown, [])
