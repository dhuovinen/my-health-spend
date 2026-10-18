# My Health Spend (MHS): Test Plan

Oct 15, 2026 · Revised Oct 15, 2026: all conflicts and ambiguities decided; P1 = Release 1 (49 requirements)

**Covers:** all 100 requirements in the [Product Requirements](<My Health Spend (MHS) Product Requirements.md>) (the PRD). They are checked against [`MVP_REQUIREMENTS.md`](MVP_REQUIREMENTS.md) (agreed and built 2026-10-09) and the [Problem Statement & Plan](<My Health Spend (MHS) Problem Statement & Plan.md>).

**At a glance:** 326 test cases cover all 100 requirements; 183 are for Release 1 (P1), none of them blocked. All 16 conflicts and 14 ambiguities are decided. 3 Release 2 cases still wait on one PRD open question (does self-pay count toward the deductible). 22 cases are already partly or fully automated by the existing 32 tests.

**How to use it**

1. Section 1 lists each conflict (X-01 to X-16) and ambiguity (A-01 to A-14) with its decision. All are decided; the records are in [DECISIONS.md](DECISIONS.md). Test cases marked **Blocked** cannot get a fixed expected result until they are decided.
2. Section 3 has the test cases by area. Section 4 is the traceability matrix, one row per requirement.
3. Appendix A maps the 32 existing automated tests to requirements. Appendix B lists built MVP behavior that has no PRD requirement.

---

## 1. Conflicts for your review

Severity: **High** means the build or existing tests would have to change, or two requirements give opposite answers for the same input. **Medium** means the expected result is undefined for a common case. **Low** means a labeling or edge-case inconsistency.

| # | Severity | Conflict | Requirements involved | Decision |
| --- | --- | --- | --- | --- |
| X-01 | High | Two different definitions of "MVP" | PRD P1 (65 items) vs MVP_REQUIREMENTS scope, D2, B-1, B-6, B-8, B-12, B-16 | **Decided:** built MVP = Release 0; P1 = Release 1 |
| X-02 | High | HSA first vs HSA last | TAX-03, TAX-04 vs MVP C5, D11, Problem Statement check 5 | **Decided:** HSA is the primary vehicle; FSAs secondary |
| X-03 | High | Two incompatible visit status models | REC-11, REC-05 vs MVP D5, section 5 status order, HR-3, ST-7 | **Decided:** one ordered list of 9 statuses (REC-11) |
| X-04 | High | Where data lives: local laptop app vs device-plus-server | PRV-01, 04, 05, 07, 08, PLT-04, ING-01, UX-10 vs MVP D1, NM-1, NM-5 | **Decided:** data resides server-side; application tier + back-end tier |
| X-05 | Medium | The billed identity is missing terms that other requirements create | REC-01, ALC-01, ALC-05 vs MVP C1 | **Decided:** three identities: adjudication, cost-sharing, settlement |
| X-06 | Medium | $1 auto-clear tolerance vs to-the-cent checks | REC-10 vs MVP C1 | **Decided:** under $1.00 auto-clears; $5.00 cumulative cap |
| X-07 | Medium | Payments belong to a visit vs to a provider | MAT-01, MAT-09, ALC-04, REC-03, PRD "visit is the anchor" vs MVP D4, C4, payment allocation rule | **Decided:** statement split, else oldest first; member can override (ADR-016) |
| X-08 | Medium | Manual decisions never overwritten vs automatic superseding and re-import | MAT-07 vs MAT-08, ING-05, ING-06, MVP IM-4 | **Decided:** member decisions win; built into Release 0 import |
| X-09 | Medium | Items marked P1 that the PRD's own text defers | MAT-02, UX-06, ALC-06, PRV-07 vs PRD "Priorities" paragraph; MVP out-of-scope list vs D9 | **Decided:** household in Release 1 (ADR-018) |
| X-10 | Medium | Eligibility rulings vs "possibilities only" | TAX-01, TAX-07 vs MVP D7, B-5, ND-14, CMP-04 | **Decided:** "likely" tax tags (ADR-021) |
| X-11 | Medium | Pseudonymization breaks features that need real dates or identity | PRV-01, PRV-04, PRV-05 vs REC-06, REC-07, TAX-05, DSP-02, DSP-05, ING-10, MAT-05 | **Decided:** real dates in the back-end tier (ADR-022) |
| X-12 | Medium | "Bill with no claim" flag vs visits that never go through insurance | REC-05 vs REC-12, PRE-04, MVP required-documents rule | **Decided:** non-insurance visits processed without a claim |
| X-13 | Low | Home screen: visit list vs hero summary | UX-01, UX-04 vs MVP HR-1 to HR-8, VL-1 | **Decided:** summary, queue, then cards (ADR-023) |
| X-14 | Low | Built MVP check demoted to P2 | REC-08 (P2), MAT-03 vs MVP C3 (built), B-11 | **Decided:** basic check in Release 1 (ADR-024) |
| X-15 | Low | Member-held key vs recovery, and deletion vs retention | PRV-06, PRV-07, PRV-09 vs ING-10, PLT-03, PRV-10, CMP-01 | **Decided:** KMS keys; deletion policy (ADR-025) |
| X-16 | Low | CSV-only HSA import vs the real export format | ING-08 vs NOTES.md converter (`TransactionHistory.xls`) | **Decided:** CSV, XLS or XLSX (ADR-026) |

### X-01 · High · Two different definitions of "MVP"

> **Decision (Oct 15, 2026):** option (b). The built MVP is Release 0; P1 now means Release 1. The PRD has a Release 0 baseline table showing which requirements Release 0 already covers.

- **PRD:** "P1 = MVP", 65 requirements.
- **MVP_REQUIREMENTS (agreed, built):** a JSON-import, local, single-owner app. It explicitly excludes or defers many PRD P1 items:

| PRD P1 item | What the MVP doc says |
| --- | --- |
| ING-01 to ING-05, ING-07 (upload, classify, extract, confirm, duplicate uploads) | D2: JSON ingest only; extraction is B-1 |
| MAT-06, REC-01 per line (line-level matching and checks) | "Service lines are captured but not reconciled" (B-8) |
| MAT-07 (confirm, reject, split, merge matches) | Data is corrected by re-importing JSON (IM-4, B-6) |
| MAT-08 (claim versions with history) | "MVP keeps the latest" (B-12) |
| PRV-01 to 04, 06 to 09; CMP-01 to 04 | Deferred NFRs ND-3 to ND-7, ND-14 until anyone else uses the app (B-16) |
| UX-10 (phone) | NM-5: laptop browser; responsive is nice-to-have |
| TAX-01 (qualified tagging) | D7, B-5: possibilities only |
| DSP-04 (follow-up reminders) | B-22: notes are a plain log |

- **Why it matters:** the P1 exit criterion in section 2.6 cannot be met by the current build. Testers cannot tell which release a case belongs to.
- **Options:** (a) The PRD supersedes the MVP doc. Call the MVP doc "Release 0" and plan the gap. (b) Re-tier the PRD: P0 = built MVP, P1 = next build.
- **Recommendation:** (b). It keeps the existing tests meaningful, and the PRD already says 65 P1 items is too many.

### X-02 · High · HSA first vs HSA last

> **Decision (Oct 15, 2026):** the HSA is the primary vehicle when the member is eligible; FSAs are supported but secondary. TAX-03 now defaults to the HSA, with "save HSA for later" as an option that routes expenses to the receipt vault (TAX-04). TAX-05 (FSA expiry) moved to P3. Release 0's C5 flag is consistent with the default and `test_hsa_flags` stays valid.

- **TAX-03:** "defaulting to FSA first and HSA last", with a "save HSA for later" setting. **TAX-04:** pay out of pocket now and keep receipts to reimburse from the HSA later.
- **MVP C5 / D11 (built and tested in `test_hsa_flags`):** "all health spend is paid from the HSA". Any non-HSA payment is flagged "submit an HSA reimbursement claim". **Problem Statement check 5:** "HSA first where eligible".
- **The conflict:** an out-of-pocket card payment for a qualified expense is a *problem* under C5 but the *recommended* behavior under TAX-03 and TAX-04.
- **Also:** TAX-08 says a general-purpose FSA blocks HSA contributions. An HSA holder can therefore only have a limited-purpose FSA, and "FSA first" applies only to dental and vision.
- **Options:** make C5's flag depend on the TAX-03 setting. With "pay from HSA now" (the current owner rule), the C5 flag stays. With "save HSA for later", the payment becomes a receipt-vault entry instead of a gap.

### X-03 · High · Two incompatible visit status models

> **Decision (Oct 15, 2026):** the combined list below, in that order, with a separate Missing documents status past the threshold. Written into REC-11. Release 0 has 5 of the 9 statuses; Release 1 adds In dispute, Needs review, Awaiting documents and Resolved.

| PRD REC-11 | MVP (built, with precedence D5) |
| --- | --- |
| Discrepancy found | Discrepancy |
| (none) | Balance outstanding |
| Awaiting documents | Missing documents (30 days or older) |
| Awaiting EOB | Waiting (under 30 days) |
| Needs review | (none) |
| In dispute | (none) |
| Complete, Resolved | Matched |

- The PRD gives no precedence order and no time threshold. REC-05 says a claim with no bill is a "waiting state". The MVP never requires a bill.
- **Why it matters:** a visit that has both a discrepancy and an open dispute has no defined expected status.
- **Proposed superset, in precedence order:** In dispute → Discrepancy found → Needs review (unconfirmed data) → Balance outstanding → Awaiting EOB → Awaiting documents (past threshold) → Resolved (was a finding, now closed) → Complete. Keep the 30-day threshold, and make it configurable per ST-7.

### X-04 · High · Where data lives

> **Decision (Oct 15, 2026):** data resides server-side. Clients send data to an application tier, which tokenizes identifiers and passes them to a back-end tier for extraction, reconciliation and AI. The identity vault is a separate service. PRV-01, PRV-05 to PRV-07 rewritten; PRV-11 (sign-in and household isolation) added. Still open: web, mobile or both; vault key custody (X-15); date shifting (X-11).

- **PRD assumes a device plus a server.** PRV-01: tokenize "before data leaves the device". PRV-05: "server-side". PLT-04: AI extraction. PRV-07: "lost phone". ING-01: forwarded email, which needs an inbound mail service. PRV-08: product analytics. UX-10 (P1): phone capture.
- **MVP D1 / NM-1:** runs entirely on the owner's machine with no outbound calls carrying user data. **NM-5:** laptop browser.
- **PRD open question:** "Web app, mobile app, or both?" is unanswered, yet P1 items depend on the answer.
- **Why it matters:** every PRV, CMP and PLT-04 test needs a defined trust boundary ("device" vs "server"). Without one, those tests cannot be written.
- **Decide:** the platform for the next build, and whether extraction uses an outside AI service (this also triggers ND-9).

### X-05 · Medium · The billed identity is missing terms

> **Decision (Oct 15, 2026):** three identities, written into the REC section intro. (1) Adjudication: Billed = Plan adjustment + Other savings + Primary paid + Secondary paid + Member responsibility. (2) Cost-sharing: Member responsibility = Deductible + Copay + Coinsurance + Not covered. (3) Settlement: Member responsibility = Payments − Refunds + Provider write-offs + Still owed. ALC-01 holds only adjudication buckets; write-offs and "still owed" move to ALC-03. REC-13 added to check identity 3. Self-pay: Billed = Self-pay discount + Member responsibility.

- **REC-01:** Billed = Plan adjustment + Insurer paid + Member responsibility.
- **MVP C1 (built):** adds **additional savings**. Real EOBs carrying that line would fail REC-01.
- **ALC-05 (COB):** a secondary insurer's payment is not in the identity.
- **ALC-01:** adds **provider write-off** and **still owed** as buckets. "Still owed" is a payment state *within* deductible, copay and coinsurance, not a separate share of the billed amount. Adding it as a bucket double-counts and breaks "each dollar billed must land with exactly one party".
- **Proposal:** Billed = Plan adjustment + Other savings + Primary paid + Secondary paid + Member responsibility. Move "still owed" and "provider write-off" to ALC-03 balances.

### X-06 · Medium · Tolerance

> **Decision (Oct 15, 2026):** the proposal. A difference under $1.00 per check auto-clears and is recorded; cleared amounts per provider per plan year are flagged past $5.00; a unit-price change is always flagged (this also settles A-14). Release 0 still checks to the cent until REC-10 is built.

- **REC-10:** "under $1 auto-clears". **MVP C1:** "to the cent" (built: a 1-cent difference fails today).
- The PRD's open question offers $1, $5 or a percentage.
- **Unclear:** whether the tolerance applies to REC-03 overpayments and REC-04 duplicates, and whether many small cleared differences at one provider add up to a finding.
- **Proposal:** a $1 default per check, cleared differences recorded as "cleared within tolerance", and a cumulative cap per provider per year.

### X-07 · Medium · Payments belong to a visit vs to a provider

> **Decision (Oct 15, 2026):** payments belong to a provider. A lump sum is split by the provider's statement when it shows the split, else oldest visit first; the member can override any split. Overpayment is checked per provider and shown per visit (ADR-016; ALC-04, REC-03).

- **PRD:** "every document, claim, line and payment attaches to one [visit]". MAT-01 also allows "many-to-many" in the same doc. MAT-09 links a payment to "the visit and lines". ALC-04 allocates "by the provider's statement when available or by user choice". REC-03 tests overpayment per visit.
- **MVP D4 and the allocation rule (built):** payments belong to a provider, are applied oldest visit first with no user choice, and overpayment is computed per provider group (C4).
- **Also unanchored:** HSA contributions, interest and fees attach to no visit.
- **Decide:** which allocation method wins when there is no statement, and whether REC-03 is evaluated per visit, per provider, or both.

### X-08 · Medium · Manual decisions vs automatic updates

> **Decision (Oct 15, 2026):** member decisions win. No import, re-extraction, payer feed or new document version overwrites a member's match, split, merge, correction or setting. Conflicting new data is shown beside the member's version and applied only when the member accepts it (MAT-07, MAT-08). **Built into Release 0:** records changed in the app (Settings, provider notes) are marked as member edits. A re-import keeps them, lists the differing fields in the preview, and offers "Replace my edits with the file's values". Covered by `test_reimport_keeps_settings_edits_unless_replaced`.

- **MAT-07:** "a manual decision is never overwritten automatically".
- **MAT-08:** reprocessed or corrected EOBs "supersede earlier ones". **MVP IM-4:** re-import overwrites records by id (today's correction method). ING-06 re-learns layouts.
- **Undefined case:** a corrected EOB arrives for a claim whose lines the user manually split, or whose amount the user corrected under ING-05.
- **Proposal:** a new version never silently replaces a manual decision. It raises "Needs review: newer EOB conflicts with your edit".

### X-09 · Medium · P1 items the PRD's own text defers

> **Decision (Oct 15, 2026):** the household is in Release 1. Release 1 is a lean core plus the household plus Release 0 carry-over, 49 requirements (ADR-018). PRV-07 vault backup is in the lean core.

- The PRD's "Priorities" paragraph says the leanest MVP defers "household, vault backup and dispute drafting".
- Household items are still P1: MAT-02, ALC-06, UX-06. Vault backup is still P1: PRV-07.
- The MVP doc lists "multiple household members" as out of scope. Yet D9, ST-4 and HR-8 (family limits) are built.
- **Decide:** is the household in or out of the next build? Re-tier PRV-07 to match.

### X-10 · Medium · Eligibility rulings vs "possibilities only"

> **Decision (Oct 15, 2026):** the proposal below, accepted as ADR-021 in DECISIONS.md and written into the PRD.

- **TAX-01:** tags each expense "qualified / not qualified". **TAX-07:** flags non-qualified HSA payments and guides the member to return them as a mistaken distribution.
- **MVP D7, B-5, ND-14:** HSA flags "are possibilities, not eligibility rulings". **CMP-04:** information, not tax advice.
- Also, a mistaken distribution can only be returned when there is clear evidence of a mistake. Guidance should not suggest it for a knowing non-qualified purchase.
- **Proposal:** label tags "likely qualified / likely not / needs documentation" with the IRS Publication 502 category cited. Pair every TAX-07 guidance with the CMP-04 disclaimer.

### X-11 · Medium · Pseudonymization vs features that need real dates or identity

> **Decision (Oct 15, 2026): accepted as ADR-022.** With reconciliation in the back-end tier, that tier needs real dates for plan years, deadlines and matching. Recommendation: no date shifting in the back-end tier; apply PRV-05 only to data sent to outside AI services and to analytics. Drafts (DSP-02) are filled with real identifiers in the application tier, and unredacted originals are stored there, never in the back-end tier.

- **PRV-05 date shifting** moves a Dec 30 visit across the plan year boundary. That breaks deductible and out-of-pocket resets (REC-06, REC-07), FSA days-left (TAX-05), appeal deadlines (DSP-05) and date matching against card swipes (MAT-05). It is only safe if those all run on the device.
- **PRV-01 / PRV-04 tokenizing** vs **DSP-02:** drafted letters need the real account number and name. **ING-10:** originals kept as dispute evidence contain every identifier.
- **Decide:** which component runs reconciliation and drafting (device or server), and where unredacted originals are stored.

### X-12 · Medium · "Bill with no claim" vs visits that never go through insurance

> **Decision (Oct 15, 2026):** these visits are processed without an insurance claim and are never flagged for lacking one. A receipt or bill plus payment proof is complete (REC-05, MAT-10).

- **REC-05:** flags "a bill with no matching claim (provider may not have filed)".
- **Legitimately claim-free:** self-pay visits (REC-12, PRE-04, the $105 example), supplements and equipment (the MVP requires only a receipt) and some Rx.
- **Proposal:** suppress the flag when the visit is marked self-pay or its category does not require an EOB.

### X-13 · Low · Home screen

> **Decision (Oct 15, 2026):** the proposal below, accepted as ADR-023 in DECISIONS.md and written into the PRD.

- **UX-01:** "the visit card list ... stays the home screen".
- **MVP (built):** a hero summary screen (HR-1 to HR-8) is the landing page, and the visit list is a separate screen (VL).
- **UX-04's attention queue** overlaps HR-3 and HR-5.
- **Decide:** which one is home, and whether the queue replaces or sits inside the hero.

### X-14 · Low · A built check demoted to P2

> **Decision (Oct 15, 2026):** the proposal below, accepted as ADR-024 in DECISIONS.md and written into the PRD.

- **REC-08** (network status) is P2. Yet the MVP's C3 network check is built, and it was check 3 in the Problem Statement.
- **MAT-03** puts network on the plan per year. The MVP keeps one status per provider (B-11).
- **Proposal:** raise the basic agree/disagree part of REC-08 to P1, and keep surprise-bill detection at P2.

### X-15 · Low · Member-held key vs recovery, and deletion vs retention

> **Decision (Oct 15, 2026), ADR-025:** per-household data keys in the host's key management service; recovery through MFA account recovery. Deletion removes records, originals and vault entries at once and backups within 35 days; only security and access logs without health content are kept, for one year.

- **PRV-06 vs PRV-07:** if only the member holds the key, recovering after a lost key needs a recovery key or escrow design. Otherwise PRV-07 cannot pass.
- **PRV-09** deletes "all their data". **ING-10, PLT-03, PRV-10 and CMP-01** keep originals, rule traces, access logs and breach records.
- **Decide:** what, if anything, survives deletion, and for how long.

### X-16 · Low · HSA import format

> **Decision (Oct 15, 2026):** the proposal below, accepted as ADR-026 in DECISIONS.md and written into the PRD.

- **ING-08** says CSV. The real HSA export in use is `TransactionHistory.xls`, which `tools/build_ingest.py` already reads.
- **Proposal:** "CSV or XLS/XLSX export".

## 1b. Ambiguities that make a requirement untestable as written

| # | Requirement | Question | Decision (Oct 15, 2026; written into the PRD) |
| --- | --- | --- | --- |
| A-01 | PLT-02 | "95% correct *after* user confirmation" is circular, because confirmed data is correct by definition | **Decided:** Measure field accuracy *before* confirmation on a held-out sample of at least 50 documents per release; set a numeric false-positive ceiling, e.g. at most 5% of findings dismissed as wrong |
| A-02 | PLT-05 | Does "under one minute" include the user's confirmation time (ING-05)? | **Decided:** Machine time only, from upload complete to ready to confirm, then confirm to reconciled; p95 |
| A-03 | PLT-05 | What is a "typical upload"? | **Decided:** A PDF of 1 to 3 pages or a single photo, for one visit |
| A-04 | ING-07 | When is a re-sent statement a near-duplicate, and when is it a new version? | **Decided:** Same provider, account and visit lines with identical amounts = near-duplicate; any changed balance, line or payment = new version (MAT-08) |
| A-05 | MAT-05 | What score auto-links, and what only proposes? | **Decided:** Score ≥ 0.9 auto-links (still reversible); 0.6 to 0.9 proposes; below 0.6 leaves unmatched |
| A-06 | REC-02 | "Missed adjustment" vs balance billing: is there one finding type or two, and what if the bill predates the EOB? | **Decided:** Two finding types; no REC-02 finding until an EOB exists (state Awaiting EOB) |
| A-07 | REC-07 | "Flag charges after the out-of-pocket max is met": does this include out-of-network and non-covered services? | **Decided:** In-network covered cost-sharing only |
| A-08 | UX-10 | What does "work well" mean? | **Decided:** No horizontal scroll at 375px wide; capture and review tasks done one-handed; desktop at 1280px or wider |
| A-09 | ING-06 | What does "extracts better" mean? | **Decided:** Field error rate on the next 5 documents of the same layout drops by at least 50% |
| A-10 | TAX-06 | Which mid-year proration rule? | **Decided:** Monthly pro rata by default; last-month rule as an option, with the testing-period warning |
| A-11 | CMP-06 | Process or software? | **Decided:** Process; tested by a review record plus versioned reference tables (PLT-01) |
| A-12 | PRV-08 | What may a "pseudonymous event" contain? | **Decided:** An allow-list schema: event name, pseudonymous install ID, timestamp, app version; no amounts, providers or codes |
| A-13 | DSP-04 | Default follow-up interval? | **Decided:** 30 days for providers and insurers; user-editable per case |
| A-14 | REC-10 | A "changed unit price" relative to what? | **Decided (with X-06):** the same code from the same provider on an earlier bill or EOB within the plan year, or the GFE (PRE-06). Now in REC-10 |

---

## 2. Approach

### 2.1 Scope

- **In scope:** functional, data-integrity, UI, privacy/security, performance and compliance checks for the 100 PRD requirements.
- **Regression scope:** the built MVP (Appendix A).
- **Out of scope:** the market and presentation data in the Problem Statement; legal sign-off itself, though CMP cases check that the inputs to that sign-off exist.

### 2.2 Test levels

| Code | Level | Tooling in this repo | Used for |
| --- | --- | --- | --- |
| U | Unit | `pytest`, core functions such as `mhs.core.reconcile.build_report` with synthetic datasets (`base()`, `eob()`, `pay()` builders in `tests/test_reconcile.py`) | Rules, math, matching, status, tax logic |
| I | Integration | `pytest` with `fastapi.testclient.TestClient`, the importer and the store against a temp data dir (`tests/conftest.py`) | Import, persistence, API, document storage |
| E | End-to-end UI | Browser automation against `uv run mhs` (port 3062); manual where noted | Screens, flows, responsiveness |
| S | Security / privacy | Outbound traffic capture through a proxy, file inspection, seeded-identifier scans | PRV, PLT-04, CMP-05 |
| P | Performance | Timed runs on the scenario library | PLT-05 |
| R | Review | Document and process inspection with a checklist | CMP, PLT-06 coverage |
| M | Manual / sampling | Human-graded samples | PLT-02 accuracy |

### 2.3 Test data

| Set | Contents | Status |
| --- | --- | --- |
| Sample ingest | `samples/example-ingest.json`: made-up data covering every MVP status | Exists |
| Synthetic builders | Small in-test datasets per rule (see `tests/test_reconcile.py`) | Exists; extend per case |
| Scenario library (PLT-06) | One redacted real case per REC rule and status, each with the expected findings in a sidecar file | **New**; seed from `data/` real visits after redaction |
| Extraction corpus | At least 5 documents per type in ING-02 (provider statement, itemized bill, EOB, HSA/FSA statement, card transaction, pharmacy receipt, GFE, other), each with ground-truth JSON | **New**; needed for ING-02 to ING-07 and PLT-02 |
| Identifier seed set | Fake people with known name variants, SSN, member IDs, account numbers, addresses, phone and email, planted in documents | **New**; needed for PRV-01 to PRV-04 and PLT-04 |
| Reference tables | CPT/HCPCS, CARC/RARC, IRS limits 2025 and 2026, Pub 502 categories, each versioned | **New** (PLT-01) |

**Conventions:** money is in integer cents in assertions (NM-3) and shown in dollars below. Unit tests pin "today", as `TODAY = date(2026, 10, 9)` does now. Real data in `data/` is never committed; only redacted scenarios are.

### 2.4 Environments

- Local: macOS, Python 3.12 via `uv`, SQLite, `uv run pytest`, app on 127.0.0.1:3062.
- Release 1: a local Docker Compose stack (application tier, back-end worker, identity vault, Postgres, capture proxy) for every change, and a Google Cloud staging project for OCR accuracy, cloud integration, restore and performance runs. Details in [TESTING.md](TESTING.md#release-1-test-environment).

### 2.5 Entry criteria

- Requirement has no open conflict or ambiguity. Cases marked Blocked wait for your decision.
- Test data set for the area exists.

### 2.6 Exit criteria per release

- All cases for the release's priority level pass. For Release 1 that is every P1 case (X-01).
- No open defect of severity Critical or High. Critical means wrong money or a privacy leak; High means a wrong finding or status.
- `uv run pytest` is green, and the scenario library (PLT-06) runs in CI on every change.
- The false-positive rate for findings is measured and below the A-01 ceiling.

### 2.7 Defect severity

| Severity | Meaning | Example |
| --- | --- | --- |
| Critical | Identifier leaves the device, data loss, or a money total wrong by any amount | Overpayment shown as $80 when it is $8 |
| High | Wrong finding, missed finding, or wrong status | Visit shows Matched while bill ≠ EOB |
| Medium | Feature works with a workaround | Filter resets on back navigation |
| Low | Cosmetic or wording | Tooltip typo |

---

## 3. Test cases

Columns: **Level** per 2.2. **Status:** *New*; *Exists: `test_name`* (partly or fully automated today); or *Blocked: X-nn / A-nn* (expected result depends on your decision).

### 3.1 Ingestion and capture (ING)

| TC | Req | Scenario | Expected result | Level | Status |
| --- | --- | --- | --- | --- | --- |
| TC-ING-01-1 | ING-01 | Upload a 1-page PDF EOB | Document saved, original stored, appears in the unassigned inbox or on its matched visit | I | New |
| TC-ING-01-2 | ING-01 | Upload phone photos as JPG, PNG and HEIC (HEIC with EXIF rotation) | All accepted; each shown upright; HEIC viewable in the browser; original bytes kept | E | New |
| TC-ING-01-3 | ING-01 | Upload a 5-page PDF, and capture a 3-page statement as 3 photos | Each becomes one multi-page document, pages in order | E | New |
| TC-ING-01-4 | ING-01 | Forward an email with a PDF attachment, and one with an HTML-only statement body, to the member's inbound address | One document per attachment; the body is captured as a document when it holds the statement; unknown senders rejected | I | New |
| TC-ING-01-5 | ING-01 | Upload .docx, .zip, a 0-byte file, a corrupt PDF, a password-protected PDF and a file over the size limit | Each rejected with a plain message naming the reason; nothing saved | I | New |
| TC-ING-02-1 | ING-02 | Classify the extraction corpus (≥5 per type, 8 types), before confirmation | Every document gets one of the 8 types; accuracy per type recorded; overall ≥ 95% | I | New |
| TC-ING-02-2 | ING-02 | Summary statement and itemized bill from the same provider | Classified as provider statement and itemized bill respectively | I | New |
| TC-ING-02-3 | ING-02 | EOB printed "THIS IS NOT A BILL" | Classified EOB, never provider statement | I | New |
| TC-ING-02-4 | ING-02 | A letter that fits no type | Classified "other" with low confidence; user reclassifies; new type persists and re-runs extraction | E | New |
| TC-ING-03-1 | ING-03 | Extract headers from each corpus document | Patient, provider, DOS, claim #, account #, statement date, billed, allowed, paid, owed match ground truth; amounts exact to the cent | I | New |
| TC-ING-03-2 | ING-03 | Claim with a date-of-service range (2026-03-01 to 2026-03-04) | Stored as start and end dates | U | New |
| TC-ING-03-3 | ING-03 | Statement with no claim number printed | Field empty and marked "not on document"; no guessed value | I | New |
| TC-ING-03-4 | ING-03 | Amounts written "$1,234.56", "1234.56", "(45.00)", "-45.00", "45.00 CR" | 123456, 123456, -4500, -4500, -4500 cents | U | New |
| TC-ING-04-1 | ING-04 | Itemized hospital bill with CPT, HCPCS, revenue codes, NDC, units, modifiers | Every line extracted with all codes, units, modifiers and amounts | I | New |
| TC-ING-04-2 | ING-04 | Statement without line detail | Header only; no invented lines | I | New |
| TC-ING-04-3 | ING-04 | Extracted lines sum to $410.00 but header total is $450.00 | Extraction warning "lines differ from total by $40.00" shown before confirmation | U | New |
| TC-ING-04-4 | ING-04 | Extracted code 99999 not in the CPT reference table | Line flagged for review as unknown code | U | New |
| TC-ING-05-1 | ING-05 | Open an extracted document | Every field shows a confidence score; fields below the threshold are highlighted | E | New |
| TC-ING-05-2 | ING-05 | Extracted but unconfirmed EOB | Excluded from reconciliation; visit status Needs review; no findings computed from it | I | New |
| TC-ING-05-3 | ING-05 | Correct member responsibility $45.00 → $54.00 and confirm | Reconciliation uses $54.00; correction recorded with old value, new value and time | I | New |
| TC-ING-05-4 | ING-05 | Edit a field after confirmation | Findings for that visit recompute immediately | I | New |
| TC-ING-06-1 | ING-06 | Correct fields on 2 documents of layout X, then extract the next 5 layout-X documents | Field error rate on those 5 is at least 50% lower than on the first 2 | I | New |
| TC-ING-06-2 | ING-06 | Corrections on layout X | No change in extraction for layout Y | I | New |
| TC-ING-07-1 | ING-07 | Upload the same file twice | Second upload flagged as duplicate; no second document; no double-counted amounts | I | New |
| TC-ING-07-2 | ING-07 | Two different photos of the same paper EOB | Flagged "likely duplicate" for the user to decide | I | New |
| TC-ING-07-3 | ING-07 | Re-sent statement: same provider, account and visit lines with identical amounts, new statement date | Near-duplicate: linked as a newer copy; amounts not counted twice; REC-04 not raised | I | New |
| TC-ING-07-4 | ING-07 | New statement with a changed balance, line or payment | Not a duplicate; stored as a new version (MAT-08) | I | New |
| TC-ING-07-5 | ING-07 | Re-import an HSA export overlapping the previous one by 2 months | No duplicated transactions | I | New |
| TC-ING-08-1 | ING-08 | Import an HSA administrator CSV export | Each row becomes a transaction with date, amount, payee, kind (distribution, contribution, interest, fee) and balance | I | New |
| TC-ING-08-2 | ING-08 | Import the same export twice | Second import changes nothing (idempotent) | I | New |
| TC-ING-08-3 | ING-08 | Export with a gap in the running balance | Warning naming the date where the balance breaks | I | New |
| TC-ING-08-4 | ING-08 | CSV missing the amount column | Error naming the missing columns; nothing saved | I | New |
| TC-ING-08-5 | ING-08 | Import the real `.xls` export layout, and the same data as CSV and XLSX | All three accepted with identical transactions | I | New |
| TC-ING-09-1 | ING-09 | Connect to a payer sandbox (e.g. CMS Blue Button sandbox), grant consent | ExplanationOfBenefit resources imported as claims and lines | I | New |
| TC-ING-09-2 | ING-09 | Map FHIR adjudication categories (submitted, eligible, benefit, deductible, copay, coinsurance, noncovered) | Values land in the right fields; the REC-01 identity holds | U | New |
| TC-ING-09-3 | ING-09 | Same claim arrives by API and by uploaded PDF | One claim with two sources, not two claims | I | New |
| TC-ING-09-4 | ING-09 | Consent revoked at the payer | No further pulls; user told; already-imported data kept or deleted per user choice | I | New |
| TC-ING-09-5 | ING-09 | Token expiry, HTTP 429 and 5xx during a pull | Refresh and retry; no duplicate claims; failure reported after retries | I | New |
| TC-ING-10-1 | ING-10 | Upload, extract, correct, reclassify, then hash the stored original | SHA-256 equals the uploaded file's hash at every step | I | Exists: `test_attached_files_are_copied_and_missing_ones_warned` (copy only) |
| TC-ING-10-2 | ING-10 | Open a visit and a case | Original file viewable from both, linked to its extracted record | E | New |
| TC-ING-10-3 | ING-10 | Upload a replacement for an existing document | New version stored; old original still available | I | New |

### 3.2 Data model and matching (MAT)

| TC | Req | Scenario | Expected result | Level | Status |
| --- | --- | --- | --- | --- | --- |
| TC-MAT-01-1 | MAT-01 | Create a visit with 2 claims, 3 lines each, with allocations; reload | Full tree round-trips; no orphan records | U | Exists: `test_r1_reconcile.py::test_mat_01_1_visit_with_two_claims_three_lines_each_round_trips` |
| TC-MAT-01-2 | MAT-01 | One $300.00 payment to a provider with 3 open visits | Payment belongs to the provider; allocated across the 3 visits per ALC-04; parts sum to $300.00 | U | Exists: `test_r1_reconcile.py::test_mat_01_2_one_payment_across_three_open_visits` |
| TC-MAT-01-3 | MAT-01 | One visit paid by an HSA card swipe and a personal card | Both payments linked to the visit | U | Exists: `test_r1_reconcile.py::test_mat_01_3_one_visit_paid_by_hsa_and_card` |
| TC-MAT-01-4 | MAT-01 | Delete a visit that has lines and allocations | Blocked with a message, or cascades with confirmation; never leaves orphans | I | Exists: `test_r1_reconcile_pages.py::test_mat_01_4_a_visit_with_documents_cannot_be_deleted` |
| TC-MAT-01-5 | MAT-01 | HSA contribution, interest and fee transactions | Stored as account transactions with no visit; excluded from visit totals | U | Exists: `test_r1_reconcile.py::test_mat_01_5_account_transactions_stay_out_of_visit_totals` |
| TC-MAT-02-1 | MAT-02 | Add self, spouse and 2 dependents, each with coverage, accounts and visits | All saved; each visit belongs to exactly one member | I | New |
| TC-MAT-02-2 | MAT-02 | Dependent's visit | Never counted in another member's totals | U | New |
| TC-MAT-02-3 | MAT-02 | Remove a member (child ages off the plan) | History and visits kept; member hidden from new-entry lists | U | New |
| TC-MAT-03-1 | MAT-03 | Plan with deductible, OOP max, copays, coinsurance and network tiers; visit on 2026-03-01 | Visit resolves to the 2026 plan and its terms | U | Exists: `test_individual_and_family_limits` (limits only) |
| TC-MAT-03-2 | MAT-03 | Plan changes on 2026-07-01 (new job) | Visits before and after resolve to different plans; accumulators kept separate | U | New |
| TC-MAT-03-3 | MAT-03 | Person with primary and secondary coverage | Both plans attached with coverage order | U | New |
| TC-MAT-03-4 | MAT-03 | Visit dated with no plan on file | Finding "no coverage on file for this date" | U | New |
| TC-MAT-04-1 | MAT-04 | Claim lists billing entity, rendering provider and facility | All three roles stored and tied to one provider group | U | New |
| TC-MAT-04-2 | MAT-04 | Same NPI with "ABC Med Grp" and "ABC Medical Group" | One provider | U | New |
| TC-MAT-04-3 | MAT-04 | Similar names, different NPIs | Not merged; proposed as a suspected relationship for the owner to confirm | U | Exists: `test_suspected_relationship_joins_ledgers_and_flags_until_confirmed` |
| TC-MAT-04-4 | MAT-04 | Card merchant "SQ *ABC MED" | Mapped to the provider through its alias | U | New |
| TC-MAT-05-1 | MAT-05 | Bill and EOB with same person, provider, DOS and claim # | Linked with a high score and reasons listed: same claim #, same DOS, same provider, same person | U | Exists: `test_r1_reconcile.py::test_mat_05_1_same_person_provider_date_and_claim_links_with_reasons` |
| TC-MAT-05-2 | MAT-05 | Match scores of 0.95, 0.75 and 0.5 | 0.95 links automatically and can be undone; 0.75 is proposed for the member; 0.5 stays unmatched | U | Exists: `test_r1_reconcile.py::test_mat_05_2_score_bands` |
| TC-MAT-05-3 | MAT-05 | Two members see the same provider on the same day | Each document matched to the right member's visit | U | Exists: `test_r1_reconcile.py::test_mat_05_3_two_members_same_provider_same_day` |
| TC-MAT-05-4 | MAT-05 | Same amount and date, different provider | No match | U | Exists: `test_r1_reconcile.py::test_mat_05_4_same_amount_and_date_other_provider_never_matches` |
| TC-MAT-05-5 | MAT-05 | Open a proposed match | Reasons shown in plain language beside the score | E | Exists: `test_r1_reconcile_pages.py::test_mat_05_5_and_mat_07_1_proposed_match_is_confirmed` |
| TC-MAT-06-1 | MAT-06 | Bill lines 99214, 85025, 80053 vs EOB lines with the same codes | Each bill line paired with its EOB line | U | Exists: `test_r1_reconcile.py::test_mat_06_1_lines_pair_by_code` |
| TC-MAT-06-2 | MAT-06 | Bill line 80053 vs EOB 80053 plus a component denied as bundled (CARC 97) | One-to-many pairing; bundling noted | U | Exists: `test_r1_reconcile.py::test_mat_06_2_bundled_component_pairs_one_to_many` |
| TC-MAT-06-3 | MAT-06 | Bill has 3 separate lab lines; EOB has 1 panel line | Many-to-one pairing | U | Exists: `test_r1_reconcile.py::test_mat_06_3_separate_bill_lines_one_panel_line` |
| TC-MAT-06-4 | MAT-06 | Bill line with no EOB counterpart | Reported as unmatched with its amount | U | Exists: `test_r1_reconcile.py::test_mat_06_4_unmatched_bill_line_is_reported_with_its_amount` |
| TC-MAT-06-5 | MAT-06 | 99214 on the bill, 99214-25 on the EOB | Paired; modifier difference noted | U | Exists: `test_r1_reconcile.py::test_mat_06_5_modifier_difference_is_noted` |
| TC-MAT-07-1 | MAT-07 | Confirm a proposed match | Saved as confirmed by the user | E | Exists: `test_r1_reconcile_pages.py::test_mat_05_5_and_mat_07_1_proposed_match_is_confirmed` |
| TC-MAT-07-2 | MAT-07 | Reject a proposed match, then re-run matching | The rejected pair is never proposed again | I | Exists: `test_r1_reconcile_pages.py::test_mat_07_2_rejected_match_stays_rejected_on_reimport` |
| TC-MAT-07-3 | MAT-07 | Split one document across two visits; merge two visits | Lines and allocations move; totals unchanged | I | Exists: `test_r1_reconcile_pages.py::test_mat_07_3_split_a_statement_and_merge_visits` |
| TC-MAT-07-4 | MAT-07 | Member edits a record (R0: a provider in Settings), then re-imports a file with different values | Member's version kept; preview lists the record and the differing fields | I | Exists: `test_reimport_keeps_settings_edits_unless_replaced` |
| TC-MAT-07-5 | MAT-07 | Re-import with "Replace my edits with the file's values" ticked | File values win; the records are no longer marked as member edits | I | Exists: `test_reimport_keeps_settings_edits_unless_replaced` |
| TC-MAT-08-1 | MAT-08 | Original EOB, then a reprocessed EOB with the same claim # | Latest is current; original visible in history; reconciliation uses the latest | U | New |
| TC-MAT-08-2 | MAT-08 | Corrected EOB lowers member responsibility $200 → $50 after $200 was paid | Findings recompute: $150 overpayment | U | New |
| TC-MAT-08-3 | MAT-08 | Corrected EOB imported before the original | Order by EOB processed date, not import date | U | New |
| TC-MAT-08-4 | MAT-08 | Appeal EOB arrives | Version marked "appealed"; case (DSP) updated | U | New |
| TC-MAT-08-5 | MAT-08 | Corrected EOB arrives for a claim the member edited | Not applied automatically; visit goes to Needs review with both versions side by side; applied only when the member accepts | U | New |
| TC-MAT-09-1 | MAT-09 | HSA card swipe matching provider alias, amount and date window | Linked to the visit | U | New |
| TC-MAT-09-2 | MAT-09 | Personal card payment later reimbursed from the HSA | Reimbursement linked to the card payment; no HSA gap | U | Exists: `test_hsa_flags` (lab visit) |
| TC-MAT-09-3 | MAT-09 | Check payment manually linked to two lines | Both lines show their part; parts ≤ payment | I | New |
| TC-MAT-09-4 | MAT-09 | Payment allocated to visits and lines | Allocated parts never exceed the payment; any surplus is a credit at the provider | U | New |
| TC-MAT-10-1 | MAT-10 | Visit with bill and EOB, no payment | Bill present, EOB present, payment proof expected | U | Exists: `test_r1_reconcile.py::test_mat_10_1_bill_and_eob_without_payment` |
| TC-MAT-10-2 | MAT-10 | Supplement purchase | EOB not applicable; receipt required | U | Exists: `test_sample_statuses_match_the_notes_in_the_sample_file` (vitamins visit) |
| TC-MAT-10-3 | MAT-10 | User marks the itemized bill "not applicable" | Completeness counts it as satisfied | I | Exists: `test_r1_reconcile_pages.py::test_mat_10_3_and_4_document_checklist` |
| TC-MAT-10-4 | MAT-10 | Visit card | Completeness shown per document kind | E | Exists: `test_r1_reconcile_pages.py::test_mat_10_3_and_4_document_checklist` |
| TC-MAT-10-5 | MAT-10 | Visit marked self-pay | EOB not applicable; bill or receipt and payment proof expected | U | Exists: `test_r1_reconcile.py::test_mat_10_5_self_pay_visit` |

### 3.3 Reconciliation and discrepancies (REC)

| TC | Req | Scenario | Expected result | Level | Status |
| --- | --- | --- | --- | --- | --- |
| TC-REC-01-1 | REC-01 | Line: billed $250.00, adjustment $125.00, insurer $80.00, member $45.00 | Pass | U | Exists: `test_r1_reconcile.py::test_rec_01_1_and_alc_01_1_line_identity_and_buckets` |
| TC-REC-01-2 | REC-01 | Claim: billed $1,332.00 with parts summing to $1,275.21 | Fail with remainder $56.79 | U | Exists: `test_eob_that_does_not_add_up_fails_c1` |
| TC-REC-01-3 | REC-01 | All lines pass but claim totals ≠ sum of lines | Claim-level fail with the difference | U | Exists: `test_r1_reconcile.py::test_rec_01_3_lines_pass_but_claim_totals_differ` |
| TC-REC-01-4 | REC-01 | Member responsibility $45.00 = deductible $20.00 + copay $25.00 | Pass; with copay $30.00 instead, fail by $5.00 | U | Exists: `test_r1_reconcile.py::test_rec_01_4_cost_sharing_identity` |
| TC-REC-01-5 | REC-01 | EOB with other savings $10.00 and a secondary payer paying $15.00 | Pass when billed = adjustment + other savings + primary paid + secondary paid + member responsibility | U | Exists: `test_r1_reconcile.py::test_rec_01_5_other_savings_and_secondary_payer` |
| TC-REC-01-6 | REC-01 | Self-pay visit: billed $250.00, self-pay discount $145.00, member $105.00, no EOB | Pass; no EOB expected | U | Exists: `test_r1_reconcile.py::test_rec_01_6_self_pay_visit_adds_up_without_an_eob` |
| TC-REC-02-1 | REC-02 | EOB member responsibility $100.00; provider asks $180.00 | Finding: provider asks $80.00 more than the EOB | U | Exists: `test_bill_vs_eob_discrepancy_and_provider_overpayment`; `test_r1_reconcile.py::test_rec_02_1_two_finding_types` |
| TC-REC-02-2 | REC-02 | Provider asks exactly the EOB amount | No finding | U | Exists: `test_sample_statuses_match_the_notes_in_the_sample_file` |
| TC-REC-02-3 | REC-02 | Bill arrives, no EOB yet | No finding; status Awaiting EOB | U | Exists: `test_r1_reconcile.py::test_rec_02_3_bill_before_the_eob_waits` |
| TC-REC-02-4 | REC-02 | Provider asks less than the EOB amount | No overcharge finding; informational note only | U | Exists: `test_r1_reconcile.py::test_rec_02_2_and_4_asks_exactly_or_less` |
| TC-REC-02-5 | REC-02 | Statement billed amount differs from the claim's billed amount | Finding: charges sent to the insurer not shown to the member (MVP C2 second rule) | U | Exists: `test_r1_reconcile.py::test_rec_02_5_statement_charges_differ_from_the_claim` |
| TC-REC-03-1 | REC-03 | Responsibility $45.00; paid $45.00 by HSA and $45.00 by card to the same provider | Overpayment $45.00 at the provider, shown on the visit the surplus was allocated to | U | Exists: `test_r1_reconcile.py::test_rec_03_1_paid_twice_by_two_methods` |
| TC-REC-03-2 | REC-03 | Provider-level: should owe $240.00, paid $320.00 | Overpaid $80.00 | U | Exists: `test_bill_vs_eob_discrepancy_and_provider_overpayment` |
| TC-REC-03-3 | REC-03 | Responsibility paid across 3 methods summing exactly | No finding | U | Exists: `test_r1_reconcile.py::test_rec_03_3_three_methods_summing_exactly` |
| TC-REC-03-4 | REC-03 | Overpayment, then a $45.00 refund recorded | Finding resolved | U | Exists: `test_r1_reconcile.py::test_rec_03_4_and_rec_13_3_refund_resolves_the_overpayment` |
| TC-REC-03-5 | REC-03 | Overpayment of $0.40 | Cleared within tolerance and recorded; counts toward the $5.00 provider cap | U | Exists: `test_r1_reconcile.py::test_rec_03_5_small_overpayment_clears_within_tolerance` |
| TC-REC-04-1 | REC-04 | Same code, DOS and provider twice on one statement | Duplicate-charge finding for the second line's amount | U | Exists: `test_r1_reconcile.py::test_rec_04_1_same_code_date_and_provider_twice` |
| TC-REC-04-2 | REC-04 | Same charge on two successive statements with identical amounts | Not a duplicate charge (near-duplicate statement, ING-07) | U | Exists: `test_r1_reconcile.py::test_rec_04_2_same_charge_on_successive_statements_is_not_a_duplicate` |
| TC-REC-04-3 | REC-04 | Two payments of $18.53 to the same provider 3 days apart for one visit | Probable duplicate payment; overpaid $18.53 | U | Exists: `test_possible_duplicate_payments` |
| TC-REC-04-4 | REC-04 | Same code twice with modifier 76/77, or 2 units | No duplicate finding (or marked low confidence) | U | Exists: `test_r1_reconcile.py::test_rec_04_4_repeat_modifiers_and_units_are_not_duplicates` |
| TC-REC-05-1 | REC-05 | Bill with no claim for an insured visit, past the waiting threshold | Finding "provider may not have filed with insurance" | U | Exists: `test_r1_reconcile.py::test_rec_05_1_bill_with_no_claim_past_the_threshold` |
| TC-REC-05-2 | REC-05 | EOB with no provider bill | No finding; $0 at stake; status Complete when nothing is owed, Balance outstanding when member responsibility is unpaid | U | Exists: `test_r1_reconcile.py::test_rec_05_2_eob_without_a_bill_is_not_an_error` |
| TC-REC-05-3 | REC-05 | Self-pay visit, supplement or cash-price prescription with a receipt and payment, no claim | No finding; visit Complete | U | Exists: `test_r1_reconcile.py::test_rec_05_3_claim_free_visits_are_complete_with_receipt_and_payment` |
| TC-REC-05-4 | REC-05 | Visit missing the EOB: 8 days old vs 130 days old | Waiting vs Missing documents | U | Exists: `test_missing_eob_waits_then_becomes_missing` |
| TC-REC-06-1 | REC-06 | Plan specialist copay $60.00; EOB applies $75.00 | Finding: copay $15.00 too high | U | New |
| TC-REC-06-2 | REC-06 | Deductible met; coinsurance 20%; allowed $500.00; EOB coinsurance $150.00 | Finding: should be $100.00, difference $50.00 | U | New |
| TC-REC-06-3 | REC-06 | Year-to-date deductible $5,800 of $6,000; allowed $500.00, 20% coinsurance | Expected deductible $200.00 + coinsurance $60.00; EOB checked against $260.00 | U | New |
| TC-REC-06-4 | REC-06 | Two EOBs processed out of date-of-service order | Accumulators follow the insurer's processing order; expected cost share computed accordingly | U | New |
| TC-REC-06-5 | REC-06 | Preventive visit charged a copay | Finding: preventive service should be $0 | U | New |
| TC-REC-07-1 | REC-07 | EOB deductible amounts across visits | Per-person and family progress equal the sums | U | Exists: `test_limit_progress_uses_eob_deductible`, `test_individual_and_family_limits` |
| TC-REC-07-2 | REC-07 | One member meets the individual (embedded) deductible before the family | That member's later EOBs expected at coinsurance, not deductible | U | New |
| TC-REC-07-3 | REC-07 | Family in-network OOP max $9,000 met; later in-network covered charge with $40.00 responsibility | Finding $40.00 | U | New |
| TC-REC-07-4 | REC-07 | Out-of-pocket max met; later out-of-network charge and later non-covered charge | No finding for either | U | New |
| TC-REC-07-5 | REC-07 | Visit on 2027-01-02 after a 2026 plan year | Accumulators reset for 2027 | U | New |
| TC-REC-07-6 | REC-07 | Covered member with no claims imported | Note that family totals may be incomplete | U | New |
| TC-REC-08-1 | REC-08 | Provider in network; EOB processed out of network | Finding: network status mismatch (Release 1 basic check) | U | New |
| TC-REC-08-2 | REC-08 | Out-of-network anesthesiologist bill at an in-network facility | Surprise-bill finding citing the No Surprises Act | U | New |
| TC-REC-08-3 | REC-08 | Provider in network in 2025, out in 2026 | Each year's visits checked against that year's status | U | New |
| TC-REC-08-4 | REC-08 | Bill, EOB and provider record agree | Pass | U | New |
| TC-REC-09-1 | REC-09 | EOB codes CO-45, PR-1, PR-2, PR-3, CO-97, CO-16, CO-50 | Each shown in plain language from the reference table | U | New |
| TC-REC-09-2 | REC-09 | Denial CO-16 (missing information) | Flagged "looks appealable"; CO-45 is not | U | New |
| TC-REC-09-3 | REC-09 | Unknown code | Shown with "unknown code"; logged for table update; no crash | U | New |
| TC-REC-10-1 | REC-10 | Difference of $0.50 | Auto-cleared; recorded as "cleared within tolerance" and visible on request | U | New |
| TC-REC-10-2 | REC-10 | Differences of $0.99 and $1.00 | $0.99 clears; $1.00 is flagged | U | New |
| TC-REC-10-3 | REC-10 | Code 99214 billed $150.00 in March and $150.10 in June by the same provider | Unit price change of $0.10 flagged despite the tolerance | U | New |
| TC-REC-10-4 | REC-10 | Change the tolerance setting | Findings recompute with the new tolerance | I | New |
| TC-REC-10-5 | REC-10 | Six $0.90 differences at one provider in a plan year | Each clears alone; the sixth takes the total to $5.40 and the provider is flagged | U | New |
| TC-REC-11-1 | REC-11 | One fixture visit per status (9) | Each of In dispute, Discrepancy found, Needs review, Balance outstanding, Awaiting EOB, Awaiting documents, Missing documents, Resolved, Complete is reachable and shown | U | Exists: `test_r1_reconcile.py::test_rec_11_1_every_status_is_reachable` |
| TC-REC-11-2 | REC-11 | Visits meeting several conditions: open case + failed check; failed check + balance owed; balance owed + missing EOB | In dispute; Discrepancy found; Balance outstanding (first in the REC-11 order wins) | U | Exists for the R0 order: `test_sample_statuses_match_the_notes_in_the_sample_file`; `test_r1_reconcile.py::test_rec_11_2_first_status_in_the_order_wins` |
| TC-REC-11-3 | REC-11 | Lifecycle: Awaiting EOB → Discrepancy found → In dispute → Resolved | Each transition happens on the triggering event only; Resolved only after a finding was closed | U | Exists: `test_r1_reconcile.py::test_rec_11_3_lifecycle` |
| TC-REC-11-4 | REC-11 | Waiting threshold changed from 30 to 45 days; insured visit 40 days old with no EOB | Threshold 45 days: Awaiting EOB. Threshold 30 days: Missing documents | U | Exists: `test_r1_reconcile.py::test_rec_11_4_waiting_threshold_is_configurable` |
| TC-REC-11-5 | REC-11 | Status badges on cards | Badge text matches status; not conveyed by color alone | E | Exists: `test_r1_reconcile_pages.py::test_rec_11_dispute_lifecycle_and_findings_on_the_pages` |
| TC-REC-12-1 | REC-12 | Self-pay $105.00 vs negotiated $125.00 | Shows self-pay cheaper by $20.00 | U | New |
| TC-REC-12-2 | REC-12 | Deductible not met; self-pay does not count toward it | Comparison shows the effect on the deductible | U | Blocked: PRD open question (self-pay toward deductible) |
| TC-REC-12-3 | REC-12 | Only one of the two prices known | No comparison shown | U | New |
| TC-REC-13-1 | REC-13 | Member responsibility $100.00; paid $60.00; provider write-off $10.00 | Still owed $30.00; identity 3 holds | U | Exists: `test_r1_reconcile.py::test_rec_13_1_still_owed_after_payment_and_write_off` |
| TC-REC-13-2 | REC-13 | Visit drops off a later statement with no matching payment | Unexplained remainder flagged with its amount | U | Exists: `test_visit_that_drops_off_a_later_statement_is_settled` |
| TC-REC-13-3 | REC-13 | Responsibility $100.00; paid $120.00; then a $20.00 refund | Before the refund: credit due $20.00 (REC-03); after: still owed $0.00 | U | Exists: `test_r1_reconcile.py::test_rec_03_4_and_rec_13_3_refund_resolves_the_overpayment` |
| TC-REC-13-4 | REC-13 | Provider with 4 visits | Provider-level settlement equals the sum of its visits | U | Exists: `test_r1_reconcile.py::test_rec_13_4_provider_settlement_is_the_sum_of_its_visits` |

### 3.4 Charge allocation (ALC)

| TC | Req | Scenario | Expected result | Level | Status |
| --- | --- | --- | --- | --- | --- |
| TC-ALC-01-1 | ALC-01 | Line billed $250.00: adjustment $125.00, insurer $80.00, deductible $20.00, copay $25.00 | Buckets shown with those amounts; sum $250.00 | U | Exists: `test_r1_reconcile.py::test_rec_01_1_and_alc_01_1_line_identity_and_buckets` |
| TC-ALC-01-2 | ALC-01 | Line fully denied as not covered | 100% in "not covered" | U | Exists: `test_r1_reconcile.py::test_alc_01_2_fully_denied_line_is_all_not_covered` |
| TC-ALC-01-3 | ALC-01 | $45.00 responsibility, $30.00 paid, then a $5.00 prompt-pay write-off | ALC-01 buckets unchanged and still sum to billed; ALC-03 shows paid $30.00, write-off $5.00, still owed $10.00 | U | Exists: `test_r1_reconcile.py::test_alc_01_3_write_off_is_a_settlement_item_not_a_bucket` |
| TC-ALC-01-4 | ALC-01 | Property test: 1,000 random valid EOB lines | Every cent of billed lands in exactly one adjudication bucket; no settlement item appears in ALC-01 | U | Exists: `test_r1_reconcile.py::test_alc_01_4_every_cent_lands_in_exactly_one_bucket` |
| TC-ALC-02-1 | ALC-02 | $45.00 member share paid $30.00 by HSA card and $15.00 by personal card | Share split by source with those amounts | U | New |
| TC-ALC-02-2 | ALC-02 | Payment plan of 3 installments | Each installment attributed to "payment plan" and to the visit | U | New |
| TC-ALC-02-3 | ALC-02 | One payment from each source type (HSA card, HSA reimbursement, FSA, LPFSA, HRA, personal card, check, payment plan) | All 8 recognized and reported | U | New |
| TC-ALC-02-4 | ALC-02 | Sources sum to more than the member share | Excess raised as REC-03 overpayment, not hidden in a bucket | U | New |
| TC-ALC-03-1 | ALC-03 | Owe $45.00; pay $30.00; then pay $30.00 | Owed $15.00, then credit due from provider $15.00 | U | New |
| TC-ALC-03-2 | ALC-03 | Qualified $45.00 paid by personal card | "Pay from HSA now": reimbursement due from HSA $45.00. "Save HSA for later": receipt-vault entry, nothing due | U | New |
| TC-ALC-03-3 | ALC-03 | Per-visit balances for one provider | Sum equals the provider ledger balance (MVP PL-2) | U | New |
| TC-ALC-04-1 | ALC-04 | $300.00 lump sum; provider statement applies $200.00 to visit A and $100.00 to B | Allocation follows the statement | U | Exists: `test_r1_reconcile.py::test_alc_04_1_statement_split_wins_over_oldest_first` |
| TC-ALC-04-2 | ALC-04 | Lump sum with no statement split; member changes the default split | Member's split saved and used; kept on re-import (ADR-011) | I | Exists: `test_r1_reconcile_pages.py::test_alc_04_2_members_split_is_saved_used_and_kept` |
| TC-ALC-04-3 | ALC-04 | Lump sum with no statement split and no member override | Oldest visit first, up to what each visit was billed | U | Exists: `test_visit_that_drops_off_a_later_statement_is_settled` |
| TC-ALC-04-4 | ALC-04 | Lump sum exceeds everything outstanding | Leftover shown as credit at the provider | U | Exists: `test_r1_reconcile.py::test_alc_04_4_lump_sum_beyond_everything_owed_is_a_credit` |
| TC-ALC-05-1 | ALC-05 | Billed $200.00; primary pays $80.00, secondary $15.00, adjustment $100.00, member $5.00 | All parts shown; identity 1 holds | U | New |
| TC-ALC-05-2 | ALC-05 | Primary EOB in, secondary EOB not yet | Member remainder pending; status Awaiting EOB | U | New |
| TC-ALC-05-3 | ALC-05 | Coverage order in settings | Primary and secondary applied in that order | U | New |
| TC-ALC-06-1 | ALC-06 | Allocations on visits for 2 members | Each allocation carries the visit's member; per-person totals sum to the family total | U | New |
| TC-ALC-06-2 | ALC-06 | One HSA payment covering visits for 2 members | Split by member in reports | U | New |
| TC-ALC-07-1 | ALC-07 | Visit detail breakdown | Billed → adjustment → insurer → you → each account, amounts match the data | E | New |
| TC-ALC-07-2 | ALC-07 | Breakdown accessibility | Every segment has a text label and value; not color-only | E | New |
| TC-ALC-07-3 | ALC-07 | Visit with $0 insurer paid | Zero segment shown or omitted cleanly; no broken chart | E | New |
| TC-ALC-08-1 | ALC-08 | $45.00 provider refund to the HSA card that paid | Refund linked to the original payment; overpayment closed; HSA credited | U | New |
| TC-ALC-08-2 | ALC-08 | Refund by check to the member for an HSA-paid charge | Finding: deposit the refund back to the HSA | U | New |
| TC-ALC-08-3 | ALC-08 | Partial refund of $20.00 on a $45.00 overpayment | $25.00 still owed back | U | New |

### 3.5 HSA, FSA and tax (TAX)

| TC | Req | Scenario | Expected result | Level | Status |
| --- | --- | --- | --- | --- | --- |
| TC-TAX-01-1 | TAX-01 | Office visit copay | Tagged "likely qualified" citing Pub 502 "Physicians" | U | Exists: `test_tax.py::test_tc_tax_01_1_*` |
| TC-TAX-01-2 | TAX-01 | General vitamins; then the same with a letter of medical necessity on file | "Likely not qualified"; then "needs documentation" satisfied | U | Exists: `test_tax.py::test_tc_tax_01_2_*` |
| TC-TAX-01-3 | TAX-01 | Massage therapy | Needs documentation (letter of medical necessity) | U | Exists: `test_tax.py::test_tc_tax_01_3_*` |
| TC-TAX-01-4 | TAX-01 | Category table updated to a new version | Existing tags keep their old version; new tags use the new one (PLT-01) | U | Exists: `test_tax.py::test_tc_tax_01_4_*` |
| TC-TAX-02-1 | TAX-02 | Health FSA with a 2.5-month grace period; expense on 2027-03-10 | 2026 funds usable | U | Exists: `test_tax.py::test_tc_tax_02_1_*` |
| TC-TAX-02-2 | TAX-02 | FSA with $680 carryover; $1,000 unspent at year end | $680 carried; $320 forfeited | U | Exists: `test_tax.py::test_tc_tax_02_2_*` |
| TC-TAX-02-3 | TAX-02 | Run-out deadline 2027-03-31; claim filed 2027-04-02 | Marked past deadline | U | Exists: `test_tax.py::test_tc_tax_02_3_*` |
| TC-TAX-02-4 | TAX-02 | Limited-purpose FSA and a medical (non-dental, non-vision) expense | Not eligible from the LPFSA | U | Exists: `test_tax.py::test_tc_tax_02_4_*` |
| TC-TAX-02-5 | TAX-02 | HRA with employer-defined eligible list | Only listed expenses eligible | U | Exists: `test_tax.py::test_tc_tax_02_5_*` |
| TC-TAX-03-1 | TAX-03 | HSA-eligible member, qualified expense, default setting, HSA and LPFSA balances available | Recommend the HSA | U | Exists: `test_tax.py::test_tc_tax_03_1_*` |
| TC-TAX-03-2 | TAX-03 | Setting "save HSA for later" | Recommend paying another way and adding the expense to the receipt vault | U | Exists: `test_tax.py::test_tc_tax_03_2_*` |
| TC-TAX-03-3 | TAX-03 | Setting "pay from HSA now" | Recommend HSA | U | Exists: `test_tax.py::test_tc_tax_03_3_*` |
| TC-TAX-03-4 | TAX-03 | Medical expense with only an LPFSA and HSA | LPFSA never recommended for it | U | Exists: `test_tax.py::test_tc_tax_03_4_*` |
| TC-TAX-03-5 | TAX-03 | Dental expense; LPFSA balance $300.00 forfeits in 20 days; HSA also available | Suggest the LPFSA (forfeiture rule), with the HSA as the alternative | U | Exists: `test_tax.py::test_tc_tax_03_5_*` |
| TC-TAX-04-1 | TAX-04 | Qualified $120.00 paid outside the HSA after the HSA open date | Vault entry; running total +$120.00; receipt attached; shown as a reimbursement opportunity ("pay now") or banked savings ("save for later") | U | Exists: `test_tax.py::test_tc_tax_04_1_*` |
| TC-TAX-04-2 | TAX-04 | Qualified expense dated before the HSA was established | Not added to the vault | U | Exists: `test_tax.py::test_tc_tax_04_2_*` |
| TC-TAX-04-3 | TAX-04 | Vault entry reimbursed from the HSA | Running total decreases; the same entry cannot be reimbursed twice | U | Exists: `test_tax.py::test_tc_tax_04_3_*` |
| TC-TAX-04-4 | TAX-04 | Vault receipt | Original kept unchanged and viewable (ING-10) | I | Exists: `test_tax_pages.py::test_tc_tax_04_4_vault_receipt_is_the_unchanged_original` |
| TC-TAX-05-1 | TAX-05 | FSA balance $500.00, 30 days to plan year end, $200.00 eligible unclaimed | Alert: $500.00 at risk, 30 days left, $200.00 claimable now | U | New |
| TC-TAX-05-2 | TAX-05 | Same, with $680 carryover available | At-risk amount accounts for the carryover ($0.00 here) | U | New |
| TC-TAX-05-3 | TAX-05 | FSA balance $0.00 | No alert | U | New |
| TC-TAX-06-1 | TAX-06 | Family coverage, $8,000.00 contributed in 2026 | Under the $8,750 limit; $750.00 room left | U | Exists: `test_tax.py::test_tc_tax_06_1_*` |
| TC-TAX-06-2 | TAX-06 | Account holder aged 55 or older | Limit includes the $1,000 catch-up | U | Exists: `test_tax.py::test_tc_tax_06_2_*` |
| TC-TAX-06-3 | TAX-06 | Self-only Jan to Jun, family Jul to Dec 2026, default rule | Limit = 6/12 × $4,400 + 6/12 × $8,750 = $6,575.00; switching to the last-month rule gives $8,750.00 with the testing-period warning | U | Exists: `test_tax.py::test_tc_tax_06_3_*` |
| TC-TAX-06-4 | TAX-06 | Contributions exceed the limit by $300.00 | Finding: excess contribution $300.00 | U | Exists: `test_tax.py::test_tc_tax_06_4_*` |
| TC-TAX-06-5 | TAX-06 | 2025 vs 2026 contributions | Each year checked against its own reference table row | U | Exists: `test_tax.py::test_tc_tax_06_5_*` |
| TC-TAX-07-1 | TAX-07 | HSA paid $40.00 for a non-qualified item the member marks as a mistake | Finding with mistaken-distribution guidance and the CMP-04 disclaimer; without the mistake mark, no return guidance | U | Exists: `test_tax.py::test_tc_tax_07_1_*` |
| TC-TAX-07-2 | TAX-07 | HSA paid for a "needs documentation" item | Prompt to get a letter of medical necessity; not labeled non-qualified | U | Exists: `test_tax.py::test_tc_tax_07_2_*` |
| TC-TAX-07-3 | TAX-07 | Guidance screen | Disclaimer present | E | Exists: `test_tax_pages.py::test_tc_tax_07_3_guidance_only_after_the_member_marks_a_mistake_with_the_disclaimer` |
| TC-TAX-08-1 | TAX-08 | Member has a general-purpose FSA and makes HSA contributions | Eligibility conflict flagged | U | Exists: `test_tax.py::test_tc_tax_08_1_*` |
| TC-TAX-08-2 | TAX-08 | Limited-purpose FSA with HSA | No conflict | U | Exists: `test_tax.py::test_tc_tax_08_2_*` |
| TC-TAX-08-3 | TAX-08 | Medicare enrollment date 2026-06-01; HSA contributions after | Contributions after enrollment flagged | U | Exists: `test_tax.py::test_tc_tax_08_3_*` |
| TC-TAX-09-1 | TAX-09 | HSA pays a spouse's expense | Allowed | U | Exists: `test_tax.py::test_tc_tax_09_1_*` |
| TC-TAX-09-2 | TAX-09 | HSA pays for a 24-year-old child who is not a tax dependent | Flagged; the same expense from a health FSA is allowed | U | Exists: `test_tax.py::test_tc_tax_09_2_*` |
| TC-TAX-09-3 | TAX-09 | Dependent status changes between tax years | Each year uses its own status | U | Exists: `test_tax.py::test_tc_tax_09_3_*` |
| TC-TAX-10-1 | TAX-10 | Year-end summary | HSA distributions by person and purpose sum to account distributions | U | Exists: `test_tax.py::test_tc_tax_10_1_*` |
| TC-TAX-10-2 | TAX-10 | Unreimbursed qualified expenses line | Equals the vault total at year end | U | Exists: `test_tax.py::test_tc_tax_10_2_*` |
| TC-TAX-10-3 | TAX-10 | Medical spend total for itemizing | Total shown with the disclaimer; no advice to itemize | U | Exists: `test_tax.py::test_tc_tax_10_3_*` |

### 3.6 Pre-visit strategy (PRE)

| TC | Req | Scenario | Expected result | Level | Status |
| --- | --- | --- | --- | --- | --- |
| TC-PRE-01-1 | PRE-01 | Create a planned visit (provider, service, date) | Shown as Planned on the visit list | E | New |
| TC-PRE-01-2 | PRE-01 | Documents for that provider and date arrive | Planned visit becomes the real visit; estimate kept for comparison | I | New |
| TC-PRE-01-3 | PRE-01 | Planned date passes with no documents | Prompt to confirm the visit happened or cancel it | U | New |
| TC-PRE-02-1 | PRE-02 | $500.00 deductible left, expected allowed $800.00, 20% coinsurance | Estimate $560.00 with the math shown ($500.00 + 20% × $300.00) | U | New |
| TC-PRE-02-2 | PRE-02 | OOP max $200.00 from being met | Estimate capped at $200.00 | U | New |
| TC-PRE-02-3 | PRE-02 | Copay-only service | Estimate equals the copay | U | New |
| TC-PRE-03-1 | PRE-03 | Same CPT paid twice before | Past amounts shown with dates | U | New |
| TC-PRE-03-2 | PRE-03 | Provider quote entered | Shown beside past amounts | U | New |
| TC-PRE-03-3 | PRE-03 | Price-transparency source unavailable | Section shows "not available"; rest of the page works | I | New |
| TC-PRE-04-1 | PRE-04 | Self-pay $105.00 vs estimated insured cost $125.00, deductible not met | Comparison and deductible effect shown | U | Blocked: PRD open question (self-pay toward deductible) |
| TC-PRE-04-2 | PRE-04 | Plan setting "self-pay counts toward deductible" switched on and off | Recommendation changes accordingly | U | Blocked: PRD open question |
| TC-PRE-05-1 | PRE-05 | Planned visit, in-network provider | Checklist includes network confirmation, cost estimate, itemized bill request | U | New |
| TC-PRE-05-2 | PRE-05 | Out-of-network provider | Checklist adds balance-billing and GFE questions | U | New |
| TC-PRE-06-1 | PRE-06 | GFE $400.00; final self-pay bill $850.00 | Flag: exceeds the GFE by $450.00 (≥ $400 No Surprises Act dispute threshold), with the 120-day window | U | New |
| TC-PRE-06-2 | PRE-06 | Final bill within the GFE | No flag | U | New |
| TC-PRE-07-1 | PRE-07 | Planned visit, HSA-eligible member with an HSA balance | Recommendation equals TAX-03 output for the same inputs (HSA by default) | U | New |

### 3.7 Disputes and follow-up (DSP)

| TC | Req | Scenario | Expected result | Level | Status |
| --- | --- | --- | --- | --- | --- |
| TC-DSP-01-1 | DSP-01 | Create a case from a REC-02 finding | Case holds the bill, EOB, payment proof, the lines and amounts | I | New |
| TC-DSP-01-2 | DSP-01 | Evidence files in the case | Same originals as ING-10 (hash match), served from the application tier only | I | New |
| TC-DSP-01-3 | DSP-01 | Finding with the payment proof missing | Case created; missing evidence listed | I | New |
| TC-DSP-02-1 | DSP-02 | Draft each of: itemized bill request, billing correction, refund request, claim resubmission, insurer appeal | Each draft has the real claim #, DOS, amounts and request, filled in by the application tier; the back-end tier only ever sees tokens | U | New |
| TC-DSP-02-2 | DSP-02 | Any draft | Never sent without an explicit user action; no auto-send | E | New |
| TC-DSP-03-1 | DSP-03 | Open a call script for a refund case | Script includes what to ask for and the reference numbers to record | U | New |
| TC-DSP-03-2 | DSP-03 | Log a call: date, person, reference #, outcome | Saved and shown in the case history | I | Exists (provider-level log): `test_provider_notes_can_be_added_edited_and_deleted` |
| TC-DSP-03-3 | DSP-03 | Log a call with no outcome | Validation message; nothing saved | I | New |
| TC-DSP-04-1 | DSP-04 | Case status changes open → waiting on provider → resolved | Each change dated and shown | U | New |
| TC-DSP-04-2 | DSP-04 | Case with no response logged 30 days after the last contact; another with a 10-day override | Reminders appear in the attention queue at 30 and 10 days respectively | U | New |
| TC-DSP-04-3 | DSP-04 | Response logged | Reminder cleared | U | New |
| TC-DSP-05-1 | DSP-05 | EOB dated 2026-03-01, 180-day appeal window | Deadline 2026-08-28 shown (real dates in the back-end tier) | U | New |
| TC-DSP-05-2 | DSP-05 | Self-pay bill exceeds GFE | No Surprises Act dispute deadline 120 days from the bill date | U | New |
| TC-DSP-05-3 | DSP-05 | Deadline within 14 days | Item rises in the attention queue | U | New |
| TC-DSP-06-1 | DSP-06 | Hospital bill; household income below the hospital's assistance threshold | Screen says "may qualify" with a link to the hospital's application | U | New |
| TC-DSP-06-2 | DSP-06 | Non-hospital provider | Screen not offered | U | New |
| TC-DSP-07-1 | DSP-07 | Case closed as refunded $75.00 | Lifetime savings +$75.00 | U | New |
| TC-DSP-07-2 | DSP-07 | Closed as written off $200.00; another closed as denied | +$200.00 and +$0.00 | U | New |
| TC-DSP-07-3 | DSP-07 | Case reopened and closed again | Savings counted once | U | New |

### 3.8 User experience and reporting (UX)

| TC | Req | Scenario | Expected result | Level | Status |
| --- | --- | --- | --- | --- | --- |
| TC-UX-01-1 | UX-01 | Home after import | Summary tiles, then the attention queue, then visit cards with person, provider, date, status badge, document completeness and amount at issue | E | New |
| TC-UX-01-2 | UX-01 | No visits yet | Empty state explains what to gather and links to import/upload | E | Exists: `test_empty_home_has_hero_help_and_settings` |
| TC-UX-01-3 | UX-01 | Card amount at issue | Equals the sum of that visit's open findings | U | New |
| TC-UX-02-1 | UX-02 | Open a visit with all document kinds and a case | Documents, line comparison, allocation, findings and case history on one page | E | Exists (MVP subset): `test_every_page_renders_after_import` |
| TC-UX-02-2 | UX-02 | Line comparison | Lines that disagree are highlighted with the difference | E | New |
| TC-UX-03-1 | UX-03 | Filter by person, provider, status, plan year, each alone and combined | Only matching visits listed | I | New |
| TC-UX-03-2 | UX-03 | Sort by dollars at issue, descending | Highest first; ties broken by date | I | New |
| TC-UX-03-3 | UX-03 | Filter with no results | "No visits match" with a clear-filters link | E | New |
| TC-UX-03-4 | UX-03 | Reload or share a filtered list URL | Same filter restored | I | Exists (partial): `test_every_page_renders_after_import` (`/visits?status=...`) |
| TC-UX-04-1 | UX-04 | Open items: $80.00 due in 40 days, $15.00 due in 3 days, $200.00 no deadline | Ranked per the agreed rule (dollars, then deadline); rule shown on screen | U | New |
| TC-UX-04-2 | UX-04 | Resolve an item | Leaves the queue | U | New |
| TC-UX-05-1 | UX-05 | Each finding type | Has a plain-language sentence with the amounts, e.g. "The provider is asking for $80.00 more than your insurer says you owe" | U | New |
| TC-UX-05-2 | UX-05 | Scan all finding templates | None renders only a code (e.g. "CO-45") without explanation | U | New |
| TC-UX-05-3 | UX-05 | Readability of finding text | Grade 8 or below on a standard readability score | R | New |
| TC-UX-06-1 | UX-06 | Household with 3 members | Per-person totals sum to the family total | U | New |
| TC-UX-06-2 | UX-06 | Switch individual ↔ family | View changes; choice kept across pages | E | New |
| TC-UX-07-1 | UX-07 | Dashboard figures | Spend by year, person, category and payment source equal the underlying totals; deductible and OOP progress equal REC-07 | U | New |
| TC-UX-07-2 | UX-07 | Savings recovered tile | Equals DSP-07 lifetime total | U | New |
| TC-UX-08-1 | UX-08 | Export one visit as PDF and CSV | Content matches the visit detail; totals tie | I | New |
| TC-UX-08-2 | UX-08 | Export a year as CSV | One row per allocation; column totals equal the dashboard | I | New |
| TC-UX-08-3 | UX-08 | Provider name beginning with "=" | Escaped in CSV (no formula injection) | S | New |
| TC-UX-09-1 | UX-09 | First run | Wizard: household → plans and accounts → first upload → first reconciliation | E | New |
| TC-UX-09-2 | UX-09 | Quit the wizard midway and return | Resumes at the step left | E | New |
| TC-UX-10-1 | UX-10 | 375px-wide phone: capture a photo and review the visit list | No horizontal scroll; camera capture works one-handed; tap targets ≥ 44px | E | New |
| TC-UX-10-2 | UX-10 | 1280px desktop: full reconciliation of a 6-line visit | All panels usable without zooming | E | New |

### 3.9 Privacy, security and pseudonymization (PRV)

All PRV cases use the identifier seed set (2.3). "Outbound capture" means routing all app traffic through an intercepting proxy and searching every payload for the seeded values.

| TC | Req | Scenario | Expected result | Level | Status |
| --- | --- | --- | --- | --- | --- |
| TC-PRV-01-1 | PRV-01 | Full workflow (upload → extract → reconcile → draft); capture all traffic from the application tier to the back-end tier and AI services | No seeded name, SSN, member ID, account #, address, phone or email in any captured payload | S | New |
| TC-PRV-01-2 | PRV-01 | Inspect back-end databases, logs, queues and AI request logs | No seeded identifiers; the token map exists only in the identity vault | S | New |
| TC-PRV-01-3 | PRV-01 | Tokens for 1,000 identifiers | Random (not a hash of the value); no collisions | U | New |
| TC-PRV-02-1 | PRV-02 | One person across 10 documents | One person token links all 10 | U | New |
| TC-PRV-02-2 | PRV-02 | Father and son both "John Smith" (Sr/Jr) in one household | Two person tokens, separated by DOB or member ID | U | New |
| TC-PRV-03-1 | PRV-03 | "JOHN A. SMITH", "Smith, John", "john  smith"; member IDs "W123-456-789" and "W123456789" | One token per person and one per member ID | U | New |
| TC-PRV-03-2 | PRV-03 | "Jon Smith" (nickname list) | Same token as "John Smith" only when another identifier agrees | U | New |
| TC-PRV-03-3 | PRV-03 | "John Smith" vs "Joan Smith" | Different tokens | U | New |
| TC-PRV-04-1 | PRV-04 | Photo of an EOB with seeded identifiers | Scrubbed image re-OCR'd finds none of the identifiers | S | New |
| TC-PRV-04-2 | PRV-04 | Free text (letter body, notes field) | Identifiers replaced by tokens | S | New |
| TC-PRV-04-3 | PRV-04 | Scrubbing recall across the corpus | Meets the agreed target (propose ≥ 99% of seeded identifiers) | S | New |
| TC-PRV-05-1 | PRV-05 | Two visits 14 days apart, shifted | Interval still 14 days; offset consistent per person | U | New |
| TC-PRV-05-2 | PRV-05 | Visit on 2026-12-30; content for it sent to the AI service | Back-end records keep 2026-12-30 (plan year 2026); the AI payload carries the person's shifted date | S | New |
| TC-PRV-06-1 | PRV-06 | Scan client-to-application and every inter-tier connection | TLS 1.2 or later only; no plaintext connection carries data | S | New |
| TC-PRV-06-2 | PRV-06 | Read the database and document folder from disk without the key | Contents unreadable | S | New |
| TC-PRV-06-3 | PRV-06 | Back-end tier operator tries to read the identity vault or originals | Cannot decrypt them; per-household keys live in the key management service | S | New |
| TC-PRV-07-1 | PRV-07 | Restore the identity vault from backup onto a fresh server | Linkage restored; documents resolve to the same people | S | New |
| TC-PRV-07-2 | PRV-07 | Restore with the wrong passphrase | Fails; nothing decrypted; no hint leaks | S | New |
| TC-PRV-07-3 | PRV-07 | Member loses their phone and password | Regains access through MFA account recovery; all data and linkage intact | E | New |
| TC-PRV-08-1 | PRV-08 | Outbound capture during a full session | No requests to advertising or third-party analytics domains | S | New |
| TC-PRV-08-2 | PRV-08 | Analytics events | Only event name, pseudonymous install ID, timestamp and app version; no amounts, providers, codes or identifiers | S | New |
| TC-PRV-08-3 | PRV-08 | Content Security Policy | Third-party scripts blocked | S | New |
| TC-PRV-09-1 | PRV-09 | Export all data | Every record and original file present (compared with a store inventory) | I | New |
| TC-PRV-09-2 | PRV-09 | Delete account | Records, originals and vault entries removed at once; confirmation shown; backups age out within 35 days | I | New |
| TC-PRV-09-3 | PRV-09 | After deletion | Sign-in and restore impossible; only security and access logs without health content remain, deleted after one year | S | New |
| TC-PRV-10-1 | PRV-10 | Read and change records | Each action logged with actor, action, record and time | U | New |
| TC-PRV-10-2 | PRV-10 | Member opens the access log; attempt to edit a log entry | Log visible; edits impossible or detected | S | New |
| TC-PRV-11-1 | PRV-11 | Sign in with password only | Second factor required; no data reachable before it | S | New |
| TC-PRV-11-2 | PRV-11 | Member of household A requests visit, document and API ids belonging to household B | Not found or forbidden; nothing from household B returned or leaked in errors | S | New |
| TC-PRV-11-3 | PRV-11 | Sign out; session idle past the timeout | Session tokens invalid; next request needs sign-in | S | New |

### 3.10 Regulatory and compliance (CMP)

| TC | Req | Scenario | Expected result | Level | Status |
| --- | --- | --- | --- | --- | --- |
| TC-CMP-01-1 | CMP-01 | Review the breach response plan | Names owners, detection sources and notice timelines for individuals and the FTC per the Health Breach Notification Rule | R | New |
| TC-CMP-01-2 | CMP-01 | Tabletop exercise: simulated unauthorized disclosure | Plan followed end to end; notices drafted within the required time | M | New |
| TC-CMP-01-3 | CMP-01 | Simulated anomalous access on the server (bulk export by one account, access from a new region) | Alert raised and incident opened | S | New |
| TC-CMP-02-1 | CMP-02 | First run | Separate opt-in for collection and for sharing; both unchecked by default; no health data collected before opt-in | E | New |
| TC-CMP-02-2 | CMP-02 | Withdraw consent | Collection and sharing stop; user told what happens to existing data | E | New |
| TC-CMP-02-3 | CMP-02 | Consent record | Stores consent text version and timestamp | I | New |
| TC-CMP-03-1 | CMP-03 | Compare the data-flow inventory with each privacy policy statement | Every mismatch logged as a defect; zero open at release | R | New |
| TC-CMP-03-2 | CMP-03 | Policy readability | Plain language (grade 8 or below) | R | New |
| TC-CMP-04-1 | CMP-04 | Every screen that recommends an action (TAX-03, TAX-07, PRE-02 to PRE-07, DSP-02, REC-09 appealable) | Shows the information-not-advice disclaimer | U | New |
| TC-CMP-05-1 | CMP-05 | Provider-sourced and consumer-uploaded records | Stored in separate logical stores; no query joins them without an explicit path | R | New |
| TC-CMP-06-1 | CMP-06 | Annual review | Review note recorded; reference tables carry new versions with effective dates | R | New |
| TC-CMP-06-2 | CMP-06 | 2027 limits loaded | 2026 records still checked against 2026 values | U | New |

### 3.11 Platform and non-functional (PLT)

| TC | Req | Scenario | Expected result | Level | Status |
| --- | --- | --- | --- | --- | --- |
| TC-PLT-01-1 | PLT-01 | Look up the HSA family limit for 2025 and 2026 | Each year returns its own value from a versioned table | U | New |
| TC-PLT-01-2 | PLT-01 | Update a reference table | Past findings keep the version they used | U | New |
| TC-PLT-01-3 | PLT-01 | Inspect the code | No IRS limits, codes or categories hard-coded outside the tables | R | New |
| TC-PLT-02-1 | PLT-02 | Each release: held-out sample of ≥ 50 documents graded by hand before confirmation | Extracted amounts ≥ 95% correct | M | New |
| TC-PLT-02-2 | PLT-02 | Findings dismissed by the member as wrong | False-positive rate computed per release and ≤ 5% | U | New |
| TC-PLT-03-1 | PLT-03 | Any finding or recommendation | Stores rule ID, rule version and source document IDs; "why" view shows them | U | New |
| TC-PLT-03-2 | PLT-03 | Rule changes to a new version | Old findings still show the old version | U | New |
| TC-PLT-04-1 | PLT-04 | Capture AI extraction calls from the back-end tier | Only pseudonymized content sent | S | New |
| TC-PLT-04-2 | PLT-04 | Override an AI-extracted value and classification | Override saved and used; AI value still visible for audit | E | New |
| TC-PLT-05-1 | PLT-05 | 50 typical uploads (1 to 3 page PDF or one photo, one visit), timed without confirmation time | p95 machine time under 60 seconds | P | New |
| TC-PLT-06-1 | PLT-06 | Scenario library coverage report | At least one redacted real scenario per REC rule; report lists REC IDs without one | R | New |
| TC-PLT-06-2 | PLT-06 | CI pipeline | Library runs on every change; failure blocks merge | R | New |
| TC-PLT-06-3 | PLT-06 | Seeded-identifier scan of the library | No real identifiers in fixtures | S | New |
| TC-PLT-07-1 | PLT-07 | Contract tests with sample FHIR EOB, HSA export and X12 835 payloads | Each adapter maps to the same internal model; REC-01 holds | I | New |
| TC-PLT-08-1 | PLT-08 | KPI job on a fixture dataset with known answers | First-pass match rate, findings per visit, dollars recovered and time to resolution equal the expected values | U | New |

---

## 4. Traceability matrix

One row per PRD requirement. **Blocked by** lists the conflicts or ambiguities that hold back at least one of its cases.

**Totals:** 100 requirements, 326 test cases (P1 183, P2 134, P3 9). 3 cases (2 requirements) are blocked on a decision; 22 are already partly or fully automated.

| Req | Priority | Test cases | Levels | Blocked by | Automated today |
| --- | --- | --- | --- | --- | --- |
| ING-01 | P1 | 1, 2, 3, 4, 5 (5) | EI | — | — |
| ING-02 | P1 | 1, 2, 3, 4 (4) | EI | — | — |
| ING-03 | P1 | 1, 2, 3, 4 (4) | IU | — | — |
| ING-04 | P1 | 1, 2, 3, 4 (4) | IU | — | — |
| ING-05 | P1 | 1, 2, 3, 4 (4) | EI | — | — |
| ING-06 | P2 | 1, 2 (2) | I | — | — |
| ING-07 | P1 | 1, 2, 3, 4, 5 (5) | I | — | — |
| ING-08 | P1 | 1, 2, 3, 4, 5 (5) | I | — | — |
| ING-09 | P2 | 1, 2, 3, 4, 5 (5) | IU | — | — |
| ING-10 | P1 | 1, 2, 3 (3) | EI | — | 1 partly |
| MAT-01 | P1 | 1, 2, 3, 4, 5 (5) | IU | — | — |
| MAT-02 | P1 | 1, 2, 3 (3) | IU | — | — |
| MAT-03 | P1 | 1, 2, 3, 4 (4) | U | — | 1 partly |
| MAT-04 | P1 | 1, 2, 3, 4 (4) | U | — | 1 partly |
| MAT-05 | P1 | 1, 2, 3, 4, 5 (5) | EU | — | — |
| MAT-06 | P1 | 1, 2, 3, 4, 5 (5) | U | — | — |
| MAT-07 | P1 | 1, 2, 3, 4, 5 (5) | EI | — | 2 partly |
| MAT-08 | P2 | 1, 2, 3, 4, 5 (5) | U | — | — |
| MAT-09 | P1 | 1, 2, 3, 4 (4) | IU | — | 1 partly |
| MAT-10 | P1 | 1, 2, 3, 4, 5 (5) | EIU | — | 1 partly |
| REC-01 | P1 | 1, 2, 3, 4, 5, 6 (6) | U | — | 1 partly |
| REC-02 | P1 | 1, 2, 3, 4, 5 (5) | U | — | 2 partly |
| REC-03 | P1 | 1, 2, 3, 4, 5 (5) | U | — | 1 partly |
| REC-04 | P1 | 1, 2, 3, 4 (4) | U | — | 1 partly |
| REC-05 | P1 | 1, 2, 3, 4 (4) | U | — | 1 partly |
| REC-06 | P2 | 1, 2, 3, 4, 5 (5) | U | — | — |
| REC-07 | P1 | 1, 2, 3, 4, 5, 6 (6) | U | — | 1 partly |
| REC-08 | P1 | 1, 2, 3, 4 (4) | U | — | — |
| REC-09 | P2 | 1, 2, 3 (3) | U | — | — |
| REC-10 | P2 | 1, 2, 3, 4, 5 (5) | IU | — | — |
| REC-11 | P1 | 1, 2, 3, 4, 5 (5) | EU | — | 1 partly |
| REC-12 | P2 | 1, 2, 3 (3) | U | PRD open question | — |
| REC-13 | P1 | 1, 2, 3, 4 (4) | U | — | 1 partly |
| ALC-01 | P1 | 1, 2, 3, 4 (4) | U | — | — |
| ALC-02 | P2 | 1, 2, 3, 4 (4) | U | — | — |
| ALC-03 | P1 | 1, 2, 3 (3) | U | — | — |
| ALC-04 | P1 | 1, 2, 3, 4 (4) | IU | — | 1 partly |
| ALC-05 | P2 | 1, 2, 3 (3) | U | — | — |
| ALC-06 | P1 | 1, 2 (2) | U | — | — |
| ALC-07 | P2 | 1, 2, 3 (3) | E | — | — |
| ALC-08 | P2 | 1, 2, 3 (3) | U | — | — |
| TAX-01 | P2 | 1, 2, 3, 4 (4) | U | — | all (ADR-043) |
| TAX-02 | P2 | 1, 2, 3, 4, 5 (5) | U | — | all (ADR-043) |
| TAX-03 | P2 | 1, 2, 3, 4, 5 (5) | U | — | all (ADR-043) |
| TAX-04 | P1 | 1, 2, 3, 4 (4) | IU | — | all (ADR-043) |
| TAX-05 | P3 | 1, 2, 3 (3) | U | — | — |
| TAX-06 | P2 | 1, 2, 3, 4, 5 (5) | U | — | all (ADR-043) |
| TAX-07 | P2 | 1, 2, 3 (3) | EU | — | all (ADR-043) |
| TAX-08 | P2 | 1, 2, 3 (3) | U | — | all (ADR-043) |
| TAX-09 | P2 | 1, 2, 3 (3) | U | — | all (ADR-043) |
| TAX-10 | P2 | 1, 2, 3 (3) | U | — | all (ADR-043) |
| PRE-01 | P2 | 1, 2, 3 (3) | EIU | — | — |
| PRE-02 | P2 | 1, 2, 3 (3) | U | — | — |
| PRE-03 | P3 | 1, 2, 3 (3) | IU | — | — |
| PRE-04 | P2 | 1, 2 (2) | U | PRD open question | — |
| PRE-05 | P2 | 1, 2 (2) | U | — | — |
| PRE-06 | P2 | 1, 2 (2) | U | — | — |
| PRE-07 | P2 | 1 (1) | U | — | — |
| DSP-01 | P2 | 1, 2, 3 (3) | I | — | — |
| DSP-02 | P2 | 1, 2 (2) | EU | — | — |
| DSP-03 | P1 | 1, 2, 3 (3) | IU | — | 1 partly |
| DSP-04 | P2 | 1, 2, 3 (3) | U | — | — |
| DSP-05 | P2 | 1, 2, 3 (3) | U | — | — |
| DSP-06 | P3 | 1, 2 (2) | U | — | — |
| DSP-07 | P2 | 1, 2, 3 (3) | U | — | — |
| UX-01 | P1 | 1, 2, 3 (3) | EU | — | 1 partly |
| UX-02 | P1 | 1, 2 (2) | E | — | 1 partly |
| UX-03 | P1 | 1, 2, 3, 4 (4) | EI | — | 1 partly |
| UX-04 | P1 | 1, 2 (2) | U | — | — |
| UX-05 | P1 | 1, 2, 3 (3) | RU | — | — |
| UX-06 | P1 | 1, 2 (2) | EU | — | — |
| UX-07 | P2 | 1, 2 (2) | U | — | — |
| UX-08 | P2 | 1, 2, 3 (3) | IS | — | — |
| UX-09 | P2 | 1, 2 (2) | E | — | — |
| UX-10 | P1 | 1, 2 (2) | E | — | — |
| PRV-01 | P1 | 1, 2, 3 (3) | SU | — | — |
| PRV-02 | P1 | 1, 2 (2) | U | — | — |
| PRV-03 | P1 | 1, 2, 3 (3) | U | — | — |
| PRV-04 | P1 | 1, 2, 3 (3) | S | — | — |
| PRV-05 | P2 | 1, 2 (2) | SU | — | — |
| PRV-06 | P1 | 1, 2, 3 (3) | S | — | — |
| PRV-07 | P1 | 1, 2, 3 (3) | ES | — | — |
| PRV-08 | P1 | 1, 2, 3 (3) | S | — | — |
| PRV-09 | P2 | 1, 2, 3 (3) | IS | — | — |
| PRV-10 | P2 | 1, 2 (2) | SU | — | — |
| PRV-11 | P1 | 1, 2, 3 (3) | S | — | — |
| CMP-01 | P2 | 1, 2, 3 (3) | MRS | — | — |
| CMP-02 | P2 | 1, 2, 3 (3) | EI | — | — |
| CMP-03 | P2 | 1, 2 (2) | R | — | — |
| CMP-04 | P2 | 1 (1) | U | — | — |
| CMP-05 | P3 | 1 (1) | R | — | — |
| CMP-06 | P2 | 1, 2 (2) | RU | — | — |
| PLT-01 | P2 | 1, 2, 3 (3) | RU | — | — |
| PLT-02 | P2 | 1, 2 (2) | MU | — | — |
| PLT-03 | P2 | 1, 2 (2) | U | — | — |
| PLT-04 | P1 | 1, 2 (2) | ES | — | — |
| PLT-05 | P2 | 1 (1) | P | — | — |
| PLT-06 | P1 | 1, 2, 3 (3) | RS | — | — |
| PLT-07 | P2 | 1 (1) | I | — | — |
| PLT-08 | P2 | 1 (1) | U | — | — |

---

## Appendix A. Existing automated tests (regression baseline)

`uv run pytest` runs these 32 tests today. They are the Release 0 regression suite. One test encoded Release 0's five statuses; phase 1.4 updated it to the nine statuses (2026-10-17).

| Test | MVP requirement | PRD requirement | Note |
| --- | --- | --- | --- |
| `test_reconcile.py::test_sample_statuses_match_the_notes_in_the_sample_file` | Section 5 status order, D5 | REC-11, MAT-10 | Updated 2026-10-17 (phase 1.4, X-03): expects the nine REC-11 statuses; Matched is Complete, Waiting is Awaiting EOB |
| `test_reconcile.py::test_bill_vs_eob_discrepancy_and_provider_overpayment` | C2, C4 | REC-02, REC-03 | Provider-level overpayment (X-07) |
| `test_reconcile.py::test_hsa_flags` | C5, D11 | MAT-09, TAX-03, TAX-04 | Consistent with X-02 decision (HSA by default) |
| `test_reconcile.py::test_limit_progress_uses_eob_deductible` | HR-8 | REC-07 | |
| `test_reconcile.py::test_payment_with_no_claim_is_flagged` | C7 | none | See Appendix B |
| `test_reconcile.py::test_suspected_relationship_joins_ledgers_and_flags_until_confirmed` | C8, ST-5, D10 | MAT-04 | |
| `test_reconcile.py::test_visit_that_drops_off_a_later_statement_is_settled` | Payment allocation rule | ALC-04, MAT-08 | X-07 |
| `test_reconcile.py::test_prior_year_visit_on_a_current_statement_is_carried_in` | Payment allocation rule | none | See Appendix B |
| `test_reconcile.py::test_possible_duplicate_payments` | C4 | REC-04 | |
| `test_reconcile.py::test_eob_that_does_not_add_up_fails_c1` | C1 | REC-01 | Asserts to-the-cent failure (X-06) |
| `test_reconcile.py::test_missing_eob_waits_then_becomes_missing` | Section 5 status, ST-7 | REC-05, REC-11 | 30-day threshold |
| `test_reconcile.py::test_individual_and_family_limits` | ST-1a, D12 | REC-07, MAT-03 | |
| `test_web.py::test_empty_home_has_hero_help_and_settings` | SH-1 to SH-5, HR-6 | UX-01 | X-13 |
| `test_web.py::test_every_page_renders_after_import` | HR, VL, VD, PL, IM, ST screens | UX-02, UX-03 | Smoke test only |
| `test_web.py::test_import_with_errors_saves_nothing` | IM-2 | none | See Appendix B |
| `test_web.py::test_settings_edits_are_saved_and_written_to_settings_json` | ST-1, ST-1a | MAT-03 | |
| `test_web.py::test_provider_notes_can_be_added_edited_and_deleted` | PL-4 | DSP-03 (partial) | Notes are per provider; DSP-03 logs are per case |
| `test_web.py::test_reimport_does_not_touch_notes` | PL-4, D13 | MAT-07 (spirit) | |
| `test_importer.py::test_money_round_trip` | NM-3 | none | Money in cents |
| `test_importer.py::test_schema_error_names_the_record_and_blocks_saving` | IM-2 | none | |
| `test_importer.py::test_reference_errors` | IM-2 | none | |
| `test_importer.py::test_references_can_point_at_records_already_saved` | IM-2, IM-4 | none | |
| `test_importer.py::test_reimport_is_idempotent_and_counts_updates` | IM-3, IM-4 | ING-07 (spirit) | Re-import updates by id, except member edits (X-08) |
| `test_importer.py::test_attached_files_are_copied_and_missing_ones_warned` | IM-5 | ING-10 | |
| `test_importer.py::test_provider_notes_import` | PL-4, IM-1 | none | |
| `test_web.py::test_reimport_keeps_settings_edits_unless_replaced` | IM-4, ST-1 to ST-5 | MAT-07 | Added Oct 15, 2026 for X-08 |
| `test_reconcile.py::test_open_balance_is_aged_and_repeat_notices_counted` | C6 | ALC-03 | Added Oct 15, 2026 (Release 0 gap) |
| `test_reconcile.py::test_hsa_counts_sit_behind_the_hsa_totals` | HR-4 | UX-04 | Added Oct 15, 2026 (Release 0 gap) |
| `test_web.py::test_home_hsa_counts_link_to_filtered_lists` | HR-4, C6 | UX-03, UX-04 | Added Oct 15, 2026 (Release 0 gap) |
| `test_reconcile.py::test_hsa_counts_include_carry_in_visits_like_the_totals` | HR-4 | UX-04 | Added Oct 15, 2026 (code review) |
| `test_importer.py::test_owner_edits_made_after_the_preview_are_still_kept` | IM-4 | MAT-07 | Added Oct 15, 2026 (code review) |
| `test_importer.py::test_records_deleted_in_the_app_stay_deleted` | IM-4, PL-4 | MAT-07 | Added Oct 15, 2026 (code review) |

## Appendix B. Built MVP behavior with no PRD requirement

These are built and tested in Release 0, but the PRD does not mention them. Before Release 1, each needs a PRD requirement or a decision to drop it.

| MVP item | What it does | Closest PRD item | Suggestion |
| --- | --- | --- | --- |
| C6 Balance outstanding | Open balance with age in days and second-notice flag (completed Oct 15, 2026) | ALC-03 (balance only) | Add a REC requirement for open-balance aging |
| C7 HSA payment without a claim | HSA payment with nothing to match | REC-05 (inverse case only) | Add to REC-05 or a new REC item |
| C8 / ST-5 Provider relationships | Suspected, confirmed or rejected same-provider pairs, flagged until confirmed | MAT-04 | Expand MAT-04 to include the confirm step |
| PL-1 to PL-4 Provider ledger and notes | Per-provider running balance, three balances side by side, dated contact log | ALC-03, DSP-03 | Add a UX requirement for the provider ledger |
| Payment allocation rules | Oldest visit first; dropped-off visit treated as settled; prior-year visits carried in | ALC-04, REC-13 (dropped-off visit now covered) | Fold the rest into ALC-04 once X-07 is decided |
| IM-2 All-or-nothing import | Any error means nothing is saved | ING-05 | Add to ING as a general data-integrity rule |
| HR-7 Plan-year selector, HR-2 summary tiles | Year scoping and hero totals | UX-03, UX-07 | Settle with X-13 |
| SH-1 to SH-5 App shell, help stub, favicon | Header, help and settings icons | none | Add a UX requirement or leave as design detail |
