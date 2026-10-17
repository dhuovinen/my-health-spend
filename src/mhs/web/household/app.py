"""Application tier (Release 1): sign-in with MFA, household tenancy, the Release 0 pages, encrypted files.

Every data route needs a session that has passed both factors, and reaches records, files and vault entries
only through the session's household. Anything outside it answers 404, the same as something that doesn't
exist (PRV-11). Files are sealed with the household's data key before they reach object storage (PRV-06).
The Release 0 pages (web/pages.py) are mounted over the household's store (ADR-032).
"""

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from markupsafe import Markup
from starlette.exceptions import HTTPException as StarletteHTTPException

from mhs.data.db import Database
from mhs.data.household_store import HouseholdStore
from mhs.data.keys import Keyring, db_keyring, keys_from_env
from mhs.data.objects import ObjectStore, object_store_from_env
from mhs.data.queue import JobQueue
from mhs.data.records import HouseholdRecords
from mhs.ingest.ocr import get_engine
from mhs.ingest.scrub import scrubber_class
from mhs.stack import AppConfig, load_app_config
from mhs.vault.client import VaultClient
from mhs.web.household import privacy, security
from mhs.web.household.auth import AccountError, Accounts, Session
from mhs.web.household.files import EncryptedFiles
from mhs.web.household.intake import Intake, add_intake
from mhs.web.household.qr import qr_svg
from mhs.web.pages import WEB, add_pages, make_templates

HERE = Path(__file__).parent
COOKIE = "mhs_session"
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PREVIEW_MINUTES = 60  # an import preview must be confirmed within an hour
LINK_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,100}$")


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
        session = self.session(request)
        return HouseholdStore(self.db, session.household_id, actor=session.member_id)

    def record_view(self, request: Request, kind: str, record_id: str, action: str = "view") -> None:
        self.store(request).log(action, kind, record_id)

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

    def save_preview(self, request: Request, preview: dict) -> str:
        """Sealed in the database (ADR-036), so any app instance can confirm it; replaces the household's last one."""
        hid = self.session(request).household_id
        token = secrets.token_urlsafe(16)
        sealed = self.keyring.encrypt(hid, json.dumps(preview).encode(), f"preview:{token}")
        with self.db.tx(hid) as c:
            c.execute("DELETE FROM app.import_previews WHERE household_id = %s", (hid,))
            c.execute("INSERT INTO app.import_previews (household_id, token, sealed) VALUES (%s, %s, %s)",
                      (hid, token, sealed))
        return token

    def load_preview(self, request: Request, token: str) -> dict | None:
        hid = self.session(request).household_id
        with self.db.tx(hid) as c:
            row = c.execute(
                "DELETE FROM app.import_previews WHERE household_id = %s AND token = %s "
                "RETURNING sealed, created_at > now() - interval '%s minutes' AS fresh",
                (hid, token, PREVIEW_MINUTES)).fetchone()
        if row is None or not row["fresh"]:
            return None
        return json.loads(self.keyring.decrypt(hid, bytes(row["sealed"]), f"preview:{token}"))

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
    keyring = keyring or db_keyring(db, keys_from_env(config.key_file), "app.household_keys")
    objects = objects or object_store_from_env(config.objects_dir)
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

    # Enrolment links (mhs-admin prints them): the authenticator QR code, shown once. Opening the link only
    # offers a button, so a link preview doesn't use it up; the post shows the code and deletes the link.
    @app.get("/enrol/{token}", response_class=HTMLResponse)
    def enrol_form(request: Request, token: str):
        if not (LINK_PATTERN.match(token) and accounts.enrolment_link_valid(token)):
            return page(request, "enrol.html", 404, gone=True)
        return page(request, "enrol.html", token=token)

    @app.post("/enrol/{token}", response_class=HTMLResponse)
    def enrol(request: Request, token: str):
        found = accounts.redeem_enrolment_link(token) if LINK_PATTERN.match(token) else None
        if found is None:
            return page(request, "enrol.html", 404, gone=True)
        email, totp_secret = found
        return enrolled(request, email, totp_secret, accounts.new_recovery_codes(email))

    def enrolled(request: Request, email: str, totp_secret: str, codes: list[str], status: int = 200):
        """The authenticator QR code and the recovery codes, shown once."""
        return page(request, "enrol.html", status, email=email,
                    qr=Markup(qr_svg(accounts.provisioning_uri(email, totp_secret))),
                    key=" ".join(totp_secret[i:i + 4] for i in range(0, len(totp_secret), 4)), codes=codes)

    # Self-service recovery (TC-PRV-07-3, ADR-037): a recovery code instead of the password and the authenticator,
    # then a new password, a new authenticator and new codes. Household data is untouched.
    @app.get("/recover", response_class=HTMLResponse)
    def recover_form(request: Request):
        return page(request, "recover.html")

    @app.post("/recover", response_class=HTMLResponse)
    def recover(request: Request, email: str = Form(""), code: str = Form("")):
        token = accounts.start_recovery(email, code)
        if token is None:
            return page(request, "recover.html", 401, email=email,
                        error="That email and recovery code don't match, the code was already used, or the account "
                              "is locked for 15 minutes after too many tries.")
        return page(request, "recover.html", token=token)

    @app.post("/recover/{token}", response_class=HTMLResponse)
    def recover_finish(request: Request, token: str, password: str = Form(""), password2: str = Form("")):
        if not LINK_PATTERN.match(token):
            return page(request, "recover.html", 404, gone=True)
        if password != password2:
            return page(request, "recover.html", 400, token=token, error="The two passwords don't match.")
        try:
            done = accounts.finish_recovery(token, password)
        except AccountError as e:
            return page(request, "recover.html", 400, token=token, error=str(e))
        if done is None:
            return page(request, "recover.html", 404, gone=True)
        email, totp_secret, codes = done
        return enrolled(request, email, totp_secret, codes)

    @app.get("/account", response_class=HTMLResponse)
    def account(request: Request):
        session = member(request)
        return page(request, "account.html", left=accounts.recovery_codes_left(session.member_id))

    @app.post("/account/recovery-codes", response_class=HTMLResponse)
    def new_codes(request: Request, code: str = Form(""), csrf_token: str = Form("")):
        """New recovery codes for a signed-in member, after a fresh authenticator code."""
        session = member(request)
        check_csrf(session, csrf_token)
        if not accounts.check_totp(session.member_id, code):
            return page(request, "account.html", 401, left=accounts.recovery_codes_left(session.member_id),
                        error="That code didn't work. Use the current code from your authenticator app.")
        codes = accounts.new_recovery_codes(accounts.email_of(session.member_id))
        return page(request, "account.html", left=len(codes), codes=codes)

    # --- your data: export, and delete the account (PRV-09) ---

    def data_page(request: Request, session: Session, status: int = 200, **ctx) -> HTMLResponse:
        return page(request, "data.html", status, household=accounts.household_name(session.household_id),
                    last=privacy.member_count(db, session.household_id) == 1,
                    access_log=HouseholdStore(db, session.household_id).access_log(), **ctx)

    @app.get("/data", response_class=HTMLResponse)
    def your_data(request: Request):
        return data_page(request, member(request))

    @app.post("/data/export")
    def export(request: Request, password: str = Form(""), csrf_token: str = Form("")):
        session = member(request)
        check_csrf(session, csrf_token)
        if accounts.check_password(privacy.member_email(db, session.member_id), password) is None:
            return data_page(request, session, 401, error="That password didn't work.")
        privacy.log_event(db, session.household_id, session.member_id, "data_exported")
        HouseholdStore(db, session.household_id, actor=session.member_id).log("export", "household", session.household_id)
        data = privacy.export_household(db, keyring, objects, vault, session.household_id,
                                        accounts.household_name(session.household_id) or "")
        name = f"my-health-spend-export-{datetime.now(timezone.utc).date().isoformat()}.zip"
        return Response(data, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/data/delete", response_class=HTMLResponse)
    def delete_account(request: Request, password: str = Form(""), code: str = Form(""), confirm: str = Form(""),
                       csrf_token: str = Form("")):
        session = member(request)
        check_csrf(session, csrf_token)
        if confirm.strip() != "DELETE":
            return data_page(request, session, 400, error="Type DELETE to confirm.")
        if accounts.check_password(privacy.member_email(db, session.member_id), password) is None \
                or not accounts.check_totp(session.member_id, code):
            return data_page(request, session, 401, error="That password or authenticator code didn't work.")
        last = privacy.member_count(db, session.household_id) == 1
        if last:
            reference = privacy.delete_household(db, objects, vault, session.household_id, session.member_id)
        else:
            reference = privacy.delete_member(db, session.household_id, session.member_id)
        request.state.session = None
        response = page(request, "deleted.html", household_deleted=last, reference=reference)
        response.delete_cookie(COOKIE, path="/")
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
