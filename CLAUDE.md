# My Health Spend (MHS)

Reconciles provider bills, insurer EOBs and HSA payments per visit to find billing errors and overpayment. **Durable tier** (docs/DECISIONS.md ADR-020): read `docs/VISION.md`, `docs/ARCHITECTURE.md` and `docs/ROADMAP.md` before structural work, and record irreversible choices as an ADR in `docs/DECISIONS.md` first.

**Current phase:** Release 1, phase 1.6 (acceptance) next. On `main` (2026-10-17, tag `r1-web-experience`): phases 1.1 to 1.5 and the local build of 1.3; phase 1.5 added home in the ADR-023 order with visit cards, the visit page in five sections, the Household page and view switch, and the phone layout with a bottom bar. Members sign in with MFA (recovery codes for a lost phone or password); upload or forward by email provider statements, EOBs (PDF or photo), HSA exports and insurer claims exports; Tesseract OCR and Presidio run in the app tier, the worker extracts fields (layout rules, or Claude per household with dates shifted, PRV-05); the member reviews and confirms; phase 1.4 matches lines, checks the three money identities with the $1.00 tolerance and gives each visit one of nine statuses. Export and delete, an access log and Google Cloud adapters (tested against emulators, DEPLOYMENT.md) are built. ADR-031 to ADR-041 are accepted. Still to come in 1.3: the staging project (needs the Google Cloud account) and the 95% accuracy target on the held-out corpus (the layout rules score 80% classification and 61.5% amounts; Claude extraction is the plan, not yet measured, needs an API key). Release 2 disputes (DSP-01, DSP-02, DSP-04, DSP-05, DSP-07; ADR-042 proposed) are built on branch `feat/r2-disputes`, not merged.

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

The second command prints, once, an authenticator secret and a single-use link (`/enrol/<token>`, 15 minutes) that shows it as a QR code to scan; sign in with email, password and the 6-digit code. For a demo, one command does all of that plus Settings (household member, 2026 plan, HSA) and prints a generated password; then upload the four files in `samples/demo/` and follow `docs/DEMO.md` (rerunnable; new password and code each time):

```bash
docker compose exec app mhs-admin demo-setup
```

Regenerate the synthetic demo pack (committed) after changing its text: `uv run tools/make_demo_pack.py`. Load the made-up sample into a household (or upload an ingest file on the Import page):

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

A three-person synthetic household (Household page, view switch, a six-line visit) for trying the pages: point `MHS_DATA_DIR` at a scratch folder and import `samples/household-ingest.json` (regenerate with `uv run tools/make_household_sample.py`). The layout tests at 375 and 1280 px drive headless Chromium (`uv run playwright install chromium` once; they skip without it):

```bash
uv run pytest tests/test_ux_layout.py
```

Extraction accuracy on the synthetic corpus (development set `tests/corpus`, held-out set `tests/corpus-holdout`; regenerate with `uv run python tools/make_corpus.py`; add `--extractor claude` with an API key to measure Claude):

```bash
uv run python tools/extraction_accuracy.py tests/corpus-holdout
```

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
- `src/mhs/core/` is pure functions: no database or web imports, and never changed to suit the UI. `reconcile.py` builds the report (claims per visit, allocation, checks, settlement, the nine statuses); `lines.py` holds the identities, ALC-01 buckets, line pairing and duplicates; `matching.py` the MAT-05 scores; `edits.py` the member's decisions as record changes. `TOLERANCE` in `lines.py` is ADR-015's $1.00.
- The member's reconciliation decisions are saved on the records they change, through `save_record` in `web/pages.py` (validated, marked as member edits): a payment's `allocations`, a document's `visit_id` and `match`, a visit's `payment_path`, `dispute`, `closed_findings` and `documents`. The waiting threshold is a `preference` record (`data/repository.py`) that imports never touch. Findings are matched to closed ones by check code and amount, so a changed amount reopens it.
- Edits made in the app (Settings, provider notes, deletes) are marked in the `owner_edits` table and survive re-import unless the owner ticks "Replace my edits" (ADR-011). Save through `Store.upsert(..., edited=True)` / `Store.delete(..., edited=True)` from any new in-app write path.
- Settings edits are also written to `data/settings.json`, which the converter reads, so in-app changes flow into the next ingest file.
- Release 1 code: adapters in `data/` (db, records, household_store, queue, objects, keys, migrate); upload pipeline in `ingest/` (values, hsa, claims, text, scrub, extract, resolve, worker, OCR stub) with routes in `web/household/intake.py`; vault service in `vault/`, application tier in `web/household/`, stack settings in `stack.py`. The Release 0 pages live once in `web/pages.py` and are mounted by both apps through a `PagesHost`; change a page there, never per app. Templates must stay CSP-clean: no inline `style=`, `<script>` or `on*=` handlers (use `style.css` classes and `static/app.js`), and every post form starts with `{{ csrf_input() }}`. Each tier uses its own Postgres role; household tables have row-level security, so always go through `HouseholdRecords` / `db.tx(household_id)`. Add schema changes as a new numbered file in `src/mhs/data/migrations/`.
- If `docker pull` or a build hangs on `docker-credential-desktop`, run it with a config that has no credential store: `DOCKER_CONFIG=<dir with {} config.json and a cli-plugins symlink to ~/.docker/cli-plugins>`.
- AI requests must stay pseudonymized: identifiers become tokens in the app tier and dates are shifted per person in the worker (`ingest/dates.py`, PRV-05) right before the call; anything new sent to the AI goes through both. Real household data still needs the production project and the data-processing agreement (ADR-028) before AI extraction is turned on.
- Upload rule: identifiers are scrubbed in the application tier (`ingest/scrub.py`, vault tokens) before anything is queued; the worker never sees raw document text, and the Claude extractor (`ingest/ai.py`) sends only that scrubbed text. OCR (`ingest/ocr.py`) also runs in the app tier. Keep it that way. Test documents come from `tests/pdfs.py` (`make_pdf`, `make_image`, `make_scanned_pdf`); never use real documents. AI tests use recorded responses in `tests/fixtures/ai` (no key, no network); `capture` serves the same recordings to `worker-ai` on the stack.
- Tesseract isn't installed locally, so OCR tests skip under `uv run pytest`; they run in the compose `tests` container. Presidio loads spaCy `en_core_web_md` (a uv dependency) once per process.
- The compose project is named `mhs` in every checkout, and images are tagged `mhs:dev` / `mhs:test`: running the stack from a worktree replaces the main checkout's containers. Use `docker compose -p <other-name>` with an override that changes the image tags and drops the published port to test a worktree beside a running stack.
- Phones (ADR-041): at 860px and narrower the top nav is hidden and the pages are in `nav.tabbar`; every control is at least 44px tall. A new standalone link (not inside a sentence) needs a class the phone rule covers (`a.back`, `.page-head a`, `td > a`, or `btn`), or `tests/test_ux_layout.py` flags it. Add new pages to its `PAGES` list.
- The household view's member is in the `mhs_view` cookie (`VIEW_COOKIE` in `web/pages.py`); Home, Visits and Household read it through `view_of()`.
- Dispute cases live on the visit record (`visit.cases`, ADR-042) and their contact log on `provider_note` records with a `case_id`. Letters are drafted in the application tier when the member asks (`web/letters.py`, identifiers from `PagesHost.identifiers`) and are never stored, queued, logged with their text or sent; keep it that way.
- Unit tests pin "today" (`TODAY = date(2026, 10, 9)` in `tests/test_reconcile.py`); web tests run on the real date, so don't assert exact day counts there.
