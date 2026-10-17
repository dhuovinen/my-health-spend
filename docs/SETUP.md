# Setup

How to install, configure and run Release 0 locally, and the Release 1 Docker Compose stack (see "Release 1 stack" below). The exact run commands are also in the root `CLAUDE.md` ("How to run").

## Prerequisites

- macOS or Linux
- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 from `.python-version` on first use)
- Port 3062 free (the app is registered in `~/Projects/app-registry`)

## Install

```bash
uv sync
```

## Run

```bash
uv run mhs
```

Open http://127.0.0.1:3062. The app binds to 127.0.0.1 only: there is no login, and it holds real health data.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `MHS_DATA_DIR` | `data/` in the repo | Folder for `mhs.db`, `documents/` and `settings.json` |
| `MHS_PORT` | `3062` | Port to serve on |

The data folder is git-ignored. Back it up by copying the whole folder while the app is stopped.

## Load data

1. **Try it with made-up data:** start the app with `MHS_DATA_DIR` pointing at an empty scratch folder, open Import and enter the path to `samples/example-ingest.json`.
2. **Real data:** build an ingest file with the converter, then import it by path on the Import page. The preview shows new, updated and unchanged records, and lists any of your in-app edits the file would overwrite (kept unless you tick "Replace my edits").

### Converter

`tools/build_ingest.py` reads the insurer claims CSV, the HSA transaction export (XLS) and provider statement PDFs, plus `data/settings.json` for plans, members and provider name aliases. It declares its own `pypdf` dependency, so `uv run` installs it.

```bash
uv run tools/build_ingest.py --settings data/settings.json --claims data/source/2026-10-09/claims.csv --hsa data/source/2026-10-09/TransactionHistory.xls --statements data/source/2026-10-09/patient-statements --out data/ingest-2026.json
```

Its warnings list:

- unmapped provider or member names (add them as `aliases` in `data/settings.json`)
- statement lines that don't add up
- duplicate statements
- any break in the HSA running balance

It supports one claims CSV layout, one HSA export layout and one statement layout (Southeastern Retina); see BACKLOG B-18 and B-20.

## Ingest format

JSON Schema `schema/mhs-ingest.schema.json` (version 0.1); rules in [MVP_REQUIREMENTS.md](MVP_REQUIREMENTS.md) section 4. Records link by id and re-import upserts by id. Use `extensions` on any record to trial new fields.

## Release 1 stack (phase 1.1)

The server-side app for the household, run locally on Docker Compose (ADR-030, ADR-031). **Synthetic data only:** never point it at the real `data/` folder.

### Prerequisites

- Docker Desktop (Compose v2.23 or later, for volume subpaths)
- Port 3063 free (registered in `~/Projects/app-registry` as `my-health-spend-r1`)

### Start

```bash
docker compose up --build
```

| Service | Role | Network |
| --- | --- | --- |
| `setup` | One-shot: generates database passwords, the vault service token and the two key files into the `secrets` volume, once | none |
| `postgres` | Records database and job queue (`postgres:17-alpine`) | internal only |
| `migrate` | One-shot: creates the tier roles and applies `src/mhs/data/migrations/` | internal only |
| `vault` | Identity vault service on port 8100, inside the network only | internal only |
| `app` | Application tier, http://127.0.0.1:3063 (the only published port) | internal + frontend |
| `worker` | Back-end tier: claims jobs from the Postgres queue | internal only (no route out) |
| `capture`, `tests` | Test profile only: mitmproxy logging every request, and the pytest runner | |

Each service mounts only its own folder of the `secrets` volume: the worker gets its database password and nothing else, and only `app` and `vault` have a key file, each its own.

### Add a household and a member

```bash
docker compose exec app mhs-admin create-household "Household name"
```

```bash
docker compose exec -it app mhs-admin add-member --household <household-id> --email you@example.com --name "Your name"
```

`add-member` asks for a password (12 characters or more) and prints an authenticator secret and `otpauth://` URI, once, with a single-use enrolment link: `http://127.0.0.1:3063/enrol/<token>` offers a button that shows the secret as a QR code to scan, then the link stops working (it also expires after 15 minutes, and `reset-mfa` cancels it; only a hash of the token is stored). Add it to an authenticator app, then sign in at http://127.0.0.1:3063 with email, password and the 6-digit code. Five wrong tries lock the account for 15 minutes; sessions end after 15 idle minutes or 12 hours. The enrolment page also shows ten single-use recovery codes, once: save them. Forgot your password or lost your phone? Use one on the sign-in page's "Forgot your password or lost your phone?" link to set a new password and a new authenticator (ADR-037); the Account page (your name in the header) makes new codes. No codes left: `docker compose exec app mhs-admin reset-mfa --email you@example.com` issues a new secret and ends the member's sessions.

### Demo household

`docker compose exec app mhs-admin demo-setup` creates the household "Sample household" and the member `demo@example.com` (Jordan Sample) with a generated password, adds Jordan, a 2026 HDHP plan and the HSA in Settings, and prints the sign-in details and enrolment link once. Rerunning it reuses the household, sets a new password and authenticator secret, and restores those Settings records. `--email`, `--name`, `--household` and `--password-stdin` change the defaults. The walkthrough with the synthetic documents in `samples/demo/` is [DEMO.md](DEMO.md).

### Upload documents

On the Uploads page, choose a file and what it is (or let the app decide):

- **Provider bills, statements, EOBs** as PDF, or a photo (JPG, PNG, HEIC). The app reads the text, replaces names and ID numbers with vault tokens, and the worker extracts the fields. When the status turns to Review, open it, check the fields ("check" marks the doubtful ones), correct them and confirm. Only then does the document reach your visits. Photos and scanned PDFs are read with OCR (Tesseract); iPhone HEIC photos are converted first. A photo that can't be opened is refused with the reason.
- **HSA/FSA exports** (CSV, XLS, XLSX) and the **insurer's claims export** (CSV) go straight to the import preview; confirm there.

The same file twice is refused. Add your household members and the year's plan in Settings first, so patients and claims match.

### AI extraction (optional, off by default)

Claude can read a household's documents instead of the layout rules (ADR-028, ADR-034). It only ever gets the scrubbed text, with identifiers replaced by tokens and every date shifted by a random per-person offset (PRV-05); the worker shifts the dates in the answer back, so your records keep the real dates. Two switches, both needed:

1. A worker with `MHS_EXTRACTOR=claude`, an API key (`MHS_ANTHROPIC_API_KEY` or `MHS_ANTHROPIC_API_KEY_FILE`) and a way out: the compose `backend` network has no route to the internet, so set `MHS_AI_PROXY` to an egress proxy that allows only the Anthropic API (or run that worker on a network that can reach it). The compose test profile has such a worker (`worker-ai`), pointed at the `capture` proxy, which answers with recorded responses.
2. The household turned on:

```bash
docker compose exec app mhs-admin ai-extraction --household <household-id> on
```

`off` turns it off and `status` shows it. With it on, the Uploads page says documents are read with AI's help and the review page names the model. If no AI worker is running, or the AI declines or fails, the layout rules read the document after a minute and the review page says so.

### Load data

Upload an ingest file on the Import page, with the statement and EOB files it refers to (matched by file name, stored encrypted). Or, as an admin, import a file that is inside the app container:

```bash
docker compose exec app mhs-admin import --household <household-id> /srv/mhs/samples/example-ingest.json
```

Without `--yes` it only previews (counts, warnings, member edits it would keep); add `--yes` to save, and `--replace-edits` to let the file overwrite edits made in the app. For a file on your machine, copy its folder in first with `docker compose cp <folder> app:/tmp/import`. The local stack is for synthetic data only (ARCHITECTURE.md "Environments"). Settings has a "Download settings.json" link for `tools/build_ingest.py`.

### Back up and restore the vault (PRV-07)

```bash
docker compose exec -it vault mhs-vault backup --out /backups/vault-2026-10-16.mhsvb
```

```bash
docker compose exec -it vault mhs-vault restore --in /backups/vault-2026-10-16.mhsvb
```

Backups land in the `vault-backups` volume. The passphrase is prompted (or `MHS_BACKUP_PASSPHRASE` / `MHS_BACKUP_PASSPHRASE_FILE`); restore only goes into an empty vault. A backup holds the vault's data keys wrapped by the vault's key file, so **keep a copy of the key file with the backups**: restoring needs both. Locally the key is `vault/kek` in the `secrets` volume; in Google Cloud it will be a Cloud KMS key.

### Test

```bash
docker compose --profile test run --rm tests
```

This runs the whole suite in the `tests` container: unit and integration tests on a fresh database with throwaway roles in the stack's Postgres, then the stack tests through `capture`. CI (`.github/workflows/ci.yml`) runs the same command plus `uv run pytest` on every push and pull request.

### Stop and reset

`docker compose down` stops the stack and keeps its data. `docker compose --profile test down -v` also deletes the volumes: database, originals, secrets and key files, and vault backups.

### Configuration

| Variable | Used by | Meaning |
| --- | --- | --- |
| `MHS_DATABASE_URL` | app, worker, vault | Full Postgres URL; otherwise built from `MHS_DB_HOST`, `MHS_DB_NAME`, `MHS_DB_USER` and `MHS_DB_PASSWORD(_FILE)` |
| `MHS_KEY_FILE` | app, vault | The service's key-encryption key file |
| `MHS_KEYS` | app, vault | `file` (default) or `kms` with `MHS_KMS_KEY` (Google Cloud, DEPLOYMENT.md) |
| `MHS_OBJECT_STORE` | app | `local` (default, `MHS_OBJECTS_DIR`) or `gcs` with `MHS_GCS_BUCKET` |
| `MHS_VAULT_URL`, `MHS_VAULT_TOKEN(_FILE)` | app, vault | Where the vault is, and the shared service token |
| `MHS_OBJECTS_DIR` | app | Folder for encrypted originals |
| `MHS_HOST`, `MHS_APP_PORT` | app | Bind address (0.0.0.0 inside the container) and port (3063) |
| `MHS_PUBLIC_URL` | app, mhs-admin | Where members open the app, for the enrolment links `mhs-admin` prints (`http://127.0.0.1:3063`) |
| `MHS_COOKIE_SECURE` | app | `1` once served over TLS (staging, production) |
| `MHS_SESSION_IDLE_MINUTES`, `MHS_SESSION_MAX_HOURS` | app | Session timeouts (15, 12) |
| `MHS_WORKER_POLL_SECONDS` | worker | Queue poll interval (1) |
| `MHS_OCR_ENGINE` | app | `tesseract` (compose), `documentai` (Google Cloud, with `MHS_DOCAI_PROCESSOR`) or `stub` (default: photos are typed by hand) |
| `MHS_SCRUBBER` | app | `presidio` (compose) or `rules` (default) |
| `MHS_EXTRACTOR` | worker | `rules` (default) or `claude`, which lets the worker take AI extraction jobs |
| `MHS_ANTHROPIC_API_KEY(_FILE)` | worker | Anthropic API key, when `MHS_EXTRACTOR=claude` |
| `MHS_AI_MODEL`, `MHS_AI_BASE_URL`, `MHS_AI_PROXY`, `MHS_AI_TIMEOUT_SECONDS` | worker | Model (`claude-opus-5-5`), API address, egress proxy, request timeout (120) |

