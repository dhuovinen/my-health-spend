"""Release 0's record-store interface (store.Store) over one household's Postgres records (ADR-032).

The importer, the dataset loader and the shared pages work against either store. Owner-edit marks and the
import log live in household tables with row-level security, like the records themselves.
"""

from datetime import timezone

from psycopg.types.json import Jsonb

from mhs.data.records import HouseholdRecords


class HouseholdStore(HouseholdRecords):
    def ids(self, kind: str) -> set[str]:
        with self.db.tx(self.household_id) as c:
            rows = c.execute(
                "SELECT id FROM app.records WHERE household_id = %s AND kind = %s", (self.household_id, kind)
            )
            return {r["id"] for r in rows}

    def upsert_many(self, items: list[tuple[str, dict]]) -> None:
        with self.db.tx(self.household_id) as c:
            with c.cursor() as cur:
                cur.executemany(
                    "INSERT INTO app.records (household_id, kind, id, data) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (household_id, kind, id) DO UPDATE SET data = excluded.data, updated_at = now()",
                    [(self.household_id, kind, rec["id"], Jsonb(rec)) for kind, rec in items],
                )

    def upsert(self, kind: str, record: dict, edited: bool = False) -> None:
        """Save one record; edited=True marks it as changed by a member in the app."""
        self.upsert_many([(kind, record)])
        if edited:
            self._mark_edited(kind, record["id"])

    def delete(self, kind: str, record_id: str, edited: bool = False) -> bool:
        """Delete one record; edited=True keeps a mark so an import does not bring it back."""
        with self.db.tx(self.household_id) as c:
            cur = c.execute(
                "DELETE FROM app.records WHERE household_id = %s AND kind = %s AND id = %s",
                (self.household_id, kind, record_id),
            )
            if not edited:
                c.execute(
                    "DELETE FROM app.owner_edits WHERE household_id = %s AND kind = %s AND id = %s",
                    (self.household_id, kind, record_id),
                )
        if edited:
            self._mark_edited(kind, record_id)
        return cur.rowcount > 0

    def _mark_edited(self, kind: str, record_id: str) -> None:
        with self.db.tx(self.household_id) as c:
            c.execute(
                "INSERT INTO app.owner_edits (household_id, kind, id) VALUES (%s, %s, %s) "
                "ON CONFLICT (household_id, kind, id) DO UPDATE SET edited_at = now()",
                (self.household_id, kind, record_id),
            )

    def edited_ids(self, kind: str) -> set[str]:
        with self.db.tx(self.household_id) as c:
            rows = c.execute(
                "SELECT id FROM app.owner_edits WHERE household_id = %s AND kind = %s", (self.household_id, kind)
            )
            return {r["id"] for r in rows}

    def clear_edited(self, items: list[tuple[str, str]]) -> None:
        with self.db.tx(self.household_id) as c:
            with c.cursor() as cur:
                cur.executemany(
                    "DELETE FROM app.owner_edits WHERE household_id = %s AND kind = %s AND id = %s",
                    [(self.household_id, kind, rid) for kind, rid in items],
                )

    def log_import(self, source: str, summary: dict) -> None:
        with self.db.tx(self.household_id) as c:
            c.execute(
                "INSERT INTO app.imports (household_id, source, summary) VALUES (%s, %s, %s)",
                (self.household_id, source, Jsonb(summary)),
            )

    def imports(self, limit: int = 20) -> list[dict]:
        with self.db.tx(self.household_id) as c:
            rows = c.execute(
                "SELECT imported_at, source, summary FROM app.imports WHERE household_id = %s "
                "ORDER BY id DESC LIMIT %s",
                (self.household_id, limit),
            ).fetchall()
        return [{"imported_at": r["imported_at"].astimezone(timezone.utc).replace(tzinfo=None).isoformat(
                     timespec="seconds"), "source": r["source"], "summary": r["summary"]} for r in rows]
