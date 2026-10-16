# Setup

How to install, configure and run Release 0 locally. The exact run commands are also in the root `CLAUDE.md` ("How to run"). Release 1 server setup will be added in phase 1.1 (see [ROADMAP.md](ROADMAP.md)).

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
