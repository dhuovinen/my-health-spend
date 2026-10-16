# Vision

## The problem

People pay for healthcare through three parties at once: the provider, the insurer and a payment account such as an HSA. Nobody reconciles the three, so billing errors and avoidable overpayment go unseen. A single visit produces a provider bill, an insurance decision (the EOB) and a payment, often weeks apart and in different formats. The full problem statement is in [`My Health Spend (MHS) Problem Statement & Plan.md`](<My Health Spend (MHS) Problem Statement & Plan.md>).

## What MHS does

1. **After a visit (priority one):** match the provider bill, the EOB and the payment for every visit. Show whether they agree, flag every gap with a dollar amount, and help the member get money back.
2. **Before a visit (priority two):** estimate what the member will owe, compare self-pay with insurance, and recommend how to pay.

The HSA is the primary payment vehicle. MHS helps the member pay qualified expenses from the HSA, or bank receipts to reimburse later. FSAs and HRAs are supported but secondary.

## Who it is for

| Stage | User |
| --- | --- |
| Release 0 | The owner, on a laptop, with JSON import |
| Release 1 | The owner's household (spouse and dependents), on a server-side responsive web app with document upload |
| Release 2 and later | Other individuals and households, once the compliance launch gate is passed; later, a provider-facing offering |

## Principles

- **The visit is the unit.** Every document, claim, line and payment attaches to a visit (payments through the provider's ledger).
- **Every dollar is accounted for.** Three money identities (adjudication, cost-sharing, settlement) must hold, and any remainder becomes a finding.
- **Accuracy beats speed.** One wrong "you were overcharged" finding costs more trust than ten missed ones. Every finding shows its numbers and the documents behind it.
- **The member decides.** Imports, extraction and feeds never overwrite a member's edit. MHS drafts and tracks; the member approves and sends.
- **Privacy by design.** Back-end processing and AI see tokens, never names or ID numbers. No advertising or third-party analytics, ever.
- **Information, not advice.** HSA and tax flags are possibilities, not eligibility rulings.

## Success criteria

| Measure | Target | Source |
| --- | --- | --- |
| Dollars recovered or avoided per household per year | Tracked from Release 1; target set after 3 months of real use | PLT-08, DSP-07 |
| False-positive findings (dismissed by the member as wrong) | ≤ 5% of findings | PLT-02, test plan A-01 |
| Extracted amounts correct before confirmation | ≥ 95% | PLT-02 |
| First-pass match rate (documents auto-linked to the right visit) | Tracked from Release 1 | PLT-08 |
| Upload to reconciled visit, machine time | p95 under 60 seconds | PLT-05 |
| Identifiers reaching the back-end tier or AI services | Zero | PRV-01, PLT-04 |

## Where the details live

| Topic | Document |
| --- | --- |
| Requirements (100, by release) | [Product Requirements](<My Health Spend (MHS) Product Requirements.md>) |
| Release 0 as built | [MVP_REQUIREMENTS.md](MVP_REQUIREMENTS.md) |
| System design | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Plan and current phase | [ROADMAP.md](ROADMAP.md) |
| Decisions | [DECISIONS.md](DECISIONS.md) |
| Testing | [TESTING.md](TESTING.md), [TEST_PLAN.md](TEST_PLAN.md) |
| Running it locally | [SETUP.md](SETUP.md) |
