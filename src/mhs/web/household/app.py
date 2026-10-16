"""Application tier (Release 1): sign-in with MFA, household tenancy, the Release 0 pages, encrypted files.

Every data route needs a session that has passed both factors, and reaches records, files and vault entries
only through the session's household. Anything outside it answers 404, the same as something that doesn't
exist (PRV-11). Files are sealed with the household's data key before they reach object storage (PRV-06).
The Release 0 pages (web/pages.py) are mounted over the household's store (ADR-032).
"""

import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from mhs.data.db import Database
from mhs.data.household_store import HouseholdStore
from mhs.data.keys import Keyring, LocalKeyFile, db_keyring
from mhs.data.objects import LocalObjectStore, ObjectStore
from mhs.data.queue import JobQueue
from mhs.data.records import HouseholdRecords
from mhs.ingest.ocr import get_engine
from mhs.ingest.scrub import scrubber_class
from mhs.stack import AppConfig, load_app_config
from mhs.vault.client import VaultClient
from mhs.web.household import security
from mhs.web.household.auth import Accounts, Session
from mhs.web.household.files import EncryptedFiles
from mhs.web.household.intake import Intake, add_intake
from mhs.web.pages import WEB, add_pages, make_templates

HERE = Path(__file__).parent
COOKIE = "mhs_session"
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class SignInRequired(Exception):
    def __init__(self, mfa_pending: bool = False):
        self.mfa_pending = mfa_pending


def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:200] or "file"


class HouseholdHost:
    """PagesHost for Release 1: the signed-in member's household, behind MFA, with CSRF on every post."""

    path_import = False

    def __init__(self, app_state, db: Database, keyring: Keyring, objects: ObjectStore):
        self.state, self.db, self.keyring, self.objects = app_state, db, keyring, objects

    def session(self, request: Request) -> Session:
        return self.state.member(request)

    def store(self, request: Request) -> HouseholdStore:
        return HouseholdStore(self.db, self.session(request).household_id)

    def check_form(self, request: Request, form) -> None:
        self.state.check_csrf(self.session(request), form.get("csrf_token"))

    def settings_saved(self, store) -> None:
        pass  # no settings.json on the server: Settings offers it as a download

    def file_response(self, store: HouseholdStore, doc: dict) -> Response:
        data = EncryptedFiles(self.objects, self.keyring, store.household_id).read(doc)
        name = _safe_filename(doc.get("file", doc["id"]).split("/")[-1])
        return Response(data, media_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    def document_files(self, request: Request) -> EncryptedFiles:
        return EncryptedFiles(self.objects, self.keyring, self.session(request).household_id)

    def scope(self, request: Request) -> str:
        return self.session(request).household_id

    def default_import_path(self) -> str:
        return ""

    def resolve_import_path(self, text: str) -> Path:
        raise ValueError("Import by path isn't available on the server.")


def create_app(
    config: AppConfig,
    *,
    db: Database | None = None,
    keyring: Keyring | None = None,
    objects: ObjectStore | None = None,
    vault: VaultClient | None = None,
) -> FastAPI:
    db = db or Database(config.database_url)
    keyring = keyring or db_keyring(db, LocalKeyFile(config.key_file), "app.household_keys")
    objects = objects or LocalObjectStore(config.objects_dir)
    vault = vault or VaultClient(config.vault_url, config.vault_token)
    accounts = Accounts(db, keyring, config.session_idle_minutes, config.session_max_hours)
    queue = JobQueue(db)

    def context(request: Request) -> dict:
        session = getattr(request.state, "session", None)
        signed_in = session is not None and session.mfa_passed
        return {"session": session if signed_in else None, "csrf": session.csrf_token if session else "",
                "show_nav": signed_in, "path_import": False}

    templates = make_templates([HERE / "templates"], context)

    app = FastAPI(title="My Health Spend", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.accounts = accounts
    app.state.vault = vault
    app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # Cross-site form posts are refused outright (CSRF); the session cookie is also SameSite=Strict.
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin") or request.headers.get("referer")
            if origin:
                o, base = urlsplit(origin), urlsplit(str(request.base_url))
                if (o.scheme, o.netloc) != (base.scheme, base.netloc):
                    response = JSONResponse({"detail": "Forbidden"}, status_code=403)
                    security.apply(response.headers, request.url.path)
                    return response
        response = await call_next(request)
        security.apply(response.headers, request.url.path)
        if config.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.exception_handler(SignInRequired)
    async def sign_in_required(request: Request, exc: SignInRequired):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Sign-in required"}, status_code=401)
        return RedirectResponse("/signin/mfa" if exc.mfa_pending else "/signin", status_code=303)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        return JSONResponse({"detail": "Bad request"}, status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        # 404s never echo ids or say whether something exists in another household; 400s keep the app's own
        # message (form problems), which never contains another household's data.
        messages = {403: "Forbidden", 404: "Not found", 413: "Too large", 415: "Unsupported type"}
        detail = exc.detail if exc.status_code == 400 and isinstance(exc.detail, str) else None
        return JSONResponse({"detail": detail or messages.get(exc.status_code, "Error")}, status_code=exc.status_code)

    def set_cookie(response: Response, token: str) -> None:
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=config.cookie_secure, path="/")

    def member(request: Request) -> Session:
        session = getattr(request.state, "session", None) or accounts.get_session(request.cookies.get(COOKIE))
        request.state.session = session
        if session is None:
            raise SignInRequired()
        if not session.mfa_passed:
            raise SignInRequired(mfa_pending=True)
        return session

    def check_csrf(session: Session, token: str | None) -> None:
        if not token or not secrets.compare_digest(str(token), session.csrf_token):
            raise HTTPException(403)

    app.state.member = member
    app.state.check_csrf = check_csrf

    def page(request: Request, name: str, status: int = 200, **ctx) -> HTMLResponse:
        return templates.TemplateResponse(request, name, ctx, status_code=status)

    # --- public ---

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/signin", response_class=HTMLResponse)
    def signin_form(request: Request):
        return page(request, "signin.html")

    @app.post("/signin")
    def signin(request: Request, email: str = Form(""), password: str = Form("")):
        found = accounts.check_password(email, password)
        if found is None:
            return page(request, "signin.html", 401, error="That email and password don't match, or the account "
                        "is locked for 15 minutes after too many tries.", email=email)
        accounts.end_session(request.cookies.get(COOKIE))
        response = RedirectResponse("/signin/mfa", status_code=303)
        set_cookie(response, accounts.start_session(found))
        return response

    @app.get("/signin/mfa", response_class=HTMLResponse)
    def mfa_form(request: Request):
        session = accounts.get_session(request.cookies.get(COOKIE))
        if session is None:
            return RedirectResponse("/signin", status_code=303)
        if session.mfa_passed:
            return RedirectResponse("/", status_code=303)
        return page(request, "mfa.html", mfa_csrf=session.csrf_token)

    @app.post("/signin/mfa")
    def mfa(request: Request, code: str = Form(""), csrf_token: str = Form("")):
        session = accounts.get_session(request.cookies.get(COOKIE))
        if session is None:
            return RedirectResponse("/signin", status_code=303)
        check_csrf(session, csrf_token)
        if not accounts.check_totp(session.member_id, code):
            return page(request, "mfa.html", 401, mfa_csrf=session.csrf_token,
                        error="That code didn't work. Use the current code from your authenticator app.")
        response = RedirectResponse("/", status_code=303)
        set_cookie(response, accounts.pass_mfa(session))
        return response

    @app.post("/signout")
    def signout(request: Request, csrf_token: str = Form("")):
        session = accounts.get_session(request.cookies.get(COOKIE))
        if session is not None:
            check_csrf(session, csrf_token)
            accounts.end_session(request.cookies.get(COOKIE))
        response = RedirectResponse("/signin", status_code=303)
        response.delete_cookie(COOKIE, path="/")
        return response

    @app.get("/api/visits")
    def api_visits(request: Request):
        session = member(request)
        return HouseholdRecords(db, session.household_id).all("visit")

    @app.get("/api/visits/{visit_id}")
    def api_visit(request: Request, visit_id: str):
        session = member(request)
        visit = HouseholdRecords(db, session.household_id).get("visit", visit_id) if ID_PATTERN.match(visit_id) else None
        if visit is None:
            raise HTTPException(404)
        return visit

    @app.get("/api/session")
    def api_session(request: Request):
        session = member(request)
        return {"display_name": session.display_name, "csrf_token": session.csrf_token}

    @app.post("/api/jobs/ping")
    def api_ping(request: Request):
        session = member(request)
        check_csrf(session, request.headers.get("x-csrf-token"))
        return {"job_id": queue.enqueue(session.household_id, "ping")}

    @app.get("/api/jobs/{job_id}")
    def api_job(request: Request, job_id: int):
        session = member(request)
        status = queue.status(session.household_id, job_id)
        if status is None:
            raise HTTPException(404)
        return {"job_id": job_id, "status": status}

    # --- the Release 0 pages, for the signed-in household ---

    preview_import = add_pages(app, templates, HouseholdHost(app.state, db, keyring, objects))
    add_intake(app, templates, Intake(db, keyring, objects, vault, queue, member, check_csrf, accounts.household_name,
                                      preview_import, get_engine(config.ocr_engine),
                                      scrubber_class(config.scrubber), accounts.ai_extraction))
    return app


def app_from_env() -> FastAPI:
    return create_app(load_app_config())


def main() -> None:
    import uvicorn

    config = load_app_config()
    uvicorn.run("mhs.web.household.app:app_from_env", factory=True, host=config.host, port=config.port,
                proxy_headers=False, server_header=False)
