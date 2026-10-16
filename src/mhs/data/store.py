"""SQLite record store.

Every record (plan, provider, visit, document, ...) is kept as its JSON object, keyed by kind and id.
The ingest schema is expected to evolve, so the database does not mirror its fields as columns.
Money values inside records are integer cents (see money.py).
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

KINDS = ("plan", "account", "member", "provider", "provider_relationship", "provider_note", "visit", "document")

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    kind TEXT NOT NULL,
    id TEXT NOT NULL,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (kind, id)
);
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    imported_at TEXT NOT NULL,
    source TEXT NOT NULL,
    summary TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS owner_edits (
    kind TEXT NOT NULL,
    id TEXT NOT NULL,
    edited_at TEXT NOT NULL,
    PRIMARY KEY (kind, id)
);
"""


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def all(self, kind: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT data FROM records WHERE kind = ? ORDER BY id", (kind,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def get(self, kind: str, record_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT data FROM records WHERE kind = ? AND id = ?", (kind, record_id)).fetchone()
        return json.loads(row[0]) if row else None

    def ids(self, kind: str) -> set[str]:
        with self._conn() as c:
            return {r[0] for r in c.execute("SELECT id FROM records WHERE kind = ?", (kind,))}

    def upsert_many(self, items: list[tuple[str, dict]]) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as c:
            c.executemany(
                "INSERT INTO records (kind, id, data, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(kind, id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
                [(kind, rec["id"], json.dumps(rec), now) for kind, rec in items],
            )

    def upsert(self, kind: str, record: dict, edited: bool = False) -> None:
        """Save one record; edited=True marks it as changed by the owner in the app."""
        self.upsert_many([(kind, record)])
        if edited:
            self._mark_edited(kind, record["id"])

    def delete(self, kind: str, record_id: str, edited: bool = False) -> None:
        """Delete one record; edited=True keeps a mark so an import does not bring it back."""
        with self._conn() as c:
            c.execute("DELETE FROM records WHERE kind = ? AND id = ?", (kind, record_id))
            if not edited:
                c.execute("DELETE FROM owner_edits WHERE kind = ? AND id = ?", (kind, record_id))
        if edited:
            self._mark_edited(kind, record_id)

    # Records the owner changed or deleted in the app. Imports leave them alone unless the owner says otherwise.

    def _mark_edited(self, kind: str, record_id: str) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO owner_edits (kind, id, edited_at) VALUES (?, ?, ?)",
                      (kind, record_id, datetime.now().isoformat(timespec="seconds")))

    def edited_ids(self, kind: str) -> set[str]:
        with self._conn() as c:
            return {r[0] for r in c.execute("SELECT id FROM owner_edits WHERE kind = ?", (kind,))}

    def clear_edited(self, items: list[tuple[str, str]]) -> None:
        with self._conn() as c:
            c.executemany("DELETE FROM owner_edits WHERE kind = ? AND id = ?", items)

    def log_import(self, source: str, summary: dict) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO imports (imported_at, source, summary) VALUES (?, ?, ?)",
                      (datetime.now().isoformat(timespec="seconds"), source, json.dumps(summary)))

    def imports(self, limit: int = 20) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT imported_at, source, summary FROM imports ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"imported_at": r[0], "source": r[1], "summary": json.loads(r[2])} for r in rows]
