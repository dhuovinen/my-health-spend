"""Back-end tier worker: claims jobs from the Postgres queue and runs their handlers.

Job kinds: `ping` proves the path app → queue → worker → records end to end; `extract` classifies scrubbed
document text and extracts its fields for the member to review (ADR-033). The worker has no key and no
originals: it connects as its own database role, which can't read accounts, sessions or the vault (ADR-031),
and it only ever sees text whose identifiers the application tier already replaced with tokens.
"""

import logging
import os
import signal
import time
from datetime import datetime, timezone
from typing import Callable

from mhs.data.db import Database
from mhs.data.queue import Job, JobQueue
from mhs.data.records import HouseholdRecords
from mhs.ingest.extract import extract
from mhs.stack import database_url

log = logging.getLogger("mhs.worker")

Handler = Callable[[Job, Database], None]


def handle_ping(job: Job, db: Database) -> None:
    HouseholdRecords(db, job.household_id).put(
        "job_result",
        {"id": f"job-{job.id}", "kind": job.kind, "finished_at": datetime.now(timezone.utc).isoformat()},
    )


def handle_extract(job: Job, db: Database) -> None:
    """payload: upload_id, text (scrubbed), how_read, pages, forced_type (when the member reclassified)."""
    p = job.payload
    if not p.get("text", "").strip():
        result = extract("", forced_type=p.get("forced_type") or "other").to_record()
        result["warnings"] = ["No text could be read from this file yet; enter the fields from the document."]
    else:
        result = extract(p["text"], forced_type=p.get("forced_type")).to_record()
    records = HouseholdRecords(db, job.household_id)
    records.put("extraction", {
        "id": p["upload_id"],
        "status": "review",
        "how_read": p.get("how_read", ""),
        "pages": p.get("pages", 0),
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "job_id": job.id,
        **result,
    })


HANDLERS: dict[str, Handler] = {"ping": handle_ping, "extract": handle_extract}


def run_once(queue: JobQueue, db: Database, handlers: dict[str, Handler] = HANDLERS) -> Job | None:
    """Claim and run one job. Returns it, or None when the queue is empty."""
    job = queue.claim()
    if job is None:
        return None
    handler = handlers.get(job.kind)
    try:
        if handler is None:
            raise LookupError(f"no handler for job kind {job.kind!r}")
        handler(job, db)
    except Exception as e:  # noqa: BLE001 - any failure goes back to the queue
        log.warning("job %s (%s) failed on attempt %s: %s", job.id, job.kind, job.attempts, type(e).__name__)
        queue.fail(job, f"{type(e).__name__}: {e}")
    else:
        queue.complete(job)
    return job


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    poll = float(os.environ.get("MHS_WORKER_POLL_SECONDS", "1"))
    db = Database(database_url(), max_size=2)
    queue = JobQueue(db)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log.info("worker started; handlers: %s", ", ".join(HANDLERS))
    while not stopping:
        if run_once(queue, db) is None:
            time.sleep(poll)
    db.close()
    log.info("worker stopped")


if __name__ == "__main__":
    main()
