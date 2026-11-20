"""Connect an insurer (ING-09, ADR-054): one pull of the member's EOBs through the payer's Patient Access API.

The session cookie is SameSite=Strict, so it isn't sent when the payer redirects back: like linking a social account
(ADR-048), the member is recorded against the flow's state when the pull starts. The callback pulls, maps and seals
the result as an import preview, and shows a link; following it (a same-site navigation, so the session is sent)
opens the ordinary import preview, where the member confirms. Payer tokens are used once and never stored or logged.
"""

import secrets
import time
from collections.abc import Callable

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from mhs.data.db import Database
from mhs.data.household_store import HouseholdStore
from mhs.ingest import fhir
from mhs.stack import AppConfig
from mhs.web.household import privacy
from mhs.web.household.auth import Accounts

FLOW_COOKIE = "mhs_fhir"
FLOW_PATH = "/connect"
FLOW_MINUTES = 10

# Tests replace these to talk to a fake payer.
TRANSPORT: httpx.BaseTransport | None = None
SLEEP: Callable[[float], None] = time.sleep


def add_insurer_connection(app: FastAPI, *, config: AppConfig, accounts: Accounts, db: Database, page: Callable,
                           member: Callable, host, preview_import: Callable, consented: Callable) -> None:

    def payer_of(name: str) -> fhir.Payer:
        found = next((p for p in config.fhir_payers if p.name == name), None)
        if found is None:
            raise HTTPException(404)
        return found

    def redirect_uri(payer: fhir.Payer) -> str:
        return f"{config.public_url}{FLOW_PATH}/{payer.name}/callback"

    @app.get(FLOW_PATH, response_class=HTMLResponse)
    def connect_page(request: Request):
        session = member(request)
        store = HouseholdStore(db, session.household_id)
        return page(request, "connect.html", payers=config.fhir_payers, members=store.all("member"),
                    allowed=consented(session))

    @app.get(FLOW_PATH + "/{name}")
    def start(request: Request, name: str, who: str = ""):
        """A plain link, not a form: form-action 'self' can block a submission that redirects to the payer."""
        session = member(request)
        if not consented(session):
            return RedirectResponse("/consent", status_code=303)
        payer = payer_of(name)
        store = HouseholdStore(db, session.household_id)
        if who and not store.get("member", who):
            raise HTTPException(404)
        flow = fhir.Flow.new(payer.name, who or "-")
        accounts.start_payer_pull(session.member_id, flow.state, FLOW_MINUTES)
        response = RedirectResponse(fhir.authorization_url(payer, flow, redirect_uri(payer)), status_code=303)
        response.set_cookie(FLOW_COOKIE, flow.to_cookie(), max_age=FLOW_MINUTES * 60, httponly=True, samesite="lax",
                            secure=config.cookie_secure, path=FLOW_PATH)
        return response

    @app.get(FLOW_PATH + "/{name}/callback", response_class=HTMLResponse)
    def callback(request: Request, name: str, code: str = "", state: str = "", error: str = ""):
        payer = payer_of(name)
        flow = fhir.Flow.from_cookie(request.cookies.get(FLOW_COOKIE))

        def finish(response: Response) -> Response:
            response.delete_cookie(FLOW_COOKIE, path=FLOW_PATH)
            return response

        def failed(message: str, status: int = 400) -> Response:
            return finish(page(request, "connect_done.html", status, payer=payer, error=message))

        if error or not code or flow is None or flow.payer != payer.name \
                or not secrets.compare_digest(state.encode(), flow.state.encode()):
            return failed("The connection wasn't completed. Nothing was imported; please try again.")
        who = accounts.take_payer_pull(flow.state)
        if who is None:
            return failed("The connection took too long. Nothing was imported; please start again.")
        with httpx.Client(transport=TRANSPORT) as client:
            try:
                grant = fhir.exchange(payer, flow, code, redirect_uri(payer), client)
                eobs = fhir.pull(payer, grant, client, sleep=SLEEP)
            except fhir.FhirError as e:
                privacy.log_event(db, who.household_id, who.id, "payer_pull_failed")
                return failed(f"{e}")
            del grant  # used once, never kept
        store = HouseholdStore(db, who.household_id)
        for_member = flow.for_member if flow.for_member != "-" and store.get("member", flow.for_member) else None
        result = fhir.to_ingest(eobs, payer, for_member, store.all("provider"), store.all("visit"),
                                store.all("document"), store.all("plan"))
        notes = list(result.skipped)
        if result.already:
            notes.append(f"{result.already} claim{'s' if result.already != 1 else ''} already on file, from an upload "
                         "or an earlier connection, were left out.")
        token = host.save_preview_for(who.household_id, {"source": f"{payer.label} (insurer connection)",
                                                         "data": result.ingest, "files": None, "notes": notes})
        privacy.log_event(db, who.household_id, who.id, "payer_pull")
        return finish(page(request, "connect_done.html", payer=payer, result=result, token=token, notes=notes))

    @app.get(FLOW_PATH + "/review/{token}", response_class=HTMLResponse)
    def review(request: Request, token: str):
        session = member(request)
        preview = host.load_preview(request, token)
        if preview is None:
            return RedirectResponse("/import", status_code=303)
        store = HouseholdStore(db, session.household_id, actor=session.member_id)
        return preview_import(request, store, preview["data"], preview["source"], None, preview.get("notes") or ())
