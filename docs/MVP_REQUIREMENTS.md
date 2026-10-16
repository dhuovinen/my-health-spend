# My Health Spend (MH$): MVP Requirements

> Derived from `My Health Spend (MHS) Problem Statement & Plan.md` (2026-10-09).
> Status: **agreed with owner 2026-10-09**, pending sample data. Deferred items live in `BACKLOG.md`.
> **This is Release 0** (decision 2026-10-15). Release 1 and later are specified in
> `My Health Spend (MHS) Product Requirements.md`; tests for both are in `TEST_PLAN.md`.

## 1. MVP scope

**Goal:** prove on the owner's own past visits that reconciling provider bill, insurer EOB and
payment record finds real problems worth real dollars.

**Assumptions**

- Single user (the owner), personal use only. Claims and visits are linked to household members,
  starting with the owner; the HSA pays for the whole household.
- Local web app on the owner's machine: local database plus a local folder for documents. No login,
  no cloud storage.
- Data comes in through a simple JSON ingest file (section 4). Source documents are attached and
  viewable but not machine-read.
- Security, privacy and multi-user concerns are deferred NFRs (section 8), not built.

**In scope:** use case 1 (after the visit: reconcile). Plan phases 1–4, with phase 2 (ingest)
reduced to JSON import.

**Out of scope:** pre-visit strategy (use case 2), automatic extraction from PDFs/images, account
connections, multiple household members, negotiated-rate lookup from outside sources, and the
market/presentation data in the plan (that is for the pitch, not the app).

## 2. Application shell

| ID | Requirement |
| --- | --- |
| SH-1 | A header on every screen shows the app name/logo (links to the hero screen), a **?** icon and a **gear** icon, top right. |
| SH-2 | **?** opens Help/Documentation. MVP: stub page ("Help is coming soon"). |
| SH-3 | **Gear** opens Settings (admin/config); see 3.6. |
| SH-4 | Both icons have accessible labels ("Help", "Settings") and tooltips. |
| SH-5 | The app has a browser tab icon (favicon). |

## 3. Screens

### 3.1 Hero screen (landing)

Answers "how am I doing, and what needs my attention?"

| ID | Requirement |
| --- | --- |
| HR-1 | Headline with app name and a one-line value statement (e.g. "See where your health dollars leak"). |
| HR-2 | Summary tiles for the selected plan year: **Total billed**, **You paid**, **Insurer paid**, **$ at stake** (sum of open discrepancies). |
| HR-3 | Visit count by status (Discrepancy, Balance outstanding, Missing documents, Waiting, Matched); each links to the filtered visit list. |
| HR-4 | Count and dollar total of **HSA gaps** (C5: unpaid, or paid outside the HSA) and **HSA payments without a claim** (C7), linking to them (visit list filtered by HSA gap, or provider list filtered by flag). |
| HR-5 | Primary action: **Import data**. Secondary: **Review flagged visits**. |
| HR-6 | Empty state: explains the three documents to gather and links to Import. |
| HR-7 | Plan-year selector (defaults to the current year). |
| HR-8 | Progress toward each plan limit for the year (e.g. "Family deductible: $2,873.94 of $6,000"), from EOB deductible, copay and coinsurance amounts. Shows a note when some covered members' claims have not been imported, since family totals are then incomplete. |

### 3.2 Visit list

| ID | Requirement |
| --- | --- |
| VL-1 | One card per visit: date, member, provider, category, total billed, what I paid, status badge, and an HSA-gap chip when it applies. |
| VL-2 | Sort by date (newest first); filter by status, member, category and provider. |
| VL-3 | Selecting a card opens visit detail. |

### 3.3 Visit detail

| ID | Requirement |
| --- | --- |
| VD-1 | Visit fields (date, provider, category, description, notes). |
| VD-2 | Document panel: provider bill(s), EOB, receipt, payments — each Missing / Received / Matched, with the attached file viewable. |
| VD-3 | Reconciliation panel: each check (section 5) as pass / fail / not applicable / waiting, with the dollar difference on fail. |
| VD-4 | Link to the provider ledger (3.4). |

### 3.4 Provider ledger

Payments belong to a provider, not to a single visit, so they are balanced against all of that
provider's charges.

| ID | Requirement |
| --- | --- |
| PL-1 | Chronological table for one provider: each visit's charge (EOB patient responsibility, or the bill amount when no EOB), each payment and refund, and a running balance. |
| PL-2 | Three balances side by side: **what I should owe** (from EOBs), **what the provider says I owe** (latest bill), **what I've paid**. Differences are highlighted. |
| PL-3 | Reachable from visit detail and from a provider list. |
| PL-4 | **Provider notes**: a dated log per provider (e.g. an email sent to the provider's billing office or a call with the insurer), with how it happened (email, phone, portal, in person, letter), direction (I sent, they sent, my note) and optionally the visit it concerns. Add, edit and delete on the provider page; shown read-only on visit detail; note count on the provider list. Notes live only in the app and are never changed by an import. |

A chart of charges, payments and balance over time is in the backlog.

### 3.5 Import

| ID | Requirement |
| --- | --- |
| IM-1 | Choose a JSON ingest file (section 4). |
| IM-2 | Validate against the schema and cross-references; show errors by record id with a plain message. Nothing is saved if there are errors. |
| IM-3 | Preview: counts of new and updated records per section, and warnings (e.g. attached file not found). |
| IM-4 | Confirm to save. Re-importing the same ids updates those records; this is how data is corrected in the MVP. Records changed in the app (Settings, provider notes) keep the owner's version when the file differs: the preview lists them with the differing fields, and they are replaced only if the owner ticks "Replace my edits with the file's values". |
| IM-5 | Attached files are copied into the app's local document folder. |

### 3.6 Settings (gear)

| ID | Requirement |
| --- | --- |
| ST-1 | **Insurance plan** per plan year: insurer, **coverage order (primary / secondary)**, members covered, plan name, coverage dates, HSA-eligible flag, coinsurance, copays. View and edit. The primary insurer is shown at the top of Settings. |
| ST-1a | **Plan limits**: any number of deductibles, out-of-pocket maximums and annual maximums, each with network tier (in-network, out-of-network, combined), level (individual or family) and, for an individual limit, optionally the member it applies to. 2026 example: Donald in-network OOP max $4,500; family in-network deductible $6,000; family in-network OOP max $9,000. |
| ST-2 | **Payment accounts**: name and type (HSA, FSA, card, bank, cash). View and edit. |
| ST-3 | **Providers**: name, kind, network status. View and edit. |
| ST-4 | **Household members**: name, relationship, and the names they appear under in source files. Providers can be assigned to members (e.g. a pediatrician to a child) so HSA payments without a claim can be attributed. |
| ST-5 | **Provider relationships**: pairs of provider records that may be the same individual or organization (different names on claims and card statements), with status suspected / confirmed / rejected and the evidence. The owner confirms or rejects them here. |
| ST-6 | Settings can also be loaded through Import (same JSON file or a settings-only file). |
| ST-7 | Stub sections for later: data export/backup/delete, the "waiting" threshold (fixed at 30 days for now), FSA rules. |

## 4. Ingestion format

- **Schema:** [`schema/mhs-ingest.schema.json`](../schema/mhs-ingest.schema.json) (JSON Schema 2020-12), version `0.1`.
- **Example:** [`samples/example-ingest.json`](../samples/example-ingest.json): made-up data covering every status.
- **Sections** (all optional): `plans`, `accounts`, `providers`, `visits`, `documents`.
- **Document types:** `provider_bill`, `eob`, `payment`, `receipt`, `account_reimbursement`,
  `account_transaction` (HSA contributions, interest, fees, opening balance).
- **Provider aliases:** each provider lists the names it appears under in source files (insurer
  "Provided By", card-statement merchant). Importers map rows to providers through them.
- **Converter:** `tools/build_ingest.py` builds an ingest file from the insurer claims CSV, the
  HSA transaction export and provider patient-statement PDFs, plus `data/settings.json` (see NOTES.md, How to run). Real data lives in
  `data/`, which is git-ignored.
- **Rules**
  - You choose each record's `id`; records link by id, and re-import upserts by id.
  - Dates are `YYYY-MM-DD`. Money is in dollars and stored as integer cents.
  - `file` paths are relative to the JSON file; a missing file is a warning.
  - `extensions` on any record holds fields not yet in the schema, so the format can grow without
    breaking imports. Fields that prove useful get promoted into the schema and `schema_version` is
    raised.
- **Expected to evolve** toward a general baseline for all scenarios (backlog B-15).

## 5. Reconciliation checks

| # | Check | MVP rule |
| --- | --- | --- |
| C1 | EOB adds up | billed = insurer paid + adjustment + additional savings + patient responsibility, and patient responsibility = deductible + copay + coinsurance + not covered (to the cent). |
| C2 | Bill matches EOB | For each visit, `patient_amount` on the latest statement that lists the visit = EOB `patient_responsibility`. Also flags a visit whose billed amount on the statement differs from the claim's billed amount (charges sent to the insurer but not shown to me). |
| C3 | Network status agrees | Bill, EOB and provider record agree. The rate used is the **agreed rate on the EOB** (`allowed`); no outside negotiated-rate lookup. |
| C4 | Paid matches responsibility | Per provider group (providers joined by a suspected or confirmed relationship): payments − refunds vs what I should owe (EOB patient responsibility), and vs what the provider billed me. Flags overpayment, underpayment and probable duplicates (same provider, same amount, within 14 days). |
| C5 | HSA gap | Owner rule: all health spend is paid from the HSA, and there are no other payments. Patient responsibility not matched by HSA payments is flagged: **Unpaid — pay from HSA** if the provider still shows it owed; **Paid outside the HSA — submit an HSA reimbursement claim** if the provider shows it paid. A payment from any non-HSA account gets the same reimbursement flag. Eligibility is not confirmed. |
| C6 | Balance outstanding | Provider bill shows a balance > 0 not covered by later payments; shows the age in days and whether the statement is a second notice. Age counts from the first statement that listed the balance (else the EOB date). Second notice: the visit is on two or more statements with a balance, or the statement's optional `notice` field carries the printed wording (e.g. "Past due"). |
| C7 | HSA payment without a claim | An HSA payment to a provider with no claim, statement or receipt to match. Likely another household member's claim not yet imported, a purchase that never goes through insurance, or a missing claim. |
| C8 | Unconfirmed provider match | A ledger that joins providers through a **suspected** relationship carries this flag until the owner confirms or rejects it. |

**Required documents by category:** provider visit and service → EOB; Rx → receipt, bill or EOB;
supplements and equipment → receipt. A provider statement is not required (many providers collect at the
visit and never send one); when present it drives C2 and C6. Payments are checked at provider level (C4, C5).

**Payment allocation:** payments belong to a provider. For per-visit figures they are applied oldest visit
first (to visits on or before the payment date), up to what the provider billed for each visit (latest
statement amount, else the EOB amount). Anything left over is an overpayment on the latest visit before
the payment. A visit that drops off a later statement from the same provider is treated as settled.
Earlier-year visits still listed on a statement in the selected year are carried into that year's ledger.

**Visit status** (the card shows the first that applies):
**Discrepancy** (C1–C4 fail) → **Balance outstanding** (C6) → **Missing documents** → **Waiting**
(required documents missing but visit < 30 days old) → **Matched**.

## 6. Data model (MVP)

| Entity | Key fields |
| --- | --- |
| Plan | plan year, insurer, coverage order, members covered, coinsurance, copays, HSA-eligible, limits |
| PlanLimit | type (deductible, OOP max, annual max), network tier, level (individual, family), member (optional), amount |
| Member | name, relationship (self, spouse, child, other), aliases |
| Account | name, type |
| Provider | name, kind, network status, aliases, members served |
| ProviderNote | provider, date, channel, direction, visit (optional), text |
| ProviderRelationship | two providers, relationship (same individual, same organization, affiliated), status (suspected, confirmed, rejected), evidence |
| Visit | date, member, provider, plan, category, description, notes |
| ProviderBill | provider, date, balance due, last payment received, lines (one per visit: billed, insurance paid, adjustment, agreed rate if shown, patient amount, patient paid, balance, service items) |
| EOB | plan, provider, visit, claim #, network status, billed, allowed, adjustment, insurer paid, deductible, copay, coinsurance, not covered, patient responsibility, optional service lines |
| Payment | provider, account, date, amount, payment or refund, optional visit hint, account balance after |
| AccountTransaction | account, date, kind (contribution, interest, fee, balance forward), amount, tax year, balance after |
| Receipt | provider, visit, total, items |
| AccountReimbursement | HSA/FSA account, date, amount, payments it covers |

Service lines (CPT codes) are captured but not reconciled in the MVP.

## 7. MVP non-functional requirements (apply now)

| ID | Requirement |
| --- | --- |
| NM-1 | Runs entirely on the owner's machine; no outbound network calls with user data. |
| NM-2 | Database and documents live in one local data folder, easy to back up and excluded from git. |
| NM-3 | Money stored as integer cents. |
| NM-4 | Reconciliation logic is separate from the UI and unit-tested against the sample file. |
| NM-5 | Usable in a laptop browser; responsive layout is nice-to-have. |

## 8. Deferred non-functional requirements (before anyone else uses it)

Trigger: the app moves from a single personal application to one used by others.

| ID | Area | Requirement to address |
| --- | --- | --- |
| ND-1 | Authentication | User sign-in, session management, MFA, or SSO. |
| ND-2 | Authorization | Per-user data isolation (multi-tenancy); household roles (owner, member, viewer). |
| ND-3 | PII / PHI handling | Classify fields (health, financial, identity); minimise what is stored; mask in UI and logs. |
| ND-4 | Encryption | At rest (database and documents) and in transit (TLS); key management. |
| ND-5 | Regulatory | Assess HIPAA applicability (likely not a covered entity; confirm), FTC Health Breach Notification Rule, state health-data laws (e.g. Washington My Health My Data Act), CCPA/CPRA. |
| ND-6 | Consent & privacy policy | Terms of use, privacy notice, explicit consent for health data and any AI processing. |
| ND-7 | Data rights | Export, deletion on request, retention schedule. |
| ND-8 | Audit | Log of access and changes to health and financial records. |
| ND-9 | Third-party processing | If extraction uses an outside OCR/AI service: data-processing agreement, no training on user data, data region. |
| ND-10 | Backup & recovery | Automated backups, tested restore, defined RPO/RTO. |
| ND-11 | Hosting & ops | Deployment target, monitoring, incident response, breach-notification procedure. |
| ND-12 | Accessibility | WCAG 2.2 AA. |
| ND-13 | Account connections | Secure token storage for HSA, insurer and card connections. |
| ND-14 | Disclaimer | Information only, not medical, legal, tax or financial advice; HSA flags are possibilities, not eligibility rulings. |

## 9. Decisions log

| # | Decision | Date |
| --- | --- | --- |
| D1 | Local web app; local database and document folder. | 2026-10-09 |
| D2 | MVP ingests a simple JSON file; automatic extraction is post-MVP. | 2026-10-09 |
| D3 | No negotiated-rate lookup; use the agreed rate on the EOB. Rate from provider bills → backlog. | 2026-10-09 |
| D4 | Payments map to a provider and are balanced against all that provider's charges. | 2026-10-09 |
| D5 | Status order Discrepancy → Balance outstanding → Missing documents → Waiting → Matched. | 2026-10-09 |
| D6 | Plan, accounts and providers live on the Settings page. | 2026-10-09 |
| D7 | Unmatched charges and non-HSA payments are flagged as HSA reimbursement opportunities, not as confirmed eligible. | 2026-10-09 |
| D8 | Market data is for the presentation only. | 2026-10-09 |
| D9 | Claims and visits link to household members; providers can be assigned to members. | 2026-10-09 |
| D10 | Likely-same providers are tracked as explicit relationships (suspected → confirmed / rejected), reconciled together and flagged until confirmed. | 2026-10-09 |
| D11 | No payments outside the HSA are expected; any charge not matched to an HSA payment is a gap to flag. | 2026-10-09 |
| D13 | Provider notes are a separate record kind, not part of the provider record or settings.json, so imports and the converter never overwrite them. | 2026-10-09 |
| D12 | Plan limits are a list (type × network × level × member), not fixed individual/family fields; each plan records its coverage order. | 2026-10-09 |
| D14 | This MVP is Release 0. The Product Requirements doc's P1 is Release 1, which moves data server-side. | 2026-10-15 |
| D15 | Owner edits win: an import never silently overwrites a record changed in the app (IM-4). | 2026-10-15 |

## 10. Waiting on

- 2026 dental and 2025 UMR plan limits, if wanted (empty `limits` lists in `data/settings.json`).
