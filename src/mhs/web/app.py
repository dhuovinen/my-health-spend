"""Release 0 app: the shared pages (web/pages.py) over the SQLite store in the data folder.

Single owner on their own laptop, bound to 127.0.0.1, no sign-in. Settings changes are written to
data/settings.json so the converter picks them up.
"""

import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mhs.config import ROOT, Config, load_config
from mhs.data.importer import FolderFiles
from mhs.data.settings_file import export_settings
from mhs.data.store import Store
from mhs.web.pages import WEB, add_pages, make_templates


class LocalHost:
    """PagesHost for Release 0."""

    path_import = True
    cookie_secure = False  # loopback http

    def __init__(self, config: Config):
        self.config = config
        self._store = Store(config.db_path)
        self._previews: dict[str, dict] = {}

    def store(self, request: Request) -> Store:
        return self._store

    def check_form(self, request: Request, form) -> None:
        pass  # loopback only, one owner

    def settings_saved(self, store: Store) -> None:
        export_settings(store, self.config.settings_file)

    def file_response(self, store: Store, doc: dict):
        path = self.config.documents_dir / doc["stored_file"]
        return FileResponse(path, filename=doc.get("file", path.name).split("/")[-1],
                            content_disposition_type="inline")

    def document_files(self, request: Request) -> FolderFiles:
        return FolderFiles(self.config.documents_dir)

    def save_preview(self, request: Request, preview: dict) -> str:
        token = secrets.token_urlsafe(16)
        self._previews = {token: preview}  # one owner, one preview at a time
        return token

    def load_preview(self, request: Request, token: str) -> dict | None:
        return self._previews.pop(token, None)

    def record_view(self, request: Request, kind: str, record_id: str, action: str = "view") -> None:
        pass  # one owner on their own laptop: no access log

    def default_import_path(self) -> str:
        candidates = sorted(self.config.data_dir.glob("ingest-*.json"))
        return str(candidates[-1]) if candidates else ""

    def resolve_import_path(self, text: str) -> Path:
        path = Path(text).expanduser()
        return path if path.is_absolute() else ROOT / path


def create_app(config: Config | None = None) -> FastAPI:
    config = config or load_config()
    app = FastAPI(title="My Health Spend", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")
    templates = make_templates([], lambda request: {"show_nav": True, "path_import": True})

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(WEB / "static" / "favicon.svg", media_type="image/svg+xml")

    add_pages(app, templates, LocalHost(config))
    return app
