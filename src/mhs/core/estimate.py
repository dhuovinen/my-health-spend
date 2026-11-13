"""Planned visits and the pre-visit estimate (PRE-01, PRE-02, PRE-04 to PRE-07), ADR-053.

Pure functions over record dicts, money in integer cents. No database or web imports. The expected share uses the
same plan terms and accumulators as the REC-06 check (core/costshare.py); the account comes from core/tax.py.
"""

from dataclasses import dataclass, field
from datetime import date

from mhs.core import costshare, tax
from mhs.core.lines import fmt
from mhs.core.reconcile import Dataset, current_claims, is_secondary


def has_documents(visit_id: str, documents: list[dict]) -> bool:
    """A document is linked to the visit: an EOB or receipt, a statement line, or a payment's hint."""
    for d in documents:
        if d.get("visit_id") == visit_id or visit_id in (d.get("visit_ids") or []):
            return True
        if any(line.get("visit_id") == visit_id for line in d.get("lines") or [] if d.get("type") == "provider_bill"):
            return True
    return False


def is_planned(visit: dict, documents: list[dict]) -> bool:
    """PRE-01: planned, not cancelled, and nothing has arrived for it yet."""
    return bool(visit.get("planned")) and visit.get("planned_outcome") != "cancelled" \
        and not has_documents(visit["id"], documents)


def planned_visits(ds: Dataset) -> list[dict]:
    return sorted((v for v in ds.visits if is_planned(v, ds.documents)), key=lambda v: (v["date"], v["id"]))


def accumulators(ds: Dataset, plan: dict) -> costshare.Accumulators:
    """What the insurer has applied this plan year so far, from the EOBs on file, in processing order."""
    visits = {v["id"]: v for v in ds.visits}
    eobs = [d for d in ds.documents if d.get("type") == "eob" and d.get("plan_id") == plan["id"]]
    acc = costshare.Accumulators()
    for c in sorted((c for cs in current_claims(eobs).values() for c in cs), key=costshare.claim_order):
        if c.get("claim_status") == "denied" or c.get("network_status") == "out_of_network":
            continue
        member = visits.get(c["visit_id"], {}).get("member_id") or ""
        acc.add(member, c.get("deductible") or 0, sum(c.get(k) or 0 for k in costshare.SHARE_KEYS))
    return acc


@dataclass
class CashChoice:
    cash: int
    insured: int
    cheaper: str  # cash | insurance | same
    counts: str  # yes | no | unknown: whether the cash amount counts toward the deductible
    text: str


@dataclass
class Estimate:
    visit: dict
    plan: dict | None
    expected: costshare.Expected | None
    cash: CashChoice | None = None
    questions: list[str] = field(default_factory=list)
    recommendation: tax.Recommendation | None = None
    missing: str = ""
    deductible_left: int | None = None
    oop_left: int | None = None
    past_due: bool = False  # the planned date passed with no documents (TC-PRE-01-3)
    disclaimer: str = tax.DISCLAIMER

    @property
    def total(self) -> int | None:
        return self.expected.total if self.expected and not self.expected.missing else None


def cash_choice(cash: int, insured: int, counts: str, ded_left: int | None) -> CashChoice:
    """PRE-04: the cheaper way to pay and what paying cash does to the deductible."""
    cheaper = "cash" if cash < insured else "insurance" if insured < cash else "same"
    text = (f"Paying cash ({fmt(cash)}) costs {fmt(insured - cash)} less than using insurance ({fmt(insured)})"
            if cheaper == "cash" else
            f"Using insurance ({fmt(insured)}) costs {fmt(cash - insured)} less than paying cash ({fmt(cash)})"
            if cheaper == "insurance" else f"Both cost {fmt(cash)}")
    if ded_left:
        if counts == "yes":
            text += ". Your plan counts a cash payment toward the deductible, so either way it moves you closer to it"
        elif counts == "no":
            text += (f". Your plan doesn't count a cash payment toward the deductible: paying cash leaves "
                     f"{fmt(ded_left)} still to meet, which can cost more on later visits this year")
        else:
            text += (f". Ask the plan whether a cash payment counts toward your deductible ({fmt(ded_left)} left); "
                     f"if it doesn't, later visits this year may cost more")
    return CashChoice(cash, insured, cheaper, counts, text)


def questions(provider: dict, plan: dict | None, insured: bool, has_estimate: bool) -> list[str]:
    """PRE-05: what to ask before the visit."""
    insurer = (plan or {}).get("insurer") or "your plan"
    network = provider.get("network_status")
    out = []
    if insured:
        out.append(f"Are you in network with {insurer} for this service, at this location?")
        out.append("Which service codes (CPT) will you bill, and what does the plan allow for them?")
        out.append("Does this need prior authorization, and have you requested it?")
    if not insured or network != "in_network":
        if insured:
            out.append("Will you bill me for the difference above what the plan allows (balance billing)? "
                       "Please put it in writing.")
        if not has_estimate:
            out.append("May I have a written good-faith estimate? If I pay without insurance, the No Surprises Act "
                       "entitles me to one.")
    out.append("What is your price if I pay cash, and is it lower than my cost through insurance?")
    out.append("Please send an itemized bill after the visit.")
    return out


def estimate(visit: dict, ds: Dataset, today: date, tables: tax.TaxTables, strategy: str = "pay_now") -> Estimate:
    plans = {p["id"]: p for p in ds.plans}
    plan = plans.get(visit.get("plan_id") or "")
    if plan is None or is_secondary(plan):
        plan = next((p for p in ds.plans if p.get("plan_year") == int(visit["date"][:4]) and not is_secondary(p)
                     and (not p.get("member_ids") or visit.get("member_id") in p["member_ids"])), plan)
    provider = next((p for p in ds.providers if p["id"] == visit["provider_id"]), {})
    member_id = visit.get("member_id") or ""
    insured = visit.get("payment_path") != "self_pay"
    est = Estimate(visit, plan, None)
    est.past_due = visit["date"] < today.isoformat() and is_planned(visit, ds.documents)
    est.questions = questions(provider, plan, insured, visit.get("good_faith_estimate") is not None)
    member = next((m for m in ds.members if m["id"] == member_id), None)
    est.recommendation = tax.recommend(tax.tag_visit(visit, provider, [], tables), member, visit["date"], ds.accounts,
                                       ds.documents, strategy, today, tables)
    if plan is None:
        est.missing = f"Add your {visit['date'][:4]} plan in Settings to estimate what insurance leaves you"
    elif visit.get("expected_allowed") is None:
        est.missing = "Enter what the plan is expected to allow (ask the provider or the plan for the negotiated rate)"
    if plan is not None:
        terms = costshare.terms_of(plan, member_id or None)
        acc = accumulators(ds, plan)
        est.deductible_left = costshare.deductible_left(terms, acc, member_id)
        est.oop_left = costshare.oop_left(terms, acc, member_id)
        if not est.missing:
            est.expected = costshare.expected_share(terms, visit["expected_allowed"], visit.get("service_type"),
                                                    acc, member_id)
            est.missing = est.expected.missing
    if visit.get("cash_price") is not None and est.total is not None:
        est.cash = cash_choice(visit["cash_price"], est.total, (plan or {}).get("cash_counts_toward_deductible")
                               or "unknown", est.deductible_left)
    return est
