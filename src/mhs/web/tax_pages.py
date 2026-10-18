"""The HSA and tax page and the visit page's tax section (TAX-01 to TAX-04, TAX-06 to TAX-10; ADR-043).

Mounted by pages.add_pages, so both apps have them. The engine is core/tax.py; the IRS limits and the Publication
502 categories come from data/reference. Every block that suggests an action carries core.tax.DISCLAIMER (CMP-04).
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from mhs.core import tax
from mhs.core.reconcile import Dataset, available_years, build_report
from mhs.data import importer
from mhs.data.money import cents, to_dollars
from mhs.data.reference import load_tables
from mhs.data.repository import PREFERENCE, load_dataset
from mhs.data.store import Store

TAX_PREFERENCE = "tax"  # the household's HSA setting: a preference record, which imports never touch
COVERAGE_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2})?\s*(?:to|–|-)?\s*(\d{4}-\d{2}-\d{2})?\s*:?\s*(self[\s_-]*only|family)$", re.I)


class TaxFormError(ValueError):
    pass


def view_for(store: Store, year: int | None = None, today: date | None = None,
             since: int | None = None) -> tuple[tax.TaxView, Dataset]:
    """The year's tax view. `since` leaves out earlier years' reports, when only one visit's section is needed (its
    payments and reimbursements are dated in its year or later)."""
    today = today or date.today()
    ds = load_dataset(store)
    reports = {y: build_report(ds, y, today) for y in available_years(ds) if since is None or y >= since}
    if year is None:
        year = today.year if today.year in reports or not reports else max(reports)
    if year not in reports:
        reports[year] = build_report(ds, year, today)
    strategy = tax.strategy_of(store.get(PREFERENCE, TAX_PREFERENCE))
    return tax.tax_view(ds, reports, year, today, load_tables(), strategy), ds


def visit_tax(store: Store, visit_id: str) -> dict:
    """The visit page's HSA and tax section: the tag, the categories it can be changed to, flags and the advice."""
    visit = store.get("visit", visit_id)
    year = int(visit["date"][:4])
    view, _ = view_for(store, year, since=year)
    tag = view.tags.get(visit_id)
    table = load_tables().version(tag.version) if tag else None
    return {"tag": tag, "categories": table.categories if table else (), "flags": view.flags.get(visit_id, []),
            "recommendation": view.recommendations.get(visit_id), "choice": visit.get("tax") or {},
            "vault": [e for e in view.vault if e.visit.id == visit_id], "strategy": view.strategy,
            "disclaimer": tax.DISCLAIMER}


def _money(text: str, label: str) -> int | None:
    text = (text or "").replace("$", "").replace(",", "").strip()
    if not text:
        return None
    try:
        return cents(Decimal(text))
    except InvalidOperation:
        raise TaxFormError(f"{label}: {text!r} is not an amount") from None


def _date(text: str, label: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise TaxFormError(f"{label}: {text!r} is not a date (YYYY-MM-DD)") from None


def _int(text: str, label: str) -> int | None:
    text = (text or "").strip()
    if not text:
        return None
    if not text.isdigit():
        raise TaxFormError(f"{label}: {text!r} is not a year")
    return int(text)


def _set(record: dict, key: str, value) -> None:
    if value in (None, "", [], False):
        record.pop(key, None)
    else:
        record[key] = value


def coverage_from(text: str) -> list[dict]:
    """Coverage periods typed one per line, e.g. "2026-01-01 to 2026-06-30: self-only"."""
    out = []
    for line in (l.strip() for l in (text or "").splitlines()):
        if not line:
            continue
        m = COVERAGE_LINE.match(line)
        if not m:
            raise TaxFormError(f"Coverage line {line!r} should look like '2026-01-01 to 2026-06-30: self-only'")
        period = {"type": "family" if m.group(3).lower() == "family" else "self_only"}
        if m.group(1):
            period["start"] = m.group(1)
        if m.group(2):
            period["end"] = m.group(2)
        out.append(period)
    return out


def coverage_text(periods: list[dict] | None) -> str:
    return "\n".join(f"{p.get('start', '')} to {p.get('end', '')}: {p['type'].replace('_', '-')}".strip()
                     for p in periods or [])


def add_tax_pages(app: FastAPI, render: Callable, host, posted: Callable) -> None:
    def tax_page(request: Request, store: Store, year: int | None = None, error: str = "", saved: str = "",
                 status_code: int = 200) -> HTMLResponse:
        view, ds = view_for(store, year)
        tables = load_tables()
        years = sorted(set(available_years(ds)) | {view.year, date.today().year}, reverse=True)
        current = tables.categories_on(date.today().isoformat())
        report_visits = {vid: vr for vid, vr in view.visits.items() if vr.visit["date"][:4] == str(view.year)}
        to_pay = sorted((vr for vr in report_visits.values() if vr.remaining > 0),
                        key=lambda v: (v.visit["date"], v.id), reverse=True)
        return render(request, "tax.html", status_code=status_code, view=view, error=error, saved=saved,
                      years=years, members=ds.members,
                      accounts=sorted(ds.accounts, key=lambda a: (a.get("type") not in tax.TAX_ADVANTAGED, a["name"])),
                      tax_accounts=[a for a in ds.accounts if a.get("type") in tax.TAX_ADVANTAGED],
                      limits=tables.limits.get(view.year), categories=current.categories, category_table=current,
                      flagged=[(view.visits[vid], fl) for vid, fl in view.flags.items()], to_pay=to_pay,
                      account_labels=tax.ACCOUNT_LABELS, strategies=tax.STRATEGIES, tags=tax.TAGS,
                      disclaimer=tax.DISCLAIMER, coverage_text=coverage_text,
                      balance=lambda a: tax.account_balance(a, ds.documents),
                      last_day=tax.last_expense_day, plan_period=tax.plan_period,
                      dependent_years=[view.year - 1, view.year],
                      may_pay=lambda a, m: tax.may_pay_for(a, m, view.year))

    async def posted_tax(request: Request, change: Callable[[Store, object], str]):
        """Run one tax-page change; a TaxFormError shows on the page instead of saving anything."""
        store, form = await posted(request)
        year = int(form.get("year")) if (form.get("year") or "").isdigit() else None
        try:
            section = change(store, form)
        except TaxFormError as e:
            return tax_page(request, store, year, error=str(e), status_code=400)
        return RedirectResponse(f"/tax?{'year=%d&' % year if year else ''}saved={section}#{section}", status_code=303)

    def save(store: Store, kind: str, definition: str, record: dict) -> None:
        errors = importer.record_errors(definition, to_dollars(record))
        if errors:
            raise TaxFormError("; ".join(errors))
        store.upsert(kind, record, edited=True)

    @app.get("/tax", response_class=HTMLResponse)
    def tax_home(request: Request, year: int | None = None, saved: str = ""):
        return tax_page(request, host.store(request), year, saved=saved)

    @app.post("/tax/strategy")
    async def save_strategy(request: Request):
        """TAX-03: "pay from HSA now" (default) or "save HSA for later"."""
        def change(store, form):
            choice = form.get("hsa_strategy") or ""
            if choice not in tax.STRATEGIES:
                raise TaxFormError("Choose how to use the HSA.")
            pref = store.get(PREFERENCE, TAX_PREFERENCE) or {"id": TAX_PREFERENCE}
            pref["hsa_strategy"] = choice
            store.upsert(PREFERENCE, pref, edited=True)
            return "strategy"
        return await posted_tax(request, change)

    @app.post("/tax/accounts/{account_id}")
    async def save_account_rules(request: Request, account_id: str):
        """TAX-02: an account's rules, kept on the account record (Settings data)."""
        def change(store, form):
            account = store.get("account", account_id)
            if not account:
                raise HTTPException(404, "Account not found")
            kind = form.get("type") or account["type"]
            if kind not in tax.TAX_ADVANTAGED:
                raise TaxFormError("Choose an HSA, health FSA, limited-purpose FSA or HRA.")
            account["type"] = kind
            if form.get("rules") == "1":  # the account's rules form; "make another account an FSA" sends the type only
                known = {m["id"] for m in store.all("member")}
                _set(account, "member_ids", [m for m in form.getlist("member_ids") if m in known])
                # Only the fields this account type's form shows; the others are kept as they are.
                for key, parse, label in (("opened", _date, "Opened"), ("plan_year", _int, "Plan year"),
                                          ("plan_year_start", _date, "Plan year start"),
                                          ("plan_year_end", _date, "Plan year end"), ("carryover", _money, "Carryover"),
                                          ("run_out_end", _date, "Claim deadline"), ("balance", _money, "Balance"),
                                          ("balance_as_of", _date, "Balance date")):
                    if key in form:
                        _set(account, key, parse(form.get(key), label))
                if "plan_year" in form:  # a spending account's form, where an unticked box sends nothing
                    _set(account, "grace_period", form.get("grace_period") == "on")
                if kind == "hra" and "plan_year" in form:
                    _set(account, "eligible_categories", form.getlist("eligible_categories"))
                if "coverage" in form:
                    _set(account, "coverage", coverage_from(form.get("coverage") or ""))
            if account.get("grace_period") and account.get("carryover"):
                raise TaxFormError("A plan can have a grace period or a carryover, not both (IRS rule).")
            if account.get("balance") is not None and not account.get("balance_as_of"):
                account["balance_as_of"] = date.today().isoformat()
            save(store, "account", "account", account)
            host.settings_saved(store)
            return "accounts"
        return await posted_tax(request, change)

    @app.post("/tax/contribution-rule/{account_id}")
    async def save_contribution_rule(request: Request, account_id: str):
        """TAX-06: monthly pro rata (default) or the last-month rule, per tax year."""
        def change(store, form):
            account = store.get("account", account_id)
            if not account or account.get("type") != "hsa":
                raise HTTPException(404, "HSA not found")
            year = _int(form.get("year"), "Year")
            years = set(account.get("last_month_rule_years") or [])
            if form.get("rule") == "last_month":
                years.add(year)
            else:
                years.discard(year)
            _set(account, "last_month_rule_years", sorted(years))
            save(store, "account", "account", account)
            host.settings_saved(store)
            return "contributions"
        return await posted_tax(request, change)

    @app.post("/tax/members/{member_id}")
    async def save_member_tax(request: Request, member_id: str):
        """TAX-06, TAX-08, TAX-09: birth year, Medicare start and tax dependent status by year."""
        def change(store, form):
            member = store.get("member", member_id)
            if not member:
                raise HTTPException(404, "Member not found")
            _set(member, "birth_year", _int(form.get("birth_year"), "Birth year"))
            _set(member, "medicare_from", _date(form.get("medicare_from"), "Medicare from"))
            dependent = dict(member.get("tax_dependent") or {})
            for key in form.keys():
                if key.startswith("dep-") and key[4:].isdigit():
                    value = form.get(key)
                    if value in ("yes", "no"):
                        dependent[key[4:]] = value == "yes"
                    else:
                        dependent.pop(key[4:], None)
            _set(member, "tax_dependent", dict(sorted(dependent.items())))
            save(store, "member", "member", member)
            host.settings_saved(store)
            return "people"
        return await posted_tax(request, change)

    @app.post("/tax/reimburse/{payment_id}")
    async def reimburse(request: Request, payment_id: str):
        """TC-TAX-04-3: record that the HSA paid you back for a vault entry; a payment can be reimbursed once."""
        def change(store, form):
            view, _ = view_for(store)
            entries = [e for e in view.vault if e.payment["id"] == payment_id]
            if not entries or not view.hsa:
                raise HTTPException(404, "Not in the receipt vault")
            left = sum(e.outstanding() for e in entries)
            if not left:
                done = entries[-1].reimbursement
                raise TaxFormError(f"This payment was already reimbursed on {done['date']}; it can't be reimbursed twice.")
            when = _date(form.get("date"), "Date") or date.today().isoformat()
            record_id, n = f"reimb-{payment_id}", 2
            while store.get("document", record_id):  # the rest of a payment reimbursed in part before
                record_id, n = f"reimb-{payment_id}-{n}", n + 1
            record = {"id": record_id, "type": "account_reimbursement", "date": when,
                      "from_account_id": view.hsa["id"], "amount": left,
                      "payment_ids": [payment_id], "notes": "Marked reimbursed on the HSA and tax page"}
            save(store, "document", "account_reimbursement", record)
            return "vault"
        return await posted_tax(request, change)

    @app.post("/visits/{visit_id}/tax")
    async def save_visit_tax(request: Request, visit_id: str):
        """TAX-01, TAX-07: the member's category for a visit, a letter on file, an HSA payment that was a mistake."""
        store, form = await posted(request)
        visit = store.get("visit", visit_id)
        if not visit:
            raise HTTPException(404, "Visit not found")
        choice = dict(visit.get("tax") or {})
        category = form.get("category") or ""
        if category:
            table = load_tables().version(choice.get("version", "")) or load_tables().categories_on(visit["date"])
            if not table.get(category):
                raise HTTPException(400, "Unknown category")
            choice.update(category=category, version=table.version)
        else:
            choice.pop("category", None)
            choice.pop("version", None)
        for key in ("documentation", "mistake"):
            _set(choice, key, form.get(key) == "on")
        _set(visit, "tax", choice)
        errors = importer.record_errors("visit", to_dollars(visit))
        if errors:
            raise HTTPException(400, "; ".join(errors))
        store.upsert("visit", visit, edited=True)
        return RedirectResponse(f"/visits/{visit_id}#tax", status_code=303)
