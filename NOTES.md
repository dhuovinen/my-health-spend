# NOTES

## What this is

My Health Spend (MH$): a personal app that reconciles provider bills, insurer EOBs and payment
records (HSA/FSA/card) per visit to find billing errors and overpayment. MVP is single-user, local
only. Product docs live in `docs/`: `MVP_REQUIREMENTS.md`, `My Health Spend (MHS) Problem Statement & Plan.md`
and `My Health Spend (MHS) Product Requirements.md` (full spec, about 98 requirements).

## How to run

**App** (FastAPI + SQLite, Python 3.12 via uv). Registered in `~/Projects/app-registry` on port 3062:

```bash
uv run mhs
```

Then open http://127.0.0.1:3062. It binds to 127.0.0.1 only (no login; personal health data).
Data lives in `data/` (`mhs.db`, `documents/`, `settings.json`); override with `MHS_DATA_DIR`, port
with `MHS_PORT`. Settings page edits are also written back to `data/settings.json` (previous copy kept
as `settings.json.bak`) so the converter below stays in step.

**Tests:**

```bash
uv run pytest
```

**Load data:** build an ingest file (below), then in the app go to Import, check the file by path and
save. Re-importing updates records by id.

Build an ingest file from the insurer claims CSV, HSA export and provider statement PDFs (Python 3.12
via uv; the script declares its own `pypdf` dependency):

```bash
uv run tools/build_ingest.py --settings data/settings.json --claims data/source/2026-10-09/claims.csv --hsa data/source/2026-10-09/TransactionHistory.xls --statements data/source/2026-10-09/patient-statements --out data/ingest-2026.json
```

Warnings list unmapped provider or member names (add them as `aliases` in `data/settings.json`),
statement lines that don't add up, duplicate statements, and any break in the HSA running balance. `data/` holds real health data and is git-ignored.


## Status

2026-10-09: MVP requirements agreed (`MVP_REQUIREMENTS.md`), backlog started (`BACKLOG.md`),
ingest schema v0.1 and a made-up sample file written and validated. Local web app chosen; framework
not yet picked. No app code yet. Waiting on the owner's real sample visits.
2026-10-09: Real 2026 claims (11) and HSA history (77 rows) converted to `data/ingest-2026.json`.
2026-10-09: Added 7 Southeastern Retina statements (2025-10 to 2026-10), household members and
provider relationships. Ingest now 15 visits, 96 documents.
2026-10-09: MVP app built: hero, visits, visit detail, provider ledgers, import, settings (plans,
limits, members, accounts, providers, provider matches), help stub. 22 tests passing. Real 2026 data imported.
2026-10-09: Provider notes (dated contact log per provider, linked to a visit) on branch feat/provider-notes.
2026-10-15: Full product requirements written; product docs moved into `docs/`.
