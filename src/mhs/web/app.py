"""FastAPI app: server-rendered pages over the store and the reconciliation engine."""

import json
import re
import secrets
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from mhs.config import ROOT, Config, load_config
from mhs.core.reconcile import STATUS_LABELS, STATUS_ORDER, Report, available_years, build_report
from mhs.data import importer
from mhs.data.money import cents, to_dollars
from mhs.data.repository import load_dataset
from mhs.data.settings_file import export_settings
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


class FormError(ValueError):
    pass


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


def create_app(config: Config | None = None) -> FastAPI:
    config = config or load_config()
    store = Store(config.db_path)
    app = FastAPI(title="My Health Spend", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")
    templates = Jinja2Templates(directory=WEB / "templates")
    templates.env.filters.update(money=money_text, nice_date=nice_date, humanize=humanize)
    templates.env.globals.update(STATUS_LABELS=STATUS_LABELS, STATUS_ORDER=STATUS_ORDER)
    pending: dict[str, importer.ImportPlan] = {}

    def report_for(year: int | None) -> Report:
        ds = load_dataset(store)
        years = available_years(ds)
        if year is None:
            year = date.today().year if date.today().year in years or not years else years[0]
        return build_report(ds, year, date.today())

    def render(request: Request, name: str, status_code: int = 200, **ctx) -> HTMLResponse:
        return templates.TemplateResponse(request, name, ctx, status_code=status_code)

    def notes_for(provider_ids) -> list[dict]:
        ids = set(provider_ids)
        notes = [n for n in store.all("provider_note") if n["provider_id"] in ids]
        return sorted(notes, key=lambda n: (n["date"], n["id"]), reverse=True)

    def safe_next(url: str | None, fallback: str = "/providers") -> str:
        return url if url and url.startswith("/") and not url.startswith("//") else fallback

    def note_from_form(form, note: dict) -> dict:
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

    def save_settings(kind: str, definition: str, record: dict) -> None:
        errors = importer.record_errors(definition, to_dollars(record))
        if errors:
            raise FormError("; ".join(errors))
        store.upsert(kind, record, edited=True)
        export_settings(store, config.settings_file)

    @app.exception_handler(FormError)
    async def form_error(request: Request, exc: FormError):
        return settings_page(request, error=str(exc), status_code=400)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(WEB / "static" / "favicon.svg", media_type="image/svg+xml")

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, year: int | None = None):
        report = report_for(year)
        attention = sorted((v for v in report.visits if v.status in ("discrepancy", "balance_outstanding")),
                           key=lambda v: -(v.at_stake + v.remaining))
        return render(request, "home.html", report=report, attention=attention[:8], totals=report.totals)

    @app.get("/visits", response_class=HTMLResponse)
    def visits(request: Request, year: int | None = None, status: str = "", member: str = "",
               provider: str = "", category: str = "", flagged: str = "", hsa: str = ""):
        report = report_for(year)
        rows = report.visits
        if hsa in HSA_FILTERS:  # matches the home page's HSA totals, so carry-in visits are included
            rows = [v for v in report.ledger_visits if getattr(v, HSA_FILTERS[hsa][0])]
        if status:
            rows = [v for v in rows if v.status == status]
        if flagged:
            rows = [v for v in rows if v.status in ("discrepancy", "balance_outstanding") or v.hsa_flags]
        if member:
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

    @app.get("/visits/{visit_id}", response_class=HTMLResponse)
    def visit_detail(request: Request, visit_id: str):
        visit = store.get("visit", visit_id)
        if not visit:
            raise HTTPException(404, "Visit not found")
        report = report_for(int(visit["date"][:4]))
        vr = report.visit(visit_id)
        group = report.group(vr.group_id)
        return render(request, "visit.html", report=report, v=vr, group=group,
                      notes=notes_for(p["id"] for p in group.providers),
                      plan=store.get("plan", visit.get("plan_id", "")),
                      accounts={a["id"]: a for a in store.all("account")})

    @app.get("/providers", response_class=HTMLResponse)
    def providers(request: Request, year: int | None = None, flag: str = ""):
        counts = {}
        for n in store.all("provider_note"):
            counts[n["provider_id"]] = counts.get(n["provider_id"], 0) + 1
        report = report_for(year)
        groups = [g for g in report.groups if flag in g.flags] if flag else report.groups
        return render(request, "providers.html", report=report, groups=groups, flag=flag, note_counts=counts)

    @app.get("/providers/{group_id}", response_class=HTMLResponse)
    def ledger(request: Request, group_id: str, year: int | None = None):
        report = report_for(year)
        group = report.group(group_id)
        if not group:
            raise HTTPException(404, f"No activity for this provider in {report.year}")
        return render(request, "ledger.html", report=report, g=group,
                      notes=notes_for(p["id"] for p in group.providers), today=date.today().isoformat(),
                      channels=NOTE_CHANNELS, directions=NOTE_DIRECTIONS)

    @app.post("/notes")
    async def add_note(request: Request):
        form = await request.form()
        note = note_from_form(form, {"id": f"note-{date.today().isoformat()}-{secrets.token_hex(3)}"})
        store.upsert("provider_note", note, edited=True)
        return RedirectResponse(safe_next(form.get("next")) + "#notes", status_code=303)

    @app.post("/notes/{note_id}")
    async def edit_note(request: Request, note_id: str):
        form = await request.form()
        note = store.get("provider_note", note_id)
        if not note:
            raise HTTPException(404, "Note not found")
        store.upsert("provider_note", note_from_form(form, note), edited=True)
        return RedirectResponse(safe_next(form.get("next")) + "#notes", status_code=303)

    @app.post("/notes/{note_id}/delete")
    async def delete_note(request: Request, note_id: str):
        form = await request.form()
        store.delete("provider_note", note_id, edited=True)
        return RedirectResponse(safe_next(form.get("next")) + "#notes", status_code=303)

    @app.get("/files/{doc_id}")
    def document_file(doc_id: str):
        doc = store.get("document", doc_id)
        if not doc or "stored_file" not in doc:
            raise HTTPException(404, "No file stored for this document")
        path = config.documents_dir / doc["stored_file"]
        return FileResponse(path, filename=doc.get("file", path.name).split("/")[-1],
                            content_disposition_type="inline")

    # ---------- import ----------

    def default_import_path() -> str:
        candidates = sorted(config.data_dir.glob("ingest-*.json"))
        return str(candidates[-1]) if candidates else ""

    @app.get("/import", response_class=HTMLResponse)
    def import_page(request: Request, done: int = 0):
        return render(request, "import.html", default_path=default_import_path(), history=store.imports(),
                      done=done, error="")

    @app.post("/import", response_class=HTMLResponse)
    async def import_preview(request: Request):
        form = await request.form()
        upload, path_text = form.get("file"), (form.get("path") or "").strip()
        try:
            if upload is not None and getattr(upload, "filename", ""):
                data = json.loads(await upload.read())
                source, base_dir = upload.filename, None
            elif path_text:
                path = Path(path_text).expanduser()
                if not path.is_absolute():
                    path = ROOT / path
                data = json.loads(path.read_text())
                source, base_dir = str(path), path.parent
            else:
                raise ValueError("Choose a file or enter a path.")
        except (OSError, ValueError) as exc:
            return render(request, "import.html", status_code=400, default_path=path_text,
                          history=store.imports(), done=0, error=str(exc))
        plan = importer.prepare(data, store, source, base_dir)
        token = secrets.token_urlsafe(16)
        pending.clear()
        pending[token] = plan
        return render(request, "import_preview.html", plan=plan, token=token)

    @app.post("/import/confirm")
    async def import_confirm(request: Request):
        form = await request.form()
        plan = pending.pop(form.get("token", ""), None)
        if plan is None or not plan.ok:
            return RedirectResponse("/import", status_code=303)
        importer.commit(plan, store, config.documents_dir, replace_edits=form.get("replace_edits") == "1")
        if any(s in plan.data for s in ("plans", "accounts", "members", "providers", "provider_relationships")):
            export_settings(store, config.settings_file)
        return RedirectResponse("/import?done=1", status_code=303)

    # ---------- settings ----------

    def settings_page(request: Request, error: str = "", status_code: int = 200, saved: str = ""):
        plans = sorted(store.all("plan"), key=lambda p: (-p["plan_year"], p.get("coverage_order") != "primary", p.get("plan_name", "")))
        current = [p for p in plans if p.get("coverage_order") == "primary"]
        return render(request, "settings.html", status_code=status_code, error=error, saved=saved,
                      plans=plans, primary=current[0] if current else None,
                      members=store.all("member"), accounts=store.all("account"),
                      providers=sorted(store.all("provider"), key=lambda p: p["name"].lower()),
                      relationships=store.all("provider_relationship"),
                      provider_names={p["id"]: p["name"] for p in store.all("provider")},
                      member_names={m["id"]: m["name"] for m in store.all("member")},
                      opts={"account_types": ACCOUNT_TYPES, "provider_kinds": PROVIDER_KINDS,
                            "network_statuses": NETWORK_STATUSES, "relationships": RELATIONSHIPS,
                            "limit_types": LIMIT_TYPES, "limit_networks": LIMIT_NETWORKS})

    @app.get("/settings", response_class=HTMLResponse)
    def settings(request: Request, saved: str = ""):
        return settings_page(request, saved=saved)

    def back(section: str) -> RedirectResponse:
        return RedirectResponse(f"/settings?saved={section}#{section}", status_code=303)

    def plan_or_404(plan_id: str) -> dict:
        plan = store.get("plan", plan_id)
        if not plan:
            raise HTTPException(404, "Plan not found")
        return plan

    @app.post("/settings/plans")
    async def add_plan(request: Request):
        form = await request.form()
        year = int(form.get("plan_year") or date.today().year)
        name = (form.get("plan_name") or "Medical").strip()
        plan_id = f"plan-{year}-{slug(name)}"
        if store.get("plan", plan_id):
            raise FormError(f"A plan with id {plan_id} already exists")
        save_settings("plan", "plan", {"id": plan_id, "plan_year": year, "insurer": (form.get("insurer") or "TBD").strip(),
                                       "plan_name": name, "limits": []})
        return back("plans")

    @app.post("/settings/plans/{plan_id}")
    async def edit_plan(request: Request, plan_id: str):
        form = await request.form()
        plan = plan_or_404(plan_id)
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
        save_settings("plan", "plan", plan)
        return back("plans")

    @app.post("/settings/plans/{plan_id}/limits")
    async def add_limit(request: Request, plan_id: str):
        form = await request.form()
        plan = plan_or_404(plan_id)
        limit = {"type": form.get("type"), "network": form.get("network"), "level": form.get("level"),
                 "amount": parse_money(form.get("amount", ""), "Limit amount")}
        if form.get("level") == "individual" and form.get("member_id"):
            limit["member_id"] = form.get("member_id")
        plan.setdefault("limits", []).append(limit)
        save_settings("plan", "plan", plan)
        return back("plans")

    @app.post("/settings/plans/{plan_id}/limits/{index}/delete")
    def delete_limit(plan_id: str, index: int):
        plan = plan_or_404(plan_id)
        if 0 <= index < len(plan.get("limits", [])):
            plan["limits"].pop(index)
            save_settings("plan", "plan", plan)
        return back("plans")

    @app.post("/settings/members")
    async def save_member(request: Request):
        form = await request.form()
        name = (form.get("name") or "").strip()
        if not name:
            raise FormError("Member name is required")
        member_id = form.get("id") or f"mbr-{slug(name)}"
        member = store.get("member", member_id) or {"id": member_id}
        member.update(name=name, relationship=form.get("relationship") or "other",
                      aliases=lines_of(form.get("aliases", "")) or [name])
        save_settings("member", "member", member)
        return back("members")

    @app.post("/settings/accounts")
    async def save_account(request: Request):
        form = await request.form()
        name = (form.get("name") or "").strip()
        if not name:
            raise FormError("Account name is required")
        account_id = form.get("id") or f"acct-{slug(name)}"
        account = store.get("account", account_id) or {"id": account_id}
        account.update(name=name, type=form.get("type") or "other")
        save_settings("account", "account", account)
        return back("accounts")

    @app.post("/settings/providers/{provider_id}")
    async def save_provider(request: Request, provider_id: str):
        form = await request.form()
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
        save_settings("provider", "provider", provider)
        return back("providers")

    @app.post("/settings/relationships/{rel_id}")
    async def save_relationship(request: Request, rel_id: str):
        form = await request.form()
        rel = store.get("provider_relationship", rel_id)
        if not rel:
            raise HTTPException(404, "Relationship not found")
        rel["status"] = form.get("status") or rel["status"]
        notes = (form.get("notes") or "").strip()
        if notes:
            rel["notes"] = notes
        save_settings("provider_relationship", "provider_relationship", rel)
        return back("relationships")

    @app.get("/help", response_class=HTMLResponse)
    def help_page(request: Request):
        return render(request, "help.html")

    return app
