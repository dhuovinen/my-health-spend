"""Plan ahead: planned visits and the pre-visit estimate (PRE-01, PRE-02, PRE-04 to PRE-07; ADR-053).

Mounted by pages.add_pages, so both apps have it. The engine is core/estimate.py; every block that suggests an
action carries core.tax.DISCLAIMER (CMP-04).
"""

from collections.abc import Callable
from datetime import date

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from mhs.core import costshare, estimate, tax
from mhs.data import importer
from mhs.data.money import to_dollars
from mhs.data.reference import load_tables
from mhs.data.repository import PREFERENCE, load_dataset
from mhs.data.store import Store
from mhs.ingest.resolve import Providers
from mhs.ingest.values import parse_amount

TAX_PREFERENCE = "tax"


class PlanFormError(ValueError):
    pass


def _money(form, name: str, label: str) -> int | None:
    raw = (form.get(name) or "").strip()
    if not raw:
        return None
    value = parse_amount(raw)
    if value is None or value < 0:
        raise PlanFormError(f"{label}: {raw!r} isn't an amount")
    return value


def estimate_for(store: Store, visit: dict, today: date | None = None) -> estimate.Estimate:
    ds = load_dataset(store)
    strategy = tax.strategy_of(store.get(PREFERENCE, TAX_PREFERENCE))
    return estimate.estimate(visit, ds, today or date.today(), load_tables(), strategy)


def add_plan_pages(app: FastAPI, render: Callable, host, posted: Callable) -> None:
    def save(store: Store, visit: dict) -> None:
        """Validated like an import and marked as the member's edit (ADR-011), with the estimate as of now."""
        est = estimate_for(store, visit)
        if est.total is not None:
            visit["estimated_share"] = est.total
        else:
            visit.pop("estimated_share", None)
        errors = importer.record_errors("visit", to_dollars(visit))
        if errors:
            raise PlanFormError("; ".join(errors))
        store.upsert("visit", visit, edited=True)

    def plan_page(request: Request, store: Store, error: str = "", status_code: int = 200) -> HTMLResponse:
        ds = load_dataset(store)
        today = date.today()
        planned = [estimate_for(store, v, today) for v in estimate.planned_visits(ds)]
        return render(request, "plan.html", status_code=status_code, planned=planned, error=error,
                      providers=sorted(ds.providers, key=lambda p: p["name"]), members=ds.members,
                      plans=sorted(ds.plans, key=lambda p: -p["plan_year"]), service_types=costshare.SERVICE_TYPES,
                      today=today.isoformat(), providers_by_id={p["id"]: p for p in ds.providers},
                      members_by_id={m["id"]: m for m in ds.members}, disclaimer=tax.DISCLAIMER)

    def fields_from(form, visit: dict, store: Store) -> dict:
        when = (form.get("date") or "").strip()
        try:
            visit["date"] = date.fromisoformat(when).isoformat()
        except ValueError:
            raise PlanFormError("Enter the date of the visit") from None
        providers = Providers(store.all("provider"))
        choice = form.get("provider_id") or ""
        name = (form.get("provider") or "").strip()
        if choice and choice != "new":
            if choice not in providers.records:
                raise PlanFormError("Choose a provider")
            visit["provider_id"] = choice
        elif name:
            visit["provider_id"] = providers.resolve(name)
            for p in providers.new.values():
                store.upsert("provider", p, edited=True)
        elif not visit.get("provider_id"):
            raise PlanFormError("Choose a provider, or name a new one")
        for key in ("member_id", "plan_id"):
            value = form.get(key) or ""
            if value and not store.get(key.removesuffix("_id"), value):
                raise PlanFormError(f"Choose a {key.removesuffix('_id')}")
            if value:
                visit[key] = value
            else:
                visit.pop(key, None)
        kind = form.get("service_type") or ""
        if kind and kind not in costshare.SERVICE_TYPES:
            raise PlanFormError("Choose a kind of service")
        if kind:
            visit["service_type"] = kind
        else:
            visit.pop("service_type", None)
        description = (form.get("description") or "").strip()
        if description:
            visit["description"] = description
        for key, label in (("expected_allowed", "Expected allowed amount"), ("cash_price", "Cash price"),
                           ("good_faith_estimate", "Good-faith estimate")):
            value = _money(form, key, label)
            if value is None:
                visit.pop(key, None)
            else:
                visit[key] = value
        if form.get("self_pay") == "on":
            visit["payment_path"] = "self_pay"
        else:
            visit.pop("payment_path", None)
        return visit

    async def posted_plan(request: Request, change: Callable[[Store, object], str]):
        store, form = await posted(request)
        try:
            target = change(store, form)
        except PlanFormError as e:
            return plan_page(request, store, error=str(e), status_code=400)
        return RedirectResponse(target, status_code=303)

    def planned_or_404(store: Store, visit_id: str) -> dict:
        visit = store.get("visit", visit_id)
        if not visit or not visit.get("planned"):
            raise HTTPException(404, "Planned visit not found")
        return visit

    @app.get("/plan", response_class=HTMLResponse)
    def plan(request: Request):
        return plan_page(request, host.store(request))

    @app.post("/plan")
    async def add_planned(request: Request):
        def change(store: Store, form) -> str:
            visit = fields_from(form, {"category": "provider_visit", "planned": True}, store)
            base = f"plan-{visit['date']}-{visit['provider_id'].removeprefix('prov-')}"
            vid, n = base, 2
            while store.get("visit", vid):
                vid, n = f"{base}-{n}", n + 1
            visit["id"] = vid
            save(store, visit)
            return f"/plan/{vid}"
        return await posted_plan(request, change)

    @app.get("/plan/{visit_id}", response_class=HTMLResponse)
    def planned_visit(request: Request, visit_id: str, error: str = ""):
        store = host.store(request)
        visit = planned_or_404(store, visit_id)
        host.record_view(request, "visit", visit_id)
        ds = load_dataset(store)
        est = estimate_for(store, visit)
        return render(request, "plan_visit.html", est=est, v=visit, error=error,
                      provider=next((p for p in ds.providers if p["id"] == visit["provider_id"]), {}),
                      member=next((m for m in ds.members if m["id"] == visit.get("member_id")), None),
                      providers=sorted(ds.providers, key=lambda p: p["name"]), members=ds.members,
                      plans=sorted(ds.plans, key=lambda p: -p["plan_year"]), service_types=costshare.SERVICE_TYPES,
                      arrived=estimate.has_documents(visit_id, ds.documents), disclaimer=tax.DISCLAIMER)

    @app.post("/plan/{visit_id}")
    async def edit_planned(request: Request, visit_id: str):
        def change(store: Store, form) -> str:
            visit = planned_or_404(store, visit_id)
            save(store, fields_from(form, visit, store))
            return f"/plan/{visit_id}"
        return await posted_plan(request, change)

    @app.post("/plan/{visit_id}/outcome")
    async def outcome(request: Request, visit_id: str):
        """TC-PRE-01-3: the planned date passed. It happened: an ordinary visit waiting for its documents.
        Cancelled: kept, but off the list."""
        def change(store: Store, form) -> str:
            visit = planned_or_404(store, visit_id)
            answer = form.get("outcome") or ""
            if answer == "happened":
                visit.update(planned=False, planned_outcome="happened")
                save(store, visit)
                return f"/visits/{visit_id}"
            if answer == "cancelled":
                visit["planned_outcome"] = "cancelled"
                save(store, visit)
                return "/plan"
            raise PlanFormError("Say whether the visit happened")
        return await posted_plan(request, change)
