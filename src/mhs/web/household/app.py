"""Application tier (Release 1): sign-in with MFA, household tenancy, encrypted originals.

Every data route needs a session that has passed both factors, and reaches records, files and vault entries
only through the session's household. Anything outside it answers 404, the same as something that doesn't
exist (PRV-11). Originals are sealed with the household's data key before they reach object storage (PRV-06).
"""

import hashlib
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from mhs.data.db import Database
from mhs.data.keys import Keyring, LocalKeyFile, db_keyring
from mhs.data.objects import LocalObjectStore, ObjectStore
from mhs.data.queue import JobQueue
from mhs.data.records import HouseholdRecords
from mhs.stack import AppConfig, load_app_config
from mhs.vault.client import VaultClient
from mhs.web.household import security
from mhs.web.household.auth import Accounts, Session

HERE = Path(__file__).parent
STATIC = HERE.parent / "static"
COOKIE = "mhs_session"
MAX_UPLOAD = 20 * 1024 * 1024
UPLOAD_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/heic", "image/webp"}
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class SignInRequired(Exception):
    def __init__(self, mfa_pending: bool = False):
        self.mfa_pending = mfa_pending


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
    templates = Jinja2Templates(directory=HERE / "templates")

    app = FastAPI(title="My Health Spend", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.accounts = accounts
    app.state.vault = vault
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

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
        # One message per status, so errors never echo ids or say whether something exists elsewhere.
        messages = {400: "Bad request", 403: "Forbidden", 404: "Not found", 413: "Too large", 415: "Unsupported type"}
        return JSONResponse({"detail": messages.get(exc.status_code, "Error")}, status_code=exc.status_code)

    def set_cookie(response: Response, token: str) -> None:
        response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=config.cookie_secure, path="/")

    def member(request: Request) -> Session:
        session = accounts.get_session(request.cookies.get(COOKIE))
        if session is None:
            raise SignInRequired()
        if not session.mfa_passed:
            raise SignInRequired(mfa_pending=True)
        return session

    def check_csrf(session: Session, token: str | None) -> None:
        if not token or not secrets.compare_digest(token, session.csrf_token):
            raise HTTPException(403)

    def page(request: Request, name: str, status: int = 200, **context) -> HTMLResponse:
        return templates.TemplateResponse(request, name, context, status_code=status)

    def document_view(session: Session, doc: dict) -> dict:
        name = keyring.decrypt(session.household_id, bytes.fromhex(doc["filename_sealed"]), f"filename:{doc['id']}")
        return {k: doc[k] for k in ("id", "content_type", "size", "sha256", "uploaded_at")} | {"filename": name.decode()}

    def get_document(session: Session, doc_id: str) -> dict:
        doc = HouseholdRecords(db, session.household_id).get("document", doc_id) if ID_PATTERN.match(doc_id) else None
        if doc is None:
            raise HTTPException(404)
        return doc

    # --- public ---

    @app.get("/health")
    def health():
        return {"status": "ok"}

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
        return page(request, "mfa.html", csrf=session.csrf_token)

    @app.post("/signin/mfa")
    def mfa(request: Request, code: str = Form(""), csrf_token: str = Form("")):
        session = accounts.get_session(request.cookies.get(COOKIE))
        if session is None:
            return RedirectResponse("/signin", status_code=303)
        check_csrf(session, csrf_token)
        if not accounts.check_totp(session.member_id, code):
            return page(request, "mfa.html", 401, csrf=session.csrf_token,
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

    # --- household pages ---

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, uploaded: str | None = None):
        session = member(request)
        docs = [document_view(session, d) for d in HouseholdRecords(db, session.household_id).all("document")]
        return page(request, "home.html", session=session, household=accounts.household_name(session.household_id),
                    documents=docs, csrf=session.csrf_token, uploaded=uploaded)

    @app.post("/documents")
    async def upload(request: Request, file: UploadFile = File(...), csrf_token: str = Form("")):
        session = member(request)
        check_csrf(session, csrf_token)
        content_type = (file.content_type or "").split(";")[0].strip().lower()
        if content_type not in UPLOAD_TYPES:
            raise HTTPException(415)
        data = await file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413)
        if not data:
            raise HTTPException(400)
        hid = session.household_id
        doc_id = "doc_" + secrets.token_hex(12)
        object_key = f"households/{hid}/originals/{doc_id}"
        objects.put(object_key, keyring.encrypt(hid, data, f"original:{doc_id}"))
        filename = Path(file.filename or "upload").name[:200]
        HouseholdRecords(db, hid).put("document", {
            "id": doc_id,
            "content_type": content_type,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),  # ING-10: originals are hashed and never modified
            "object_key": object_key,
            "filename_sealed": keyring.encrypt(hid, filename.encode(), f"filename:{doc_id}").hex(),
            "uploaded_at": _now(),
            "uploaded_by": session.member_id,
        })
        return RedirectResponse(f"/?uploaded={doc_id}", status_code=303)

    @app.get("/documents/{doc_id}")
    def download(request: Request, doc_id: str):
        session = member(request)
        doc = get_document(session, doc_id)
        data = keyring.decrypt(session.household_id, objects.get(doc["object_key"]), f"original:{doc_id}")
        if hashlib.sha256(data).hexdigest() != doc["sha256"]:
            raise HTTPException(500)
        filename = re.sub(r"[^A-Za-z0-9._ -]", "_", document_view(session, doc)["filename"])
        return Response(data, media_type=doc["content_type"],
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    # --- JSON API (same session; POSTs carry the X-CSRF-Token header) ---

    @app.get("/api/documents")
    def api_documents(request: Request):
        session = member(request)
        return [document_view(session, d) for d in HouseholdRecords(db, session.household_id).all("document")]

    @app.get("/api/documents/{doc_id}")
    def api_document(request: Request, doc_id: str):
        session = member(request)
        return document_view(session, get_document(session, doc_id))

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

    return app


def app_from_env() -> FastAPI:
    return create_app(load_app_config())


def main() -> None:
    import uvicorn

    config = load_app_config()
    uvicorn.run("mhs.web.household.app:app_from_env", factory=True, host=config.host, port=config.port,
                proxy_headers=False, server_header=False)
