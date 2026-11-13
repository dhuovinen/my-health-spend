"""Guided first run (UX-09, ADR-055): a checklist computed from the household's records, so leaving and coming back
resumes where the records say (TC-UX-09-2). Pure: no database or web imports."""

from dataclasses import dataclass

from mhs.core.reconcile import Dataset, is_secondary


@dataclass
class Step:
    key: str
    title: str
    why: str
    href: str
    done: bool


def steps(ds: Dataset, year: int, add_url: str, first_visit: str | None) -> list[Step]:
    plans = [p for p in ds.plans if p.get("plan_year") == year and not is_secondary(p)]
    limits = any(l.get("type") == "deductible" for p in plans for l in p.get("limits") or [])
    terms = any(p.get("terms_confirmed") for p in plans)
    accounts = [a for a in ds.accounts if a.get("type") in ("hsa", "fsa", "lpfsa", "hra")] or ds.accounts
    return [
        Step("members", "Add the people in your household", "Each visit belongs to someone, and each person has "
             "their own deductible.", "/settings#members", bool(ds.members)),
        Step("plan", f"Add your {year} insurance plan with its deductible and out-of-pocket maximum",
             "MHS tracks how close you are to them and checks each claim against them.", "/settings#plans",
             bool(plans) and limits),
        Step("terms", "Enter the plan's coinsurance and copays, then confirm them",
             "So MHS can tell whether each EOB charged you what your plan says.", "/settings#plans", terms),
        Step("account", "Add your HSA, FSA or the card you pay with", "So MHS can tell which payments came from the "
             "HSA and which you can still reimburse.", "/settings#accounts", bool(accounts)),
        Step("document", "Add your first bill or EOB", "A photo or PDF, an insurer export, or your insurer's "
             "connection.", add_url, any(d.get("type") != "account_transaction" for d in ds.documents)),
        Step("result", "See your first reconciled visit", "Where the bill, the EOB and what you paid agree, or "
             "don't.", f"/visits/{first_visit}" if first_visit else "/visits", first_visit is not None),
    ]


def remaining(all_steps: list[Step]) -> int:
    return sum(not s.done for s in all_steps)
