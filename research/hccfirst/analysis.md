# HCC FIRST vs. My Health Spend: focus, gaps and opportunities

2026-10-10. Based on the documentation in this folder and on MH$'s problem statement, MVP requirements
and its first run on the owner's real 2026 data.

## 1. HCC FIRST's focus in one paragraph

HCC FIRST answers one question, **"should I pay this bill, and how much?"**, one bill at a time, before
you pay. You upload a bill (ideally with its EOB); AI plus human reviewers check the bill against the EOB
and return a one-sentence verdict (okay to pay / don't pay yet / question this). Revenue comes from a
$10/month subscription for unlimited reviews and a $35/month tier where humans negotiate large
hospital/facility bills for a 10% success fee (capped at $200). Around that core sit a document vault,
basic payment/HSA tagging, a free education library, a price-shopping feature still in preview, and an
employer-sponsorship channel still under discussion. The brand is built on candor, privacy and peace of
mind.

## 2. Side-by-side focus

| Dimension | HCC FIRST | My Health Spend (as articulated) |
| --- | --- | --- |
| Core question | Is this bill right and should I pay it? | Do provider, insurer and payments agree, and where is money leaking? |
| Unit of work | A bill (with its EOB) | A visit, rolled up into a **provider ledger** and a **plan year** |
| Timing | Before payment | **After the fact first** (priority one), then before the visit (priority two) |
| Payments | "Payment and spending tracker", HSA/FSA *tagging* | Payments reconciled against what was owed; overpayments, underpayments, duplicates; HSA statement reconciled to claims |
| HSA | A label on spending | An optimization target: pay from HSA, reimbursement opportunities, fees, contribution limits (backlog) |
| Household | One person per account; household "not built yet" | Members, family deductible/OOP, member–provider relationships |
| Plan year | Taught in a slider module; you're told to *ask your plan* where you are in the year | Computed from your claims: deductible and OOP progress against your limits |
| Provider identity | Not addressed | Explicit matching of claim names to card-merchant names, tracked as suspected/confirmed |
| Data ingestion | Upload or photograph bills and EOBs, one visit at a time; never asks for records access | Bulk: insurer claims export, HSA transaction export, provider statement PDFs → a full year in one import |
| Resolution | Human negotiation of large facility bills (paid) | Self-advocacy: findings, provider notes/contact log; negotiation not in scope |
| Pre-visit | "Shop Services" preview: price list per facility (cash vs allowed), generic | Strategy using *your* accumulators and HSA balance: self-pay vs insurance, which account, expected cost |
| Education | Strong: six interactive modules | Help (?) stubbed |
| Scope of spend | Medical and facility bills | Provider visits, services, Rx, supplements, equipment |
| Privacy model | Cloud vault, "HIPAA-aware", FTC HBNR | Local-first MVP; NFRs deferred until multi-user |
| Business model | B2C subscription + success fee; employer sponsorship | Not yet defined |

## 3. Where you overlap

1. **Bill vs. EOB check.** Their entire core product is your check C2 (and part of C1). Both say the
   amount due should equal the EOB's patient responsibility.
2. **Waiting for documents.** Their "don't pay yet, we need the EOB" matches your Waiting / Missing
   documents statuses.
3. **Price shopping before care.** Their Shop Services preview (cash price vs insurance allowed, site of
   care) overlaps your priority two, including the self-pay vs insurance question.
4. **HSA awareness and a document vault.** Both have them, at very different depths.

## 4. Focus areas that differ

**Theirs, not yours:**
- **Negotiation as a paid service** for large facility bills (human advocates, authorizations, success fee).
- **Consumer education** as a free acquisition funnel (Know Before You Pay).
- **Employer channel** (sponsorship with a strict privacy firewall).
- **Uninsured / self-pay bill review.**

**Yours, not theirs:**
- **Look-back reconciliation of money already paid** across a provider relationship, including recovery
  of overpayments. Their flow is review-then-pay; it doesn't go back over past payments.
- **The HSA as a financial account to optimize**, not a tag.
- **Household and plan-year accumulators**: family deductible and OOP tracking from real claims.
- **Cross-source identity and evidence**: provider aliases, relationship matching, statement history,
  notes.
- **The macro story** (health as a share of GDP and household budgets) behind the company, plus spend
  categories beyond medical bills (supplements, equipment).

## 5. What your own data shows that their model would miss

From the first MH$ run on 2026 data (11 visits, 24 HSA card payments to providers):

| Finding | Amount | Would a per-bill, pre-payment review catch it? |
| --- | --- | --- |
| Men's Mental Health: claim denied with $0 owed, HSA paid anyway | $340.02 | No; the money was already paid at time of service, with no bill to upload |
| Baptist: owed $23.60 per EOB, HSA paid $122.50 (suspected same provider) | $98.90 | No; needs payment-to-claim matching across provider names |
| Coastal Dermatology: point-of-service collection above EOB amount | $25.02 net | No; collected at the visit |
| Southeastern Retina, Jan 21: insurer says $1,230 not covered, provider never billed it | $1,230.00 | Partly; a bill vs EOB check flags the mismatch, but only if the user uploads both |
| Southeastern Retina: $902.15 on a second notice | $902.15 | Yes; this is their sweet spot |
| HSA payments with no matching claim (other members or never-claimed) | $1,613.66 | No; needs the HSA statement as an input |
| Family deductible probably met around Sep 22 (claims show it stopped applying) | Future claims | No; needs plan-year accumulators |

Most of the dollars at stake came from **payments made at or right after the visit**, which never turn
into a bill a user would upload. That's the gap a reconciliation product owns.

## 6. Opportunities for differentiated value

Ordered by how strongly they differentiate and how close MH$ already is.

1. **"Money back", not just "don't overpay".** Position MH$ as the tool that finds money you've *already*
   paid but didn't owe: point-of-service overcollections, denied-claim payments, duplicates, credits
   sitting with providers. Pair each finding with a refund-request letter and a notes trail. HCC FIRST's
   promise is peace of mind before paying; yours can be recovered dollars.
2. **HSA optimizer.** Reconcile the HSA statement to claims and bills, then flag:
   - charges paid outside the HSA → reimbursement opportunities,
   - unreimbursed out-of-pocket expenses kept as a tax-free "shoebox" (receipts on file for later reimbursement),
   - account fees (the $1/month paper-statement fee),
   - contributions vs the annual limit and spending vs balance.
   HCC FIRST only tags. HSA custodians and apps track receipts but don't see claims. You can own the join.
3. **Household plan-year intelligence.** Family deductible and OOP progress computed from everyone's
   claims, with alerts like:
   - "deductible met Sep 22; later claims shouldn't carry a deductible",
   - "you're $X from the OOP max; schedule elective care before Dec 31".
   They explicitly tell users to ask the plan. Household accounts are on their "not built" list.
4. **Personalized pre-visit strategy (priority two) that beats a price list.** Their Shop Services shows
   cash vs allowed ranges and leaves the deductible math to the user. MH$ already knows the accumulators
   and HSA balance, so it can say "for you, today, insurance costs $X and self-pay $Y; pay from the HSA".
   Add the open question of whether self-pay counts toward the deductible as a feature (help submit the
   claim) rather than a caveat.
5. **Bulk, year-at-a-time ingestion.** Their per-bill upload is slow for someone with a year of claims.
   Your converter turns three exports into a full year. Productize importers for the major insurer
   portals, HSA custodians and statement layouts (backlog B-18, B-20); later, consented connections.
   Respect the trust line they've drawn ("never ask for records access") by making connections optional
   and explicit.
6. **Provider relationship ledger and evidence file.** A running ledger per provider with matched names,
   statement history, payments and a dated contact log is a natural dispute file. Add follow-up tracking
   (B-22), templates (itemized-bill request with CPT codes, refund request, EOB/bill mismatch query) and an
   exportable case packet. This is a self-serve alternative to paid negotiation, and a hand-off into it.
7. **Privacy-first by architecture.** They argue privacy through policy ("HIPAA-aware"). You could argue
   it through design: local-first or on-device processing, user-held data, export anytime. That's a
   sharper claim than theirs, but keep it only if the product stays that way.
8. **Wider spend scope.** Rx, supplements, equipment, telehealth, dental and vision; their product is
   centered on medical/facility bills. This feeds the "where your health dollars go" story.

## 7. Where they're ahead (learn from, or partner)

- **Polish and voice:** one-sentence verdicts, candid limitation statements, example results on the home
  page. Worth borrowing (see [ux-and-design.md](ux-and-design.md)).
- **Education content:** their interactive modules are a good model for MH$'s ? section, and stronger if
  applied to the user's *own* documents.
- **Human negotiation:** not something MH$ should build early. A referral or partnership for large facility
  bills could complement MH$'s findings.
- **Legal groundwork:** their HIPAA-aware page, FTC Health Breach Notification Rule position and Terms
  are a useful checklist for your deferred NFRs (ND-3, ND-5, ND-6, ND-14).
- **Distribution ideas:** a free tier with a document limit, and employer sponsorship with a hard privacy
  firewall.

## 8. Risks and watch-points

- **They can move toward you.** They already have a payment tracker and HSA tagging; payment-to-EOB
  matching is a logical next step. Your defensible edge is the depth of the reconciliation engine:
  household + plan year + provider identity + HSA statement + bulk ingestion.
- **Messaging collision.** "Peace of mind about every medical bill" and "know what's okay to pay" will
  sound similar to a bill-vs-EOB pitch. Lead MH$ with outcomes they don't claim: money recovered, HSA
  optimized, family plan year tracked.
- **Evidence.** Their testimonials are unverified, but they have them. Your real-data findings
  ($1,693.94 at stake, $924.15 unpaid, $1,613.66 unexplained HSA payments in one person's year) are a
  stronger proof point once the HCC FIRST-style polish is added.

## 9. Suggested next steps for MH$

1. Add a **one-sentence verdict** to each visit card and visit detail (borrowing their strongest UX idea).
2. Add a **"Recovered / recoverable"** total to the hero and a refund-request template on overpaid visits.
3. Prioritize backlog items that deepen the moat: B-14 (other members' claims), B-18/B-20 (importers),
   B-19 (HSA contribution limit), B-22 (note follow-ups), and B-7 (personalized pre-visit strategy).
4. Use the ? (help) stub for **document anatomy on the user's own EOB and statement**.
5. Decide the business model early: a flat subscription like theirs, an HSA-custodian or employer
   partnership, or a share of recovered money. Each implies different positioning against HCC FIRST.
