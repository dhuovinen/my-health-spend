# Testing

The strategy in brief. Test cases for every requirement, the open conflicts and the traceability matrix are in [TEST_PLAN.md](TEST_PLAN.md).

## How to run

```bash
uv run pytest
```

The Release 1 tests (marked `postgres`) need a Postgres server: `MHS_TEST_DATABASE_ADMIN_URL`, or Docker running, in which case the session starts a throwaway `postgres:17-alpine` container. Without either they skip. Full suite against the running stack, including the `stack` tests through the `capture` proxy:

```bash
docker compose --profile test run --rm tests
```

```bash
uv run --with pytest-cov pytest --cov=mhs
```

## Current state (2026-10-16, phase 1.3 in progress, engines on `feat/r1-ingest-engines`)

| Measure | Value |
| --- | --- |
| Automated tests | 240 on the compose stack; `uv run pytest` 227 with 13 skipped (5 stack tests, including the fake GCS server round trip, and 8 that need the tesseract binary), 2026-10-16 on `feat/r1-cloud-adapters`. They include 55 from the Release 0 suite (the 32 Appendix A tests plus one Settings regression, 22 of them run a second time against Release 1 with `[release1]` or `[postgres]` ids); the Release 1 tests in `tests/test_r1_*.py`, among them 26 upload scenarios in `test_r1_scenarios.py`, 22 rule and scrubbing tests in `test_r1_extract.py`, 11 OCR tests in `test_r1_ocr.py`, 7 recall and letterhead tests in `test_r1_scrub_recall.py`, 8 Claude extractor tests in `test_r1_ai.py`, the PRV-05 date tests in `test_r1_dates.py` 8 laptop-demo tests in `test_r1_demo.py`, and the corpus and Google Cloud adapter tests (`test_r1_corpus.py`, `test_r1_cloud.py`); and 4 stack tests (`tests/stack/`) |
| Coverage, `core/` | 96% (target ≥ 80%) |
| Coverage, `data/` | 89 to 100% per module |
| Coverage, `web/pages.py` (shared pages), `web/household/app.py`, `auth.py` | 85%, 95%, 98% |
| Coverage, `ingest/` (upload pipeline), `web/household/intake.py` | 72 to 100% per module under `uv run pytest` (OCR and worker paths run fully only on the stack) |
| Coverage, total | 91% (`uv run pytest`) |

**Appendix A on the server (phase 1.2 exit).** `tests/test_web.py` runs each Release 0 web test against both apps through the `web` fixture: Release 0 over SQLite, and the Release 1 application tier as a signed-in member, importing by upload, with CSRF tokens on every post. `tests/test_importer.py` runs each store-backed importer test against the SQLite store and a household's Postgres store (`store` fixture). The core tests (`test_reconcile.py`) are shared code. `tests/test_r1_pages.py` adds household isolation on every ported page, encrypted import attachments and `mhs-admin import`.

Release 1 test cases covered in phase 1.1:

| Case | Test |
| --- | --- |
| TC-PRV-11-1 password alone reaches no data | `test_r1_auth.py::test_tc_prv_11_1_*`, `stack/test_stack.py` |
| TC-PRV-11-2 two-household isolation (records, files, jobs, vault entries; database row-level security) | `test_r1_isolation.py`, `test_r1_database.py::test_row_level_security_*` |
| TC-PRV-11-3 sign-out and idle timeout | `test_r1_auth.py::test_tc_prv_11_3_*` |
| TC-PRV-06-2 unreadable without the key | `test_r1_encryption.py`, `stack/test_stack.py::test_originals_volume_holds_only_ciphertext` |
| TC-PRV-06-3 back-end tier can't decrypt or read the vault | `test_r1_database.py::test_worker_role_*`, `test_r1_encryption.py::test_tc_prv_06_3_*` |
| TC-PRV-07-1 restore onto a fresh server; TC-PRV-07-2 wrong passphrase | `test_r1_backup.py` (including the scripted `mhs-vault` commands) |
| TC-PRV-08-3 CSP; TC-PRV-08-1 (partial) first-party traffic only | `test_r1_csp.py`, `stack/test_stack.py::test_captured_traffic_stays_first_party` |
| TC-PLT-06-2 CI on every change | `.github/workflows/ci.yml` (runs once the repo is on GitHub) |

Not yet: TC-PRV-06-1 (TLS; staging), TC-PRV-07-3 (self-service MFA recovery; `mhs-admin reset-mfa` meanwhile), TC-PRV-08-2 (no analytics events exist).

## User scenarios (phase 1.3)

Each scenario is automated in `tests/test_r1_scenarios.py` (with the worker run in-process); scenarios 1, 3, 8, 12 and 15 also run on the compose stack through the real workers (`tests/stack/test_stack.py`): a photo is read by Tesseract in the app, scrubbed with Presidio, and extracted by the `worker-ai` container through the `capture` proxy, which answers with recorded responses and logs each AI request for TC-PLT-04-1. Tesseract tests skip under `uv run pytest` when the binary isn't installed. To try one by hand: `docker compose up --build`, create a household and member (SETUP.md), sign in at http://127.0.0.1:3063 with the authenticator code, add a member and a 2026 plan in Settings, then use the Uploads page. Use synthetic documents only (`tests/pdfs.py` makes them).

| # | Scenario | Steps | Expected | Requirements / test cases | Test |
| --- | --- | --- | --- | --- | --- |
| 1 | Sign in with MFA | Email and password, then the 6-digit code | No data before the code; home after it | PRV-11 (TC-1, TC-3) | `test_r1_auth.py`, stack |
| 2 | Upload a provider statement | Upload a statement PDF ("Let the app decide") | Status Reading, then Review; fields with confidences, low ones marked "check"; nothing on Visits yet; Confirm creates the visit and the bill; the original opens from the visit's document | ING-01 TC-1, ING-02, ING-03, ING-05 TC-1/2, ING-10 TC-1 | `test_statement_upload_review_and_confirm` |
| 3 | Upload the EOB for that visit | Upload an EOB PDF; correct "You owe" from 45.00 to 54.00; confirm; edit back | Classified EOB ("THIS IS NOT A BILL"); provider, plan and visit preselected; correction kept with the extracted value; visit updates at once | ING-02 TC-3, ING-04, ING-05 TC-3/4, PLT-04 TC-2 | `test_eob_upload_corrected_and_matched_to_the_visit`, stack |
| 4 | Upload an HSA export | Upload the administrator's CSV, XLS or XLSX; check the preview; confirm | Card payments become HSA payments to the provider; contributions, interest and fees become account transactions; the same file again is refused as a duplicate; an overlapping export adds no duplicates | ING-08 TC-1/2/5, ING-07 TC-1/5 | `test_hsa_export_upload`, `test_hsa_export_formats_agree` |
| 5 | A bad HSA export | Upload a CSV without the amount column; one with a balance gap | Refused naming the missing column, nothing saved; the gap is warned about by date | ING-08 TC-3/4 | `test_hsa_export_problems` |
| 6 | Upload the insurer's claims export | Upload the claims CSV | One EOB per claim on a visit, with the member and the year's plan | ING-08 (spirit), MAT-03 | `test_claims_export_upload` |
| 7 | Refused files | Upload .docx, .zip, an empty file, a damaged PDF, a password-protected PDF, a file over 20 MB | Each refused with a plain reason; nothing saved | ING-01 TC-5 | `test_unreadable_uploads_are_refused`, `test_password_protected_and_oversized_pdfs_are_refused` |
| 8 | A photo of an EOB | Upload a PNG, an iPhone HEIC photo or a scanned PDF of an EOB | Read by OCR in the app ("photo, OCR (tesseract)"), scrubbed, extracted like the PDF; without an OCR engine the form is empty with "No text could be read" and the member types the fields | ING-01 TC-2/3, ING-03, ING-05, PRV-04 | `test_photo_and_scan_are_read_by_ocr`, `test_photo_is_entered_by_hand`, `test_r1_ocr.py`, stack |
| 9 | Wrong type | Upload a letter; change its type to provider statement | First "Other"; after the change, read again as a statement | ING-02 TC-4 | `test_reclassify_reads_again` |
| 10 | Multi-page PDF | Upload a 2-page EOB | One upload, both pages read | ING-01 TC-3 (PDF part) | `test_multi_page_pdf_is_one_document` |
| 11 | Lines that don't add up | Upload an EOB whose lines total $40 less than the header | Warning before confirmation | ING-04 TC-3 | `test_lines_that_dont_add_up_are_flagged` |
| 12 | Identifiers stay in the application tier | Upload a statement and an EOB that name the patient, member ID, account number and phone | The queued text and the worker's records hold tokens only; one token for "Example, Pat A." and "Pat Example"; the member sees the real values | PRV-01 TC-1/2, PRV-03 TC-1, PRV-04 TC-2 | `test_identifiers_never_reach_the_worker`, `test_r1_extract.py` |
| 13 | Another household | A second household asks for the first one's upload, review, confirm or reclassify | Not found every time | PRV-11 TC-2 | `test_another_household_cannot_see_or_confirm_an_upload` |
| 14 | Strangers in a letter | Upload a letter that names people the household doesn't know, with a phone number | With Presidio, none of the names or the number reach the worker; dates, amounts and the provider do | PRV-04 TC-2/3 | `test_presidio_scrubs_strangers_in_a_letter`, `test_r1_scrub_recall.py` |
| 15 | AI extraction | `mhs-admin ai-extraction --household <id> on`; upload an EOB | The Uploads page says AI helps; the review names the model; a value the document doesn't show is marked "not found in the document text"; the member's correction is confirmed and the AI's value is kept beside it; the AI request holds tokens, never identifiers | ADR-028, PLT-04 TC-1/2 | `test_ai_extraction_for_a_household_that_turned_it_on`, `test_r1_ai.py`, stack (TC-PLT-04-1) |
| 16 | AI unavailable | AI on, but no AI worker for a minute, or the AI declines | The layout rules read the document and the review says why | ADR-034 | `test_ai_jobs_are_read_by_the_rules_when_ai_is_unavailable` |
| 17 | Dates sent to the AI are shifted | AI on; upload an EOB for a visit on 2026-12-30, and two EOBs for one patient 14 days apart | The AI request carries shifted dates, 14 days apart for the same person; the review and the visit keep 2026-12-30 (plan year 2026) | PRV-05 (TC-1, TC-2) | `test_r1_dates.py`, stack (`test_photo_read_by_ocr_scrubbed_and_extracted_by_ai`) |
| 18 | Laptop demo (DEMO.md) | `mhs-admin demo-setup`; open the enrolment link and scan the QR code; sign in; upload the four files in `samples/demo/` in order | One household and member however often it runs, Settings restored, old password and link void; the QR decodes to the member's `otpauth://` URI and shows once; the Riverbend visit is a Discrepancy ($480.00 asked, $300.00 owed, $180.00 at stake), Lakeside $800.00 outstanding, deductible $1,100.00 of $1,700.00; no page scrolls sideways at 375 px | PRV-11, UX-10 | `test_r1_demo.py` (the photo through Tesseract on the stack, typed in elsewhere) |
| 19 | A bare letterhead | With Presidio, upload a statement whose provider name sits right above its address with no heading between them ("Riverbend Orthopedics" over "455 River Road, Springfield"), or one from a practice named after a person ("Kessler Orthopedics") | The review names the provider from the letterhead on every upload; the address, account number, patient and phone are tokens | PRV-04, ING-03 | `test_a_bare_letterhead_survives_every_upload`, `test_a_practice_named_after_a_person_is_kept` |

**Scrubbing is deterministic (scenario 19).** Presidio reads each document's original text once, and its finds are placed in the rules' output wherever the rules left them whole. It used to run a second time on text that already held random vault tokens, so the same statement scrubbed differently from upload to upload: a bare letterhead above a tokenized address read as a person in about one upload in four (43 of 150 in `mhs:test`), and extraction took the table header as the provider. Names and places Presidio finds that hold a practice word (Orthopedics, Radiology, Clinic, Imaging, Pharmacy, Labs and the rest of `ORG_WORDS` in `ingest/scrub.py`), with any capitalized words after them on the line, are kept, because spaCy reads "Bennett Radiology" as a person even in the original text. The recall seed set is unchanged at 189 of 190 identifiers (99.5%).

## Extraction accuracy (PLT-02, TC-ING-02-1, TC-ING-03-1)

Two synthetic corpora with ground truth, made by `tools/make_corpus.py` (seeded): `tests/corpus/` (56 documents) is the development set the layout rules were fixed against; `tests/corpus-holdout/` (50 documents, other layouts and wording) was written once and is never used to tune them, so its result is the honest figure. Both cover all eight ING-02 types with at least 5 documents each. `tools/extraction_accuracy.py <corpus> [--extractor claude]` runs each document the way an upload goes (text layer, scrubbing, classification, extraction), compares it with the ground truth before any confirmation, and prints the report. `tests/test_r1_corpus.py` keeps the development set at the targets and the held-out set from getting worse.

Layout rules, 2026-10-16:

| Measure | Development (56) | Held-out (50) | Target |
| --- | --- | --- | --- |
| Classification | 100% | 80% (40 of 50) | 95% |
| Amounts correct before confirmation | 100% | 61.5% (40 of 65) | 95% |
| All header fields | 100% | 43.8% (70 of 160) | |

On the held-out set, both statement layouts ("Invoice", "Billing Statement") were read as "other", and labels without a colon or in a two-column layout ("Claim   123", "Statement Dt  10/01/2026") weren't read. The rules only know the wording they were written for, so they won't reach PLT-02 on documents they haven't seen; Claude extraction (ADR-028, ADR-034) is the way to the target. Its run (`--extractor claude`, with an API key) hasn't been made yet. Before tuning anything on these results, generate a fresh held-out set; tuning on this one would make its figure meaningless. OCR accuracy (TC-PLT-02-1) is measured with Document AI in staging.

## Levels

| Level | Where | Covers |
| --- | --- | --- |
| Unit | `tests/test_reconcile.py`: synthetic datasets built with `base()`, `eob()`, `pay()`, `visit()`; "today" pinned | Core rules: checks, statuses, allocation, ledgers, HSA flags, limits |
| Integration | `tests/test_importer.py`, `tests/test_web.py`: temp data folder, `fastapi.testclient.TestClient` | Import validation and upsert, owner-edit protection, pages, forms |
| End-to-end | Browser against `uv run mhs` with `MHS_DATA_DIR` on a scratch folder | Screens and flows |
| Security and privacy (Release 1) | Intercepting proxy between tiers, seeded identifiers, storage inspection | PRV, PLT-04 |
| Performance (Release 1) | Timed runs on the scenario library | PLT-05 |
| Review | Checklists | CMP, PLT-06 coverage |

## Rules

- Tests run alongside implementation. A task isn't done until `uv run pytest` is green.
- `src/mhs/core/` keeps unit coverage ≥ 80%.
- Never use the real `data/` folder in tests; fixtures use `samples/example-ingest.json` or synthetic data. Real-world scenarios enter the scenario library only after redaction (PLT-06).
- Assertions on money use integer cents.
- No secrets or environment-specific values in tests.

## Release 1 test environment

Defined 2026-10-16; built in phase 1.1. Environments and adapters are in [ARCHITECTURE.md](ARCHITECTURE.md#environments).

### Local (every change)

| Piece | How |
| --- | --- |
| Stack | `docker compose --profile test up`: `app`, `worker`, `vault`, `postgres`, plus `capture` |
| Database | Fresh Postgres database and tier roles per test session; tables truncated before each test (the app's own pooled transactions can't be wrapped in one rollback) |
| Outside services | AI extraction answered from recorded responses (`tests/fixtures/ai`: by an in-process transport in unit tests, by `capture` on the stack); OCR is Tesseract; keys from a throwaway key file |
| Outbound capture | `capture` is an intercepting proxy (mitmproxy) on the app → worker → AI path. PRV and PLT-04 tests seed the identifier set, run a workflow, then search every captured payload |
| Isolation | Tests create two households and assert neither can read the other's records, files or vault entries (TC-PRV-11-*) |
| Data | `samples/`, synthetic builders, the extraction corpus and the identifier seed set; the redacted scenario library once it exists. Never the real `data/` folder |
| Commands | `uv run pytest` for unit and integration tests; `docker compose --profile test run --rm tests` for the full suite against the stack |
| CI | The same compose file in CI on every change; merge blocked on failure (PLT-06) |

### Staging (per release and on demand)

| Run | What it proves |
| --- | --- |
| OCR accuracy | The extraction corpus through Document AI meets the 95% target before confirmation (PLT-02, TC-PLT-02-1) |
| Cloud integration | The same suite with the Cloud SQL, Cloud Storage and Cloud KMS adapters |
| Restore drill | Vault and database restored from backup into a fresh staging project (TC-PRV-07-1) |
| Performance | 50 typical uploads, p95 machine time under 60 seconds (TC-PLT-05-1) |
| Outbound capture | Traffic from Cloud Run to the AI service captured through a proxy egress; no identifiers (TC-PLT-04-1) |

### Production

No test data and no test runs. Health checks, audit logs and the owner's acceptance in phase 1.6.

## Release 1 additions

| Need | Phase |
| --- | --- |
| Docker Compose stack, CI, household isolation tests | 1.1 |
| Release 0 regression suite (TEST_PLAN Appendix A) run against the stack | 1.2 |
| Extraction corpus with ground truth (≥ 5 documents per type), identifier seed set, capture tests | 1.3 |
| Staging project and the OCR accuracy run | 1.3 |
| Redacted real-world scenario per REC rule | 1.4 |
| Restore drill and performance run in staging | 1.6 |
