# My Health Spend (MHS)

Reconciles provider bills, insurer EOBs and HSA payments per visit to find billing errors and overpayment. **Durable tier** (docs/DECISIONS.md ADR-020): read `docs/VISION.md`, `docs/ARCHITECTURE.md` and `docs/ROADMAP.md` before structural work, and record irreversible choices as an ADR in `docs/DECISIONS.md` first.

**Current phase:** Release 1, phase 1.1 (Foundation) built on branch `feat/r1-foundation`: the Docker Compose stack, the four adapters, MFA sign-in with household isolation, encryption at rest, vault backup and restore, CSP, CI. ADR-031 (the build choices) awaits the owner's acceptance. Next is phase 1.2, porting Release 0 to the server. Release 0, the local MVP, is built and tagged `release-0`. Production target is Google Cloud (ADR-030). See `docs/ROADMAP.md`.

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

The second command prints an authenticator secret and URI once; sign in with email, password and the 6-digit code. Full suite against the stack (unit, integration and stack tests, through the `capture` proxy):

```bash
docker compose --profile test run --rm tests
```

Vault backup and restore (passphrase prompted, or `MHS_BACKUP_PASSPHRASE`) are in `docs/SETUP.md`. Wipe the local stack, data included: `docker compose --profile test down -v`.

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
- Release 1 code: adapters in `data/` (db, records, queue, objects, keys, migrate), worker and OCR stub in `ingest/`, vault service in `vault/`, application tier in `web/household/`, stack settings in `stack.py`. Each tier uses its own Postgres role; household tables have row-level security, so always go through `HouseholdRecords` / `db.tx(household_id)`. Add schema changes as a new numbered file in `src/mhs/data/migrations/`.
- If `docker pull` or a build hangs on `docker-credential-desktop`, run it with a config that has no credential store: `DOCKER_CONFIG=<dir with {} config.json and a cli-plugins symlink to ~/.docker/cli-plugins>`.
- Unit tests pin "today" (`TODAY = date(2026, 10, 9)` in `tests/test_reconcile.py`); web tests run on the real date, so don't assert exact day counts there.
