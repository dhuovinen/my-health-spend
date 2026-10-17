# Roadmap

**Current phase: 1.3, Ingestion and privacy pipeline, in progress.** Phases 1.1 and 1.2 and the local build of 1.3 (upload pipeline with Tesseract OCR, Presidio and Claude extraction) are merged into `main` and tagged `r1-uploads` on 2026-10-16; ADR-031 to ADR-034 accepted. PRV-05 date shifting for AI requests (meets ADR-034's condition), the laptop demo (DEMO.md) and deterministic scrubbing are merged into `main`. The extraction corpus and accuracy run are built on `feat/r1-extraction-corpus`: the layout rules score 80% classification and 61.5% amounts on the held-out set against the 95% targets (TESTING.md "Extraction accuracy"), so meeting PLT-02 needs Claude extraction, which has not been measured yet. The Google Cloud adapters (Cloud Storage, Cloud KMS, Document AI over REST) and database-held import previews are built and tested against emulators on `feat/r1-cloud-adapters` (ADR-036); DEPLOYMENT.md lists what the owner sets up first. Next in 1.3: the Claude accuracy run (needs an API key), the staging project (needs the Google Cloud account).

Requirement IDs refer to the [Product Requirements](<My Health Spend (MHS) Product Requirements.md>). Test cases for each are in [TEST_PLAN.md](TEST_PLAN.md).

## Release 0: local MVP (done)

Built Oct 9 to 15, 2026 from [MVP_REQUIREMENTS.md](MVP_REQUIREMENTS.md). A single-owner laptop app: JSON import from a converter, the reconciliation checks C1 to C8, visit list and detail, provider ledgers and notes, plan-limit progress, HSA flags with counts, and Settings. Re-import keeps edits made in the app. 32 automated tests; core coverage 96%.

| Item | Status |
| --- | --- |
| All MVP requirements built | Done (C6 aging and HR-4 counts closed 2026-10-15) |
| Merge `feat/provider-notes` into `main` and tag `release-0` | Done 2026-10-15 (merge commit `075f187`) |
| Owner data still to load | 2026 dental and 2025 UMR plan limits; 2025 HSA history (B-21) |

## Release 1: server-side web app for the household

49 requirements: lean core, household, and Release 0 carried over ([PRD Release 1 scope](<My Health Spend (MHS) Product Requirements.md#release-1-scope>), ADR-018).

| Phase | Goal | Requirements | Exit |
| --- | --- | --- | --- |
| 1.0 Planning (done) | Settle what is still open and set up for the build | none | Done 2026-10-16: ADRs 021 to 030 accepted (hosting: local Docker Compose, then Google Cloud; OCR: text layer then Document AI); test environment defined in TESTING.md; Release 0 merged and tagged |
| **1.1 Foundation** (built 2026-10-16) | A secure, empty server app the household can sign in to, on the local Docker Compose stack | PRV-11, PRV-06, PRV-07, PRV-08, PLT-06 | Compose stack with the four adapters (ARCHITECTURE.md "Environments"); local port registered in app-registry; MFA sign-in; household isolation tests pass (TC-PRV-11-*); encrypted storage and a tested restore; CI runs the suite. **Built:** all exit items met locally (port 3063; 95 tests on the stack). Open: CI runs once the repo has a GitHub remote; TC-PRV-07-3 self-service recovery (built 2026-10-16 with recovery codes, ADR-037); TC-PRV-06-1 TLS arrives with staging |
| 1.2 Port Release 0 | Everything Release 0 does, on the server, for a household | MAT-02, MAT-03, MAT-04, MAT-07, MAT-09, ALC-03, ALC-04, ALC-06, REC-07, REC-08, TAX-04, DSP-03, UX-03, UX-04, UX-05, ING-08, ING-10 | Owner's Release 0 data migrated through the JSON admin import; Appendix A regression suite green on the server. **Built:** the Release 0 pages run on the server for a signed-in household; Appendix A runs against both apps and is green (126 tests on the stack); `mhs-admin import` migrates an ingest file with its attachments, tested with the sample. Open: the owner's real data isn't loaded: ARCHITECTURE.md keeps real data off the local stack, so it waits for the production project (phase 1.6) unless the owner decides to load it locally. These requirements are ported at their Release 0 level and finished in later phases: ING-08 (converter reads XLS only; CSV and XLSX to add), DSP-03 (contact log, no call script), ALC-04 (no member override of splits), REC-07 (no after-OOP-max flag), MAT-02 and ALC-06 (members exist, no per-person reporting yet) |
| 1.3 Ingestion and privacy pipeline | Upload a photo or PDF and get confirmed, pseudonymized data | ING-01, ING-02, ING-03, ING-04, ING-05, ING-07, PRV-01, PRV-02, PRV-03, PRV-04, PLT-04 | Staging Google Cloud project set up; extraction corpus through Document AI meets the accuracy target; outbound capture finds no identifiers (TC-PRV-01-1, TC-PLT-04-1). **Built 2026-10-16 (local):** upload of PDFs, photos, HSA exports (CSV, XLS, XLSX) and insurer claims CSVs; identifiers scrubbed to vault tokens in the application tier; worker classifies into the 8 types and extracts header fields and lines with confidences; member review, correction (kept beside the extracted value) and confirmation; duplicate uploads refused; originals linked and hashed; 13 user scenarios automated (TESTING.md). **Engines built 2026-10-16 (local, branch `feat/r1-ingest-engines`, ADR-034 proposed):** Tesseract OCR for photos (HEIC included) and scanned PDFs in the app tier; Presidio scrubbing on top of the rules (99.5% recall on the synthetic seed set); Claude extraction per household behind `mhs-admin ai-extraction` and a worker flag, with the AI worker routed through `capture` in the test profile and TC-PLT-04-1 automated. **Still open:** Document AI OCR in staging, OCR off the upload request, image blanking from word boxes (TC-PRV-04-1), meeting the 95% accuracy targets on the held-out corpus (TC-ING-02-1, PLT-02; the rules are at 80% and 61.5%), near-duplicate statements and versions (TC-ING-07-2 to 4), email forwarding (TC-ING-01-4), HEIC display and rotation, the staging project |
| 1.4 Matching and reconciliation | Line-level matching and the three money identities | MAT-01, MAT-05, MAT-06, MAT-10, REC-01, REC-02, REC-03, REC-04, REC-05, REC-11, REC-13, ALC-01 | All P1 REC and MAT cases pass; nine statuses live |
| 1.5 Web experience | Visit cards and detail on phone and desktop, household view | UX-01, UX-02, UX-06, UX-10 | UX cases pass at 375px and 1280px |
| 1.6 Hardening and acceptance | Prove it on real visits, in production | none new | Production Google Cloud project with the BAA accepted and Cloud KMS confirmed as covered; restore drill and performance run in staging; full P1 test pass; owner reconciles a month of real household visits; false-positive rate measured |

**Launch gate for anyone outside the owner's household:** CMP-01 to CMP-04 (breach response, consent, privacy policy, disclaimers) and PRV-09 (export and delete), plus a review by a healthcare privacy attorney.

## Release 2

The 47 P2 requirements, grouped:

| Theme | Requirements |
| --- | --- |
| Accuracy and trust | MAT-08 claim versions, REC-06 cost-sharing checks, REC-09 denial codes, REC-10 tolerance, PLT-01 reference tables, PLT-02 accuracy targets, PLT-03 traceability, ING-06 learning from corrections |
| Money detail | ALC-02 payment sources, ALC-05 secondary insurance, ALC-07 visual breakdown, ALC-08 refunds, REC-12 self-pay vs negotiated |
| HSA and tax | TAX-01, TAX-02, TAX-03, TAX-06 to TAX-10 |
| Disputes | DSP-01, DSP-02, DSP-04, DSP-05, DSP-07 |
| Pre-visit strategy | PRE-01, PRE-02, PRE-04 to PRE-07 |
| Experience | UX-07 dashboard, UX-08 export, UX-09 onboarding |
| Privacy and compliance | PRV-05 for analytics (AI requests done in 1.3), PRV-09, PRV-10, CMP-01 to CMP-04, CMP-06 |
| Platform and integrations | ING-09 payer FHIR API, PLT-05 performance, PLT-07 import layer, PLT-08 KPIs |

## Later (P3)

PRE-03 price transparency data, TAX-05 FSA expiry alerts, DSP-06 charity care screening, CMP-05 provider-facing data separation.
