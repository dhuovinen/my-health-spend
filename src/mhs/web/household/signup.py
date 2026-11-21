"""Self-service sign-up with Google or Microsoft (PRV-13, ADR-059), and the Terms of Service page.

An unlinked provider account that comes back while the owner has sign-up open gets "Create your account": its verified
email, a name to type and a box to agree to the Terms of Service and the Privacy Policy. Until then, who came back is
held on the server for 15 minutes under a hashed token in a cookie limited to /signup, with a form token as well.
Creating the account makes a household, a member with no password and the link, all or nothing, and goes on to the
code step (while the code is required) or Home. Linking stays by provider and subject, never by email (ADR-048).
"""

import secrets
from collections.abc import Callable

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from mhs.data.db import Database
from mhs.stack import AppConfig, SignInProvider
from mhs.web.household import oidc, privacy
from mhs.web.household.auth import MAX_NAME, SIGNUP_MINUTES, AccountError, Accounts
from mhs.web.household.consent import NOTICE_VERSION
from mhs.web.pages import VIEW_COOKIE

TERMS_VERSION = "2026-11-21"
SIGNUP_COOKIE = "mhs_signup"
SIGNUP_PATH = "/signup"


def add_signup(app: FastAPI, *, config: AppConfig, accounts: Accounts, db: Database, page: Callable,
               set_cookie: Callable, needs_code: Callable, signup_open: Callable[[], bool],
               providers_on: Callable) -> Callable:
    """Adds /signup and /terms. Returns what the provider callback calls for an unlinked account: a response, or None
    when sign-up is closed and the callback should give its usual refusal."""

    def refused(request: Request, message: str, status: int) -> Response:
        privacy.log_event(db, None, None, "signup_refused")
        return page(request, "signin.html", status, error=message)

    def begin(request: Request, provider: SignInProvider, identity: oidc.Identity) -> Response | None:
        if not signup_open():
            return None
        if not provider.signup:
            return refused(request, f"Signing up with {provider.label} isn't available yet. Use Google or Microsoft, "
                                    f"or sign in another way and link {provider.label} on your Account page.", 401)
        if not identity.email_verified:
            return refused(request, f"{provider.label} didn't confirm an email address for this account, so it can't "
                                    "be used to sign up. Try another account.", 401)
        if accounts.email_taken(identity.email):
            return refused(request, f"There's already an account for {identity.email}. Sign in the way you did before, "
                                    f"then link {provider.label} on your Account page.", 409)
        token, form_token = accounts.start_signup(provider.name, identity.subject, identity.email)
        response = form(request, {"provider": provider.name, "email": identity.email, "form_token": form_token},
                        provider)
        response.set_cookie(SIGNUP_COOKIE, token, max_age=SIGNUP_MINUTES * 60, httponly=True, samesite="strict",
                            secure=config.cookie_secure, path=SIGNUP_PATH)
        return response

    def form(request: Request, pending: dict, provider: SignInProvider, status: int = 200, **ctx) -> HTMLResponse:
        return page(request, "signup.html", status, email=pending["email"], provider=provider,
                    form_token=pending["form_token"], **ctx)

    def expired(request: Request, status: int = 400) -> Response:
        response = page(request, "signup.html", status, gone=True)
        response.delete_cookie(SIGNUP_COOKIE, path=SIGNUP_PATH)
        return response

    def signup_provider(name: str) -> SignInProvider | None:
        """The provider still on and still allowing sign-up: turning it off stops pending sign-ups too (SU-23)."""
        return next((p for p in providers_on() if p.name == name and p.signup), None)

    @app.get(SIGNUP_PATH, response_class=HTMLResponse)
    def signup_form(request: Request):
        pending = accounts.pending_signup(request.cookies.get(SIGNUP_COOKIE))
        provider = signup_provider(pending["provider"]) if pending else None
        if pending is None or provider is None or not signup_open():
            return expired(request, 404)
        return form(request, pending, provider)

    @app.post(SIGNUP_PATH, response_class=HTMLResponse)
    def create(request: Request, name: str = Form(""), agree: str = Form(""), form_token: str = Form("")):
        token = request.cookies.get(SIGNUP_COOKIE)
        pending = accounts.pending_signup(token)
        if pending is None or not secrets.compare_digest(form_token.encode(), pending["form_token"].encode()):
            return expired(request)
        provider = signup_provider(pending["provider"])
        if provider is None or not signup_open():
            accounts.end_signup(token)
            return expired(request)
        if agree != "on":
            return form(request, pending, provider, 400, entered=name,
                        error="Tick the box to agree to the Terms of Service and the Privacy Policy.")
        if not 0 < len(" ".join(name.split())) <= MAX_NAME:
            return form(request, pending, provider, 400, entered=name,
                        error=f"Enter your name (up to {MAX_NAME} characters).")
        if not accounts.end_signup(token):  # another post with this token got there first
            return expired(request)
        try:
            member = accounts.sign_up(provider.name, pending["subject"], pending["email"], name, TERMS_VERSION,
                                      NOTICE_VERSION)
        except AccountError as e:
            response = refused(request, f"{e} Sign in the way you did before.", 409)
            response.delete_cookie(SIGNUP_COOKIE, path=SIGNUP_PATH)
            return response
        privacy.log_event(db, member.household_id, member.id, "signup")
        # A same-site post, so the Strict session cookie set here is sent with the redirect that follows.
        code = needs_code(member)
        if not code:
            privacy.log_event(db, member.household_id, member.id, "signin_without_code")
        response = RedirectResponse("/signin/mfa" if code else "/", status_code=303)
        set_cookie(response, accounts.start_session(member, without_code=not code))
        response.delete_cookie(SIGNUP_COOKIE, path=SIGNUP_PATH)
        response.delete_cookie(VIEW_COOKIE, path="/")
        return response

    @app.get("/terms", response_class=HTMLResponse)
    def terms(request: Request):
        """Public, like the privacy notice: read before signing up."""
        return page(request, "terms.html", version=TERMS_VERSION)

    return begin
