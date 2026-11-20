"""Social sign-in routes (PRV-12, ADR-048, ADR-057): Google, Microsoft or Apple in place of the password, for members
who linked them.

The session cookie is SameSite=Strict, so it isn't sent on a redirect chain that started at the provider. That's why
the callback shows the next page itself instead of redirecting to it, why the flow's cookie is Lax, and why linking
records the member when the flow starts rather than reading the session on the way back. It's also why Apple is asked
for no scope: a scope makes Apple come back with a cross-site POST, which the Lax cookie doesn't survive.
"""

import secrets
from collections.abc import Callable

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from mhs.data.db import Database
from mhs.stack import AppConfig, SignInProvider
from mhs.web.household import oidc, privacy
from mhs.web.household.auth import AccountError, Accounts
from mhs.web.pages import VIEW_COOKIE

FLOW_COOKIE = "mhs_oidc"
FLOW_PATH = "/signin/with"  # only the callback reads it
FLOW_MINUTES = 10

NOT_COMPLETED = "Sign-in was not completed. Please try again."


def add_social_sign_in(app: FastAPI, *, config: AppConfig, accounts: Accounts, db: Database, page: Callable,
                       member: Callable, check_csrf: Callable, set_cookie: Callable, providers_on: Callable,
                       needs_code: Callable, mfa_page: Callable) -> None:

    def provider_of(name: str) -> SignInProvider:
        """A configured provider the owner hasn't turned off (ADR-049); anything else is 404."""
        found = next((p for p in providers_on() if p.name == name), None)
        if found is None:
            raise HTTPException(404)
        return found

    def redirect_uri(provider: SignInProvider) -> str:
        return f"{config.public_url}{FLOW_PATH}/{provider.name}/callback"

    def leave_for(provider: SignInProvider, flow: oidc.Flow) -> Response:
        response = RedirectResponse(oidc.authorization_url(provider, flow, redirect_uri(provider)), status_code=303)
        response.set_cookie(FLOW_COOKIE, flow.to_cookie(), max_age=FLOW_MINUTES * 60, httponly=True, samesite="lax",
                            secure=config.cookie_secure, path=FLOW_PATH)
        return response

    # Plain links, not forms: the policy's form-action 'self' can block a post that redirects to the provider.
    @app.get(FLOW_PATH + "/{name}")
    def start_sign_in(name: str):
        provider = provider_of(name)
        return leave_for(provider, oidc.Flow.new(provider.name))

    @app.get("/account/link/{name}")
    def start_link(request: Request, name: str):
        session = member(request)  # SameSite=Strict: another site can't start this for a signed-in member
        provider = provider_of(name)
        flow = oidc.Flow.new(provider.name)
        accounts.start_identity_link(session.member_id, flow.state, FLOW_MINUTES)
        return leave_for(provider, flow)

    @app.get(FLOW_PATH + "/{name}/callback", response_class=HTMLResponse)
    def callback(request: Request, name: str, code: str = "", state: str = "", error: str = ""):
        provider = provider_of(name)
        flow = oidc.Flow.from_cookie(request.cookies.get(FLOW_COOKIE))

        def finish(response: Response) -> Response:
            response.delete_cookie(FLOW_COOKIE, path=FLOW_PATH)  # single use, however it ended
            return response

        def refused(message: str, status: int) -> Response:
            return finish(page(request, "signin.html", status, error=message))

        if error or not code or flow is None or flow.provider != provider.name \
                or not secrets.compare_digest(state.encode(), flow.state.encode()):
            return refused(NOT_COMPLETED, 400)
        try:
            identity = oidc.complete(provider, flow, code, redirect_uri(provider))
        except oidc.OidcError:
            return refused(NOT_COMPLETED, 400)

        linking = accounts.take_identity_link(flow.state)
        if linking is not None:
            try:
                accounts.link_identity(linking, provider.name, identity.subject, identity.email)
            except AccountError as e:
                return finish(page(request, "identity_linked.html", 409, provider=provider, error=str(e)))
            privacy.log_event(db, None, linking, "identity_linked")
            return finish(page(request, "identity_linked.html", provider=provider))

        found = accounts.member_for_identity(provider.name, identity.subject)
        if found is None:  # unlinked or locked, whatever the email says: the same answer either way (ADR-048)
            privacy.log_event(db, None, None, "social_signin_refused")
            return refused(f"That {provider.label} account can't sign in here. Sign in with your email and "
                           "password, then link it on your Account page. If you've just had too many tries, "
                           "wait 15 minutes.", 401)
        privacy.log_event(db, found.household_id, found.id, "social_signin")
        if needs_code(found):
            token = accounts.start_session(found)
            response = mfa_page(request, accounts.get_session(token))
        else:  # the owner turned the code off: signed in, but a link to Home, since a redirect wouldn't carry the cookie
            privacy.log_event(db, found.household_id, found.id, "signin_without_code")
            token = accounts.start_session(found, without_code=True)
            response = page(request, "signed_in.html", provider=provider)
        set_cookie(response, token)
        response.delete_cookie(VIEW_COOKIE, path="/")  # a new sign-in starts on the family view
        return finish(response)

    @app.post("/account/identities/{name}/unlink")
    def unlink(request: Request, name: str, csrf_token: str = Form("")):
        session = member(request)
        check_csrf(session, csrf_token)
        provider = provider_of(name)
        if accounts.unlink_identity(session.member_id, provider.name):
            privacy.log_event(db, session.household_id, session.member_id, "identity_unlinked")
        return RedirectResponse("/account", status_code=303)
