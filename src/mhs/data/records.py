"""Records adapter: one household's records in Postgres JSONB (ADR-027).

Every query runs with the household set for row-level security and also filters by it, so a missing filter
in one place still can't return another household's rows (PRV-11).
"""

from psycopg.types.json import Jsonb

from mhs.data.db import Database


class HouseholdRecords:
    def __init__(self, db: Database, household_id: str):
        self.db = db
        self.household_id = str(household_id)

    def get(self, kind: str, record_id: str) -> dict | None:
        with self.db.tx(self.household_id) as c:
            row = c.execute(
                "SELECT data FROM app.records WHERE household_id = %s AND kind = %s AND id = %s",
                (self.household_id, kind, record_id),
            ).fetchone()
        return row["data"] if row else None

    def all(self, kind: str) -> list[dict]:
        with self.db.tx(self.household_id) as c:
            rows = c.execute(
                "SELECT data FROM app.records WHERE household_id = %s AND kind = %s ORDER BY id",
                (self.household_id, kind),
            ).fetchall()
        return [r["data"] for r in rows]

    def count(self, kind: str) -> int:
        with self.db.tx(self.household_id) as c:
            row = c.execute(
                "SELECT count(*) AS n FROM app.records WHERE household_id = %s AND kind = %s",
                (self.household_id, kind),
            ).fetchone()
        return row["n"]

    def put(self, kind: str, record: dict) -> None:
        with self.db.tx(self.household_id) as c:
            c.execute(
                "INSERT INTO app.records (household_id, kind, id, data) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (household_id, kind, id) DO UPDATE SET data = excluded.data, updated_at = now()",
                (self.household_id, kind, record["id"], Jsonb(record)),
            )

    def delete(self, kind: str, record_id: str) -> bool:
        with self.db.tx(self.household_id) as c:
            cur = c.execute(
                "DELETE FROM app.records WHERE household_id = %s AND kind = %s AND id = %s",
                (self.household_id, kind, record_id),
            )
        return cur.rowcount > 0
