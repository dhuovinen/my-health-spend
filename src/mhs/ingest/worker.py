"""Back-end tier worker: claims jobs from the Postgres queue and runs their handlers.

Job kinds: `ping` proves the path app → queue → worker → records end to end; `extract` classifies scrubbed
document text and extracts its fields for the member to review with the layout rules (ADR-033); `extract_ai` does
the same with Claude (ADR-028, ADR-034) for households that have AI extraction turned on. The worker has no key
and no originals: it connects as its own database role, which can't read accounts, sessions or the vault
(ADR-031), and it only ever sees text whose identifiers the application tier already replaced with tokens.

MHS_EXTRACTOR=claude lets this worker take `extract_ai` jobs (ingest/ai.py has its settings). A worker without it
reads an `extract_ai` job with the rules once the job has waited a minute, and says so on the review page.
"""

import logging
import os
import signal
import time
from datetime import datetime, timezone
from functools import partial
from typing import Callable

from mhs.data.db import Database
from mhs.data.queue import Job, JobQueue
from mhs.data.records import HouseholdRecords
from mhs.ingest.extract import extract
from mhs.stack import database_url

log = logging.getLogger("mhs.worker")

Handler = Callable[[Job, Database], None]
EXTRACT_AI = "extract_ai"
STALE_AI_SECONDS = 60
EXTRACTORS = ("rules", "claude")


def handle_ping(job: Job, db: Database) -> None:
    HouseholdRecords(db, job.household_id).put(
        "job_result",
        {"id": f"job-{job.id}", "kind": job.kind, "finished_at": datetime.now(timezone.utc).isoformat()},
    )


def handle_extract(job: Job, db: Database, ai=None) -> None:
    """payload: upload_id, text (scrubbed), how_read, pages, text_confidence (OCR), forced_type (when the member
    reclassified). An `extract_ai` job goes to `ai` when this worker has it; otherwise, or when the AI can't
    read the document, the layout rules read it and the review page says why."""
    from mhs.ingest.ai import AiUnavailable

    p = job.payload
    extractor, model, note = "rules", None, None
    if not p.get("text", "").strip():
        result = extract("", forced_type=p.get("forced_type") or "other").to_record()
        result["warnings"] = ["No text could be read from this file yet; enter the fields from the document."]
    else:
        x = None
        if job.kind == EXTRACT_AI and ai is None:
            note = "AI reading isn't running on this server, so the layout rules read this document."
        elif job.kind == EXTRACT_AI:
            try:
                x = ai.extract(p["text"], forced_type=p.get("forced_type"))
                extractor, model = "ai", ai.config.model
            except AiUnavailable as e:
                log.warning("job %s: %s; using the layout rules", job.id, e)
                note = f"{e}, so the layout rules read this document."
        result = (x or extract(p["text"], forced_type=p.get("forced_type"))).to_record()
        cap_confidence(result, p.get("text_confidence", 1.0))
        if note:
            result["warnings"].insert(0, note)
    records = HouseholdRecords(db, job.household_id)
    records.put("extraction", {
        "id": p["upload_id"],
        "status": "review",
        "how_read": p.get("how_read", ""),
        "pages": p.get("pages", 0),
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "extractor": extractor,
        "ai_model": model,
        "job_id": job.id,
        **result,
    })


def cap_confidence(result: dict, text_confidence: float) -> None:
    """A field read from OCR text is no surer than the OCR itself, so weak scans are marked for checking."""
    if text_confidence >= 1.0:
        return
    for f in result.get("fields", {}).values():
        f["confidence"] = round(min(f["confidence"], text_confidence), 2)
    result["type_confidence"] = round(min(result["type_confidence"], text_confidence), 2)


def make_handlers(ai=None) -> dict[str, Handler]:
    extract_with = partial(handle_extract, ai=ai)
    return {"ping": handle_ping, "extract": extract_with, EXTRACT_AI: extract_with}


HANDLERS: dict[str, Handler] = make_handlers()


def run_once(queue: JobQueue, db: Database, handlers: dict[str, Handler] = HANDLERS, kinds: list[str] | None = None,
             stale_kinds: list[str] = ()) -> Job | None:
    """Claim and run one job (of `kinds`, or any kind). Returns it, or None when there is nothing to do."""
    job = queue.claim(kinds, stale_kinds, STALE_AI_SECONDS)
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


def ai_from_env():
    """The Claude extractor when MHS_EXTRACTOR=claude, else None."""
    name = os.environ.get("MHS_EXTRACTOR", "rules")
    if name not in EXTRACTORS:
        raise SystemExit(f"MHS_EXTRACTOR must be one of {', '.join(EXTRACTORS)}, not {name!r}")
    if name != "claude":
        return None
    from mhs.ingest.ai import ClaudeExtractor, config_from_env

    return ClaudeExtractor(config_from_env())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    poll = float(os.environ.get("MHS_WORKER_POLL_SECONDS", "1"))
    ai = ai_from_env()
    handlers = make_handlers(ai)
    kinds = list(handlers) if ai else [k for k in handlers if k != EXTRACT_AI]
    stale = [] if ai else [EXTRACT_AI]
    db = Database(database_url(), max_size=2)
    queue = JobQueue(db)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log.info("worker started; jobs: %s; AI extraction: %s", ", ".join(kinds), ai.config.model if ai else "off")
    while not stopping:
        if run_once(queue, db, handlers, kinds, stale) is None:
            time.sleep(poll)
    db.close()
    log.info("worker stopped")


if __name__ == "__main__":
    main()
