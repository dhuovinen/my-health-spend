# My Health Spend (MHS): Product Requirements

Oct 15, 2026 · @Donald Huovinen · Revised Oct 15, 2026 with owner decisions (see [Decisions](#decisions-oct-15-2026))

## Scope and sizing

A robust MHS needs about 100 requirements across 11 areas. Around 45 would cover the reconciliation core, but would leave tax optimization, disputes, household handling and privacy too thin to build from.

The count is driven by multiplication: three parties (provider, insurer, member), four or more documents per visit, line-item detail, several payment accounts, several household members, and weeks of lag between documents. Each factor adds its own edge cases.

| Area | ID prefix | Requirements | Why this depth |
| --- | --- | --- | --- |
| Ingestion and capture | ING | 10 | Documents arrive in many formats, out of order, from many sources |
| Data model and matching | MAT | 10 | Matching a bill to a claim to a payment is the hardest technical problem |
| Reconciliation and discrepancies | REC | 13 | The core value: every check needs a defined rule and tolerance |
| Charge allocation | ALC | 8 | Each line splits across insurer, member, accounts and adjustments |
| HSA, FSA and tax | TAX | 10 | Distinct rules per account type, plan year and household member |
| Pre-visit strategy | PRE | 7 | Priority two; needs plan and price data the core already collects |
| Disputes and follow-up | DSP | 7 | Findings are worthless unless the member can act on them |
| User experience | UX | 10 | Visit cards, household view, dashboards, exports |
| Privacy and security | PRV | 11 | Pseudonymization and consumer health data obligations |
| Regulatory and compliance | CMP | 6 | FTC, state health data laws, future HIPAA path |
| Platform and non-functional | PLT | 8 | Integrations, accuracy targets, performance, auditability |

**Priority key:** R0 = Release 0, the local MVP already built (see [`MVP_REQUIREMENTS.md`](MVP_REQUIREMENTS.md) and [Release 0 baseline](#release-0-baseline)). P1 = Release 1 (server-side post-visit reconciliation). P2 = the release after, including pre-visit strategy. P3 = later or provider-facing.

**Do we need to go deeper?** Not yet. About 100 is the right altitude for a product spec. The next level down (field-level schemas, specific CARC/RARC code handling, UI specs) belongs in design docs per area, written as each area enters the backlog.

## Patterns borrowed from comparable apps

The closest non-healthcare analog is accounts payable three-way matching: a provider bill, an EOB and a payment record map neatly onto an invoice, a purchase order and a receipt. Most requirements below borrow from one of these six patterns.

| Pattern | Where it comes from | What MHS borrows |
| --- | --- | --- |
| Three-way match with tolerances | [Accounts payable automation](https://tray.ai/automate/three-way-match/) | Match at the line, not the total; auto-clear small variances; treat a price change as an exception; track first-pass match rate |
| Open-item reconciliation | Bank and ledger reconciliation | Matched, partially matched and unmatched states; aging of open items; a period close (plan year end) |
| Receipt capture and auto-match | Expense management apps | Photo or PDF capture with OCR; auto-link a card swipe to its receipt; policy flags for ineligible spend |
| Shared-cost allocation | Bill-splitting apps | One charge split across several payers with running balances per party |
| Line-item medical audit | [Goodbill](https://www.geekwire.com/2024/goodbill-raises-2m-and-expands-customer-base-to-unearth-and-challenge-medical-billing-errors/), [Healthvocate](https://www.producthunt.com/posts/1240957) | Compare bill to EOB line by line; screen for financial assistance; the user approves anything sent on their behalf |
| Receipt vault for deferred reimbursement | HSA administrators | Store receipts now, reimburse from the HSA years later |

One lesson recurs: the provider bill often arrives before the EOB, so patients cannot know the right amount yet. A [patent on bill-to-EOB validation](https://patents.justia.com/patent/10664921) centers on that timing problem, and MHS should treat "waiting for the EOB" as a first-class state.

## Ingestion and document capture

Release 1 runs on uploaded documents; direct connections to insurers come later through the patient access APIs.

| ID | Requirement | Priority |
| --- | --- | --- |
| ING-01 | Accept uploads as PDF, phone photo (JPG/PNG/HEIC) and forwarded email, including multi-page documents | P1 |
| ING-02 | Classify each document by type: provider statement, itemized bill, EOB, HSA/FSA statement, card transaction, pharmacy receipt, good faith estimate, other | P1 |
| ING-03 | Extract header fields: patient, provider, date(s) of service, claim number, account number, statement date, amounts billed, allowed, paid, owed | P1 |
| ING-04 | Extract line items with CPT/HCPCS, revenue and NDC codes, units, modifiers and per-line amounts when present | P1 |
| ING-05 | Show a confidence score per extracted field and let the user confirm or correct before data enters reconciliation | P1 |
| ING-06 | Learn from corrections so the same provider or insurer layout extracts better next time | P2 |
| ING-07 | Detect duplicate uploads (same document twice) and near-duplicates (a re-sent statement with a new date) | P1 |
| ING-08 | Import HSA/FSA transactions by CSV export from the account administrator | P1 |
| ING-09 | Connect to insurers through the CMS patient access API (FHIR ExplanationOfBenefit, CARIN Blue Button) with per-app member consent | P2 |
| ING-10 | Keep the original file unchanged, linked to its extracted data, for audit and dispute evidence | P1 |

Payer APIs return adjudicated claims with remittance and member cost-sharing as FHIR resources, and members authorize each app separately ([Patient Access API overview](https://www.health-samurai.io/docs/payerbox/interop-apis/patient-access)).

## Data model and matching

The visit is the anchor object: every document, claim, line and payment attaches to one. Matching must be explainable, because the user has to trust why two documents were linked.

| ID | Requirement | Priority |
| --- | --- | --- |
| MAT-01 | Model Visit > Claim > Line item > Allocation, plus Payment and Document entities, with many-to-many links where needed (one payment can cover several visits) | P1 |
| MAT-02 | Model the household: member, spouse and dependents, each with their own coverage, accounts and visits | P1 |
| MAT-03 | Model coverage per person and plan year: insurer, plan type, deductible, out-of-pocket max, copays, coinsurance, network | P1 |
| MAT-04 | Normalize provider identity across documents (billing entity vs. rendering provider vs. facility; NPI when available) | P1 |
| MAT-05 | Auto-match documents to visits using person, provider, date of service, claim number and amounts, with a match score and the reasons shown | P1 |
| MAT-06 | Match at line level: pair each bill line to its EOB line by code, date and charge; handle one-to-many (bundled codes) and many-to-one | P1 |
| MAT-07 | Let the user confirm, reject, split or merge any proposed match. Member decisions win: a match, split, merge, correction or setting the member made is never overwritten by an import, re-extraction, payer feed or new document version. When new data conflicts, keep the member's version, show what differs, and let the member accept the new data explicitly | P1 |
| MAT-08 | Track claim versions: original, reprocessed, corrected and appealed EOBs supersede earlier ones while history stays visible. If the member edited the earlier version, the new version does not apply automatically; the visit goes to Needs review with both versions side by side (MAT-07) | P1 |
| MAT-09 | Link payments (HSA card swipe, HSA reimbursement, credit card, check) to the visit and lines they paid | P1 |
| MAT-10 | Show a visit's document completeness: which of bill, itemized bill, EOB, receipt and payment proof are present, expected or not applicable. What is expected depends on the visit's payment path (insurance or self-pay) and category (REC-05) | P1 |

## Reconciliation and discrepancy detection

Every dollar is checked by three identities, and every gap between the documents becomes a typed finding with a dollar amount.

**1. Adjudication: where the billed amount goes.** Checked per line and per claim from the EOBs.

```latex
\text{Billed} = \text{Plan adjustment} + \text{Other savings} + \text{Primary paid} + \text{Secondary paid} + \text{Member responsibility}
```

- **Plan adjustment:** the contractual write-off down to the allowed amount.
- **Other savings:** any further discount the EOB reports separately, such as "additional savings" or a repricing discount. Zero when absent.
- **Secondary paid:** from a secondary EOB under coordination of benefits (ALC-05). Zero with one plan.
- **Member responsibility:** what the last payer's EOB says the member owes.
- **Self-pay visits** have no EOB. For them, Billed = Self-pay discount + Member responsibility.

**2. Cost-sharing: why the member owes it.** Checked on each EOB.

```latex
\text{Member responsibility} = \text{Deductible} + \text{Copay} + \text{Coinsurance} + \text{Not covered}
```

**3. Settlement: what happened to what the member owes.** Checked per visit and per provider over time, because payments, refunds and write-offs arrive weeks apart.

```latex
\text{Member responsibility} = \text{Payments} - \text{Refunds} + \text{Provider write-offs} + \text{Still owed}
```

- **Payments:** from every source (ALC-02).
- **Provider write-offs:** prompt-pay discounts, financial assistance and small-balance write-offs made *after* adjudication.
- **Still owed:** positive means a balance is due; negative means a credit is due from the provider.

The decision behind these identities (Oct 15, 2026): adjudication buckets (ALC-01) and settlement balances (ALC-03) are kept apart. Write-offs and "still owed" are settlement items, not shares of the billed amount, so nothing is counted twice.

| ID | Requirement | Priority |
| --- | --- | --- |
| REC-01 | Check identities 1 (adjudication) and 2 (cost-sharing) per line and per claim, and flag any remainder | P1 |
| REC-02 | Flag when the provider asks for more than the EOB's member responsibility (balance billing or a missed adjustment) | P1 |
| REC-03 | Flag when the member paid more than member responsibility, across all payment methods combined (overpayment and credit owed) | P1 |
| REC-04 | Flag duplicate charges: same code, date and provider billed twice, or the same bill paid twice | P1 |
| REC-05 | Flag a bill with no matching claim (provider may not have filed with insurance) and treat a claim with no bill yet as a waiting state, not an error. Visits that never go through insurance are processed without a claim and are never flagged for lacking one: self-pay visits, and categories such as supplements, equipment and cash-price prescriptions. For those, a receipt or bill plus payment proof is complete | P1 |
| REC-06 | Verify cost-sharing against the plan: copay amount, coinsurance rate, and deductible applied correctly given year-to-date accumulators | P1 |
| REC-07 | Track deductible and out-of-pocket accumulators per person and family from EOBs, and flag charges after the out-of-pocket max is met | P1 |
| REC-08 | Flag network status problems: an in-network provider processed as out-of-network, or a surprise out-of-network bill | P2 |
| REC-09 | Translate denial and adjustment codes into plain language, and flag denials that look appealable (e.g. missing information, coding error) | P2 |
| REC-10 | Apply configurable tolerances: a difference under $1.00 per check auto-clears and is recorded as "cleared within tolerance" (visible on request). Cleared amounts at one provider are added up per plan year and flagged once they pass $5.00. A changed unit price is always flagged regardless of size: the same code from the same provider costing differently from an earlier bill or EOB in the plan year, or from the good faith estimate | P1 |
| REC-11 | Give each visit one status, the first that applies in this order: In dispute (an open case, DSP-01) → Discrepancy found (a check failed) → Needs review (unconfirmed data or a conflicting new version) → Balance outstanding (still owed > 0) → Awaiting EOB (insured visit, no EOB yet, within the waiting threshold) → Awaiting documents (another expected document missing within the threshold) → Missing documents (an expected document missing past the threshold) → Resolved (had a finding, now closed) → Complete. The waiting threshold defaults to 30 days and is configurable | P1 |
| REC-12 | Compare self-pay or cash price against the negotiated rate when both are known, and surface the cheaper option (your $105 vs. $125 case) | P2 |
| REC-13 | Check identity 3 (settlement) per visit and per provider: every dollar of member responsibility must be paid, refunded, written off or still owed. Flag any unexplained remainder, such as a visit that drops off a statement with no matching payment | P1 |

## Charge allocation across parties

Each dollar billed must land with exactly one party, and the user must see that split per line, per visit and per year. This is the bill-splitting pattern applied to provider, insurer, member and accounts. ALC-01 splits the billed amount (identity 1); ALC-02 and ALC-03 track how the member's share is settled (identity 3).

| ID | Requirement | Priority |
| --- | --- | --- |
| ALC-01 | Split every line into adjudication buckets that sum to the billed amount: plan adjustment, other savings, primary paid, secondary paid, deductible, copay, coinsurance, not covered (self-pay: self-pay discount, member responsibility) | P1 |
| ALC-02 | Split the member's share further by payment source: HSA card, HSA reimbursement, FSA, LPFSA, HRA, personal card, check, payment plan | P1 |
| ALC-03 | Keep settlement balances per party per visit: paid by source, refunds, provider write-offs, still owed to the provider, credit due from the provider, and reimbursement due from the HSA | P1 |
| ALC-04 | Allocate a lump-sum payment across several visits or lines, by the provider's statement when available or by user choice | P1 |
| ALC-05 | Handle secondary insurance and coordination of benefits: primary EOB, secondary EOB, then member remainder | P2 |
| ALC-06 | Attribute every allocation to the household member who received care, for per-person and per-account reporting | P1 |
| ALC-07 | Show the allocation as a visual breakdown per visit (billed to adjustment to insurer to you to which account) | P1 |
| ALC-08 | Track refunds and credits from providers back to the original payment source, including refunds owed to an HSA | P2 |

## HSA, FSA and tax efficiency

The HSA is the primary vehicle. For an HSA-eligible member it is usually the better account: it never expires, it grows tax-free and it moves with the member. So MHS centers on paying qualified expenses from the HSA, or tracking out-of-pocket qualified expenses so they can be reimbursed from it later. FSAs, limited-purpose FSAs and HRAs are supported where they exist but are secondary (owner decision, Oct 15, 2026). The rules change yearly, so limits live in a data table, not in code.

| ID | Requirement | Priority |
| --- | --- | --- |
| TAX-01 | Tag each expense as qualified, not qualified, or needs documentation (e.g. a letter of medical necessity), using IRS Publication 502 categories | P1 |
| TAX-02 | Model each account's rules: HSA, health FSA (grace period or carryover), limited-purpose FSA, HRA; plan year dates; claim run-out deadlines | P2 |
| TAX-03 | Recommend which account should pay each expense, defaulting to the HSA when the member is HSA-eligible and the expense is qualified. A user setting chooses "pay from HSA now" (default) or "save HSA for later" (pay another way and add the expense to the receipt vault, TAX-04). Suggest an FSA, LPFSA or HRA only when it is the sole tax-advantaged account for that expense or its balance would otherwise be forfeited | P2 |
| TAX-04 | Keep an HSA receipt vault: qualified expenses paid outside the HSA after it was opened, with a running total the member can reimburse later. With "pay from HSA now", these show as reimbursement opportunities (Release 0 C5); with "save HSA for later", as savings banked for later | P1 |
| TAX-05 | Alert before FSA money expires: balance at risk, days left, and eligible expenses not yet claimed | P3 |
| TAX-06 | Track contributions against yearly IRS limits, including family vs. self-only coverage, the 55+ catch-up, and mid-year proration | P2 |
| TAX-07 | Flag an HSA payment for a non-qualified expense, and guide the member to return it to the custodian as a mistaken distribution before it becomes taxable | P1 |
| TAX-08 | Flag eligibility conflicts: a general-purpose FSA or Medicare enrollment blocks HSA contributions | P2 |
| TAX-09 | Respect who each account may pay for: HSA funds cover the spouse and tax dependents; FSA rules differ for adult children under 26 | P2 |
| TAX-10 | Produce a year-end summary: HSA distributions by person and purpose, unreimbursed qualified expenses, and medical spend for a possible itemized deduction | P2 |

**2026 reference values** ([OneDigital summary of IRS limits](https://www.onedigital.com/blog/irs-2026-health-welfare-limits)): HSA $4,400 self-only, $8,750 family, $1,000 catch-up at 55+; health FSA $3,400 with up to $680 carryover.

## Pre-visit strategy

Priority two reuses what reconciliation already collects (plan terms, accumulators, past prices) to answer one question before an appointment: what will this cost me, and how should I pay?

| ID | Requirement | Priority |
| --- | --- | --- |
| PRE-01 | Let the user create a planned visit (provider, service, date) that becomes a real visit once documents arrive | P2 |
| PRE-02 | Estimate member cost from plan terms and current deductible and out-of-pocket progress, showing the math | P2 |
| PRE-03 | Show price reference points: past amounts paid for the same service, the provider's quote, and public price transparency data where available | P3 |
| PRE-04 | Compare self-pay vs. insurance, including whether a self-pay amount would count toward the deductible | P2 |
| PRE-05 | Generate a checklist of questions to ask the provider (in network? cost estimate? itemized bill?) | P2 |
| PRE-06 | Store a provider's good faith estimate and compare the final bill against it | P2 |
| PRE-07 | Recommend the payment account for the planned visit using the TAX rules | P2 |

## Disputes and follow-up

A finding only creates value when it turns into money back or a corrected bill. MHS drafts and tracks, but the member approves and sends everything.

| ID | Requirement | Priority |
| --- | --- | --- |
| DSP-01 | Turn any finding into a case with the evidence attached (bill, EOB, payment proof, the specific lines and amounts) | P1 |
| DSP-02 | Draft the right message for the case: itemized bill request, billing correction to the provider, refund request, claim resubmission, or appeal to the insurer | P2 |
| DSP-03 | Provide a call script and a log for phone calls: date, person spoken to, reference number, outcome | P1 |
| DSP-04 | Track case status and follow-up dates, with reminders when a provider or insurer has not responded | P1 |
| DSP-05 | Track appeal deadlines from the EOB date, and No Surprises Act deadlines where they apply | P2 |
| DSP-06 | Screen hospital bills for financial assistance (charity care) eligibility and point to the hospital's application | P3 |
| DSP-07 | Record the outcome (corrected, refunded, written off, denied) and the dollars recovered, feeding a lifetime savings total | P1 |

## User experience and reporting

The visit card list from the original plan stays the home screen. The rest of the UX exists to explain findings in plain language and to show money recovered.

| ID | Requirement | Priority |
| --- | --- | --- |
| UX-01 | Home screen lists visits as cards with person, provider, date, status badge, document completeness and amount at issue | P1 |
| UX-02 | Visit detail shows documents, line-by-line comparison, allocation breakdown, findings and case history in one place | P1 |
| UX-03 | Filter and sort visits by person, provider, status, plan year and dollars at issue | P1 |
| UX-04 | A "needs your attention" queue ranks open items by dollars at stake and deadline | P1 |
| UX-05 | Explain every finding in plain language with the numbers shown, never just a code | P1 |
| UX-06 | Household view with per-person totals and a switch between individual and family | P1 |
| UX-07 | Dashboard: spend by year, person, category and payment source; deductible and out-of-pocket progress; savings recovered | P2 |
| UX-08 | Export a visit or a year as PDF and CSV (for taxes, a dispute or an advisor) | P2 |
| UX-09 | Guided onboarding: add household, add plans and accounts, upload the first visit, see the first reconciliation | P1 |
| UX-10 | Work well on a phone for capture and review, and on a desktop for detailed reconciliation | P1 |

## Privacy, security and pseudonymization

**Architecture decision (Oct 15, 2026):** data resides server-side. Clients (web, and later mobile) send documents to an application tier over TLS. The application tier stores them and passes them to a back-end tier that runs extraction, matching, reconciliation and any AI processing. Identifiers are replaced with tokens at the application tier, so the back-end tier and AI services see random tokens, never names or ID numbers. The token map lives in a separate identity vault service, and only the application tier re-identifies data, for the signed-in member. Build to HIPAA-grade security now so a later provider offering is not a rebuild.

| ID | Requirement | Priority |
| --- | --- | --- |
| PRV-01 | Replace direct identifiers (names, SSN, member ID, account numbers, addresses, phone, email) with random tokens in the application tier, before data reaches the back-end tier or any AI service; the token map lives only in the identity vault | P1 |
| PRV-02 | Resolve each person to one pseudonymous person ID, so all their documents link without exposing identity | P1 |
| PRV-03 | Normalize identifiers before tokenizing (case, spacing, nicknames, dashes) so one person never becomes several tokens | P1 |
| PRV-04 | Scrub identifiers from document text and images (OCR plus entity detection), not only from structured fields | P1 |
| PRV-05 | Shift dates by a consistent per-person offset wherever exact dates are not needed in the back-end tier, keeping intervals intact | P2 |
| PRV-06 | Encrypt all data in transit and at rest; encrypt the identity vault with per-member keys, kept separate from the data they protect (key custody is an open question) | P1 |
| PRV-07 | Back up the identity vault, encrypted, with tested recovery, so a lost key or failed server does not mean lost linkage | P1 |
| PRV-08 | Never send data to advertising pixels or third-party analytics; product analytics use pseudonymous events only | P1 |
| PRV-09 | Let the member export all their data and delete their account and data, with a deletion confirmation | P1 |
| PRV-10 | Keep an access log of who and what touched each record, viewable by the member | P2 |
| PRV-11 | Authenticate every member with multi-factor sign-in, and isolate each household's data so no query can return another household's records | P1 |

## Regulatory and compliance

As a consumer app, MHS is generally outside HIPAA but inside FTC and state consumer health data rules. These requirements need confirmation from a healthcare privacy attorney before launch.

| ID | Requirement | Priority |
| --- | --- | --- |
| CMP-01 | Meet the FTC Health Breach Notification Rule: breach detection, a response plan, and notice to users and the FTC on unauthorized disclosure | P1 |
| CMP-02 | Collect opt-in consent for health data collection and any sharing, separately, as Washington's My Health My Data Act requires; apply it nationally for simplicity | P1 |
| CMP-03 | Publish a plain-language privacy policy that matches actual data practices exactly | P1 |
| CMP-04 | State clearly that MHS gives information, not legal, tax or medical advice, wherever it recommends an action | P1 |
| CMP-05 | Keep provider-sourced data logically separate from consumer-uploaded data, ready for business associate agreements and the HIPAA Security Rule | P3 |
| CMP-06 | Run a yearly review of rules that change: IRS limits, state health data laws, payer API rules | P2 |

## Platform and non-functional

Accuracy and explainability matter more than speed: one wrong "you were overcharged" finding costs more trust than ten missed ones.

| ID | Requirement | Priority |
| --- | --- | --- |
| PLT-01 | Reference data as versioned tables: CPT/HCPCS descriptions, denial and adjustment codes, IRS limits, eligible expense categories | P1 |
| PLT-02 | Accuracy targets: at least 95% of extracted amounts correct after user confirmation sampling, and a measured false-positive rate for findings | P1 |
| PLT-03 | Every finding and recommendation is traceable to its rule, rule version and source documents | P1 |
| PLT-04 | AI extraction runs on pseudonymized content only, and a person can always see and override what the AI concluded | P1 |
| PLT-05 | Process a typical upload to a reconciled visit in under one minute | P2 |
| PLT-06 | A test library of real-world scenarios (redacted) covering each REC rule, run on every change | P1 |
| PLT-07 | An API and import layer designed for payer FHIR, HSA administrator and clearinghouse feeds | P2 |
| PLT-08 | Measure first-pass match rate, findings per visit, dollars recovered and time to resolution as product KPIs | P2 |

## Priorities and open questions

67 of the 100 requirements are P1 (Release 1), which is too much for one build. The leanest useful Release 1 is single-person, upload-only reconciliation on the server-side architecture, deferring household, vault backup and dispute drafting.

| Priority | Count | Meaning |
| --- | --- | --- |
| P1 | 67 | Release 1: server-side post-visit reconciliation |
| P2 | 29 | The release after: tax optimization, pre-visit, payer APIs |
| P3 | 4 | Later: price transparency data, FSA expiry alerts, charity care, provider-facing |

### Release 0 baseline

Release 0 is the local MVP built on Oct 9, 2026 from [`MVP_REQUIREMENTS.md`](MVP_REQUIREMENTS.md). It is a single-owner laptop app with JSON import. It already covers these requirements fully or in part; Release 1 builds on them rather than starting over.

| Requirement | Release 0 coverage |
| --- | --- |
| ING-08 | Partial: HSA export converted by `tools/build_ingest.py` (XLS), not uploaded in the app |
| ING-10 | Partial: attached originals copied unchanged and viewable |
| MAT-01 | Partial: visits, documents and payments; no line or allocation entities |
| MAT-02, ALC-06 | Partial: household members, member on each visit, providers assigned to members |
| MAT-03 | Partial: plans per year with limits, coinsurance, copays and coverage order |
| MAT-04 | Partial: provider aliases and suspected/confirmed provider relationships; no NPI or provider roles |
| MAT-07 | Partial: in-app edits survive re-import unless the owner chooses to replace them |
| MAT-09, ALC-04 | Partial: payments belong to a provider and are applied oldest visit first |
| MAT-10 | Partial: document panel shows missing or received; required documents by category |
| REC-01 | Partial: identities 1 and 2 at claim level, including other savings |
| REC-02 | Full (check C2) |
| REC-03, REC-13 | Partial: overpayment and unexplained settlement per provider group (C4) |
| REC-04 | Partial: probable duplicate payments within 14 days |
| REC-05 | Partial: missing EOB waits 30 days; HSA payments with no claim flagged (C7) |
| REC-07 | Partial: deductible and out-of-pocket progress per person and family |
| REC-08 | Partial: bill, EOB and provider network status agree (C3) |
| REC-11 | Partial: five of the nine statuses |
| ALC-03 | Partial: provider ledger with running balance |
| TAX-04 | Partial: payments outside the HSA flagged as reimbursement opportunities |
| DSP-03 | Partial: dated contact log per provider |
| UX-01 to UX-05 | Partial: visit cards, visit detail, filters, a needs-attention list, plain-language checks |
| PLT-06 | Partial: made-up sample file and synthetic unit tests, not a redacted real-world library |

### Decisions (Oct 15, 2026)

| # | Decision |
| --- | --- |
| 1 | The built MVP is Release 0. P1 now means Release 1. |
| 2 | The HSA is the primary payment vehicle; FSAs and HRAs are secondary (TAX section intro, TAX-03, TAX-04; TAX-05 moved to P3). |
| 3 | One ordered visit status list (REC-11). |
| 4 | Data resides server-side, with an application tier and a back-end tier (Privacy section intro, PRV-01, PRV-05 to PRV-07; PRV-11 added). |
| 5 | Three money identities: adjudication, cost-sharing and settlement (REC intro, REC-01, ALC-01, ALC-03; REC-13 added). |
| 6 | Tolerance: under $1.00 per check auto-clears; cumulative cap $5.00 per provider per plan year (REC-10). |
| 7 | Member decisions win over imports, feeds and new versions (MAT-07, MAT-08). Built into Release 0 import. |
| 8 | Visits that never go through insurance are processed without a claim (REC-05, MAT-10). |

### Open questions

- [ ] Cut P1 further for Release 1? A candidate is ING-01 to 05, MAT-01, 05, 06, 10, REC-01 to 05, REC-13, ALC-01, UX-01 and 02, PRV-01, 06 and 11, about 23 items.
- [ ] Is the household (MAT-02, UX-06) in Release 1, or single person first?
- [ ] Does self-pay count toward the deductible on your plan? This decides how REC-12 and PRE-04 compute savings.
- [ ] Should these requirements go into a backlog and be groomed one by one, as on the family calendar app?
- [x] Which tolerance should auto-clear small differences (REC-10)? $1.00 per check, with a $5.00 cumulative cap per provider per plan year.
- [ ] Web app, mobile app, or both for Release 1 (UX-10)? Data resides server-side either way.
- [ ] Identity vault key custody (PRV-06, PRV-07): who holds the keys, and how does a member recover?

## Sources

- [Three-way matching guidance, Tray.ai](https://tray.ai/automate/three-way-match/)
- [Goodbill funding and approach, GeekWire](https://www.geekwire.com/2024/goodbill-raises-2m-and-expands-customer-base-to-unearth-and-challenge-medical-billing-errors/)
- [Healthvocate launch, Product Hunt](https://www.producthunt.com/posts/1240957)
- [Bill-to-EOB validation patent, Justia](https://patents.justia.com/patent/10664921)
- [Patient Access API overview, Health Samurai](https://www.health-samurai.io/docs/payerbox/interop-apis/patient-access)
- [2026 IRS health and welfare limits, OneDigital](https://www.onedigital.com/blog/irs-2026-health-welfare-limits)
