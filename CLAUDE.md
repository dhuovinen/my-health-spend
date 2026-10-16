# My Health Spend (MHS)

Reconciles provider bills, insurer EOBs and HSA payments per visit to find billing errors and overpayment. **Durable tier** (docs/DECISIONS.md ADR-020): read `docs/VISION.md`, `docs/ARCHITECTURE.md` and `docs/ROADMAP.md` before structural work, and record irreversible choices as an ADR in `docs/DECISIONS.md` first.

**Current phase:** Release 1, phase 1.3 (Ingestion and privacy pipeline) in progress. On `main` (tag `r1-uploads`): phases 1.1 and 1.2 and the local build of 1.3. Members upload provider statements, EOBs (PDF or photo), HSA exports and insurer claims exports; Tesseract OCR and Presidio run in the app tier, the worker extracts fields (layout rules, or Claude per household), the member reviews and confirms. ADR-031 to ADR-034 are accepted (034 with a condition: no AI extraction on real data until PRV-05 date shifting). Still to come in 1.3: Document AI and the staging project, PRV-05 date shifting, the extraction corpus. Release 0, the local MVP, is built and tagged `release-0`. Production target is Google Cloud (ADR-030). See `docs/ROADMAP.md`.

## How to run

Release 0 app (FastAPI + SQLite, Python 3.12 via uv), registered in `~/Projects/app-registry` on port 3062:

```bash
uv run mhs
```

Open http://127.0.0.1:3062. It binds to 127.0.0.1 only (no login; real health data). Env vars: `MHS_DATA_DIR` (default `data/`), `MHS_PORT` (default 3062).

Release 1 stack (Docker Compose; app on http://127.0.0.1:3063, registered in app-registry as `my-health-spend-r1`). The first run generates passwords and key files into the `secrets` volume:

```bash
docker compose up --build
```

```bash
docker compose exec app mhs-admin create-household "Household name"
```

```bash
docker compose exec -it app mhs-admin add-member --household <household-id> --email you@example.com --name "Your name"
```

The second command prints an authenticator secret and URI once; sign in with email, password and the 6-digit code. Load the made-up sample into a household (or upload an ingest file on the Import page):

```bash
docker compose exec app mhs-admin import --household <household-id> /srv/mhs/samples/example-ingest.json --yes
```

 Full suite against the stack (unit, integration and stack tests, through the `capture` proxy):

```bash
docker compose --profile test run --rm tests
```

Upload documents on the Uploads page (bills, statements, EOBs as PDF or photo; HSA CSV/XLS/XLSX; insurer claims CSV); each document shows "Review" once the worker has read it. The compose app runs Tesseract OCR (`MHS_OCR_ENGINE`) and the Presidio scrubber (`MHS_SCRUBBER`). Claude extraction is off: turn it on per household (it needs a worker with `MHS_EXTRACTOR=claude`, an API key and an egress proxy; SETUP.md "AI extraction"):

```bash
docker compose exec app mhs-admin ai-extraction --household <household-id> on
```

 The user scenarios and how to try each by hand are in `docs/TESTING.md` ("User scenarios"). Vault backup and restore (passphrase prompted, or `MHS_BACKUP_PASSPHRASE`) are in `docs/SETUP.md`. Wipe the local stack, data included: `docker compose --profile test down -v`.

Tests and coverage (the Release 1 tests start a throwaway Postgres container, so Docker must be running; they skip without it):

```bash
uv run pytest
```

```bash
uv run --with pytest-cov pytest --cov=mhs
```

Build an ingest file from real source files, then import it on the Import page by path:

```bash
uv run tools/build_ingest.py --settings data/settings.json --claims data/source/2026-10-09/claims.csv --hsa data/source/2026-10-09/TransactionHistory.xls --statements data/source/2026-10-09/patient-statements --out data/ingest-2026.json
```

First-time setup and the converter's warnings are in `docs/SETUP.md`.

## Gotchas

- `data/` holds the owner's real health data and is git-ignored. Never import test files into it, never commit it, and don't read the source PDFs or statements unless the owner asks. To try the app, point `MHS_DATA_DIR` at a scratch folder and import `samples/example-ingest.json`.
- Money is integer cents everywhere inside the app (`src/mhs/data/money.py`); ingest files use dollars.
- `src/mhs/core/` is pure functions: no database or web imports, and never changed to suit the UI.
- Edits made in the app (Settings, provider notes, deletes) are marked in the `owner_edits` table and survive re-import unless the owner ticks "Replace my edits" (ADR-011). Save through `Store.upsert(..., edited=True)` / `Store.delete(..., edited=True)` from any new in-app write path.
- Settings edits are also written to `data/settings.json`, which the converter reads, so in-app changes flow into the next ingest file.
- Release 1 code: adapters in `data/` (db, records, household_store, queue, objects, keys, migrate); upload pipeline in `ingest/` (values, hsa, claims, text, scrub, extract, resolve, worker, OCR stub) with routes in `web/household/intake.py`; vault service in `vault/`, application tier in `web/household/`, stack settings in `stack.py`. The Release 0 pages live once in `web/pages.py` and are mounted by both apps through a `PagesHost`; change a page there, never per app. Templates must stay CSP-clean: no inline `style=`, `<script>` or `on*=` handlers (use `style.css` classes and `static/app.js`), and every post form starts with `{{ csrf_input() }}`. Each tier uses its own Postgres role; household tables have row-level security, so always go through `HouseholdRecords` / `db.tx(household_id)`. Add schema changes as a new numbered file in `src/mhs/data/migrations/`.
- If `docker pull` or a build hangs on `docker-credential-desktop`, run it with a config that has no credential store: `DOCKER_CONFIG=<dir with {} config.json and a cli-plugins symlink to ~/.docker/cli-plugins>`.
- Don't turn on Claude extraction (`mhs-admin ai-extraction ... on`) for a household with real data until PRV-05 date shifting is built (ADR-034 condition); synthetic households only.
- Upload rule: identifiers are scrubbed in the application tier (`ingest/scrub.py`, vault tokens) before anything is queued; the worker never sees raw document text, and the Claude extractor (`ingest/ai.py`) sends only that scrubbed text. OCR (`ingest/ocr.py`) also runs in the app tier. Keep it that way. Test documents come from `tests/pdfs.py` (`make_pdf`, `make_image`, `make_scanned_pdf`); never use real documents. AI tests use recorded responses in `tests/fixtures/ai` (no key, no network); `capture` serves the same recordings to `worker-ai` on the stack.
- Tesseract isn't installed locally, so OCR tests skip under `uv run pytest`; they run in the compose `tests` container. Presidio loads spaCy `en_core_web_md` (a uv dependency) once per process.
- The compose project is named `mhs` in every checkout, and images are tagged `mhs:dev` / `mhs:test`: running the stack from a worktree replaces the main checkout's containers. Use `docker compose -p <other-name>` with an override that changes the image tags and drops the published port to test a worktree beside a running stack.
- Unit tests pin "today" (`TODAY = date(2026, 10, 9)` in `tests/test_reconcile.py`); web tests run on the real date, so don't assert exact day counts there.
