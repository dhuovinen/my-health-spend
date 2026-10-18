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
| 015 | Tolerance: under $1.00 auto-clears; $5.00 cumulative cap per provider per year | 2026-10-15 | Accepted; amended by 035 |
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
| 035 | Matching and reconciliation: claims by claim number, line pairing, the $1.00 tolerance in Release 1, what "still owed" means before the EOB, member decisions stored on the records they change | 2026-10-16 | Accepted |
| 036 | Google Cloud adapters over REST (Cloud Storage, Cloud KMS, Document AI), chosen by environment variables; import previews sealed in the database | 2026-10-16 | Accepted |
| 037 | Self-service account recovery with single-use recovery codes, shown once at enrolment | 2026-10-16 | Accepted |
| 038 | Export and delete: a re-importable ZIP; deleting the last member deletes the household at once, a security log line stays a year | 2026-10-16 | Accepted |
| 039 | Forwarded email: a private address per household, members' own addresses only, attachments and statement bodies become uploads | 2026-10-17 | Accepted |
| 040 | Access log: member views and changes logged per household, readable by members, append-only for the app | 2026-10-17 | Accepted |
| 041 | Web experience: home order, amount at issue, a household view kept in a cookie, phone layout with a bottom bar and 44px targets, browser layout tests | 2026-10-17 | Accepted |
| 042 | Dispute cases on the visit record: four dated statuses, follow-ups and deadlines in the attention queue, a call log on provider notes, letters drafted on request in the application tier and never stored, outcomes feeding lifetime savings | 2026-10-18 | Proposed |

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
**Amended by ADR-035 (2026-10-17):** the tolerance applies in Release 1 already, not only once REC-10 is built.

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

**Condition met (2026-10-16).** PRV-05 date shifting is built for AI requests: the worker shifts every date in the scrubbed text by a random per-person offset (30 to 365 days either way, kept in the household's records, never sent) just before the call, and shifts the dates in the answer back, so stored records keep real dates (TC-PRV-05-1, TC-PRV-05-2). Real household data still waits for the production project and the data-processing agreement (ADR-028).

### ADR-035 · Matching and reconciliation, first build (Accepted)
Implementation choices for phase 1.4, inside ADR-004, 009, 011, 014 to 017. Proposed by the build session on 2026-10-16 and accepted by the owner on 2026-10-17. One choice changes an accepted decision: ADR-015 said Release 1 checks to the cent until REC-10 is built; this applies its tolerance now (TC-REC-03-5 is a P1 case that needs it).

**Decision.**
- **Claims and versions.** Every EOB on a visit is a claim. EOBs with the same claim number are versions of one claim and the latest processed one counts; EOBs with different claim numbers are separate claims (a facility and a professional claim) and the visit adds them up. EOBs without a claim number on one visit are treated as versions, as Release 0 did. Showing the version history side by side is MAT-08 (Release 2).
- **The three identities** (ADR-014) are checked per claim and per EOB line: (1) billed = plan adjustment + other savings + primary paid + secondary paid + member responsibility, with the adjustment taken as billed − allowed when the EOB prints only the allowed amount; (2) member responsibility = deductible + copay + coinsurance + not covered, checked only when the EOB breaks the member's share down; and the lines must add up to the claim. Self-pay visits check billed = self-pay discount + member responsibility on the bill. (3) Settlement is checked per visit and per provider: member responsibility = payments − refunds + provider write-offs + still owed. A remainder the documents don't explain (a visit that drops off a statement with no payment, or a statement balance lower than the payments and write-offs explain) is a finding.
- **Tolerance in Release 1.** A difference under $1.00 in a money check (an identity, bill against EOB, overpayment, an unexplained settlement remainder) is "cleared within tolerance": recorded and shown on request, not a finding. Cleared amounts are added up per provider per plan year and the provider is flagged past $5.00. Balances owed, duplicate charges and network status are never cleared. Making the tolerance configurable and the unit-price rule stay in REC-10 (Release 2).
- **Line pairing (MAT-06).** Bill lines (statement items, which now keep their CPT/HCPCS code, date and units) pair with EOB lines by code, then by base code when only the modifier differs (noted), then by date and charge; a bill line can pair with an EOB line plus the components the insurer bundled into it (CARC 97, noted), and several bill lines with one EOB line whose charge is their sum. Lines left over are listed with their amounts but are not findings on their own, because missing line detail is common and the claim totals already catch the money. Duplicate charges (REC-04) are the same code, date and provider twice on one statement, unless a repeat modifier (76, 77, 91, 59, X{EPSU}) or units say otherwise; the same lines on two statements are not duplicates.
- **What "still owed" means.** For an insured visit, what the member owes is the EOB's member responsibility (summed over its claims). Payments are allocated up to that amount, so paying an inflated bill shows as an overpayment on the visit it was allocated to (REC-03), and "at stake" takes the larger of the bill-against-EOB difference and the overpayment, since they are the same dollars. Before the EOB arrives the statement's ask is used, but within the waiting threshold the visit is Awaiting EOB, not Balance outstanding (REC-02); past the threshold the statement's ask counts as owed and a "provider may not have filed with insurance" finding appears (REC-05). That finding is a missing-document finding (status Missing documents unless a balance is owed), not a discrepancy.
- **Allocation order (ADR-016).** A split the member set on a payment comes first and is used exactly; then the provider's statement split (the payments it credits to each visit); then oldest visit first; anything left is an overpayment on the latest visit before the payment and a credit at the provider. Refunds offset overpayments first, latest visit first.
- **Statuses (ADR-009).** In dispute: the member opened a dispute on the visit (a minimal case until DSP-01, Release 2). Discrepancy found: a money check, duplicate, network or settlement finding fails. Needs review: a document linked by a proposed match the member hasn't confirmed. Balance outstanding, Awaiting EOB, Awaiting documents, Missing documents as in REC-11, from a document checklist per visit (MAT-10): EOB for insured visits; receipt for supplements and equipment; bill or receipt for prescriptions and self-pay visits; payment proof when something is owed; an itemized bill only when the member asks for one; the member can mark any of them not applicable or expected. Resolved: a finding the member closed (by closing a dispute or marking the finding dealt with), or an overpayment a refund cleared. The waiting threshold (30 days) is a household preference record that imports never touch.
- **Match scores (MAT-05).** Same provider (or a provider group) 0.35, same service date 0.35 (1 to 3 days apart 0.2, up to 14 days 0.1), same household member 0.2 (unknown on one side 0.1), the same claim number as a document already on the visit 0.3, the same billed amount 0.2; capped at 1. Another member's visit or another provider never matches. 0.9 or more links automatically, 0.6 to 0.9 links as a proposal the member confirms (the visit is Needs review), below 0.6 makes a new visit; two candidates within 0.05 of each other are only proposed. Used when an EOB or statement is reviewed after upload and for each claim in an insurer's claims export.
- **Member decisions live on the records they change** and are marked as member edits (ADR-011), so imports keep them unless the member ticks "Replace my edits": a payment's split (`allocations`), a document's link and match decision (`visit_id`, `match`, with the visits the member rejected so they are never proposed again), and on the visit its payment path (insurance or self-pay), dispute, closed findings and document expectations. Splitting moves statement lines or items to another visit; merging moves every document, payment split and note of one visit to the other and deletes the empty visit; a visit that still has documents can't be deleted.

**Consequences.** Release 0's five statuses become nine on both apps (TEST_PLAN Appendix A's ⚠ test is updated). The ingest schema gains the fields above (all optional, so existing files stay valid). A statement uploaded before its EOB now reads Awaiting EOB for 30 days rather than Balance outstanding. Pending the owner's acceptance, the tolerance change can be reverted by setting it to zero in one constant.
### ADR-036 · Google Cloud adapters, built before the account (Accepted)
How the four adapters (ARCHITECTURE.md "Environments", ADR-030) reach Google Cloud, built and tested locally so staging becomes configuration. Proposed by the build session on 2026-10-16 and accepted by the owner on 2026-10-17.

**Decision.**
- **REST over httpx, not the client libraries.** Cloud Storage (JSON API), Cloud KMS (`encrypt`/`decrypt`) and Document AI (`process`) are called over HTTPS with httpx, which the app already uses; `google-auth` supplies the access token (the Cloud Run service account through the metadata server). The gRPC client libraries would add several hundred megabytes to an image that is already 1.15 GB, for three calls each.
- **Chosen by environment variables, local by default.** `MHS_OBJECT_STORE=gcs` with `MHS_GCS_BUCKET`; `MHS_KEYS=kms` with `MHS_KMS_KEY` (one key per service and environment: the app's and the vault's, as the two key files are now); `MHS_OCR_ENGINE=documentai` with `MHS_DOCAI_PROCESSOR`. The envelope encryption, per-household data keys and object layout don't change; KMS takes the place of the key file only.
- **Tested without an account.** Cloud Storage against the fake GCS server in the compose test profile; KMS and Document AI against fakes that answer in the APIs' request and response shapes. HEIC photos are converted to JPEG before Document AI, which doesn't take HEIC.
- **Import previews in the database.** The preview between "Check" and "Confirm" (ADR-032 kept it in the app's memory) is stored per household with row-level security, sealed with the household's data key because it can hold attached statements, and expires after an hour. The plan is computed again at confirm, as the importer already re-checks member edits there. More than one app instance can then serve a household. Release 0 keeps its in-memory preview.

**Consequences.** The adapters have only met emulators and fakes; the first staging run (phase 1.3) is where they meet the real services, and any differences in error handling show up there. Nothing here needs the account, so the owner's first steps (project, billing, the BAA, the KMS key ring) are listed in DEPLOYMENT.md.
### ADR-037 · Self-service account recovery (Accepted)
How a member who loses their phone, their password or both gets back in (PRV-07, TC-PRV-07-3), replacing the admin reset as the normal path. Proposed by the build session on 2026-10-16 and accepted by the owner on 2026-10-17.

**Decision.**
- **Recovery codes, not email.** The app sends no email, and a reset by email would make the mailbox the weakest factor. Each member gets ten single-use codes of 50 random bits (`XXXXX-XXXXX`), shown once: on the enrolment page beside the authenticator QR code, after a recovery, and when a signed-in member makes new ones on the Account page (which asks for a current authenticator code). Only SHA-256 hashes are stored; codes this random don't need a slow hash. Making new codes voids the old set.
- **One code replaces both factors.** "Forgot your password or lost your phone?" takes the email and a code. A wrong code counts toward the same lock as a wrong password (five tries, 15 minutes), and an unknown email gets the same answer. A right code is used up, the member's sessions end, and a 15-minute recovery link (its own kind of link, so an enrolment link can't change a password and a recovery link can't show a QR code) asks for a new password, then shows a new authenticator QR code and ten new codes.
- **Nothing else changes.** Household data, keys and vault entries are untouched, so everything is there after the next sign-in. `mhs-admin reset-mfa` stays for a member with no codes left.

**Consequences.** A member who loses both their phone and their codes still needs an admin. Anyone holding a member's email and one unused code can take over the account, as with any recovery code scheme; the Account page shows how many codes are left so a member notices one going missing.
### ADR-038 · Export and delete (Accepted)
How PRV-09 and ADR-025's deletion rule are built, ahead of the launch gate. Proposed by the build session on 2026-10-16 and accepted by the owner on 2026-10-17.

**Decision.**
- **Export** is a ZIP any member can download from "Your data" after typing their password: the household's records as an ingest file with the attached files beside it (so it imports again), the uploads with what was read from them and the member's corrections, the identifiers behind the tokens (from the vault), and a manifest with counts and a SHA-256 per file.
- **Deleting an account** needs the password, a current authenticator code and typing DELETE. If other members remain, only that member's account goes. If it is the last member, the household goes at once: the vault deletes its entries and its data key first (if the vault can't be reached nothing is deleted, so the member can try again), then the stored files, then every record and the app's household data key with the household row. Deleting the data keys makes anything left behind (a stray copy, a backup) unreadable.
- **The security log** (`app.security_log`) records exports and deletions with the household and member ids, the event and the time, and nothing else; it has no foreign key, so the record of a deletion survives the household, and lines older than a year are removed.

**Consequences.** One member can delete the household only as its last member, so a household with two adults needs both to leave. Database backups and vault backup files keep the data until they rotate out (within 35 days in production, DEPLOYMENT.md); local vault backup files are not rotated automatically.

### ADR-039 · Forwarded email (Accepted)
How ING-01's forwarded email (TC-ING-01-4) works. Proposed by the build session on 2026-10-17 and accepted by the owner on 2026-10-17.

**Decision.**
- **One private address per household** (`<random token>@<inbound domain>`), shown on the Uploads page. The token is the only thing that routes mail to a household, so it is random and can be replaced.
- **Only the household's members' own email addresses are accepted** as senders; anything else is refused at SMTP and nothing is stored. Locally the `From` header is taken on trust; in production the inbound-mail service's sender checks (SPF, DKIM, DMARC) must pass before a message is handed over.
- **What becomes an upload:** each PDF or photo attachment, also inside a forwarded message; a message without one becomes an upload only when its body (HTML or text) reads as a statement, bill or EOB. Other attachments are skipped, the same file twice is a duplicate, and a message with nothing usable is refused. From there it is the Uploads page's path: stored sealed, scrubbed, read by the worker, reviewed and confirmed.
- **Locally an SMTP service** (`mhs-mail`, the `mail` container on the internal network); in production an inbound-mail service posts the raw message to the same handler, which needs an account and a domain with an MX record (DEPLOYMENT.md).

**Consequences.** An attacker who learns a household's address and fakes a member's `From` could add uploads locally, but they still wait for a member's review; production relies on the sender checks. Email bodies are stored as uploads like any other original, sealed with the household key.

### ADR-040 · Access log (Accepted)
PRV-10 (P2, built early because it needs no account): who looked at or changed which record. Proposed by the build session on 2026-10-17 and accepted by the owner on 2026-10-17.

**Decision.**
- **What is logged:** every change a member makes through the app (records created, changed or deleted, through Settings, notes, imports or confirming an upload), and their views of a visit, an upload's review, and downloads of stored files, plus exports. Each entry has the member, the action, the record's kind and id, and the time. Work the worker does on its own (reading an upload) isn't a member's action and isn't logged as one.
- **Where:** `app.access_log`, per household with row-level security; the application tier's role can add and read entries but has no right to change or delete them, so an edit is impossible from the app (TC-PRV-10-2). Members read the last 200 entries on "Your data".
- **How:** the household store logs changes when it acts for a member (the pages and uploads pass the signed-in member); views go through one hook per route. Release 0 has one owner and no log.

**Consequences.** Record ids name providers and dates, so the log goes with the household when it is deleted (ADR-038); the security log keeps the deletion itself. List pages (visits, providers) aren't logged entry by entry; the visit detail is.

### ADR-041 · Web experience, first build (Accepted)
Implementation choices for phase 1.5 (UX-01, UX-02, UX-06, UX-10), inside ADR-019 and ADR-023. Proposed by the build session on 2026-10-17 and accepted by the owner as written on 2026-10-17. Nothing here is hard to undo; it is recorded because it settles how two test cases are read and adds a cookie and a test dependency.

**Decision.**
- **Home order (ADR-023).** The summary first: the four tiles and a row of the nine statuses with their counts. Then "Needs your attention", ranked by the dollars on the visit (at stake plus still owed), then oldest first, with the rule printed under it and each item's reason in a plain sentence (the open finding, else the status's help). Then the year's visits as cards, newest first, the first twelve with a link to all of them. HSA, plan limits and where the billed dollars went follow as "The year in detail".
- **Amount at issue on a card (TC-UX-01-3)** is the visit's at-stake amount from ADR-035: the open money findings, with the same dollars counted once (a bill's excess that was also paid is one amount, not two). Closing a finding takes it off the card. A balance still owed is shown beside it, not added to it.
- **Visit detail (UX-02)** keeps one page with five named sections in this order, each reachable from a jump list at the top: what's wrong (findings), line by line (bill lines against EOB lines, with the difference on each line that disagrees), who pays what (where the billed amount went, payments applied, where your share stands), documents (checklist, EOBs, statements, receipts), and case history (one timeline, newest first, built from what the records already hold: service date, statements, EOBs, payments applied, expectations the member set, the dispute, closed findings and notes about the visit). No new records.
- **One change to `core/`.** Plan-limit progress now carries the member an individual limit is for (`LimitProgress.member_id`), and `core/household.py` adds the per-person totals: both are reconciliation facts UX-06 needs (each person's deductible, totals that add up to the family's), not presentation, so they live with the engine as pure functions.
- **Household view (UX-06).** A Household page lists each member's visits, billed, insurer paid, paid by you, still owed and at issue, a "not assigned to anyone" row when some visits have no member (or one no longer in Settings), and the family total, which is the sum of the rows. A switch "Showing: Family / a member" sits on Home, Visits and Household; the choice is kept in a cookie (`mhs_view`, the member's record id, HttpOnly, SameSite=Lax so a link from elsewhere keeps it, Secure where sign-in cookies are, for the browser session) so it holds across pages; signing in, signing out and deleting the account clear it. Visits starts filtered to that person unless another member filter is chosen. An individual view filters the tiles, statuses, attention queue, cards and plan limits to that person; HSA figures stay the family's and say so. Set by a form post (CSRF-checked in Release 1); an unknown id falls back to Family.
- **Phones (UX-10).** At 860px and narrower, and on touch screens, every control is at least 44px tall; the top bar keeps the brand, Help, Settings and Account, and the pages move to a bottom bar within thumb reach: Home, Visits, Add, Household, Providers. Add opens Uploads in Release 1 (Import in Release 0). Uploads gets a "Take a photo" button that opens the camera and uploads as soon as the photo is taken, next to a plain "Choose a file" form; the old single input asked for the camera only, which kept phone users from choosing a PDF. "Your data" and "Sign out" sit on the Account page on a phone. Tables scroll inside their cards; nothing scrolls sideways.
- **Layout tests.** TC-UX-10-1 and TC-UX-10-2 run in headless Chromium through Playwright (a dev dependency) at 375 by 812 (phone emulation) and 1280 by 800, on both apps, measuring page width, tap target sizes and that every visit section is on screen. They skip where no browser is installed; the compose `tests` image installs Chromium so the stack run includes them.

**Consequences.** The home page grows a card list and gets longer on a phone; the year-detail panels move below it. A member's view choice is per browser, not per account. The test image is larger by the browser (about 300 MB).

### ADR-042 · Dispute cases (Proposed)
How Release 2's disputes are built (DSP-01, DSP-02, DSP-04, DSP-05, DSP-07, and DSP-03's call script), replacing the minimal dispute of ADR-035, inside ADR-011 and ADR-022. Proposed by the build session on 2026-10-18. Recorded before building because two choices are hard to undo: where cases are stored (it fixes the ingest schema and the export), and that drafted letters are never stored.

**Decision.**
- **A case lives on its visit** (`visit.cases`, a list), like the other member decisions of ADR-035, so it is the member's edit that imports keep, it goes into the export and comes back on import, and no migration is needed. A case covers one finding, or the whole visit (every finding open when it is opened). An old `visit.dispute` is read as a case; any change writes `cases` and drops `dispute`. The "Open a dispute" form and its route go.
- **Four statuses, each change dated:** open, contacted (you reached out and wait for an answer), waiting (they answered and you wait for them to act), resolved. The case keeps a history of every change with its date; logging something you sent moves an open case to contacted. A resolved case can be reopened. The visit is In dispute while any of its cases isn't resolved.
- **Who the case is with:** the provider or the insurer, defaulting from the finding (an EOB that doesn't add up or a network mismatch goes to the insurer; everything else to the provider) and changeable.
- **Contact log and call script (DSP-03).** The provider notes of Release 0 gain `case_id`, `party`, `person`, `reference` and `outcome`; a phone call logged on a case needs an outcome. Notes stay per provider (ledger and visit pages), and a case shows its own. The call script is made per case: who to call, what to have ready (claim number, dates, amounts, account number), what to ask for, and what to write down.
- **Follow-ups (DSP-04, A-13).** A reminder is due 30 days after the last thing you sent or a call you made, unless a reply (logged as "they sent") came after it; the 30 days are editable per case (1 to 365). A due reminder puts the visit at the top of "Needs your attention" with the reminder as its reason.
- **Deadlines (DSP-05), from real dates (ADR-022).** The insurer appeal deadline is each claim's EOB date plus the plan's appeal window (`appeal_days`, default 180, the ACA minimum for internal appeals). For a self-pay visit, the member can enter the good-faith estimate; a bill above it is a new finding ("Bill exceeds the good-faith estimate", kind `over_estimate`, a discrepancy), and when it is $400 or more above it, the No Surprises Act patient-provider dispute deadline is 120 days from the first bill that lists the visit. Deadlines show on every visit with an open finding or case; one 14 days away or nearer raises the visit in the attention queue (soonest first, ahead of the dollar order of ADR-041); passed deadlines are shown as passed and don't raise it.
- **Evidence (DSP-01).** Opening a case keeps a copy of its findings (code, kind, amount, wording) and of the bill and EOB lines that disagree, since both can change later. The documents (statements, EOBs, receipts, payments) are listed as they are now, each linking to its stored original, served only by the application tier (ING-10, ADR-033). Missing evidence is listed: the bill, the EOB for an insured visit, payment proof when something is owed or the finding is about a payment.
- **Letters (DSP-02) are drafted on request and never stored.** Five drafts: itemized bill request, billing correction, refund request, claim resubmission, insurer appeal, with one recommended per finding (missed adjustment, balance billing, charges that differ and duplicate charges: billing correction; overpayment: refund; claim may not be filed: claim resubmission; an EOB that doesn't add up or a network mismatch: appeal). The application tier fills the draft when the member asks: name from Settings, claim number, dates, amounts and lines from the records, and the account number re-identified from the vault tokens of the visit's confirmed uploads (Release 0 has no vault and leaves a blank). What the app doesn't know (insurer member ID, mailing address) the member types into the draft form, which is posted, used for that draft and not kept; nothing goes in a URL. The draft is shown to copy, print or download; it isn't saved, queued, logged with its text, or sent: the app sends no mail, and "I sent it" only logs the contact. Each draft carries the information-not-advice line (CMP-04).
- **Outcomes (DSP-07).** Resolving takes a result (corrected, refunded, written off, denied) and the dollars recovered (default the case's amount at issue; denied is $0) and closes the case's findings ("case resolved: refunded"). Reopening drops the outcome and reopens the findings it closed. Lifetime savings add the dollars recovered of every resolved case in every year, each case once.

**Consequences.** The ingest schema gains optional fields (`visit.cases`, `visit.good_faith_estimate`, `plan.appeal_days`, the note fields), so existing files stay valid; the engine's Dataset now carries the provider notes, which it reads for follow-ups. Identifiers typed for a letter are typed again for the next one; keeping them as vault tokens on the case is a later choice. A provider or insurer reply that isn't logged keeps the reminder due, by design. Release 0 gets everything except the account number from uploads.
