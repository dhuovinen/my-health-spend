"""The Release 0 pages: home, visits, providers and ledgers, notes, import, settings, help (ADR-032).

Both apps mount these routes. Release 0 (web/app.py) hosts them over its SQLite store on the owner's laptop;
the Release 1 application tier (web/household/app.py) hosts them behind MFA sign-in over the signed-in
household's Postgres store. A PagesHost supplies everything that differs between the two.
"""

import base64
import json
import re
import secrets
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from markupsafe import Markup, escape

from mhs.core import edits
from mhs.core.household import NOBODY, household_totals, visits_for
from mhs.core.lines import BUCKETS, LineMatch
from mhs.core.reconcile import (ATTENTION, CHECK_NAMES, DOCUMENT_LABELS, FINDING_KINDS, STATUS_HELP, STATUS_LABELS,
                                STATUS_ORDER, Report, VisitResult, available_years, build_report)
from mhs.data import importer
from mhs.data.importer import BOOKKEEPING, DocumentFiles, FileSource, UploadedSource
from mhs.data.money import cents, to_dollars
from mhs.data.repository import PREFERENCE, RECONCILIATION, load_dataset, waiting_days
from mhs.data.settings_file import settings_document
from mhs.data.store import Store

WEB = Path(__file__).parent
CATEGORIES = ["provider_visit", "service", "supplements", "rx", "equipment"]
ACCOUNT_TYPES = ["hsa", "fsa", "credit_card", "debit_card", "bank", "cash", "other"]
PROVIDER_KINDS = ["physician_practice", "hospital", "lab", "imaging", "pharmacy", "retailer", "other"]
NETWORK_STATUSES = ["in_network", "out_of_network", "not_applicable", "unknown"]
RELATIONSHIPS = ["self", "spouse", "child", "other"]
LIMIT_TYPES = ["deductible", "out_of_pocket_max", "annual_maximum"]
LIMIT_NETWORKS = ["in_network", "out_of_network", "combined"]
NOTE_CHANNELS = ["email", "phone", "portal", "in_person", "letter", "other"]
NOTE_DIRECTIONS = ["sent", "received", "note"]
# Visit-list filters behind the home page's HSA totals: query value -> (VisitResult attribute, label)
HSA_FILTERS = {
    "unpaid": ("remaining", "Unpaid — pay from HSA"),
    "outside_hsa": ("outside_hsa", "Paid outside the HSA"),
    "unexplained": ("unexplained", "Settled by provider, no matching payment"),
}
VIEW_COOKIE = "mhs_view"  # the household view's member (UX-06, ADR-041); absent for the family
HOME_CARDS = 12
HOME_ATTENTION = 8


# Plain-language help for the checks (UX-05; the statuses' help is STATUS_HELP in core). The Help page lists whatever
# the engine defines, so a check without a sentence here still shows with its name.
CHECK_HELP = {
    "C1": "The EOB's own numbers add up: billed = plan paid + discounts + what you owe, and what you owe = deductible "
          "+ copay + coinsurance + not covered.",
    "self_pay": "For a visit paid without insurance, the bill's charges, discount and what you owe add up.",
    "C2": "What the provider asks you for equals what the EOB says you owe, and the provider billed the insurer what it "
          "billed you.",
    "lines": "Each line on the bill pairs with a line on the EOB (bundled and panel codes included).",
    "duplicate": "The same service, date and provider isn't charged twice on a statement.",
    "C3": "The bill, the EOB and your provider list agree on whether the provider is in network.",
    "C4": "What you paid the provider matches what you owe: no overpayment, underpayment or payment made twice.",
    "settlement": "Every dollar you owe is accounted for: paid, written off by the provider, or still owed.",
    "claim_filed": "A bill with no EOB after the waiting time may mean the provider never filed the claim.",
    "C6": "A balance the provider shows as owed, how long it has been owed, and whether it's a second notice.",
}


class FormError(ValueError):
    pass


class PagesHost(Protocol):
    """What the pages need from the app that mounts them."""

    path_import: bool  # offer import by a path on this computer (Release 0 only)
    cookie_secure: bool  # the household view's cookie is Secure where the sign-in cookie is

    def store(self, request: Request) -> Store:
        """The request's record store. Raises to turn away a visitor who isn't signed in."""
        ...

    def check_form(self, request: Request, form) -> None:
        """Refuse a forged form post (Release 1 checks the CSRF token)."""
        ...

    def settings_saved(self, store: Store) -> None:
        """Called after any Settings change or settings import."""
        ...

    def file_response(self, store: Store, doc: dict) -> Response:
        """Serve the stored file attached to a document record."""
        ...

    def document_files(self, request: Request) -> DocumentFiles:
        """Where attached files go on import."""
        ...

    def save_preview(self, request: Request, preview: dict) -> str:
        """Keep an import preview (JSON-safe dict) until it is confirmed; returns its token. One per household."""
        ...

    def load_preview(self, request: Request, token: str) -> dict | None:
        """Take back this household's preview for the token (it can be used once), or None."""
        ...

    def record_view(self, request: Request, kind: str, record_id: str, action: str = "view") -> None:
        """Note that the request's member looked at a record (Release 1's access log, PRV-10)."""
        ...

    def default_import_path(self) -> str: ...

    def resolve_import_path(self, text: str) -> Path: ...


def files_to_json(files) -> dict | None:
    """Where an import's attached files come from, in a form a preview can be stored as."""
    if files is None:
        return None
    if isinstance(files, Path):
        return {"folder": str(files)}
    if isinstance(files, UploadedSource):
        return {"uploaded": {n: base64.b64encode(d).decode() for n, d in files.files.items()}}
    raise TypeError(type(files))


def files_from_json(spec: dict | None):
    if spec is None:
        return None
    if "folder" in spec:
        return Path(spec["folder"])
    return UploadedSource({n: base64.b64decode(d) for n, d in spec["uploaded"].items()})


def money_text(value: int | None) -> str:
    if not isinstance(value, (int, float)):  # None or a missing field (jinja Undefined)
        return "—"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value) / 100:,.2f}"


def nice_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%b %-d, %Y")
    except ValueError:
        return value


def humanize(value: str | None) -> str:
    return (value or "").replace("_", " ").capitalize()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def parse_money(text: str, field_name: str) -> int:
    try:
        return cents(Decimal(text.replace("$", "").replace(",", "").strip()))
    except InvalidOperation:
        raise FormError(f"{field_name}: {text!r} is not an amount") from None


def lines_of(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def attention_queue(visits: list[VisitResult]) -> list[VisitResult]:
    """UX-04: visits that need the member, the most dollars first (at stake plus still owed), then the oldest."""
    return sorted((v for v in visits if v.status in ATTENTION),
                  key=lambda v: (-(v.at_stake + v.remaining), v.visit["date"], v.id))


def line_rows(match: LineMatch | None) -> list[dict]:
    """TC-UX-02-2: each bill line beside its EOB line, with the difference where they disagree. "asked" is what the
    statement asks you to pay for the line and "owed" what the EOB says you owe for it, when both print it."""
    if not match:
        return []

    def total(lines: list[dict], key: str) -> int | None:
        values = [l.get(key) for l in lines]
        return sum(values) if values and all(isinstance(x, int) for x in values) else None

    rows = []
    for p in match.pairs:
        asked, owed = total(p.bill, "patient_amount"), total(p.eob, "patient_responsibility")
        charge_diff = p.charge - p.billed
        you_diff = asked - owed if asked is not None and owed is not None else 0
        rows.append({"bill": p.bill, "eob": p.eob, "charge": p.charge, "billed": p.billed, "asked": asked,
                     "owed": owed, "charge_diff": charge_diff, "you_diff": you_diff, "notes": p.notes,
                     "disagree": bool(charge_diff or you_diff)})
    for b in match.bill_only:
        rows.append({"bill": [b], "eob": [], "charge": b.get("charge"), "billed": None,
                     "asked": b.get("patient_amount"), "owed": None, "charge_diff": b.get("charge") or 0,
                     "you_diff": 0, "notes": ["Only on the bill"], "disagree": True})
    for e in match.eob_only:
        rows.append({"bill": [], "eob": [e], "charge": None, "billed": e.get("billed"), "asked": None,
                     "owed": e.get("patient_responsibility"), "charge_diff": -(e.get("billed") or 0),
                     "you_diff": 0, "notes": ["Only on the EOB"], "disagree": True})
    return rows


def case_history(v: VisitResult, notes: list[dict], accounts: dict[str, dict]) -> list[dict]:
    """UX-02: one timeline of the visit, newest first, from what its records already hold."""
    events: list[tuple[str, str, str]] = [(v.visit["date"], "Visit", v.visit.get("description") or "")]
    for e in v.claims:
        if e.get("received_date"):
            events.append((e["received_date"], "The insurer received the claim", e.get("claim_number") or ""))
        events.append((e["date"], "Insurance decision (EOB)",
                       f"Claim {e.get('claim_number') or 'without a number'}: you owe "
                       f"{money_text(e.get('patient_responsibility'))} of {money_text(e.get('billed'))} billed"))
    for bill, line in reversed(v.bill_lines):
        balance = f", balance {money_text(line['balance'])}" if line.get("balance") is not None else ""
        events.append((bill["date"], "Provider statement", f"Asks {money_text(line.get('patient_amount'))}{balance}"))
    for r in v.receipts:
        events.append((r["date"], "Receipt", money_text(r.get("total"))))
    for a in v.allocations:
        account = accounts.get(a.payment.get("account_id"), {}).get("name", a.payment.get("account_id") or "")
        what = "Refund" if a.refund else "Payment applied"
        events.append((a.payment["date"], what, f"{money_text(a.amount)}{' from ' + account if account else ''}"
                                                f"{' (more than owed)' if a.surplus else ''}"))
    for kind, choice in (v.visit.get("documents") or {}).items():
        state = {"expected": "you expect one", "not_applicable": "not needed"}.get(choice.get("state"), "")
        events.append((choice.get("since") or "", f"{DOCUMENT_LABELS.get(kind, kind)}: {state}", "Set by you"))
    dispute = v.dispute or {}
    if dispute.get("opened"):
        events.append((dispute["opened"], "You opened a dispute", dispute.get("note") or ""))
    if dispute.get("closed"):
        events.append((dispute["closed"], "Dispute closed", (dispute.get("outcome") or "").capitalize()))
    for f in v.visit.get("closed_findings") or []:
        events.append((f["closed"], f"Finding closed: {CHECK_NAMES.get(f['code'], f['code'])}",
                       f"{money_text(f['amount'])}, {f.get('how', '')}"))
    for n in notes:
        if n.get("visit_id") == v.id:
            how = " · ".join(humanize(n[k]) for k in ("channel", "direction") if n.get(k))
            events.append((n["date"], f"Note{' (' + how + ')' if how else ''}", n["text"]))
    order = sorted(range(len(events)), key=lambda i: (events[i][0], i), reverse=True)
    return [{"date": events[i][0], "what": events[i][1], "detail": events[i][2]} for i in order]


@pass_context
def csrf_input(ctx) -> Markup:
    """The hidden CSRF field for a post form; empty where the host has no CSRF token (Release 0)."""
    token = ctx.get("csrf")
    return Markup(f'<input type="hidden" name="csrf_token" value="{escape(token)}">') if token else Markup("")


def make_templates(directories: list[Path], context: Callable[[Request], dict]) -> Jinja2Templates:
    templates = Jinja2Templates(directory=[*directories, WEB / "templates"], context_processors=[context])
    templates.env.filters.update(money=money_text, nice_date=nice_date, humanize=humanize)
    templates.env.globals.update(STATUS_LABELS=STATUS_LABELS, STATUS_ORDER=STATUS_ORDER, STATUS_HELP=STATUS_HELP,
                                 BUCKETS=BUCKETS, FINDING_KINDS=FINDING_KINDS, csrf_input=csrf_input)
    return templates


def add_pages(app: FastAPI, templates: Jinja2Templates, host: PagesHost) -> Callable:
    """Mount the pages. Returns preview_import(request, store, data, source, files, notes), which shows the import
    preview for records built elsewhere (Release 1 uploads of HSA and claims exports) and confirms them the same way."""

    def report_for(store: Store, year: int | None) -> Report:
        ds = load_dataset(store)
        years = available_years(ds)
        if year is None:
            year = date.today().year if date.today().year in years or not years else years[0]
        return build_report(ds, year, date.today())

    def render(request: Request, name: str, status_code: int = 200, **ctx) -> HTMLResponse:
        return templates.TemplateResponse(request, name, ctx, status_code=status_code)

    async def posted(request: Request) -> tuple[Store, object]:
        """The store and the form of a post, once the host has accepted it."""
        store = host.store(request)
        form = await request.form()
        host.check_form(request, form)
        return store, form

    def notes_for(store: Store, provider_ids) -> list[dict]:
        ids = set(provider_ids)
        notes = [n for n in store.all("provider_note") if n["provider_id"] in ids]
        return sorted(notes, key=lambda n: (n["date"], n["id"]), reverse=True)

    def safe_next(url: str | None, fallback: str = "/providers") -> str:
        return url if url and url.startswith("/") and not url.startswith("//") else fallback

    def note_from_form(store: Store, form, note: dict) -> dict:
        text = (form.get("text") or "").replace("\r\n", "\n").strip()
        if not text:
            raise HTTPException(400, "A note needs some text")
        note.update(provider_id=form.get("provider_id") or note.get("provider_id"),
                    date=form.get("date") or date.today().isoformat(), text=text)
        for key in ("visit_id", "channel", "direction"):
            if form.get(key):
                note[key] = form.get(key)
            else:
                note.pop(key, None)
        errors = importer.record_errors("provider_note", note)
        if errors or not store.get("provider", note["provider_id"]):
            raise HTTPException(400, "; ".join(errors) or "Unknown provider")
        if note.get("visit_id") and not store.get("visit", note["visit_id"]):
            raise HTTPException(400, "Unknown visit")
        return note

    def save_settings(store: Store, kind: str, definition: str, record: dict) -> None:
        errors = importer.record_errors(definition, to_dollars(record))
        if errors:
            raise FormError("; ".join(errors))
        store.upsert(kind, record, edited=True)
        host.settings_saved(store)

    @app.exception_handler(FormError)
    async def form_error(request: Request, exc: FormError):
        return settings_page(request, host.store(request), error=str(exc), status_code=400)

    def view_of(request: Request, store: Store) -> dict | None:
        """The household member the pages show (UX-06), or None for the whole family."""
        member_id = request.cookies.get(VIEW_COOKIE) or ""
        return store.get("member", member_id) if member_id else None

    @app.post("/view")
    async def set_view(request: Request):
        """The household view's switch (UX-06): a member, or the family. Kept for the browser session."""
        store, form = await posted(request)
        member_id = form.get("member") or ""
        response = RedirectResponse(safe_next(form.get("next"), "/"), status_code=303)
        if member_id and store.get("member", member_id):
            response.set_cookie(VIEW_COOKIE, member_id, httponly=True, samesite="lax",
                                secure=host.cookie_secure, path="/")
        else:
            response.delete_cookie(VIEW_COOKIE, path="/")
        return response

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, year: int | None = None):
        """ADR-023 and ADR-041: the summary, then the attention queue, then the year's visits as cards."""
        store = host.store(request)
        report = report_for(store, year)
        view = view_of(request, store)
        visits = visits_for(report.visits, view and view["id"])
        if view:
            mine = household_totals(visits, [view], ATTENTION)[1]
            totals = {**report.totals, "billed": mine.billed, "insurer_paid": mine.insurer_paid, "you_paid": mine.paid,
                      "at_stake": mine.at_issue}
            status_counts = mine.status_counts
            limits = [l for l in report.limits if l.member_id in (None, view["id"])]
        else:
            totals, status_counts, limits = report.totals, report.status_counts, report.limits
        attention = attention_queue(visits)
        cards = sorted(visits, key=lambda v: (v.visit["date"], v.id), reverse=True)
        return render(request, "home.html", report=report, totals=totals, status_counts=status_counts, limits=limits,
                      visits=visits, attention=attention[:HOME_ATTENTION], attention_more=len(attention) - HOME_ATTENTION,
                      cards=cards[:HOME_CARDS], view=view, members=store.all("member"))

    @app.get("/household", response_class=HTMLResponse)
    def household(request: Request, year: int | None = None):
        """UX-06: each member's totals for the plan year and the family's."""
        store = host.store(request)
        report = report_for(store, year)
        members = store.all("member")
        people, family = household_totals(report.visits, members, ATTENTION)
        limits = {p.member_id: [l for l in report.limits if l.member_id == p.member_id] for p in people}
        return render(request, "household.html", report=report, people=people, family=family, limits=limits,
                      family_limits=[l for l in report.limits if l.member_id is None], members=members,
                      view=view_of(request, store), NOBODY=NOBODY)

    @app.get("/visits", response_class=HTMLResponse)
    def visits(request: Request, year: int | None = None, status: str = "", member: str | None = None,
               provider: str = "", category: str = "", flagged: str = "", hsa: str = ""):
        store = host.store(request)
        report = report_for(store, year)
        if member is None:  # no filter chosen: the household view's member, if any (UX-06)
            view = view_of(request, store)
            member = view["id"] if view else ""
        rows = report.visits
        if hsa in HSA_FILTERS:  # matches the home page's HSA totals, so carry-in visits are included
            rows = [v for v in report.ledger_visits if getattr(v, HSA_FILTERS[hsa][0])]
        if status:
            rows = [v for v in rows if v.status == status]
        if flagged:
            rows = [v for v in rows if v.status in ATTENTION or v.hsa_flags]
        if member == "none":  # the Household page's "not assigned" row: no member, or one no longer in Settings
            known = {m["id"] for m in store.all("member")}
            rows = [v for v in rows if v.visit.get("member_id") not in known]
        elif member:
            rows = [v for v in rows if v.visit.get("member_id") == member]
        if provider:
            rows = [v for v in rows if v.group_id == provider]
        if category:
            rows = [v for v in rows if v.visit["category"] == category]
        members = store.all("member")
        return render(request, "visits.html", report=report, rows=rows, members=members, categories=CATEGORIES,
                      filters={"status": status, "member": member, "provider": provider,
                               "category": category, "flagged": flagged, "hsa": hsa if hsa in HSA_FILTERS else ""},
                      hsa_filters=HSA_FILTERS)

    def visit_page(request: Request, store: Store, visit_id: str, error: str = "", status_code: int = 200):
        visit = store.get("visit", visit_id)
        if not visit:
            raise HTTPException(404, "Visit not found")
        host.record_view(request, "visit", visit_id)
        report = report_for(store, int(visit["date"][:4]))
        vr = report.visit(visit_id)
        group = report.group(vr.group_id)
        notes = notes_for(store, (p["id"] for p in group.providers))
        accounts = {a["id"]: a for a in store.all("account")}
        return render(request, "visit.html", status_code=status_code, report=report, v=vr, group=group, error=error,
                      notes=notes, plan=store.get("plan", visit.get("plan_id", "")), accounts=accounts,
                      others=[o for o in group.visits if o.id != visit_id], lines=line_rows(vr.line_match),
                      history=case_history(vr, notes, accounts))

    @app.get("/visits/{visit_id}", response_class=HTMLResponse)
    def visit_detail(request: Request, visit_id: str):
        return visit_page(request, host.store(request), visit_id)

    # ---------- the member's reconciliation decisions (MAT-07, ALC-04, REC-11, MAT-10; ADR-011, ADR-035) ----------

    def visit_or_404(store: Store, visit_id: str) -> dict:
        visit = store.get("visit", visit_id)
        if not visit:
            raise HTTPException(404, "Visit not found")
        return visit

    def save_record(store: Store, kind: str, record: dict) -> None:
        """Validate and save a record the member changed, marked as their edit so imports keep it."""
        definition = record["type"] if kind == "document" else kind
        clean = {k: v for k, v in record.items() if k not in BOOKKEEPING}
        errors = importer.record_errors(definition, to_dollars(clean))
        if errors:
            raise edits.EditError("; ".join(errors))
        store.upsert(kind, record, edited=True)

    def back_to(visit_id: str, anchor: str = "") -> RedirectResponse:
        return RedirectResponse(f"/visits/{visit_id}" + (f"#{anchor}" if anchor else ""), status_code=303)

    async def decide(request: Request, visit_id: str, change: Callable[[Store, dict, object], str]):
        """Run one decision on a visit; an EditError shows on the visit page instead of saving anything."""
        store, form = await posted(request)
        visit = visit_or_404(store, visit_id)
        try:
            target = change(store, visit, form)
        except edits.EditError as e:
            return visit_page(request, store, visit_id, error=str(e), status_code=400)
        return back_to(target or visit_id)

    def new_visit_like(store: Store, visit: dict, when: str | None = None) -> dict:
        when = when or visit["date"]
        base = f"v-{when}-{visit['provider_id'].removeprefix('prov-')}"
        vid, n = base, 2
        while store.get("visit", vid):
            vid, n = f"{base}-{n}", n + 1
        new = {k: visit[k] for k in ("provider_id", "member_id", "plan_id", "category", "payment_path") if k in visit}
        return {"id": vid, "date": when, **new, "description": "Split off from another visit"}

    def document_on(store: Store, visit_id: str, doc_id: str) -> dict:
        doc = store.get("document", doc_id)
        if not doc or doc_id not in edits.references(visit_id, [doc]):
            raise HTTPException(404, "Document not found on this visit")
        return doc

    @app.post("/visits/{visit_id}/documents/{doc_id}/confirm")
    async def confirm_match(request: Request, visit_id: str, doc_id: str):
        def change(store, visit, form):
            save_record(store, "document", edits.confirm_match(document_on(store, visit_id, doc_id), visit_id))
            return ""
        return await decide(request, visit_id, change)

    @app.post("/visits/{visit_id}/documents/{doc_id}/move")
    async def move_document(request: Request, visit_id: str, doc_id: str):
        """Not this visit: move a document, or some of a statement's lines, to another visit or a new one."""
        def change(store, visit, form):
            doc = document_on(store, visit_id, doc_id)
            target = form.get("target") or ""
            items = [int(i) for i in form.getlist("items") if str(i).isdigit()] or None
            if target == "new":
                lines = [l for l in doc.get("lines", []) if l.get("visit_id") == visit_id]
                chosen = [it for l in lines for n, it in enumerate(l.get("items") or []) if items is None or n in items]
                dates = sorted(d for d in (it.get("service_date") for it in chosen) if d)
                new = new_visit_like(store, visit, dates[0] if dates else None)
                save_record(store, "visit", new)
                target = new["id"]
            elif not store.get("visit", target):
                raise edits.EditError("Choose the visit it belongs to.")
            save_record(store, "document", edits.move_document(doc, visit_id, target,
                                                               reject=form.get("reject") == "1", items=items))
            return target
        return await decide(request, visit_id, change)

    @app.post("/visits/{visit_id}/merge")
    async def merge_visit(request: Request, visit_id: str):
        """Merge another visit into this one: its documents, payment splits and notes move here."""
        def change(store, visit, form):
            other = form.get("other") or ""
            if not store.get("visit", other):
                raise edits.EditError("Choose the visit to merge into this one.")
            for kind, record in edits.merge_visits(visit_id, other, store.all("document"), store.all("provider_note")):
                if kind == "document":
                    save_record(store, kind, record)
                else:
                    store.upsert(kind, record, edited=True)
            store.delete("visit", other, edited=True)
            return ""
        return await decide(request, visit_id, change)

    @app.post("/visits/{visit_id}/delete")
    async def delete_visit(request: Request, visit_id: str):
        """TC-MAT-01-4: a visit that still has documents, payments or notes can't be deleted (no orphans)."""
        store, form = await posted(request)
        visit_or_404(store, visit_id)
        refs = edits.references(visit_id, store.all("document"), store.all("provider_note"))
        if refs:
            return visit_page(request, store, visit_id, status_code=400, error=(
                f"This visit still has {len(refs)} document{'s' if len(refs) != 1 else ''} or note"
                f"{'s' if len(refs) != 1 else ''} ({', '.join(refs)}). Move them to another visit, or merge the "
                f"visits, before deleting it."))
        store.delete("visit", visit_id, edited=True)
        return RedirectResponse("/visits", status_code=303)

    @app.post("/visits/{visit_id}/dispute")
    async def dispute(request: Request, visit_id: str):
        def change(store, visit, form):
            today = date.today().isoformat()
            if form.get("action") == "open":
                changed = edits.open_dispute(visit, today, (form.get("note") or "").strip())
            else:
                report = report_for(store, int(visit["date"][:4]))
                accepted = [(c.code, c.amount) for c in report.visit(visit_id).findings
                            if form.get("outcome") == "accepted"]
                changed = edits.close_dispute(visit, today, accepted, (form.get("outcome") or "").replace("_", " "))
            save_record(store, "visit", changed)
            return ""
        return await decide(request, visit_id, change)

    @app.post("/visits/{visit_id}/findings")
    async def finding(request: Request, visit_id: str):
        def change(store, visit, form):
            try:
                code, amount = form.get("code") or "", int(form.get("amount") or 0)
            except ValueError:
                raise edits.EditError("Unknown finding.") from None
            if form.get("action") == "reopen":
                changed = edits.reopen_finding(visit, code, amount)
            else:
                changed = edits.close_finding(visit, code, amount, date.today().isoformat())
            save_record(store, "visit", changed)
            return ""
        return await decide(request, visit_id, change)

    @app.post("/visits/{visit_id}/expected")
    async def expected(request: Request, visit_id: str):
        def change(store, visit, form):
            state = form.get("state") or None
            save_record(store, "visit", edits.set_expectation(visit, form.get("kind") or "",
                                                              None if state == "default" else state,
                                                              date.today().isoformat()))
            return ""
        return await decide(request, visit_id, change)

    @app.post("/visits/{visit_id}/payment-path")
    async def payment_path(request: Request, visit_id: str):
        def change(store, visit, form):
            path = form.get("path")
            changed = {k: v for k, v in visit.items() if k != "payment_path"}
            if path in ("insurance", "self_pay"):
                changed["payment_path"] = path
            save_record(store, "visit", changed)
            return ""
        return await decide(request, visit_id, change)

    @app.post("/payments/{payment_id}/split")
    async def split_payment(request: Request, payment_id: str):
        """ALC-04: the member's split of a payment across visits; "reset" goes back to the statement or oldest first."""
        store, form = await posted(request)
        payment = store.get("document", payment_id)
        if not payment or payment["type"] != "payment" or payment.get("kind") == "refund":
            raise HTTPException(404, "Payment not found")
        year = int(payment["date"][:4])
        group = next((g for g in report_for(store, year).groups if payment in g.payments), None)
        group_id = group.id if group else ""
        group_visits = {v.id for v in group.visits} if group else set()
        try:
            if form.get("action") == "reset":
                changed = edits.clear_split(payment)
            else:
                splits = {}
                for key in form.keys():
                    if key.startswith("split-") and (form.get(key) or "").strip():
                        vid = key.removeprefix("split-")
                        if vid not in group_visits:
                            raise edits.EditError("A payment can only be split across this provider's visits.")
                        splits[vid] = parse_money(form.get(key), "Amount")
                changed = edits.set_split(payment, splits)
            save_record(store, "document", changed)
        except (edits.EditError, FormError) as e:
            return ledger_page(request, store, group_id, year, {payment_id: str(e)}, status_code=400)
        return RedirectResponse(f"/providers/{group_id}?year={year}#pay-{payment_id}", status_code=303)

    @app.get("/providers", response_class=HTMLResponse)
    def providers(request: Request, year: int | None = None, flag: str = ""):
        store = host.store(request)
        counts = {}
        for n in store.all("provider_note"):
            counts[n["provider_id"]] = counts.get(n["provider_id"], 0) + 1
        report = report_for(store, year)
        groups = [g for g in report.groups if flag in g.flags] if flag else report.groups
        return render(request, "providers.html", report=report, groups=groups, flag=flag, note_counts=counts)

    def ledger_page(request: Request, store: Store, group_id: str, year: int | None, split_error: dict | None = None,
                    status_code: int = 200):
        report = report_for(store, year)
        group = report.group(group_id)
        if not group:
            raise HTTPException(404, f"No activity for this provider in {report.year}")
        split = {}  # payment id -> {visit id: amount} as allocated now
        for v in group.visits:
            for a in v.allocations:
                if not a.refund:
                    split.setdefault(a.payment["id"], {}).setdefault(v.id, 0)
                    split[a.payment["id"]][v.id] += a.amount
        return render(request, "ledger.html", status_code=status_code, report=report, g=group, split=split,
                      split_error=split_error or {},
                      notes=notes_for(store, (p["id"] for p in group.providers)), today=date.today().isoformat(),
                      channels=NOTE_CHANNELS, directions=NOTE_DIRECTIONS)

    @app.get("/providers/{group_id}", response_class=HTMLResponse)
    def ledger(request: Request, group_id: str, year: int | None = None):
        return ledger_page(request, host.store(request), group_id, year)

    @app.post("/notes")
    async def add_note(request: Request):
        store, form = await posted(request)
        note = note_from_form(store, form, {"id": f"note-{date.today().isoformat()}-{secrets.token_hex(3)}"})
        store.upsert("provider_note", note, edited=True)
        return RedirectResponse(safe_next(form.get("next")) + "#notes", status_code=303)

    @app.post("/notes/{note_id}")
    async def edit_note(request: Request, note_id: str):
        store, form = await posted(request)
        note = store.get("provider_note", note_id)
        if not note:
            raise HTTPException(404, "Note not found")
        store.upsert("provider_note", note_from_form(store, form, note), edited=True)
        return RedirectResponse(safe_next(form.get("next")) + "#notes", status_code=303)

    @app.post("/notes/{note_id}/delete")
    async def delete_note(request: Request, note_id: str):
        store, form = await posted(request)
        if not store.get("provider_note", note_id):
            raise HTTPException(404, "Note not found")
        store.delete("provider_note", note_id, edited=True)
        return RedirectResponse(safe_next(form.get("next")) + "#notes", status_code=303)

    @app.get("/files/{doc_id}")
    def document_file(request: Request, doc_id: str):
        store = host.store(request)
        doc = store.get("document", doc_id)
        if not doc or "stored_file" not in doc:
            raise HTTPException(404, "No file stored for this document")
        host.record_view(request, "document", doc_id, "download")
        return host.file_response(store, doc)

    # ---------- import ----------

    def import_page_for(request: Request, store: Store, status_code: int = 200, done: int = 0, error: str = "",
                        path: str | None = None):
        return render(request, "import.html", status_code=status_code, done=done, error=error,
                      history=store.imports(),
                      default_path=host.default_import_path() if path is None else path)

    @app.get("/import", response_class=HTMLResponse)
    def import_page(request: Request, done: int = 0):
        return import_page_for(request, host.store(request), done=done)

    @app.post("/import", response_class=HTMLResponse)
    async def import_preview(request: Request):
        store, form = await posted(request)
        upload = form.get("file")
        path_text = (form.get("path") or "").strip() if host.path_import else ""
        attachments = [a for a in form.getlist("attachments") if getattr(a, "filename", "")]
        files: Path | FileSource | None
        try:
            if upload is not None and getattr(upload, "filename", ""):
                data = json.loads(await upload.read())
                source = upload.filename
                files = UploadedSource({a.filename: await a.read() for a in attachments})
                if not attachments and host.path_import:
                    files = None  # Release 0: point at import by path instead
            elif path_text:
                path = host.resolve_import_path(path_text)
                data = json.loads(path.read_text())
                source, files = str(path), path.parent
            else:
                raise ValueError("Choose a file" + (" or enter a path." if host.path_import else "."))
            if not isinstance(data, dict):
                raise ValueError("An ingest file is a JSON object.")
        except (OSError, ValueError) as exc:
            return import_page_for(request, store, status_code=400, error=str(exc), path=path_text)
        return preview_import(request, store, data, source, files)

    def preview_import(request: Request, store: Store, data: dict, source: str, files, notes=(),
                       status_code: int = 200) -> HTMLResponse:
        plan = importer.prepare(data, store, source, files)
        plan.warnings.extend(notes)
        token = host.save_preview(request, {"source": source, "data": data, "files": files_to_json(files)})
        return render(request, "import_preview.html", status_code=status_code, plan=plan, token=token)

    @app.post("/import/confirm")
    async def import_confirm(request: Request):
        store, form = await posted(request)
        preview = host.load_preview(request, form.get("token") or "")
        if preview is None:
            return RedirectResponse("/import", status_code=303)
        # The plan is made again from what was checked; commit re-checks member edits made since the preview.
        plan = importer.prepare(preview["data"], store, preview["source"], files_from_json(preview["files"]))
        if not plan.ok:
            return RedirectResponse("/import", status_code=303)
        importer.commit(plan, store, host.document_files(request), replace_edits=form.get("replace_edits") == "1")
        if any(s in plan.data for s in ("plans", "accounts", "members", "providers", "provider_relationships")):
            host.settings_saved(store)
        return RedirectResponse("/import?done=1", status_code=303)

    # ---------- settings ----------

    def settings_page(request: Request, store: Store, error: str = "", status_code: int = 200, saved: str = ""):
        plans = sorted(store.all("plan"), key=lambda p: (-p["plan_year"], p.get("coverage_order") != "primary", p.get("plan_name", "")))
        current = [p for p in plans if p.get("coverage_order") == "primary"]
        return render(request, "settings.html", status_code=status_code, error=error, saved=saved,
                      plans=plans, primary=current[0] if current else None,
                      members=store.all("member"), accounts=store.all("account"),
                      providers=sorted(store.all("provider"), key=lambda p: p["name"].lower()),
                      relationships=store.all("provider_relationship"),
                      provider_names={p["id"]: p["name"] for p in store.all("provider")},
                      member_names={m["id"]: m["name"] for m in store.all("member")},
                      waiting_days=waiting_days(store),
                      opts={"account_types": ACCOUNT_TYPES, "provider_kinds": PROVIDER_KINDS,
                            "network_statuses": NETWORK_STATUSES, "relationships": RELATIONSHIPS,
                            "limit_types": LIMIT_TYPES, "limit_networks": LIMIT_NETWORKS})

    @app.get("/settings", response_class=HTMLResponse)
    def settings(request: Request, saved: str = ""):
        return settings_page(request, host.store(request), saved=saved)

    @app.get("/settings/export")
    def settings_export(request: Request):
        """The settings file tools/build_ingest.py reads (plans, members, accounts, providers, aliases)."""
        doc = settings_document(host.store(request))
        return JSONResponse(doc, headers={"Content-Disposition": 'attachment; filename="settings.json"'})

    def back(section: str) -> RedirectResponse:
        return RedirectResponse(f"/settings?saved={section}#{section}", status_code=303)

    def plan_or_404(store: Store, plan_id: str) -> dict:
        plan = store.get("plan", plan_id)
        if not plan:
            raise HTTPException(404, "Plan not found")
        return plan

    @app.post("/settings/plans")
    async def add_plan(request: Request):
        store, form = await posted(request)
        year = int(form.get("plan_year") or date.today().year)
        name = (form.get("plan_name") or "Medical").strip()
        plan_id = f"plan-{year}-{slug(name)}"
        if store.get("plan", plan_id):
            raise FormError(f"A plan with id {plan_id} already exists")
        save_settings(store, "plan", "plan", {"id": plan_id, "plan_year": year,
                                              "insurer": (form.get("insurer") or "TBD").strip(),
                                              "plan_name": name, "limits": []})
        return back("plans")

    @app.post("/settings/plans/{plan_id}")
    async def edit_plan(request: Request, plan_id: str):
        store, form = await posted(request)
        plan = plan_or_404(store, plan_id)
        plan["insurer"] = form.get("insurer", "").strip() or plan["insurer"]
        plan["plan_name"] = form.get("plan_name", "").strip()
        plan["plan_year"] = int(form.get("plan_year") or plan["plan_year"])
        for key in ("coverage_order", "coverage_start", "coverage_end"):
            value = (form.get(key) or "").strip()
            if value:
                plan[key] = value
            else:
                plan.pop(key, None)
        plan["hsa_eligible_plan"] = form.get("hsa_eligible_plan") == "on"
        plan["member_ids"] = form.getlist("member_ids")
        rate = (form.get("coinsurance_pct") or "").strip()
        plan["coinsurance_rate"] = float(Decimal(rate) / 100) if rate else None
        copays = {}
        for line in lines_of(form.get("copays", "")):
            if ":" not in line:
                raise FormError(f"Copay line {line!r} should look like 'specialist: 60'")
            k, v = line.split(":", 1)
            copays[slug(k).replace("-", "_")] = parse_money(v, f"Copay {k.strip()}")
        if copays:
            plan["copays"] = copays
        else:
            plan.pop("copays", None)
        save_settings(store, "plan", "plan", plan)
        return back("plans")

    @app.post("/settings/plans/{plan_id}/limits")
    async def add_limit(request: Request, plan_id: str):
        store, form = await posted(request)
        plan = plan_or_404(store, plan_id)
        limit = {"type": form.get("type"), "network": form.get("network"), "level": form.get("level"),
                 "amount": parse_money(form.get("amount", ""), "Limit amount")}
        if form.get("level") == "individual" and form.get("member_id"):
            limit["member_id"] = form.get("member_id")
        plan.setdefault("limits", []).append(limit)
        save_settings(store, "plan", "plan", plan)
        return back("plans")

    @app.post("/settings/plans/{plan_id}/limits/{index}/delete")
    async def delete_limit(request: Request, plan_id: str, index: int):
        store, _ = await posted(request)
        plan = plan_or_404(store, plan_id)
        if 0 <= index < len(plan.get("limits", [])):
            plan["limits"].pop(index)
            save_settings(store, "plan", "plan", plan)
        return back("plans")

    @app.post("/settings/reconciliation")
    async def save_reconciliation(request: Request):
        """REC-11: how long to wait for an EOB or another document before it counts as missing."""
        store, form = await posted(request)
        try:
            days = int(form.get("waiting_days") or 0)
        except ValueError:
            days = 0
        if not 1 <= days <= 365:
            raise FormError("The waiting time is a number of days from 1 to 365")
        store.upsert(PREFERENCE, {"id": RECONCILIATION, "waiting_days": days}, edited=True)
        return back("reconciliation")

    @app.post("/settings/members")
    async def save_member(request: Request):
        store, form = await posted(request)
        name = (form.get("name") or "").strip()
        if not name:
            raise FormError("Member name is required")
        member_id = form.get("id") or f"mbr-{slug(name)}"
        member = store.get("member", member_id) or {"id": member_id}
        member.update(name=name, relationship=form.get("relationship") or "other",
                      aliases=lines_of(form.get("aliases", "")) or [name])
        save_settings(store, "member", "member", member)
        return back("members")

    @app.post("/settings/accounts")
    async def save_account(request: Request):
        store, form = await posted(request)
        name = (form.get("name") or "").strip()
        if not name:
            raise FormError("Account name is required")
        account_id = form.get("id") or f"acct-{slug(name)}"
        account = store.get("account", account_id) or {"id": account_id}
        account.update(name=name, type=form.get("type") or "other")
        save_settings(store, "account", "account", account)
        return back("accounts")

    @app.post("/settings/providers/{provider_id}")
    async def save_provider(request: Request, provider_id: str):
        store, form = await posted(request)
        provider = store.get("provider", provider_id)
        if not provider:
            raise HTTPException(404, "Provider not found")
        provider.update(name=(form.get("name") or provider["name"]).strip(), kind=form.get("kind") or "other",
                        network_status=form.get("network_status") or "unknown",
                        aliases=lines_of(form.get("aliases", "")))
        members = form.getlist("member_ids")
        if members:
            provider["member_ids"] = members
        else:
            provider.pop("member_ids", None)
        save_settings(store, "provider", "provider", provider)
        return back("providers")

    @app.post("/settings/relationships/{rel_id}")
    async def save_relationship(request: Request, rel_id: str):
        store, form = await posted(request)
        rel = store.get("provider_relationship", rel_id)
        if not rel:
            raise HTTPException(404, "Relationship not found")
        rel["status"] = form.get("status") or rel["status"]
        notes = (form.get("notes") or "").strip()
        if notes:
            rel["notes"] = notes
        save_settings(store, "provider_relationship", "provider_relationship", rel)
        return back("relationships")

    @app.get("/help", response_class=HTMLResponse)
    def help_page(request: Request):
        host.store(request)
        return render(request, "help.html", CHECK_NAMES=CHECK_NAMES, CHECK_HELP=CHECK_HELP, STATUS_HELP=STATUS_HELP)

    return preview_import
