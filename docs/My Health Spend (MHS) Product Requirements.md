# My Health Spend (MHS): Product Requirements

Oct 15, 2026 · @Donald Huovinen

## Scope and sizing

A robust MHS needs about 98 requirements across 11 areas. Around 45 would cover the reconciliation core, but would leave tax optimization, disputes, household handling and privacy too thin to build from.

The count is driven by multiplication: three parties (provider, insurer, member), four or more documents per visit, line-item detail, several payment accounts, several household members, and weeks of lag between documents. Each factor adds its own edge cases.

| Area | ID prefix | Requirements | Why this depth |
| --- | --- | --- | --- |
| Ingestion and capture | ING | 10 | Documents arrive in many formats, out of order, from many sources |
| Data model and matching | MAT | 10 | Matching a bill to a claim to a payment is the hardest technical problem |
| Reconciliation and discrepancies | REC | 12 | The core value: every check needs a defined rule and tolerance |
| Charge allocation | ALC | 8 | Each line splits across insurer, member, accounts and adjustments |
| HSA, FSA and tax | TAX | 10 | Distinct rules per account type, plan year and household member |
| Pre-visit strategy | PRE | 7 | Priority two; needs plan and price data the core already collects |
| Disputes and follow-up | DSP | 7 | Findings are worthless unless the member can act on them |
| User experience | UX | 10 | Visit cards, household view, dashboards, exports |
| Privacy and security | PRV | 10 | Pseudonymization and consumer health data obligations |
| Regulatory and compliance | CMP | 6 | FTC, state health data laws, future HIPAA path |
| Platform and non-functional | PLT | 8 | Integrations, accuracy targets, performance, auditability |

**Priority key:** P1 = MVP (post-visit reconciliation, priority one in the plan). P2 = next release, including pre-visit strategy. P3 = later or provider-facing.

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

The MVP runs on uploaded documents; direct connections to insurers come later through the patient access APIs.

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
| MAT-07 | Let the user confirm, reject, split or merge any proposed match; a manual decision is never overwritten automatically | P1 |
| MAT-08 | Track claim versions: original, reprocessed, corrected and appealed EOBs supersede earlier ones while history stays visible | P1 |
| MAT-09 | Link payments (HSA card swipe, HSA reimbursement, credit card, check) to the visit and lines they paid | P1 |
| MAT-10 | Show a visit's document completeness: which of bill, itemized bill, EOB and payment proof are present, expected or not applicable | P1 |

## Reconciliation and discrepancy detection

Every covered line must satisfy one identity, and every gap between the documents becomes a typed finding with a dollar amount.

```latex
\text{Billed} = \text{Plan adjustment} + \text{Insurer paid} + \text{Member responsibility}
```

```latex
\text{Member responsibility} = \text{Deductible} + \text{Copay} + \text{Coinsurance} + \text{Not covered}
```

| ID | Requirement | Priority |
| --- | --- | --- |
| REC-01 | Check the billed-equals-sum identity per line and per claim, and flag any remainder | P1 |
| REC-02 | Flag when the provider asks for more than the EOB's member responsibility (balance billing or a missed adjustment) | P1 |
| REC-03 | Flag when the member paid more than member responsibility, across all payment methods combined (overpayment and credit owed) | P1 |
| REC-04 | Flag duplicate charges: same code, date and provider billed twice, or the same bill paid twice | P1 |
| REC-05 | Flag a bill with no matching claim (provider may not have filed with insurance) and a claim with no bill yet (waiting state, not an error) | P1 |
| REC-06 | Verify cost-sharing against the plan: copay amount, coinsurance rate, and deductible applied correctly given year-to-date accumulators | P1 |
| REC-07 | Track deductible and out-of-pocket accumulators per person and family from EOBs, and flag charges after the out-of-pocket max is met | P1 |
| REC-08 | Flag network status problems: an in-network provider processed as out-of-network, or a surprise out-of-network bill | P2 |
| REC-09 | Translate denial and adjustment codes into plain language, and flag denials that look appealable (e.g. missing information, coding error) | P2 |
| REC-10 | Apply configurable tolerances (e.g. under $1 auto-clears), but always flag a changed unit price regardless of size | P1 |
| REC-11 | Give each visit a status: Complete, Awaiting documents, Awaiting EOB, Needs review, Discrepancy found, In dispute, Resolved | P1 |
| REC-12 | Compare self-pay or cash price against the negotiated rate when both are known, and surface the cheaper option (your $105 vs. $125 case) | P2 |

## Charge allocation across parties

Each dollar billed must land with exactly one party, and the user must see that split per line, per visit and per year. This is the bill-splitting pattern applied to provider, insurer, member and accounts.

| ID | Requirement | Priority |
| --- | --- | --- |
| ALC-01 | Split every line into allocation buckets: plan adjustment, insurer paid, deductible, copay, coinsurance, not covered, provider write-off, still owed | P1 |
| ALC-02 | Split the member's share further by payment source: HSA card, HSA reimbursement, FSA, LPFSA, HRA, personal card, check, payment plan | P1 |
| ALC-03 | Keep a running balance per party per visit (owed to provider, credit due from provider, reimbursement due from account) | P1 |
| ALC-04 | Allocate a lump-sum payment across several visits or lines, by the provider's statement when available or by user choice | P1 |
| ALC-05 | Handle secondary insurance and coordination of benefits: primary EOB, secondary EOB, then member remainder | P2 |
| ALC-06 | Attribute every allocation to the household member who received care, for per-person and per-account reporting | P1 |
| ALC-07 | Show the allocation as a visual breakdown per visit (billed to adjustment to insurer to you to which account) | P1 |
| ALC-08 | Track refunds and credits from providers back to the original payment source, including refunds owed to an HSA | P2 |

## HSA, FSA and tax efficiency

The optimization goal is simple to state: spend expiring money first (FSA), and preserve money that grows tax-free (HSA) for as long as the member wants. The rules behind it change yearly, so limits live in a data table, not in code.

| ID | Requirement | Priority |
| --- | --- | --- |
| TAX-01 | Tag each expense as qualified, not qualified, or needs documentation (e.g. a letter of medical necessity), using IRS Publication 502 categories | P1 |
| TAX-02 | Model each account's rules: HSA, health FSA (grace period or carryover), limited-purpose FSA, HRA; plan year dates; claim run-out deadlines | P2 |
| TAX-03 | Recommend which account should pay each expense, defaulting to FSA first and HSA last, with a user setting for "pay from HSA now" vs. "save HSA for later" | P2 |
| TAX-04 | Keep an HSA receipt vault: qualified expenses paid out of pocket after the HSA was opened, with a running total the member can reimburse later | P1 |
| TAX-05 | Alert before FSA money expires: balance at risk, days left, and eligible expenses not yet claimed | P2 |
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

The design choice is a token vault held on the member's side: the server and any AI processing see random tokens, never names or ID numbers. Build to HIPAA-grade security now so a later provider offering is not a rebuild.

| ID | Requirement | Priority |
| --- | --- | --- |
| PRV-01 | Replace direct identifiers (names, SSN, member ID, account numbers, addresses, phone, email) with random tokens before data leaves the device; the token map stays with the member | P1 |
| PRV-02 | Resolve each person to one pseudonymous person ID, so all their documents link without exposing identity | P1 |
| PRV-03 | Normalize identifiers before tokenizing (case, spacing, nicknames, dashes) so one person never becomes several tokens | P1 |
| PRV-04 | Scrub identifiers from document text and images (OCR plus entity detection), not only from structured fields | P1 |
| PRV-05 | Shift dates by a consistent per-person offset wherever exact dates are not needed server-side, keeping intervals intact | P2 |
| PRV-06 | Encrypt all data in transit and at rest; encrypt the token vault with a key the member controls | P1 |
| PRV-07 | Offer encrypted backup and recovery of the vault so a lost phone does not mean lost linkage | P1 |
| PRV-08 | Never send data to advertising pixels or third-party analytics; product analytics use pseudonymous events only | P1 |
| PRV-09 | Let the member export all their data and delete their account and data, with a deletion confirmation | P1 |
| PRV-10 | Keep an access log of who and what touched each record, viewable by the member | P2 |

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

65 of the 98 requirements are P1, which is too much for a first build. The leanest useful MVP is single-person, upload-only reconciliation, deferring household, vault backup and dispute drafting.

| Priority | Count | Meaning |
| --- | --- | --- |
| P1 | 65 | MVP: post-visit reconciliation |
| P2 | 30 | Next release: tax optimization, pre-visit, payer APIs |
| P3 | 3 | Later: price transparency data, charity care, provider-facing |

### Open questions

- [ ] Cut P1 further for a first prototype? A candidate is ING-01 to 05, MAT-01, 05, 06, 10, REC-01 to 05, ALC-01, UX-01 and 02, PRV-01 and 06, about 20 items.
- [ ] Is the household (MAT-02, UX-06) in the MVP, or single person first?
- [ ] Does self-pay count toward the deductible on your plan? This decides how REC-12 and PRE-04 compute savings.
- [ ] Should these requirements go into a backlog and be groomed one by one, as on the family calendar app?
- [ ] Which tolerance should auto-clear small differences (REC-10): $1, $5, or a percentage?
- [ ] Web app, mobile app, or both for the first build (UX-10)?

## Sources

- [Three-way matching guidance, Tray.ai](https://tray.ai/automate/three-way-match/)
- [Goodbill funding and approach, GeekWire](https://www.geekwire.com/2024/goodbill-raises-2m-and-expands-customer-base-to-unearth-and-challenge-medical-billing-errors/)
- [Healthvocate launch, Product Hunt](https://www.producthunt.com/posts/1240957)
- [Bill-to-EOB validation patent, Justia](https://patents.justia.com/patent/10664921)
- [Patient Access API overview, Health Samurai](https://www.health-samurai.io/docs/payerbox/interop-apis/patient-access)
- [2026 IRS health and welfare limits, OneDigital](https://www.onedigital.com/blog/irs-2026-health-welfare-limits)
