"""Guided first run (UX-09, ADR-055): a checklist computed from the household's records, so leaving and coming back
resumes where the records say (TC-UX-09-2). Pure: no database or web imports."""

from dataclasses import dataclass

from mhs.core.reconcile import Dataset, is_dental, is_secondary


@dataclass
class Step:
    key: str
    title: str
    why: str  # what to do, in plain words
    href: str
    done: bool
    action: str = "Open"  # the button's words


def steps(ds: Dataset, year: int, add_url: str, first_visit: str | None) -> list[Step]:
    plans = [p for p in ds.plans if p.get("plan_year") == year and not is_secondary(p) and not is_dental(p)]
    limits = any(l.get("type") == "deductible" for p in plans for l in p.get("limits") or [])
    terms = any(p.get("terms_confirmed") for p in plans)
    accounts = [a for a in ds.accounts if a.get("type") in ("hsa", "fsa", "lpfsa", "hra")] or ds.accounts
    uploads = add_url == "/uploads"
    to_confirm = next((p for p in plans if not p.get("terms_confirmed")), None)
    terms_href = (f"/coverage?year={year}&edit={to_confirm['id']}#edit-{to_confirm['id']}" if to_confirm
                  else f"/coverage?year={year}")
    return [
        Step("members", "Add the people in your household",
             "In Settings, under Household members, add each person whose visits you'll track. Each person has "
             "their own deductible.", "/settings#members", bool(ds.members), "Add household members"),
        Step("plan", f"Add your {year} insurance plan with its deductible and out-of-pocket maximum",
             "On the Coverage page, add the plan, then its in-network deductible and out-of-pocket maximum from "
             "your plan documents.", f"/coverage?year={year}", bool(plans) and limits, "Add your plan"),
        Step("terms", "Enter the plan's coinsurance and copays, then confirm them",
             "On the Coverage page, under Edit this plan: type the coinsurance % and the copays from your plan "
             "documents, tick \u201cThese terms match my plan documents\u201d and press Save plan. MHS then checks "
             "whether each EOB charged you what your plan says.", terms_href, terms, "Confirm your plan's terms"),
        Step("account", "Add your HSA, FSA or the card you pay with",
             "In Settings, under Payment accounts, add the accounts you pay providers from, so MHS can tell which "
             "payments came from the HSA.", "/settings#accounts", bool(accounts), "Add a payment account"),
        Step("document", "Add your first bill or EOB",
             "Upload a provider's bill or your insurer's EOB as a PDF or a photo, or your HSA's export; you check "
             "what MHS read before anything is saved." if uploads else
             "Import an ingest file built from your claims, HSA export and statements.", add_url,
             any(d.get("type") != "account_transaction" for d in ds.documents),
             "Upload a document" if uploads else "Import a file"),
        Step("result", "See your first reconciled visit", "Open a visit to see where the bill, the EOB and what "
             "you paid agree, or don't.", f"/visits/{first_visit}" if first_visit else "/visits",
             first_visit is not None, "Open your first visit"),
    ]


def remaining(all_steps: list[Step]) -> int:
    return sum(not s.done for s in all_steps)
