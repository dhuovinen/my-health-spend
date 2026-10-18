"""HSA and tax core (Release 2: TAX-01 to TAX-04, TAX-06 to TAX-10; ADR-042), one test per TEST_PLAN case.

Synthetic datasets only, with "today" pinned. The page tests (both apps) are in tests/test_tax_pages.py.
"""

import json
from dataclasses import replace
from datetime import date

import pytest

from mhs.config import ROOT
from mhs.core import tax
from mhs.core.reconcile import Dataset, available_years, build_report
from mhs.data.importer import commit, prepare
from mhs.data.reference import load_tables, tables_from
from mhs.data.repository import load_dataset
from mhs.data.store import Store

TODAY = date(2026, 10, 9)
TABLES = load_tables()
SAMPLE = ROOT / "samples" / "tax-ingest.json"

ME = {"id": "me", "name": "Pat", "relationship": "self", "birth_year": 1980}
SPOUSE = {"id": "sp", "name": "Lee", "relationship": "spouse"}
KID = {"id": "kid", "name": "Ash", "relationship": "child", "birth_year": 2002, "tax_dependent": {"2026": False}}
HSA = {"id": "hsa", "name": "HSA", "type": "hsa", "opened": "2025-01-01", "member_ids": ["me"]}
CARD = {"id": "card", "name": "Card", "type": "credit_card"}


def visit(vid, d, member="me", category="provider_visit", description="Office visit copay", provider="doc", **extra):
    return {"id": vid, "date": d, "provider_id": provider, "member_id": member, "category": category,
            "description": description, **extra}


def eob(vid, owed, d=None, provider="doc"):
    return {"id": f"eob-{vid}", "type": "eob", "date": d or "2026-12-01", "plan_id": "plan", "provider_id": provider,
            "visit_id": vid, "billed": owed * 2, "allowed": owed, "adjustment": owed, "insurer_paid": 0,
            "patient_responsibility": owed}


def receipt(vid, total, item, provider="shop", d="2026-03-01"):
    return {"id": f"rcpt-{vid}", "type": "receipt", "date": d, "provider_id": provider, "visit_id": vid, "total": total,
            "items": [{"description": item, "amount": total}]}


def pay(pid, d, amount, account="card", provider="doc", kind="payment"):
    return {"id": pid, "type": "payment", "date": d, "provider_id": provider, "account_id": account, "amount": amount,
            "kind": kind}


def contribution(d, amount, kind="contribution_employee", account="hsa", tax_year=None):
    doc = {"id": f"c-{d}-{kind}-{amount}", "type": "account_transaction", "date": d, "account_id": account,
           "kind": kind, "amount": amount}
    if tax_year:
        doc["tax_year"] = tax_year
    return doc


def dataset(visits=(), documents=(), accounts=(HSA, CARD), members=(ME, SPOUSE, KID), plans=None) -> Dataset:
    return Dataset(
        plans=plans if plans is not None else [{"id": "plan", "plan_year": 2026, "insurer": "X", "limits": [],
                                                "hsa_eligible_plan": True, "member_ids": ["me"]}],
        accounts=list(accounts), members=list(members),
        providers=[{"id": "doc", "name": "Doc", "kind": "physician_practice"}, {"id": "shop", "name": "Shop", "kind": "retailer"},
                   {"id": "dent", "name": "Dentist", "kind": "physician_practice"}],
        visits=list(visits), documents=list(documents))


def view(ds: Dataset, year=2026, strategy="pay_now", tables=TABLES, today=TODAY) -> tax.TaxView:
    reports = {y: build_report(ds, y, today) for y in set(available_years(ds)) | {year}}
    return tax.tax_view(ds, reports, year, today, tables, strategy)


def tag(description, category="provider_visit", provider=None, receipts=(), **extra) -> tax.Tag:
    return tax.tag_visit(visit("v", "2026-03-01", category=category, description=description, **extra), provider,
                         list(receipts), TABLES)


# ---------- TAX-01 tags ----------

def test_tc_tax_01_1_office_visit_copay_is_likely_qualified_citing_physicians():
    t = tag("Office visit copay")
    assert (t.tag, t.category.cite, t.label) == ("likely_qualified", "Physicians", "Likely qualified")
    assert t.cite == 'IRS Publication 502, "Physicians"' and t.qualified


def test_tc_tax_01_2_vitamins_likely_not_then_documented_with_a_letter():
    t = tag("", category="supplements", receipts=[receipt("v", 1800, "Vitamin D3 2000 IU")])
    assert (t.tag, t.category.cite, t.qualified) == ("likely_not_qualified", "Nutritional Supplements", False)
    t = tag("", category="supplements", receipts=[receipt("v", 1800, "Vitamin D3 2000 IU")], tax={"documentation": True})
    assert (t.tag, t.documented, t.qualified) == ("needs_documentation", True, True)
    assert t.label == "Needs documentation (letter on file)"


def test_tc_tax_01_3_massage_therapy_needs_a_letter_of_medical_necessity():
    t = tag("Massage therapy, 60 minutes", category="service")
    assert (t.tag, t.category.cite, t.needs_letter) == ("needs_documentation", "Therapy", True)
    assert "letter of medical necessity" in t.category.documentation


def test_tags_fall_back_to_the_provider_kind_then_the_visit_category_and_the_member_choice_wins():
    assert tag("", provider={"kind": "lab"}).category.id == "laboratory"
    assert tag("", category="rx").category.id == "medicines"
    assert tag("", category="equipment").tag == "needs_documentation"
    assert tag("Cosmetic botox").tag == "likely_not_qualified"
    chosen = tag("Cosmetic botox", tax={"category": "physicians"})
    assert (chosen.category.id, chosen.source, chosen.tag) == ("physicians", "member", "likely_qualified")
    assert tag("Something odd", category="unknown").category.id == "other"


def test_tc_tax_01_4_a_new_table_version_tags_new_expenses_and_leaves_earlier_ones():
    """PLT-01: tables are versioned by effective date. A new version (here vitamins move to needs documentation)
    applies to expenses dated from its effective date; earlier expenses and the member's choices keep theirs."""
    old = TABLES.categories[0]
    newer = replace(old, version="pub502-2027", effective_from="2027-01-01", categories=tuple(
        replace(c, tag="needs_documentation") if c.id == "supplements" else c for c in old.categories))
    tables = tax.TaxTables(categories=[old, newer], limits=TABLES.limits)
    before = tax.tag_visit(visit("a", "2026-06-01", category="supplements", description="Vitamins"), None, [], tables)
    after = tax.tag_visit(visit("b", "2027-02-01", category="supplements", description="Vitamins"), None, [], tables)
    assert (before.version, before.tag) == ("pub502-2025", "likely_not_qualified")
    assert (after.version, after.tag) == ("pub502-2027", "needs_documentation")
    kept = tax.tag_visit(visit("c", "2027-02-01", category="supplements", description="Vitamins",
                               tax={"category": "supplements", "version": "pub502-2025"}), None, [], tables)
    assert (kept.version, kept.tag) == ("pub502-2025", "likely_not_qualified")


def test_reference_tables_are_dated_data():
    assert TABLES.limits[2026].hsa_family == 875000 and TABLES.limits[2025].hsa_self_only == 430000
    assert all(t.effective_from and t.source for t in TABLES.categories)
    loaded = tables_from({"years": [{"year": 2030, "hsa_self_only": 1, "hsa_family": 2, "hsa_catch_up": 3, "fsa": 4,
                                     "fsa_carryover": 5}]},
                         {"versions": [{"version": "x", "effective_from": "2030-01-01",
                                        "categories": [{"id": "other", "cite": "c", "name": "n", "tag": "needs_documentation"}]}]})
    assert loaded.limits[2030].fsa_carryover == 500 and loaded.categories_on("2029-01-01").version == "x"


# ---------- TAX-02 account rules ----------

FSA = {"id": "fsa", "name": "Health FSA", "type": "fsa", "plan_year": 2026}
LPFSA = {"id": "lp", "name": "LPFSA", "type": "lpfsa", "plan_year": 2026}


def test_tc_tax_02_1_grace_period_lets_2026_money_pay_a_march_2027_expense():
    fsa = {**FSA, "grace_period": True}
    assert tax.last_expense_day(fsa) == date(2027, 3, 15)
    assert tax.funds_usable(fsa, "2027-03-10") and not tax.funds_usable(fsa, "2027-03-16")
    assert not tax.funds_usable(FSA, "2027-03-10") and tax.funds_usable(FSA, "2026-12-31")
    odd = {**FSA, "plan_year_start": "2026-07-01", "plan_year_end": "2027-06-30", "grace_period": True}
    assert tax.last_expense_day(odd) == date(2027, 9, 15) and not tax.funds_usable(odd, "2026-06-30")


def test_tc_tax_02_2_carryover_of_680_from_1000_unspent():
    assert tax.carryover({**FSA, "carryover": 68000}, 100000, TABLES) == (68000, 32000)
    assert tax.carryover({**FSA, "carryover": 90000}, 100000, TABLES) == (68000, 32000)  # capped by the IRS maximum
    assert tax.carryover({**FSA, "grace_period": True}, 100000, TABLES) == (0, 100000)


def test_tc_tax_02_3_claim_after_the_run_out_deadline_is_past_it():
    fsa = {**FSA, "run_out_end": "2027-03-31"}
    assert not tax.claim_on_time(fsa, "2027-04-02") and tax.claim_on_time(fsa, "2027-03-31")
    assert tax.claim_on_time(FSA, "2030-01-01")


def test_tc_tax_02_4_limited_purpose_fsa_pays_dental_and_vision_only():
    ok, why = tax.covers(LPFSA, tag("Office visit"))
    assert not ok and "dental and vision" in why
    assert tax.covers(LPFSA, tag("Dental cleaning"))[0] and tax.covers(LPFSA, tag("Eye exam"))[0]


def test_tc_tax_02_5_hra_pays_only_its_listed_expenses():
    hra = {"id": "hra", "name": "HRA", "type": "hra", "eligible_categories": ["physicians"]}
    assert tax.covers(hra, tag("Office visit"))[0]
    assert tax.covers(hra, tag("Dental cleaning")) == (False, "Not on this HRA's list of eligible expenses")
    assert not tax.covers(CARD, tag("Office visit"))[0]


# ---------- TAX-03 which account pays ----------

def rec(t, accounts, strategy="pay_now", member=ME, today=TODAY, documents=(), d="2026-09-01"):
    return tax.recommend(t, member, d, list(accounts), list(documents), strategy, today, TABLES)


def test_tc_tax_03_1_and_3_hsa_by_default_with_an_lpfsa_available():
    lp = {**LPFSA, "balance": 30000, "balance_as_of": "2026-09-01"}
    r = rec(tag("Office visit"), [HSA, lp, CARD])
    assert (r.action, r.account["id"]) == ("hsa", "hsa")
    # a dental expense too, while the LPFSA's money isn't close to being forfeited (TC-TAX-03-5 is when it is)
    assert rec(tag("Dental cleaning"), [HSA, lp, CARD], today=date(2026, 6, 1)).action == "hsa"


def test_tc_tax_03_2_save_hsa_for_later_routes_to_the_vault():
    r = rec(tag("Office visit"), [HSA, CARD], strategy="save_for_later")
    assert r.action == "vault" and "receipt vault" in r.text


def test_tc_tax_03_4_lpfsa_never_recommended_for_a_medical_expense():
    lp = {**LPFSA, "balance": 30000, "balance_as_of": "2026-12-01"}
    for today in (TODAY, date(2026, 12, 11)):  # even when its money is about to be forfeited
        assert rec(tag("Office visit"), [HSA, lp], today=today).action == "hsa"
    assert rec(tag("Office visit"), [lp]).action == "other"


def test_tc_tax_03_5_lpfsa_suggested_when_its_balance_would_be_forfeited():
    lp = {**LPFSA, "balance": 30000, "balance_as_of": "2026-12-01"}
    r = rec(tag("Dental filling"), [HSA, lp], today=date(2026, 12, 11))
    assert (r.action, r.account["id"]) == ("account", "lp")
    assert "$300.00" in r.text and "20 days" in r.text and r.alternative == "Or pay from HSA."
    # far from the year end, the HSA again; with a carryover covering the balance, nothing is forfeited
    assert rec(tag("Dental filling"), [HSA, lp], today=date(2026, 6, 1)).action == "hsa"
    assert rec(tag("Dental filling"), [HSA, {**lp, "carryover": 68000}], today=date(2026, 12, 11)).action == "hsa"


def test_recommendation_for_likely_not_qualified_documentation_and_no_hsa():
    assert rec(tag("Cosmetic botox"), [HSA]).action == "other"
    letter = rec(tag("Massage therapy"), [HSA])
    assert letter.action == "hsa" and "letter of medical necessity" in letter.letter
    assert rec(tag("Office visit"), [{**FSA, "balance": 10000}]).action == "account"  # the only one that can pay
    assert rec(tag("Office visit"), [{**HSA, "opened": "2026-10-01"}]).action == "other"  # opened after the visit


# ---------- TAX-04 receipt vault ----------

def vault_ds(**extra):
    visits = [visit("v1", "2026-03-01"), visit("v0", "2024-12-01")]
    docs = [eob("v1", 12000), eob("v0", 5000, d="2024-12-20"), pay("p1", "2026-03-10", 12000),
            pay("p0", "2024-12-28", 5000)]
    return dataset(visits, docs + extra.pop("documents", []), **extra)


def test_tc_tax_04_1_qualified_expense_paid_outside_the_hsa_goes_in_the_vault():
    v = view(vault_ds())
    assert [(e.visit.id, e.amount) for e in v.vault] == [("v1", 12000)]
    assert v.vault_total() == 12000


def test_tc_tax_04_2_expense_before_the_hsa_was_opened_is_not_added():
    v = view(vault_ds(), year=2024)
    assert all(e.visit.id != "v0" for e in v.vault)


def test_tc_tax_04_3_reimbursed_entry_leaves_the_total_and_counts_once():
    reimb = {"id": "r1", "type": "account_reimbursement", "date": "2026-04-01", "from_account_id": "hsa", "amount": 12000,
             "payment_ids": ["p1"]}
    again = {**reimb, "id": "r2", "date": "2026-05-01"}
    v = view(vault_ds(documents=[reimb, again]))
    assert v.vault_total() == 0 and v.vault[0].reimbursement["id"] == "r1"
    assert v.double_reimbursed == ["p1"]
    assert v.vault_total("2026-03-31") == 12000  # open before it was reimbursed
    # Both reimbursements left the HSA; the second isn't attributed to the visit again, so it shows as unmatched.
    rows = {r.member_id: r.hsa_distributions for r in v.summary.rows}
    assert v.summary.distributions == 24000 and rows["me"] == 12000 and rows[tax.UNMATCHED] == 12000
    assert v.summary.balanced


def test_vault_leaves_out_unqualified_overpaid_and_other_people():
    visits = [visit("vit", "2026-03-01", category="supplements", description="Vitamins", provider="shop"),
              visit("kid", "2026-04-01", member="kid"), visit("over", "2026-05-01", provider="dent", description="Dental")]
    docs = [receipt("vit", 2000, "Vitamin C"), pay("pv", "2026-03-01", 2000, provider="shop"), eob("kid", 5000),
            pay("pk", "2026-04-10", 5000), eob("over", 3000, provider="dent"), pay("po", "2026-05-10", 4000, provider="dent")]
    v = view(dataset(visits, docs))
    assert [(e.visit.id, e.amount) for e in v.vault] == [("over", 3000)]  # not the $10.00 paid beyond what was owed


def test_vault_label_follows_the_setting():
    assert tax.strategy_of(None) == "pay_now" and tax.strategy_of({"hsa_strategy": "save_for_later"}) == "save_for_later"
    assert tax.strategy_of({"hsa_strategy": "nonsense"}) == "pay_now"


# ---------- TAX-06 contributions ----------

FAMILY_PLAN = {"id": "plan", "plan_year": 2026, "insurer": "X", "limits": [], "hsa_eligible_plan": True,
               "member_ids": ["me", "sp"]}


def check(docs, year=2026, plans=(FAMILY_PLAN,), account=HSA, members=(ME, SPOUSE, KID), accounts=None):
    ds = dataset(documents=docs, plans=list(plans), members=members, accounts=accounts or (account, CARD))
    return tax.contribution_check(account, year, ds, TABLES)


def test_tc_tax_06_1_family_coverage_8000_contributed_leaves_750():
    c = check([contribution("2026-02-01", 600000), contribution("2026-03-01", 200000, kind="contribution_employer")])
    assert (c.limit, c.contributed, c.room, c.excess) == (875000, 800000, 75000, 0)
    assert (c.employee, c.employer) == (600000, 200000)


def test_tc_tax_06_2_catch_up_at_55():
    c = check([], members=({**ME, "birth_year": 1971}, SPOUSE))
    assert (c.limit, c.catch_up) == (975000, 100000)
    assert any("birth year" in n for n in check([], members=({**ME, "birth_year": None}, SPOUSE)).notes)


def test_tc_tax_06_3_mid_year_change_monthly_then_last_month_rule():
    plans = [{**FAMILY_PLAN, "id": "self", "member_ids": ["me"], "coverage_end": "2026-06-30"},
             {**FAMILY_PLAN, "id": "fam", "coverage_start": "2026-07-01"}]
    c = check([], plans=plans)
    assert (c.limit, c.rule, c.warning) == (657500, "monthly", "")
    c = check([], plans=plans, account={**HSA, "last_month_rule_years": [2026]})
    assert (c.limit, c.rule) == (875000, "last_month") and "testing period" in c.warning and "2027" in c.warning
    explicit = {**HSA, "coverage": [{"start": "2026-01-01", "end": "2026-06-30", "type": "self_only"},
                                    {"start": "2026-07-01", "type": "family"}]}
    assert check([], plans=[], account=explicit).limit == 657500


def test_tc_tax_06_4_excess_contribution():
    c = check([contribution("2026-01-15", 905000)])
    assert c.excess == 30000 and c.room == 0


def test_tc_tax_06_5_each_year_against_its_own_row():
    plan25 = {**FAMILY_PLAN, "id": "p25", "plan_year": 2025}
    docs = [contribution("2025-06-01", 855000), contribution("2026-03-01", 10000, tax_year=2025),
            contribution("2026-06-01", 875000)]
    c25 = check(docs, year=2025, plans=(plan25, FAMILY_PLAN))
    c26 = check(docs, year=2026, plans=(plan25, FAMILY_PLAN))
    assert (c25.limit, c25.contributed, c25.excess) == (855000, 865000, 10000)  # prior-year contribution by tax year
    assert (c26.limit, c26.contributed, c26.excess) == (875000, 875000, 0)
    assert check([], year=2031).limit is None and "no IRS limits table for 2031" in check([], year=2031).notes[0]


# ---------- TAX-07 HSA payments for non-qualified expenses ----------

def vitamins(mark=None):
    v = visit("vit", "2026-03-01", category="supplements", description="Vitamins", provider="shop",
              **({"tax": mark} if mark else {}))
    return dataset([v], [receipt("vit", 4000, "Vitamin D3"), pay("pv", "2026-03-01", 4000, account="hsa", provider="shop")])


def test_tc_tax_07_1_mistaken_distribution_guidance_only_when_marked():
    [flag] = view(vitamins()).flags["vit"]
    assert flag.kind == "not_qualified" and flag.amount == 4000 and flag.guidance == ""
    assert "likely not a qualified expense" in flag.text and "mark it" in flag.text
    [flag] = view(vitamins({"mistake": True})).flags["vit"]
    assert "mistaken distribution" in flag.guidance and "April 15" in flag.guidance
    assert "not legal, tax or medical advice" in tax.DISCLAIMER


def test_tc_tax_07_2_needs_documentation_prompts_for_a_letter_not_non_qualified():
    v = visit("m", "2026-03-01", category="service", description="Massage therapy", provider="shop", payment_path="self_pay")
    bill = {"id": "b", "type": "provider_bill", "date": "2026-03-01", "provider_id": "shop", "balance_due": 9000,
            "lines": [{"visit_id": "m", "patient_amount": 9000, "billed_charge": 9000}]}
    [flag] = view(dataset([v], [bill, pay("pm", "2026-03-02", 9000, account="hsa", provider="shop")])).flags["m"]
    assert flag.kind == "documentation" and "letter of medical necessity" in flag.text
    assert "not a qualified" not in flag.text


# ---------- TAX-08 eligibility conflicts ----------

def test_tc_tax_08_1_general_purpose_fsa_blocks_hsa_contributions():
    c = check([contribution("2026-02-15", 50000)], accounts=(HSA, FSA, CARD))
    [conflict] = c.conflicts
    assert conflict.kind == "fsa" and conflict.contributions and c.limit == 0 and c.excess == 50000


def test_tc_tax_08_2_limited_purpose_fsa_is_no_conflict():
    c = check([contribution("2026-02-15", 50000)], accounts=(HSA, LPFSA, CARD))
    assert c.conflicts == [] and c.limit == 875000


def test_tc_tax_08_3_contributions_after_medicare_are_flagged():
    docs = [contribution("2026-05-15", 50000), contribution("2026-06-15", 50000), contribution("2026-08-15", 50000)]
    c = check(docs, members=({**ME, "medicare_from": "2026-06-01"}, SPOUSE))
    [conflict] = c.conflicts
    assert conflict.kind == "medicare" and conflict.months == list(range(6, 13))
    assert [d["date"] for d in conflict.contributions] == ["2026-06-15", "2026-08-15"]
    assert c.limit == 875000 * 5 // 12


# ---------- TAX-09 who an account may pay for ----------

def test_tc_tax_09_1_hsa_pays_for_a_spouse():
    assert tax.may_pay_for(HSA, SPOUSE, 2026)[0] == "yes"


def test_tc_tax_09_2_hsa_flags_a_24_year_old_non_dependent_an_fsa_allows_it():
    answer, why = tax.may_pay_for(HSA, KID, 2026)
    assert answer == "no" and "tax dependent" in why
    assert tax.may_pay_for(FSA, KID, 2026)[0] == "yes"
    v = visit("k", "2026-04-01", member="kid")
    [flag] = view(dataset([v], [eob("k", 5000), pay("pk", "2026-04-10", 5000, account="hsa")])).flags["k"]
    assert flag.kind == "person" and "Ash" in flag.text


def test_tc_tax_09_3_dependent_status_by_tax_year():
    kid = {**KID, "birth_year": 1990, "tax_dependent": {"2025": True, "2026": False}}
    assert tax.may_pay_for(HSA, kid, 2025)[0] == "yes" and tax.may_pay_for(HSA, kid, 2026)[0] == "no"
    assert tax.may_pay_for(FSA, kid, 2026)[0] == "no"  # 36: past the FSA's under-27 rule too
    assert tax.may_pay_for(HSA, {**kid, "tax_dependent": {}}, 2026)[0] == "check"
    assert tax.may_pay_for(HSA, None, 2026)[0] == "check"


# ---------- TAX-10 year-end summary (with the synthetic sample household) ----------

@pytest.fixture
def sample_view(tmp_path):
    store = Store(tmp_path / "mhs.db")
    plan = prepare(json.loads(SAMPLE.read_text()), store, str(SAMPLE), SAMPLE.parent)
    assert plan.ok, plan.errors
    commit(plan, store, tmp_path / "documents")
    ds = load_dataset(store)

    def make(year=2026, strategy="pay_now"):
        return view(ds, year, strategy, today=date(2026, 10, 18))
    return make


def test_tc_tax_10_1_distributions_by_person_and_purpose_add_up_to_the_hsa(sample_view):
    v = sample_view()
    s = v.summary
    assert s.distributions == 15000 + 6000 + 3500 + 2400 + 12500 + 8000  # payments and the reimbursement in 2026
    assert s.balanced and sum(r.hsa_distributions for r in s.rows) == s.distributions
    assert sum(s.family.by_purpose.values()) == s.distributions
    people = {r.name: r.hsa_distributions for r in s.rows}
    assert people["Jamie Example"] == 12500 and people["Max Example"] == 8000 and people["Not matched to a visit"] == 2400
    assert s.family.by_purpose["Vitamins and supplements"] == 3500


def test_tc_tax_10_2_unreimbursed_line_equals_the_vault_at_year_end(sample_view):
    v25 = sample_view(2025)
    assert v25.summary.family.unreimbursed == v25.vault_total("2025-12-31") == 12000 + 8000
    v26 = sample_view(2026)
    assert v26.summary.family.unreimbursed == v26.vault_total("2026-12-31") == 12000 + 21000 == v26.vault_total()


def test_tc_tax_10_3_medical_spend_for_itemizing_with_the_disclaimer(sample_view):
    v = sample_view(2025)
    assert v.summary.family.out_of_pocket == 9000 + 12000  # paid by card; the dental cleaning was reimbursed
    assert sample_view(2026).summary.family.out_of_pocket == 21000  # not the vitamins, massage or LPFSA payment


def test_sample_household_flags_contributions_and_advice(sample_view):
    v = sample_view()
    assert {vid: [f.kind for f in fl] for vid, fl in v.flags.items()} == {
        "v-2026-04-11-vitamins": ["not_qualified"], "v-2026-08-12-urgent": ["person"]}
    [c] = v.contributions
    assert (c.limit, c.contributed, c.excess) == (757500, 787500, 30000)
    assert c.fee_total == 200 and len(c.fees) == 2  # B-17: fees shown as a possible saving
    assert v.recommendations["v-2026-10-02-pcp"].action == "hsa"
    assert v.recommendations["v-2026-09-15-dental"].action == "account"  # the LPFSA's $300 forfeits in 74 days
    assert sample_view(strategy="save_for_later").recommendations["v-2026-10-02-pcp"].action == "vault"


def test_partial_and_fsa_reimbursements():
    """A reimbursement pays back what it covers; the rest stays in the vault. One from an FSA closes the entry too but
    isn't HSA money."""
    part = {"id": "r1", "type": "account_reimbursement", "date": "2026-04-01", "from_account_id": "hsa", "amount": 5000,
            "payment_ids": ["p1"]}
    v = view(vault_ds(documents=[part]))
    [e] = v.vault
    assert (e.outstanding(), e.open, v.vault_total(), v.double_reimbursed) == (7000, True, 7000, [])
    assert v.vault_total("2026-03-31") == 12000 and v.summary.family.unreimbursed == 7000
    fsa = {**FSA, "plan_year": 2026}
    by_fsa = {**part, "from_account_id": "fsa", "amount": 12000}
    v = view(vault_ds(documents=[by_fsa], accounts=(HSA, CARD, fsa)))
    assert v.vault_total() == 0 and v.summary.distributions == 0 and v.vault[0].reimbursement["from_account_id"] == "fsa"


def test_an_earlier_visit_paid_from_the_hsa_this_year_is_checked_this_year():
    """TAX-07: vitamins bought in 2025, on a 2026 statement, paid from the HSA in 2026."""
    v = visit("vit", "2025-12-28", category="supplements", description="Vitamins", provider="shop")
    bill = {"id": "b", "type": "provider_bill", "date": "2026-01-03", "provider_id": "shop", "balance_due": 4000,
            "lines": [{"visit_id": "vit", "patient_amount": 4000, "billed_charge": 4000}]}
    ds = dataset([{**v, "payment_path": "self_pay"}], [bill, pay("pv", "2026-01-05", 4000, account="hsa", provider="shop")])
    assert [f.kind for f in view(ds, 2026).flags["vit"]] == ["not_qualified"]
    assert "vit" not in view(ds, 2025).flags


def test_last_month_rule_without_december_coverage_says_so():
    plan = {**FAMILY_PLAN, "coverage_end": "2026-11-30"}
    c = check([], plans=[plan], account={**HSA, "last_month_rule_years": [2026]})
    assert c.rule == "monthly" and c.limit == 875000 * 11 // 12
    assert any("needs HSA-eligible coverage on December 1" in n for n in c.notes)
