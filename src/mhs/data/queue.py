"""Job queue adapter: Postgres-backed, so Release 1 adds no separate broker (ADR-027).

The application tier enqueues for its own household (row-level security); the worker claims the oldest ready
job across households with FOR UPDATE SKIP LOCKED, so several workers never take the same job.
"""

from dataclasses import dataclass

from psycopg.types.json import Jsonb

from mhs.data.db import Database

RETRY_DELAY_SECONDS = 30


@dataclass(frozen=True)
class Job:
    id: int
    household_id: str
    kind: str
    payload: dict
    attempts: int
    max_attempts: int


class JobQueue:
    def __init__(self, db: Database):
        self.db = db

    def enqueue(self, household_id: str, kind: str, payload: dict | None = None, max_attempts: int = 3) -> int:
        with self.db.tx(household_id) as c:
            row = c.execute(
                "INSERT INTO app.jobs (household_id, kind, payload, max_attempts) VALUES (%s, %s, %s, %s) RETURNING id",
                (str(household_id), kind, Jsonb(payload or {}), max_attempts),
            ).fetchone()
        return row["id"]

    def status(self, household_id: str, job_id: int) -> str | None:
        with self.db.tx(household_id) as c:
            row = c.execute(
                "SELECT status FROM app.jobs WHERE household_id = %s AND id = %s", (str(household_id), job_id)
            ).fetchone()
        return row["status"] if row else None

    def claim(self) -> Job | None:
        with self.db.tx() as c:
            row = c.execute(
                "UPDATE app.jobs SET status = 'running', attempts = attempts + 1, locked_at = now() "
                "WHERE id = (SELECT id FROM app.jobs WHERE status = 'queued' AND run_after <= now() "
                "ORDER BY run_after, id FOR UPDATE SKIP LOCKED LIMIT 1) "
                "RETURNING id, household_id, kind, payload, attempts, max_attempts"
            ).fetchone()
        if not row:
            return None
        return Job(
            id=row["id"],
            household_id=str(row["household_id"]),
            kind=row["kind"],
            payload=row["payload"],
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
        )

    def complete(self, job: Job) -> None:
        with self.db.tx() as c:
            c.execute(
                "UPDATE app.jobs SET status = 'done', finished_at = now(), last_error = NULL WHERE id = %s", (job.id,)
            )

    def fail(self, job: Job, error: str) -> None:
        """Retry later, or mark failed once attempts are used up. The error must not contain identifiers."""
        final = job.attempts >= job.max_attempts
        with self.db.tx() as c:
            c.execute(
                "UPDATE app.jobs SET status = %s, last_error = %s, locked_at = NULL, "
                "run_after = now() + make_interval(secs => %s), finished_at = CASE WHEN %s THEN now() END "
                "WHERE id = %s",
                ("failed" if final else "queued", error[:500], RETRY_DELAY_SECONDS * job.attempts, final, job.id),
            )
