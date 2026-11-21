"""The owner's admin screen (PLT-09, ADR-049): feature toggles for the whole service, and counts.

Only an owner reaches it, and only in a session that entered the authenticator code; anyone else gets 404, as for a
page that doesn't exist. It shows no household's health data: settings, counts and who changed what.
"""

from collections.abc import Callable

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from mhs.data.db import Database
from mhs.stack import AppConfig
from mhs.web.household.auth import Accounts, Session
from mhs.web.household.features import ALLOW_SIGNUP, REQUIRE_CODE, REQUIRE_CONSENT, Features, provider_setting

KNOWN_PROVIDERS = {"google": "Google", "microsoft": "Microsoft", "apple": "Apple"}


def add_admin_screen(app: FastAPI, *, config: AppConfig, accounts: Accounts, features: Features, db: Database,
                     page: Callable, member: Callable, check_csrf: Callable) -> None:
    configured = {p.name: p for p in config.sign_in_providers}

    def owner(request: Request) -> Session:
        session = member(request)
        if not (session.is_owner and session.code_passed):
            raise HTTPException(404)
        return session

    def screen(request: Request, status: int = 200, **ctx) -> HTMLResponse:
        settings = features.all()
        providers = [{"name": name, "label": label, "configured": name in configured,
                      "on": settings.get(provider_setting(name), True)} for name, label in KNOWN_PROVIDERS.items()]
        signup_providers = [p["label"] for p in providers if p["configured"] and p["on"] and configured[p["name"]].signup]
        return page(request, "admin.html", status, require_code=settings[REQUIRE_CODE], providers=providers,
                    require_consent=settings[REQUIRE_CONSENT], allow_signup=settings[ALLOW_SIGNUP],
                    signup_providers=signup_providers,
                    counts=features.counts(), changes=features.changes(), **ctx)

    @app.get("/admin", response_class=HTMLResponse)
    def admin(request: Request):
        owner(request)
        return screen(request)

    @app.post("/admin/require-code", response_class=HTMLResponse)
    def require_code(request: Request, state: str = Form(""), code: str = Form(""), csrf_token: str = Form("")):
        session = owner(request)
        check_csrf(session, csrf_token)
        if state not in ("on", "off"):
            raise HTTPException(400)
        on = state == "on"
        # Turning protection off is the one change that weakens every household, so it takes a fresh code.
        if not on and not accounts.check_totp(session.member_id, code):
            return screen(request, 401, error="That code didn't work, so the code is still required. Use the "
                                              "current code from your authenticator app.")
        features.set(REQUIRE_CODE, on, member_id=session.member_id, household_id=session.household_id)
        return RedirectResponse("/admin", status_code=303)

    @app.post("/admin/require-consent")
    def require_consent(request: Request, state: str = Form(""), csrf_token: str = Form("")):
        """CMP-02 (ADR-055): ask every member for consent before collecting their documents and claims."""
        session = owner(request)
        check_csrf(session, csrf_token)
        if state not in ("on", "off"):
            raise HTTPException(400)
        if state == "off" and features.allow_signup():
            return screen(request, 409, error="Consent can't stop being required while sign-up is open. Close "
                                              "sign-up first.")
        features.set(REQUIRE_CONSENT, state == "on", member_id=session.member_id, household_id=session.household_id)
        return RedirectResponse("/admin", status_code=303)

    @app.post("/admin/allow-signup", response_class=HTMLResponse)
    def allow_signup(request: Request, state: str = Form(""), csrf_token: str = Form("")):
        """PRV-13 (ADR-059): let new people create a household with Google or Microsoft. Only with consent required."""
        session = owner(request)
        check_csrf(session, csrf_token)
        if state not in ("on", "off"):
            raise HTTPException(400)
        if state == "on":
            settings = features.all()
            if not settings[REQUIRE_CONSENT]:
                return screen(request, 409, error="Require consent before collection first: everyone who signs up "
                                                  "must agree before anything is collected from them.")
            if not any(p.signup and settings.get(provider_setting(p.name), True) for p in configured.values()):
                return screen(request, 409, error="Set up and turn on Google or Microsoft sign-in first: sign-up "
                                                  "uses one of them.")
        features.set(ALLOW_SIGNUP, state == "on", member_id=session.member_id, household_id=session.household_id)
        return RedirectResponse("/admin", status_code=303)

    @app.post("/admin/providers/{name}")
    def provider(request: Request, name: str, state: str = Form(""), csrf_token: str = Form("")):
        session = owner(request)
        check_csrf(session, csrf_token)
        if name not in configured or state not in ("on", "off"):
            raise HTTPException(404 if name not in configured else 400)
        features.set(provider_setting(name), state == "on", member_id=session.member_id,
                     household_id=session.household_id)
        return RedirectResponse("/admin", status_code=303)
