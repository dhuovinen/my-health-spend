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
| 031 | Foundation build: roles and row-level security per household, envelope encryption per service, TOTP sign-in, passphrase-sealed vault backup | 2026-10-16 | Accepted |
| 032 | Release 0 pages shared by both apps; Release 1 imports by upload only, files encrypted, edits and history per household | 2026-10-16 | Accepted |
| 033 | Upload pipeline: exports parsed in the app tier; documents read and scrubbed in the app tier, extracted by the worker, confirmed by the member | 2026-10-16 | Accepted |
| 034 | Ingestion engines: Tesseract OCR and Presidio in the app tier; Claude extraction per household, off by default, through a worker that only it routes out of | 2026-10-16 | Accepted with a condition |

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

### ADR-031 · Foundation build choices (Accepted)
Implementation choices for phase 1.1 inside ADR-012, 025, 027 and 030. Proposed by the build session and accepted by the owner as written on 2026-10-16.

**Decision.**
- **Household isolation in the database, not only in code.** Each tier connects as its own Postgres role (`mhs_app`, `mhs_worker`, `mhs_vault`); a one-shot `migrate` job owns the tables. Household tables have row-level security keyed on a per-transaction setting (`mhs.household_id`), and every repository query also filters by household. A query that forgets the household returns nothing. The worker role has no grant on accounts, sessions or the vault schema.
- **Envelope encryption per service.** The application tier and the vault each have their own key-encryption key (a key file locally, a Cloud KMS key later) and their own per-household data keys, stored only in wrapped form. Content is AES-256-GCM with the household and object id as associated data, so a ciphertext moved to another household or object fails to decrypt. The worker has no key.
- **Sign-in.** Email and password (Argon2id, at least 12 characters), then a TOTP code (RFC 6238) on a second step; no data route works until both pass. Server-side sessions: only a hash of the cookie is stored; 15-minute idle and 12-hour absolute timeouts; the token rotates after MFA. Five failed attempts lock the account for 15 minutes; a TOTP code can't be reused. Members are created and MFA is reset with an admin command until MFA account recovery (TC-PRV-07-3) is built.
- **Vault backup.** `mhs-vault backup` writes the vault rows (entries already encrypted, data keys still wrapped) sealed with a passphrase (scrypt, then AES-256-GCM). Restoring needs the passphrase and the vault's key-encryption key, which therefore has to be backed up separately (Cloud KMS keeps it in production).
- **Secrets locally.** A one-shot `setup` job generates the database passwords, the vault service token and the key files into a Docker volume on first `docker compose up`; each service mounts only its own subfolder. Nothing secret is in the repository.
- **Code layout.** Adapters for records, queue, object storage and keys in `data/`; OCR and the worker in `ingest/`; the vault service, client and backup in `vault/`; the application tier in `web/household/`, beside the untouched Release 0 app.

**Consequences.** Two compose services beyond the four in ARCHITECTURE.md (`setup` and `migrate`, both one-shot). Losing a key file loses that service's data locally, so the key files must be backed up with the vault backup. The test suite starts a throwaway Postgres container when no test database is given, so `uv run pytest` needs Docker for the Release 1 tests (they skip without it).

### ADR-032 · Porting Release 0 to the server (Accepted)
Implementation choices for phase 1.2. Proposed by the build session and accepted by the owner as written on 2026-10-16.

**Decision.**
- **One set of pages.** The Release 0 routes and templates move into a shared module (`web/pages.py`) that both apps mount. Release 0 (`uv run mhs`) hosts them over its SQLite store; the Release 1 application tier hosts them behind MFA sign-in, over a household-scoped Postgres store with the same interface. The Release 0 test suite (TEST_PLAN Appendix A) runs against both apps, so the two can't drift apart.
- **Pages work under the Content Security Policy.** Inline styles and inline event handlers leave the templates for `style.css` and one small same-origin script (`/static/app.js`); every form carries a CSRF token in Release 1.
- **Imports in Release 1 are by upload only.** A member uploads the ingest JSON together with its attached statement and EOB files; the server never reads a path a member types. Attached files are stored encrypted with the household's data key and hashed (ING-10). The admin command `mhs-admin import` reads a path inside the app container, for migrating Release 0 data.
- **Member edits and import history per household.** Owner-edit marks (ADR-011) and the import log become household tables with row-level security, so one household's edits never protect or expose another's.
- **Settings for the converter by download.** Release 1 has no `data/settings.json`; Settings offers the same file as a download for `tools/build_ingest.py`.
- **Uploaded originals are their own kind.** Phase 1.1 uploads (photos and PDFs awaiting extraction in phase 1.3) are stored as `original` records at `/uploads`, apart from the ingest `document` records the engine reconciles.

**Consequences.** Release 0 gains the same template changes (no visible difference). The import preview is held in the app process between preview and confirm, keyed by household, which is fine for one app instance and must move to the database before Cloud Run runs more than one.

### ADR-033 · Upload pipeline, first build (Accepted)
How uploads become reconciled data in phase 1.3, inside ADR-012, 028 and 029. Proposed by the build session and accepted by the owner as written on 2026-10-16.

**Decision.**
- **Two paths by what is uploaded.** Structured exports (the HSA administrator's CSV, XLS or XLSX, ING-08; the insurer's claims CSV) are parsed in the application tier into ingest records and go through the existing import preview and confirm step. Documents (PDFs and photos of provider statements, itemized bills and EOBs) go through extraction and member review.
- **Read and scrub in the application tier, extract in the worker.** The application tier reads a PDF's text layer (ADR-029) and replaces identifiers with vault tokens (PRV-01, PRV-03, PRV-04) before anything is queued. The worker, which holds no key and has no route out, classifies the scrubbed text into the eight ING-02 types and extracts header fields and lines with a confidence per field. The member sees the fields re-identified, corrects them, and confirms; only then do records enter reconciliation (ING-05). Every correction is kept with the extracted value, so what the machine concluded stays visible (PLT-04).
- **First implementations behind the interfaces.** Extraction uses layout rules: the statement layout Release 0's converter reads, plus label-based rules for EOBs and statements in general. The scrubber uses the household's known names, labelled identifiers (patient, member ID, account number, date of birth) and patterns (SSN, phone, email, street address). Photos are stored and reviewed by hand until OCR is added. Presidio (ADR-029), Tesseract and Document AI OCR (ADR-029) and Claude extraction (ADR-028) plug in behind the same scrubber, OCR and extractor interfaces later; this keeps the stack offline and the tests deterministic.
- **Originals stay linked and unchanged.** A confirmed document carries the original's id and a copy sealed under the document id; its SHA-256 equals the upload's (ING-10). An exact duplicate upload (same SHA-256 in the household) is refused (ING-07); HSA transactions get ids derived from their content, so overlapping exports don't duplicate them.

**Consequences.** Until OCR and AI extraction arrive, documents in layouts the rules don't know come back mostly empty for the member to fill in, and photos always do. Near-duplicate statements (ING-07 TC-3/4) and the extraction corpus accuracy run (PLT-02) are not covered yet.

### ADR-034 · Ingestion engines: OCR, Presidio, Claude extraction (Accepted with a condition)
Implementation choices for the rest of phase 1.3, inside ADR-028, ADR-029 and ADR-033. Proposed by the build session and accepted by the owner on 2026-10-16 with one condition: Claude extraction stays off for any household with real data until PRV-05 date shifting is built, because ADR-022 shifts dates before data goes to an outside AI service and this build sends real service dates; synthetic data only until then. The default model stays `claude-opus-5-5` until the extraction corpus run (PLT-02) compares models.

**Decision.**
- **OCR in the application tier with Tesseract** (`MHS_OCR_ENGINE=tesseract`, installed in the image). Photos (JPG, PNG, WebP, and iPhone HEIC converted with pillow-heif) are turned upright from their EXIF orientation; scanned PDF pages are rendered at 300 DPI (pypdfium2, no system dependency). Pages with a text layer keep it; only pages without one are OCR'd. The result carries word boxes as page fractions for image blanking later (PRV-04) and a mean word confidence, which caps every extracted field's confidence so weak scans are marked for checking. Photos that can't be opened are refused at upload with a plain reason. Document AI replaces Tesseract in Google Cloud behind the same interface.
- **Presidio on top of the rules** (`MHS_SCRUBBER=presidio`, spaCy `en_core_web_md`, 32 MB; `lg` found nothing more on the synthetic set). The rules run first (member names, labelled identifiers, patterns, plus names after words like "Dear" or "spoke with" and full street, city, state and ZIP addresses); people Presidio finds join the known names so every spelling gets one token (PRV-03); then Presidio's remaining finds (names, places, phone, email, SSN, card and bank numbers) are tokenized. Dates stay (ADR-022). The household's own providers and insurers are kept, because extraction needs them. Recall on the synthetic seed set: 99.5% of 190 planted identifiers (rules alone 89.5%), nothing else touched.
- **Claude extraction is per household, off by default.** An operator turns it on with `mhs-admin ai-extraction --household <id> on` (ADR-028's data-processing agreement is a deployment decision, not a member click; the Uploads page then says AI reads the scrubbed text). The app queues those documents as `extract_ai` jobs; only a worker started with `MHS_EXTRACTOR=claude` takes them, and a worker without AI reads one with the rules after a minute, so nothing waits forever. Model `claude-opus-5-5` (`MHS_AI_MODEL`) with structured JSON output against a fixed schema, effort `medium`, and the API's server-side fallback on refusals. Every value the model returns is checked against the scrubbed text it was sent; a value the text doesn't show is kept but marked "not found in the document text" with low confidence, and the arithmetic checks run as for the rules. Refusals, errors and malformed answers fall back to the rules with a note on the review page; log lines and job errors never carry document text. The review page names the model, and the extraction record keeps what the AI concluded beside the member's corrections (PLT-04).
- **The worker's way out is explicit.** The worker has no route out of the backend network; it reaches the AI service only through `MHS_AI_PROXY`. In the compose test profile that is `capture`, which answers with recorded responses (`tests/fixtures/ai`) and logs every request, so TC-PLT-04-1 runs on every test run without a key or network access.

**Consequences.** The image grows from about 460 MB to 1.15 GB (Tesseract, spaCy with its model, numpy, the Anthropic SDK); `UV_NO_CACHE` keeps uv's download cache out of the layers. OCR runs in the upload request, about a quarter of a second per page; long scans make the upload slow until OCR moves to a background task in the app tier. PRV-05 date shifting for AI payloads (ADR-022, P2) is not built: AI requests carry real service dates. A production deployment needs an egress path for the AI worker (a proxy or a NAT rule for the Anthropic API only) and the API key as a secret. The extraction corpus run (PLT-02) has not measured either extractor yet.

