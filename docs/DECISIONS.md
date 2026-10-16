# Decisions

Architecture and product decision records. **Append only:** never delete an entry; supersede it with a new one. Statuses: **Accepted**, **Proposed** (my recommendation, waiting for the owner), **Superseded**. ADR-021 to ADR-028 were proposed and then accepted by the owner on 2026-10-15, together with the ambiguity definitions A-01 to A-13 in TEST_PLAN.md section 1b.

ADR-001 to ADR-007 restate the Release 0 decisions log (D1 to D15 in [MVP_REQUIREMENTS.md](MVP_REQUIREMENTS.md) section 9). The "X-" and "A-" references point to the conflicts and ambiguities in [TEST_PLAN.md](TEST_PLAN.md) section 1.

## Summary

| ADR | Decision | Date | Status |
| --- | --- | --- | --- |
| 001 | Local web app on the owner's machine | 2026-10-09 | Superseded by 012 |
| 002 | Release 0 ingests a JSON file | 2026-10-09 | Superseded by 013 for Release 1 |
| 003 | Use the agreed rate on the EOB; no outside negotiated-rate lookup | 2026-10-09 | Accepted |
| 004 | Payments belong to a provider and are balanced against all its charges | 2026-10-09 | Accepted; extended by 016 |
| 005 | Status order Discrepancy → Balance outstanding → Missing documents → Waiting → Matched | 2026-10-09 | Superseded by 009 |
| 006 | HSA flags are possibilities, not eligibility rulings | 2026-10-09 | Accepted |
| 007 | Release 0 data model choices | 2026-10-09 | Accepted |
| 008 | The built MVP is Release 0; PRD P1 is Release 1 | 2026-10-15 | Accepted |
| 009 | One ordered list of nine visit statuses | 2026-10-15 | Accepted |
| 010 | The HSA is the primary payment vehicle | 2026-10-15 | Accepted |
| 011 | Member decisions win over imports, feeds and new versions | 2026-10-15 | Accepted |
| 012 | Data resides server-side: application tier, back-end tier, identity vault | 2026-10-15 | Accepted |
| 013 | Release 1 ingests uploaded documents; JSON import stays as an admin path | 2026-10-15 | Accepted |
| 014 | Three money identities: adjudication, cost-sharing, settlement | 2026-10-15 | Accepted |
| 015 | Tolerance: under $1.00 auto-clears; $5.00 cumulative cap per provider per year | 2026-10-15 | Accepted |
| 016 | Lump sums split by the statement, else oldest visit first; member can override | 2026-10-15 | Accepted |
| 017 | Visits that never go through insurance need no claim | 2026-10-15 | Accepted |
| 018 | Release 1 scope: lean core + household + Release 0 carry-over | 2026-10-15 | Accepted |
| 019 | Release 1 client is one responsive web app | 2026-10-15 | Accepted |
| 020 | The project moves from light to durable tier | 2026-10-15 | Accepted |
| 021 | Tax tags say "likely", with the IRS Publication 502 category cited | 2026-10-15 | Accepted |
| 022 | No date shifting in the back-end tier; originals and drafts stay in the application tier | 2026-10-15 | Accepted |
| 023 | Home page: summary, then the attention queue, then visit cards | 2026-10-15 | Accepted |
| 024 | The basic network-status agreement check (REC-08) is in Release 1 | 2026-10-15 | Accepted |
| 025 | Per-household keys in a cloud key management service; deletion keeps only security logs | 2026-10-15 | Accepted |
| 026 | HSA import accepts CSV, XLS and XLSX exports | 2026-10-15 | Accepted |
| 027 | Postgres for records and the job queue | 2026-10-15 | Accepted |
| 028 | AI extraction through the Claude API under a data-processing agreement | 2026-10-15 | Accepted |
| 029 | OCR: PDF text layer first, then the cloud host's OCR; Presidio finds identifiers; images blanked from OCR word boxes | 2026-10-16 | Accepted |
| 030 | Build and test locally on Docker Compose; production on Google Cloud | 2026-10-16 | Accepted |

## Records

### ADR-001 · Local web app (Superseded by 012)
Release 0 runs on the owner's laptop with a local database and document folder, bound to 127.0.0.1, no login. Release 0 keeps working this way; Release 1 moves to the server.

### ADR-002 · JSON ingest for Release 0 (Superseded by 013 for Release 1)
Release 0 imports a JSON file built by `tools/build_ingest.py`; automatic extraction came later. Validation is all-or-nothing and records upsert by id.

### ADR-003 · Agreed rate from the EOB (Accepted)
The rate checked is the EOB's allowed amount. Rates printed on provider bills are in the backlog (B-2).

### ADR-004 · Payments belong to a provider (Accepted; extended by 016)
Many providers apply a payment to the account, not a visit. Payments are balanced against all of a provider group's charges; per-visit figures come from an allocation rule.

### ADR-005 · Release 0 status order (Superseded by 009)

### ADR-006 · HSA flags are possibilities (Accepted)
Charges not matched to an HSA payment, and payments from other accounts, are flagged as HSA opportunities without confirming eligibility. Applies to TAX-04 in Release 1; see 021 for TAX-01 and TAX-07.

### ADR-007 · Release 0 data model choices (Accepted)
Plans, accounts and providers live in Settings (D6). Claims and visits link to household members, and providers can be assigned to members (D9). Likely-same providers are explicit relationships, suspected → confirmed or rejected, and flagged until confirmed (D10). Plan limits are a list of type × network × level × member (D12). Provider notes are their own record kind, never touched by imports (D13).

### ADR-008 · Release 0 and Release 1 (Accepted)
The built MVP is Release 0. PRD priorities mean releases: P1 = Release 1, P2 = Release 2, P3 = later. Release 0 behavior is the regression baseline (TEST_PLAN Appendix A). *Conflict X-01.*

### ADR-009 · Nine ordered visit statuses (Accepted)
In dispute → Discrepancy found → Needs review → Balance outstanding → Awaiting EOB → Awaiting documents → Missing documents → Resolved → Complete. The first that applies wins; waiting threshold 30 days, configurable (REC-11). *Conflict X-03.*

### ADR-010 · HSA first (Accepted)
For an HSA-eligible member the HSA pays qualified expenses by default; "save HSA for later" routes them to the receipt vault. FSAs, LPFSAs and HRAs are suggested only when they are the sole tax-advantaged option or would forfeit (TAX-03, TAX-04; TAX-05 moved to P3). *Conflict X-02.*

### ADR-011 · Member decisions win (Accepted)
No import, re-extraction, payer feed or new document version overwrites a member's match, split, merge, correction, setting or deletion. Conflicting data is shown beside the member's version and applied only on the member's say-so (MAT-07, MAT-08). Built into Release 0 import (owner-edit marks, re-checked at confirm). *Conflict X-08.*

### ADR-012 · Server-side data (Accepted)
Clients send data to an application tier, which tokenizes identifiers and passes scrubbed content to a back-end tier for processing and AI. The identity vault is a separate service. Supersedes 001 from Release 1. Consequences: authentication and household isolation become requirements (PRV-11); key custody (025) and date handling (022) need decisions. *Conflict X-04.*

### ADR-013 · Uploads replace JSON import (Accepted)
Release 1 members upload PDFs and photos (ING-01) and confirm extracted fields (ING-05). The JSON importer remains for migrating Release 0 data and for test fixtures.

### ADR-014 · Three money identities (Accepted)
(1) Billed = Plan adjustment + Other savings + Primary paid + Secondary paid + Member responsibility. (2) Member responsibility = Deductible + Copay + Coinsurance + Not covered. (3) Member responsibility = Payments − Refunds + Provider write-offs + Still owed. Self-pay: Billed = Self-pay discount + Member responsibility. ALC-01 holds adjudication buckets only; settlement items live in ALC-03; REC-13 checks identity 3. *Conflict X-05.*

### ADR-015 · Tolerance (Accepted)
Differences under $1.00 per check auto-clear and are recorded; cleared amounts per provider per plan year are flagged past $5.00; unit-price changes are always flagged (REC-10, Release 2). Release 0 and Release 1 check to the cent until REC-10 is built. *Conflict X-06, ambiguity A-14.*

### ADR-016 · Lump-sum allocation (Accepted)
A lump-sum payment is split by the provider's statement when it shows the split, else oldest visit first (the Release 0 rule); the member can override any split, and an override is protected by 011. Overpayment is checked per provider and shown on the visits it was allocated to (MAT-09, ALC-04, REC-03). *Conflict X-07.*

### ADR-017 · Claim-free visits (Accepted)
Self-pay visits and categories such as supplements, equipment and cash-price prescriptions are complete with a receipt or bill plus payment proof, and are never flagged for lacking a claim (REC-05, MAT-10). *Conflict X-12.*

### ADR-018 · Release 1 scope (Accepted)
49 requirements: a lean core of 28, the household (4) and 17 carried over from Release 0. The lean core includes the privacy controls that real health data on a server needs before AI extraction: PRV-03, PRV-04, PRV-07, PRV-08 and PLT-04. CMP-01 to CMP-04 and PRV-09 form a launch gate: nobody outside the owner's household signs up until they are done. The list is in the PRD's "Release 1 scope" section. *Conflict X-09.*

### ADR-019 · Responsive web client (Accepted)
One server-rendered web app works on phone (camera upload, review) and desktop (detailed reconciliation). A native app can follow on the same server (UX-10).

### ADR-020 · Durable tier (Accepted)
With server-side data and other users ahead, the project follows the durable-tier rules: VISION, ARCHITECTURE, ROADMAP, DECISIONS, TESTING and SETUP docs in `docs/`, the runbook in the root `CLAUDE.md`, ADRs before irreversible choices, core coverage ≥ 80%.

### ADR-021 · "Likely" tax tags (Accepted)
TAX-01 tags read "likely qualified", "likely not qualified" or "needs documentation", citing the IRS Publication 502 category; TAX-07 guidance on returning a mistaken distribution always carries the CMP-04 disclaimer and only applies to a genuine mistake. Both are Release 2. *Conflict X-10.*

### ADR-022 · Dates and identity in the tiers (Accepted)
The back-end tier keeps real dates, because plan years, deadlines and matching need them. PRV-05 date shifting applies only to content sent to outside AI services and to analytics. Unredacted originals and drafted letters are produced and stored only in the application tier. *Conflict X-11.*

### ADR-023 · Home page layout (Accepted)
Keep the Release 0 summary tiles at the top, then the "needs your attention" queue ranked by dollars and deadline (UX-04), then visit cards (UX-01). One page, no separate landing screen. *Conflict X-13.*

### ADR-024 · Network check in Release 1 (Accepted)
REC-08's basic agreement check (bill, EOB and provider record agree) is in Release 1 as a Release 0 carry-over; surprise-bill detection under the No Surprises Act stays in Release 2. *Conflict X-14.*

### ADR-025 · Keys, recovery and deletion (Accepted)
The identity vault and originals are encrypted with per-household data keys held in the hosting provider's key management service; recovery is through MFA account recovery, not a member-held key. On account deletion, all records, originals, vault entries and backups (on their normal rotation, within 35 days) are deleted; only security and access logs without health content are kept for one year for breach investigation. *Conflict X-15.*

### ADR-026 · HSA import formats (Accepted)
ING-08 accepts CSV, XLS and XLSX exports, matching what administrators actually provide (the owner's is XLS). *Conflict X-16.*

### ADR-027 · Postgres (Accepted)
Postgres for records (JSONB keeps the Release 0 record-store model and lets the schema evolve) and for the job queue, so Release 1 adds no separate broker.

### ADR-028 · AI extraction service (Accepted)
Field and line extraction uses the Claude API on scrubbed, tokenized content (PLT-04), under a data-processing agreement with no training on the data (MVP ND-9). OCR and identifier scrubbing run before any content leaves the server.

### ADR-029 · OCR and identifier scrubbing (Accepted)
Read a PDF's own text layer when it has one (as Release 0's converter does). Otherwise, for photos and scans, use the production cloud host's OCR service inside the same account and BAA (Google Document AI Enterprise OCR or AWS Textract), so unredacted images never leave the hosting boundary. Microsoft Presidio (open source, on the server) detects identifiers in the OCR text, and the back-end tier receives the text with identifiers replaced by tokens (PRV-01) plus images blanked using the OCR word boxes (PRV-04); Presidio's own image redactor is alpha, so it isn't used. OCR sits behind one interface: local development uses Tesseract, which keeps the stack offline, and the extraction corpus measures the cloud engine against the 95% target (PLT-02).

### ADR-030 · Local first, Google Cloud for production (Accepted)
**Decision.** Release 1 is built and tested on a local Docker Compose stack, then deployed to Google Cloud: Cloud Run for the application tier and back-end workers, Cloud SQL for PostgreSQL, Cloud Storage for originals, Cloud KMS for per-household keys (ADR-025) and Document AI Enterprise OCR (ADR-029). Supersedes nothing; settles the hosting question in ARCHITECTURE.md.

**Why Google Cloud over AWS** (comparison of 2026-10-16; prices approximate, check before budgeting):

| | Google Cloud | AWS |
| --- | --- | --- |
| Container hosting | Cloud Run: deploy a container, scales to zero, pay per request; jobs for workers | ECS Fargate or App Runner; Fargate needs a load balancer (about $16+/month) and, in private subnets, a NAT gateway (about $32+/month) |
| Smallest managed Postgres | Cloud SQL shared-core, roughly $9 to $13/month (no SLA on shared core) | RDS db.t4g.micro, similar price |
| OCR with word boxes | Document AI Enterprise OCR, $1.50 per 1,000 pages | Textract, similar per-page pricing |
| HIPAA BAA | Accepted in the console; Cloud Run, Cloud SQL, Cloud Storage and Document AI are on Google's covered list | Accepted in AWS Artifact; the widest eligible-services list and healthcare ecosystem |
| Fixed monthly floor for a household | Lowest (mostly the database) | Higher (load balancer, NAT) unless built carefully |
| Setup effort | Less networking and IAM to get right | More: VPC, subnets, IAM roles |

AWS would win for a large provider-facing or enterprise healthcare product, or with existing AWS skills. For a household-scale app built by one owner, Google Cloud's lower fixed cost and simpler deploys win.

**Consequences.**
- Code reaches cloud services only through four small interfaces, so the local stack runs offline and a move to AWS stays possible: records (Postgres, identical everywhere), object storage (local folder ↔ Cloud Storage), keys (local key file ↔ Cloud KMS), OCR (Tesseract ↔ Document AI).
- Before any real household data goes to Google Cloud: accept the BAA in the console, and confirm Cloud KMS on Google's HIPAA covered-products table (search results confirmed the other four services but not KMS).
- Local and staging environments never hold real data; staging is a separate Google Cloud project with synthetic data only.

