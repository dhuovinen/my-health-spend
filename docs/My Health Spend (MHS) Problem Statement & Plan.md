# My Health Spend (MHS): Problem Statement & Plan

Oct 9, 2026 · @Donald Huovinen

## Problem statement

People pay for healthcare through three parties at once (the provider, the insurer and a payment account such as an HSA), and nobody reconciles the three, so billing errors and avoidable overpayment go unseen.

A single visit produces a provider bill, an insurance decision and a payment, often weeks apart and in different formats. Today an individual cannot easily answer:

- Was the provider in network or out of network, and was I billed accordingly?
- Did the insurer process the claim, and does the amount I owe match what it says I owe?
- Am I overpaying, whether through a wrong rate, a duplicate charge or a copay applied incorrectly?
- Was the payment made from the right account (for example my HSA), and is anything still outstanding?
- Before the visit, which path costs me least: insurance, or self-pay at a discounted rate?

**Priority one:** look back at past visits and find where billing, insurance processing and payment do not line up. **Priority two:** give a clear strategy before an appointment.

## Why this matters

Healthcare is one of the largest places money goes in the US economy and in a household budget, which makes it a strong entry point for a company that helps individuals see where their health dollars are leaking. The framing from your notes: "I rob banks because that is where the money is at," a line commonly attributed to Willie Sutton.

- **Working name:** MH$, short for My Health Spend (MHS).
- **Macro view:** healthcare as a share of US GDP.
- **Household view:** where people spend, with housing and health as the two big slices.
- **Starting point:** help one person understand their own spend and inefficiencies, then grow toward optimization.

The two pie diagrams are for the presentation, not the build. They need sourced figures, so we capture them here and draw them later.

### Health in the economy

Health spending was 18.0% of US GDP in 2024 and health care employs about 11.7% of all US workers, a record share.

| Measure | Value | As of | Source |
| --- | --- | --- | --- |
| National health spending | $5.3 trillion, or $15,474 per person | 2024 | [CMS](https://www.cms.gov/data-research/statistics-trends-and-reports/national-health-expenditure-data/historical) |
| Health share of GDP | 18.0% (17.6% in 2023) | 2024 | [CMS](https://www.cms.gov/data-research/statistics-trends-and-reports/national-health-expenditure-data/historical) |
| Projected health share of GDP | 20.3% | 2033 | [CMS projections](https://www.cms.gov/files/document/national-health-expenditure-projections-results-presentation.pdf) |
| Health care jobs, share of all US jobs | 11.7% (all-time high) | Sep 2026 | [Health System Tracker](https://www.healthsystemtracker.org/brief/is-this-a-healthcare-economy/) |
| Health care jobs, level | about 18.5 million | mid-2026 | [American Action Forum](https://www.americanactionforum.org/weekly-checkup/the-health-care-jobs-boom-and-the-shortages-beneath-it/) |
| Health care job growth, 12 months | +372,000 (+2.0%), versus +124,000 (+0.1%) for all other jobs | Sep 2025 to Sep 2026 | [Health System Tracker](https://www.healthsystemtracker.org/brief/is-this-a-healthcare-economy/) |
| Registered nurses | 3.38 million, about 19% of 17.7 million healthcare practitioner and support workers | May 2025 | [Becker's, from BLS OEWS](https://www.beckershospitalreview.com/workforce/41-hospital-jobs-ranked-by-share-of-healthcare-workforce/) |
| Pharmaceutical and medicine manufacturing jobs | about 698,000 | 2024 | [Data USA](https://datausa.io/profile/naics/3254) |
| Medical equipment and supplies manufacturing jobs | about 798,000 | 2024 | [Data USA](https://datausa.io/profile/naics/3391) |

The health care jobs count covers physician offices, hospitals, outpatient centers, home health, and nursing and residential care. The two manufacturing rows come from a different dataset whose page names no source, so treat them as approximate and do not add them to the health care total. I could not find a sourced count for health insurance carriers yet.

### Where health lands in a household budget

Healthcare is the fifth-largest spending category for the average US household (7.9%) and the fourth-largest for households headed by someone 65 or older (12.7%).

**All households, 2024**

| Category | Average per year | Share of spending |
| --- | --- | --- |
| Housing | $26,266 | 33.4% |
| Transportation | $13,318 | 17.0% |
| Food | $10,169 | 12.9% |
| Personal insurance and pensions | $9,797 | 12.5% |
| **Healthcare** | **$6,197** | **7.9%** |
| All other categories | $12,788 | 16.3% |
| Total | $78,535 | 100.0% |

Source: [BLS Consumer Expenditures, 2024](https://www.bls.gov/news.release/cesan.nr0.htm). Personal insurance and pensions is mostly Social Security deductions and retirement contributions, so excluding it healthcare ranks fourth.

**Households headed by someone 65 or older, 2024**

| Category | Average per year | Share of spending |
| --- | --- | --- |
| Housing | $22,193 | 36.1% |
| Transportation | $9,538 | 15.5% |
| Food | $7,940 | 12.9% |
| **Healthcare** | **$7,799** | **12.7%** |
| Personal insurance and pensions | $3,480 | 5.7% |
| All other categories | $10,482 | 17.1% |
| Total | $61,432 | 100.0% |

Sources: BLS series for age 65 or over, via FRED: [total](https://fred.stlouisfed.org/series/CXUTOTALEXPLB0407M), [housing](https://fred.stlouisfed.org/series/CXUHOUSINGLB0407M), [transportation](https://fred.stlouisfed.org/series/CXUTRANSLB0407M), [food](https://fred.stlouisfed.org/series/CXUFOODTOTLLB0407M), [healthcare](https://fred.stlouisfed.org/series/CXUHEALTHLB0407M), [personal insurance and pensions](https://fred.stlouisfed.org/series/CXUINSPENSNLB0407M). I computed the shares and the "all other" rows by subtraction from the totals.

Households 65 and older spend about $1,600 more on healthcare per year than the average household ($7,799 against $6,197) on a budget about $17,100 smaller, which is why the share is 12.7% against 7.9%. Healthcare here means what households pay themselves, premiums included, not what insurers and government programs pay.

## Spend landscape

Spend falls into five categories and is paid through tax-advantaged accounts, while each covered visit runs through the Provider, Insurance and You triangle from your sketch.

- **What I spend on:** provider visits, services, supplements, Rx, health equipment.
- **How I pay:** HSA or FSA. Your note marks FSA "with details", which we still need to capture.

&#91;embedded content: Provider, Insurance and You · 3 parties, 3 documents\]

The provider sends a claim to the insurer, the insurer's decision (the EOB) tells you what you owe, and the provider bills you; the app checks that these three agree.

## Scenarios to model

The self-pay example shows why the price you pay depends on the path you pick: the provider mistakenly believed you had no insurance and offered a self-pay price of about $105, while the list price was about $250 and the insurance-negotiated rate about $125. Paying self-pay and then filing the claim could cost you less and cost the insurer less than the normal route, at the price of extra paperwork.

| Scenario | Question it answers | Documents needed |
| --- | --- | --- |
| Self-pay vs insurance | Is the self-pay price below the negotiated rate, and can I still file the claim? | Price quote, negotiated rate, plan rules |
| In network vs out of network | Was I billed at the right network rate? | Provider bill, insurer EOB |
| Copay, deductible, coinsurance | Did the insurer apply my cost share correctly? | EOB, plan summary |
| Bill vs EOB | Does what the provider billed me equal my responsibility on the EOB? | Provider bill, EOB |
| Wrong or duplicate payment | Did the money come from the right account, and was it paid twice? | HSA statement, card charge, bill |
| Outstanding balance | Is anything still owed or sent to collections? | Provider statement, payment record |

## Two use cases

The app serves one person at two moments: after a visit, to check that everything lines up (priority one), and before a visit, to choose the cheapest correct way to pay (priority two).

**1. After the visit: reconcile (build first).** Starting with past visits, the app takes the provider bill, the insurer's statement of what it processed, and the payment record, then shows whether they agree and flags the gaps. Output: a verdict per visit (matched, missing documents, discrepancy, balance outstanding) and the dollar amount at stake.

**2. Before the visit: strategy.** For a planned appointment, the app gathers the inputs and gives a takeaway.

- Inputs: provider and network status, service, negotiated rate, self-pay price, deductible and out-of-pocket progress, and HSA or FSA balance.
- Takeaway: which path to take (insurance or self-pay), which account to pay from, and what you should expect to owe.

## Product concept: the visit is the unit

The home screen is a list of visits, each a card that shows at a glance whether its documents are all present and agree; tapping a card opens the visit with every document and the reconciliation result.

**Visit card:** date, provider, service type (provider, service, supplements, Rx, equipment), total billed, what I paid, and a status badge: Complete and matched, Missing documents, Discrepancy, or Balance outstanding.

**Visit detail:** the assets below, each marked missing, received or matched, with the reconciliation checks beneath.

| Asset | Source | What it tells us |
| --- | --- | --- |
| Provider bill | Provider or portal | What was charged and what I am asked to pay |
| Insurance decision (EOB) | Insurer | Allowed amount, insurer payment, my responsibility, network status |
| Payment record | HSA statement, FSA, card | What I paid, from which account, and when |
| Outstanding balance | Provider statement | Anything still owed |

## Reconciliation checks and data inputs

The core test is that every dollar billed is accounted for by the insurer, a contractual write-off, or me.

```latex
\text{Billed charge} = \text{Insurer paid} + \text{Contractual adjustment} + \text{Patient responsibility}
```

Checks run on each visit once its documents are in:

1. The provider's billed charge, insurer payment, adjustment and my responsibility on the EOB add up.
2. The amount the provider bills me equals my responsibility on the EOB.
3. Network status on the bill and on the EOB agree, and the rate matches the negotiated rate.
4. What I paid equals what I owe, with no duplicate payments.
5. The payment came from the intended account (HSA first where eligible).
6. Any remaining balance is flagged with its age.

**Inputs:** you supply receipts, provider bills, EOBs, and HSA statements or card charges per visit. The app extracts the amounts, dates and provider, shows them for you to confirm, and then runs the checks. Manual upload comes first; connections to accounts come later.

## Build plan

Build the historical reconciliation first, in five phases, with each phase usable on its own.

1. **Define the model.** Settle the visit, document and payment fields, and hand-enter 3 to 5 real past visits to test whether the checks find real problems.
2. **Ingest.** Upload bills, EOBs and HSA statements; extract fields; you confirm them.
3. **Visit list and detail.** Visit cards with document-completeness status, and the drill-in view.
4. **Reconciliation engine.** The six checks, discrepancy flags and the dollar amount at stake per visit.
5. **Pre-visit strategy.** Self-pay vs insurance comparison, account choice and expected cost.

**MVP** = phases 1 to 4 on your own visits. **Later:** automatic account connections, multiple household members, and the market-level views used in the presentation.

**Process:** a first working version runs on a small set of your real visits before anything is generalized, and health documents stay private by default (storage location is an open question below).

## Open questions and risks

The biggest risk is the sensitivity of the data: bills, EOBs and HSA statements hold health and financial details, so where they are stored decides much of the design.

- [ ] Platform: web app, mobile, or both for the first version?
- [ ] Where do documents live (your own machine, or the cloud), and how are they protected?
- [ ] Does self-pay spend count toward the deductible and out-of-pocket maximum, and does it vary by insurer?
- [ ] Which historical visits do we start with, and how many are on hand?
- [ ] Do you want the backlog-first rule (every enhancement groomed in the backlog before work) used here as on the family calendar app?
- [ ] FSA details (the starred note in your photo): which rules and limits matter to capture?
- [ ] Is MH$ / My Health Spend the final name, and is it available as a domain and trademark?
- [ ] Does the app need to consider privacy rules for health data if it grows beyond personal use?

## Sources and data notes

Every figure in the market-context tables traces to the pages below, all looked up on 2026-10-09; "Opened" means I fetched the page itself, and "Search text" means I read its text in a search result without opening it separately.

| Figure | Source | Data year | How read | Notes |
| --- | --- | --- | --- | --- |
| Health spending, share of GDP, per person | [CMS National Health Expenditure data](https://www.cms.gov/data-research/statistics-trends-and-reports/national-health-expenditure-data/historical) | 2024 | Search text | Official CMS historical page, last modified 2026-01-14 |
| Projected share of GDP (20.3% by 2033) | [CMS NHE projections presentation](https://www.cms.gov/files/document/national-health-expenditure-projections-results-presentation.pdf) | 2024 to 2033 | Search text | Projection under current law, published June 2025 |
| Health care share of all jobs, 12-month job growth | [Health System Tracker, Is this a healthcare economy?](https://www.healthsystemtracker.org/brief/is-this-a-healthcare-economy/) | Sep 2026 | Opened | Secondary source citing BLS; it does not define which industries count as health care |
| Health care jobs level (about 18.5 million) | [American Action Forum, The health care jobs boom](https://www.americanactionforum.org/weekly-checkup/the-health-care-jobs-boom-and-the-shortages-beneath-it/) | mid-2026 | Search text | Month not confirmed; consistent with the 11.7% share |
| Registered nurses, share of health workforce | [Becker's Hospital Review](https://www.beckershospitalreview.com/workforce/41-hospital-jobs-ranked-by-share-of-healthcare-workforce/) | May 2025 | Search text | Secondary source citing BLS OEWS; excludes self-employed |
| Pharmaceutical and device manufacturing jobs | Data USA: [pharmaceutical](https://datausa.io/profile/naics/3254), [medical equipment](https://datausa.io/profile/naics/3391) | 2024 | Opened | The pages name no source for the counts; approximate only |
| All-household spending by category | [BLS Consumer Expenditures 2024 news release](https://www.bls.gov/news.release/cesan.nr0.htm) | 2024 | Opened | Primary source; released 2025-12-19. A consumer unit is a household-like group that shares major expenses |
| Spending for age 65 or over | BLS Consumer Expenditure Surveys series on FRED: [total](https://fred.stlouisfed.org/series/CXUTOTALEXPLB0407M), [housing](https://fred.stlouisfed.org/series/CXUHOUSINGLB0407M), [transportation](https://fred.stlouisfed.org/series/CXUTRANSLB0407M), [food](https://fred.stlouisfed.org/series/CXUFOODTOTLLB0407M), [healthcare](https://fred.stlouisfed.org/series/CXUHEALTHLB0407M), [pensions](https://fred.stlouisfed.org/series/CXUINSPENSNLB0407M) | 2024 | Opened | Age is that of the reference person; FRED republishes the BLS series |

**Open items to verify before we publish or present these numbers:**

- [ ] Check the 65+ figures against the official BLS table by age of reference person, [reference-person-age-ranges-2024.xlsx](https://www.bls.gov/cex/tables/calendar-year/mean-item-share-average-standard-error/reference-person-age-ranges-2024.xlsx); I could not open it here, so the 65+ numbers come from the FRED copies of the same BLS series.
- [ ] Replace the American Action Forum jobs level with the BLS Employment Situation table (Table B-1) for the same month as the 11.7% share.
- [ ] Find a sourced count for health insurance carriers (BLS NAICS 524114), and confirm the manufacturing counts against BLS payroll data.
- [ ] Re-pull the CMS and BLS figures when the 2025 data are released, since the household and GDP figures are annual.
