# Roadmap

**Current phase: 1.6, Release 1 acceptance (next).** On `main` (2026-10-17, tag `r1-web-experience`): phases 1.1 to 1.5 and the local build of 1.3, with the Google Cloud adapters against emulators (ADR-036), account recovery (ADR-037), export and delete (ADR-038), forwarded email (ADR-039), the access log (ADR-040), the web experience (ADR-041), the extraction corpus and a local performance run; ADR-031 to ADR-041 accepted. Still open in 1.3: the staging project (needs the Google Cloud account) and the Claude accuracy run (needs an API key): the layout rules score 80% classification and 61.5% amounts on the held-out corpus against the 95% targets.

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
| 1.3 Ingestion and privacy pipeline | Upload a photo or PDF and get confirmed, pseudonymized data | ING-01, ING-02, ING-03, ING-04, ING-05, ING-07, PRV-01, PRV-02, PRV-03, PRV-04, PLT-04 | Staging Google Cloud project set up; extraction corpus through Document AI meets the accuracy target; outbound capture finds no identifiers (TC-PRV-01-1, TC-PLT-04-1). **Built 2026-10-16 (local):** upload of PDFs, photos, HSA exports (CSV, XLS, XLSX) and insurer claims CSVs; identifiers scrubbed to vault tokens in the application tier; worker classifies into the 8 types and extracts header fields and lines with confidences; member review, correction (kept beside the extracted value) and confirmation; duplicate uploads refused; originals linked and hashed; 13 user scenarios automated (TESTING.md). **Engines built 2026-10-16 (local, branch `feat/r1-ingest-engines`, ADR-034 proposed):** Tesseract OCR for photos (HEIC included) and scanned PDFs in the app tier; Presidio scrubbing on top of the rules (99.5% recall on the synthetic seed set); Claude extraction per household behind `mhs-admin ai-extraction` and a worker flag, with the AI worker routed through `capture` in the test profile and TC-PLT-04-1 automated. **Still open:** Document AI OCR in staging, meeting the 95% accuracy targets on the held-out corpus (TC-ING-02-1, PLT-02; the rules are at 80% and 61.5%), email forwarding through a production inbound-mail service (built locally, ADR-039), the staging project |
| **1.4 Matching and reconciliation** (built 2026-10-17) | Line-level matching and the three money identities | MAT-01, MAT-05, MAT-06, MAT-10, REC-01, REC-02, REC-03, REC-04, REC-05, REC-11, REC-13, ALC-01 | All P1 REC and MAT cases pass; nine statuses live. **Built on `feat/r1-reconciliation` (ADR-035):** claims per visit by claim number; identities 1 and 2 per claim and per EOB line, identity 3 per visit and per provider, with the $1.00 tolerance and the $5.00 yearly cap per provider; bill lines paired with EOB lines (bundled, panel, modifier); missed adjustment and balance billing; overpayment shown on the visit; duplicate charges; bills without a claim; the nine statuses on both apps; document checklist per visit; adjudication buckets per line, visit and year; match scores with reasons for uploads and the claims export; the member confirms or rejects matches, splits statements, merges visits, splits payments, opens and closes disputes, closes findings and sets the waiting threshold, all kept on re-import (ADR-011). All 56 automated P1 cases mapped in TESTING.md; 307 tests on the stack. Merged into `main` 2026-10-17. Open: DSP-01 cases replace the minimal dispute later; MAT-08 version history |
| **1.5 Web experience** (built 2026-10-17) | Visit cards and detail on phone and desktop, household view | UX-01, UX-02, UX-06, UX-10 | UX cases pass at 375px and 1280px. **Built and merged 2026-10-17 (ADR-041):** Home in the ADR-023 order (summary and the nine statuses, then "Needs your attention" ranked by dollars then age with each reason in a sentence, then visit cards with person, provider, date, badge, documents received and amount at issue); the visit page with a jump list to what's wrong, line by line (lines that disagree highlighted with the difference), who pays what, documents and a case history; a Household page with each person's totals, an unassigned row and the family's, and a "Showing" switch between the family and one person kept across pages; on phones a bottom bar (Home, Visits, Add, Household, Providers), 44px tap targets and a one-tap "Take a photo" upload. All P1 UX cases for these four requirements automated, with the layout cases in headless Chromium at 375 and 1280 px on both apps (TESTING.md "Web experience"). Open: the camera on a real phone waits for staging (the local stack is loopback only) |
| 1.6 Hardening and acceptance | Prove it on real visits, in production | none new | Production Google Cloud project with the BAA accepted and Cloud KMS confirmed as covered; restore drill and performance run in staging; full P1 test pass; owner reconciles a month of real household visits; false-positive rate measured. **False-positive tracking built 2026-10-18 on `feat/r1-false-positives` (ADR-044 proposed):** closing a finding (or a dispute) asks whether it was a real problem or wrong, with an optional reason, kept as a member decision; the rate (wrong over decided, target 5% or less) per kind and overall on the member's Finding accuracy page and in `mhs-admin false-positives` for the owner, counts only, by period and release; TC-PLT-02-2 automated. To measure: close every finding on the month's visits, then run the report for that period |

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
