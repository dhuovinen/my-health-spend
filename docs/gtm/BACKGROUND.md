# CareBack: background for launch and awareness

*Draft, 2026-11-25. The source for every go-to-market asset ([README.md](README.md)). Built from [naming.md](../../naming.md), [REBRAND_PLAN.md](../REBRAND_PLAN.md), [UI_GUIDE.md](../UI_GUIDE.md), [VISION.md](../VISION.md), the problem statement, the live landing page and the competitor research in [research/hccfirst/](../../research/hccfirst/). Items marked **(owner)** need your answer before an asset uses them; they are collected in §10.*

---

## 1. CareBack in brief

**One line:** CareBack is in your corner on every medical bill.

**One sentence:** CareBack lines up your provider's bill, your insurer's explanation of benefits (EOB) and what you paid, circles where they don't agree, and helps you ask about it.

**Thirty seconds:**
> Every doctor's visit leaves three records: the provider's bill, the insurer's EOB and your payment, often from an HSA. They arrive weeks apart, in different formats, and nobody checks them against each other. So when the bill asks for more than the insurer says you owe, or your HSA payment never gets credited, it's on you to notice. CareBack does the checking. It puts the three side by side for every visit, shows where they disagree with the amount and the documents, and helps you raise it with the provider or insurer. You decide what is sent.

**Signature line (owner):** the landing page uses "In your corner on every medical bill." Other candidates: "We've got your back." · "Your bills, checked. Your money, backed." Picking one is a gate before the public switch (REBRAND_PLAN §8).

## 2. The problem

People pay for healthcare through three parties at once (the provider, the insurer and a payment account such as an HSA), and nobody reconciles the three, so billing errors and avoidable overpayment go unseen.

A single visit leaves a person unable to answer easily:

- Was the provider in network, and was I billed that way?
- Did the insurer process the claim, and does what I owe match?
- Am I overpaying through a wrong rate, a duplicate charge or a misapplied copay?
- Was it paid from the right account, and is anything still outstanding?

These four questions are the landing page's "Questions you shouldn't have to answer alone" and the strongest problem copy we have.

### Why it matters: sourced figures

Use these as stated, with the source. Health spending here is what households pay themselves, premiums included.

| Figure | Value | As of | Source |
| --- | --- | --- | --- |
| US national health spending | $5.3 trillion, $15,474 per person | 2024 | CMS National Health Expenditure data |
| Health share of US GDP | 18.0%, projected 20.3% by 2033 | 2024 | CMS, CMS projections |
| Average household healthcare spending | $6,197 a year, 7.9% of spending (fifth-largest category) | 2024 | BLS Consumer Expenditures |
| Households headed by someone 65+ | $7,799 a year, 12.7% of spending (fourth-largest) | 2024 | BLS via FRED |
| People age 55 and over | 57% of total health spending, 30% of the population | 2023 | Peterson-KFF Health System Tracker, from MEPS ([page](https://www.healthsystemtracker.org/chart-collection/health-expenditures-vary-across-population/), March 2, 2026) |
| Concentration | The top 5% of people account for nearly half of health spending; the bottom 50% for 3% | 2023 | Same page |
| Average deductible, **ACA Marketplace plans only** | $2,759 → $3,786, +37% (weighted by plan selection; individual; HealthCare.gov states) | 2025 → 2026 | KFF ([page](https://www.kff.org/affordable-care-act/deductibles-in-aca-marketplace-plans/), updated May 19, 2026; read from the chart) |

Links for the first four are in the problem statement (`docs/My Health Spend (MHS) Problem Statement & Plan.md`, "Why this matters"). The deductible figure is for people who buy their own coverage; never present it as the average for all insurance.

**Not yet sourced, so not used:** how often medical bills contain errors, how many people overpay, and typical amounts. These are the figures a launch story most wants and the ones most often quoted without a solid source. Before any asset states one, find a primary study, record it here with its date and method, and say what it measured. **(owner: worth a research pass?)**

## 3. Who it is for

**Individuals and their households only** (naming.md). No provider, employer or advocate-firm offering.

| Audience | Why CareBack fits them | First message |
| --- | --- | --- |
| **HSA households on high-deductible plans** | They pay a large share of each bill themselves, often by HSA card before the EOB arrives, so mismatches cost them directly. CareBack reconciles the HSA side, which bill-review services don't. | "Paid from your HSA before the EOB came? Check that the bill caught up." |
| **People 55 and over** | They are 30% of the population and 57% of health spending (§2), with more complex, repeated care where billing goes wrong. The founder is one of them. | "Same treatment, different bill? Check it." |
| **The household's bill manager** | One person usually handles bills for a partner and children. CareBack keeps everyone's visits, the family deductible and each provider's ledger in one place. | "Every visit for everyone in your house, checked." |
| **Adult children handling a parent's bills** | Households 65+ spend the most share on health (§2). Bills and EOBs pile up for someone who isn't the patient. | "Help with your parent's medical bills, without the shoebox." **(owner: is this an audience for launch? It depends on how a non-patient member is set up.)** |
| **People who already suspect a bill is wrong** | They need evidence and a way to ask. CareBack gives the numbers, the documents and a drafted letter. | "Think a bill is wrong? See exactly where, and what to ask." |

Early access is by invitation today; sign-up opens after the launch gate (§8).

## 4. What CareBack does

Four verbs, the same as the landing page. **Status** says what an asset may claim.

| Verb | What it does | Built | Status for members |
| --- | --- | --- | --- |
| **Check** | Upload or forward bills, EOBs (PDF or photo), HSA exports and insurer claims exports. CareBack reads them, the member confirms, and it matches every bill, EOB and payment line by line. Each visit gets one plain status. | Yes | On for early access |
| **Flag** | Findings with their numbers and documents: duplicate charges, rates that don't match the EOB, misapplied copays, payments not credited, cost sharing that doesn't match the plan, repeated services, charges over time. | Yes | On |
| **Back you up** | A case for each question the member raises, a letter drafted from the evidence for the member to edit, a call log and follow-up dates. Letters are drafted on request and never stored or sent by CareBack. | Yes | On (owner: confirm for early access) |
| **Plan ahead** | Estimate the member's share before booking, from the deductible, coinsurance and what's been paid; compare insurance and self-pay. | Yes | On (owner: confirm) |
| **HSA and tax** | Likely-qualified expenses, a receipt vault, contribution limits and a year-end summary, always as possibilities with a disclaimer, never advice. | Yes | On (owner: confirm) |

**Coming, not to be claimed as available:** connecting an insurer account directly (only a test insurer today); AI reading of documents for real households (waits on the production setup and a data-processing agreement); open sign-up.

## 5. Positioning

**For** individuals and households who pay a real share of their medical bills, often from an HSA,
**who** get a bill, an EOB and a payment for every visit and no one checks them against each other,
**CareBack is** an advocate for the member
**that** reconciles all three per visit, shows where they disagree with the evidence, and helps the member ask about it.
**Unlike** bill-review and negotiation services that look at one bill at a time, often for a fee on what they save,
**CareBack** follows every visit for the whole household through the plan year, including the HSA, and leaves the member in charge of what is sent.

### What makes it different

1. **The whole visit, not one bill.** Bill, EOB and payment together, with three money checks that must balance. Competitors compare the bill with the EOB; CareBack also follows the money.
2. **The HSA side.** HSA apps store receipts but never see claims; bill-review services don't see the HSA. CareBack joins them.
3. **The household and the plan year.** Family deductible and out-of-pocket progress from everyone's claims, every provider's running ledger, plan terms read from the household's own EOBs.
4. **Evidence first.** Every finding shows its amounts and documents and stays "a potential discrepancy" until the provider or insurer agrees.
5. **Privacy by design, not just policy.** Names, member numbers and dates are removed or shifted before any document is read by AI. No advertising or third-party analytics, ever. Export or delete everything any time.
6. **The member decides.** CareBack drafts and tracks; the member approves and sends. Free to use, with no fee and no cut of what comes back (owner, 2026-11-25).

## 6. Competitive landscape

From [research/hccfirst/](../../research/hccfirst/) (2026-10-10). Re-check before citing anything about another company.

| Player | What they do | How CareBack differs |
| --- | --- | --- |
| HCC FIRST | Per-bill review (bill against EOB) before you pay; paid negotiation for large bills; subscription | Whole visit and household, payments and HSA included; self-serve evidence and letters instead of paid negotiation |
| Goodbill | Hospital bill review and negotiation, moving toward employers | Individuals only; every visit, not large facility bills |
| Counterforce Health | Free AI help appealing insurance denials | Reconciliation of paid and owed amounts, not denials |
| HSA receipt apps and custodian apps | Receipt storage and reimbursement tracking | They don't see claims or bills; CareBack does |

**Messaging risk:** "peace of mind about every bill" sounds like HCC FIRST. Lead with what they don't say: the whole visit, the payment and the HSA, the household's year, and evidence the member controls.

**Not a competitor but a name to stay clear of:** the HSA administrator's app called MyHealthSpend, the reason for the rename. Never refer to it publicly.

## 7. Messaging

### Pillars

| Pillar | Message | Proof |
| --- | --- | --- |
| **In your corner** | Somebody should check your medical bills. Now somebody does. | Four verbs (§4); drafted letters; the member decides what is sent |
| **Careful with the facts** | Standing up to a billing office only works if you're right, so CareBack shows its work. | Evidence on every finding; "potential discrepancy" until confirmed; findings members mark as wrong are tracked against a 5% target |
| **The whole picture** | One visit, three stories. CareBack puts them side by side. | Bill + EOB + payment per visit; HSA; household; plan year |
| **Yours, privately** | Your identity stays out of it, and your data leaves with you. | Identifiers removed before AI; no ads or tracking; export and delete |

### Words

| Use | Avoid |
| --- | --- |
| In your corner · we've got your back · worth a closer look · a potential discrepancy · help you ask · what may be owed to you · lines up / doesn't line up | Get your money back · recover $X · save $X · guaranteed · error (before it's confirmed) · fraud · fight your insurer · AI-powered as a headline |
| Bill, EOB, payment, visit, household | Claims adjudication, reconciliation engine, ingest (in public copy) |
| "CareBack" (one word, capital B) | Care Back, Careback, CAREBACK; the old name |

### Proof points we can use today

- The landing page's fictional Riverview visit: $348.00 billed, $198.00 owed per the EOB, $198.00 paid by HSA card, $150.00 worth a closer look. Always labelled fictional.
- The four promises in "How we fight fair" (landing page), each true today.
- **(owner)** The first run on the owner's own 2026 data found $1,693.94 at stake across 11 visits (research/hccfirst/analysis.md §8). It's the strongest real story we have, but it is the owner's health data. Use it only with your say-so, rounded and without providers' names.
- Testimonials: none yet. Early-access members could provide them once the gate opens.

## 8. Brand basics

The full standard is [UI_GUIDE.md](../UI_GUIDE.md); the asset files come from `tools/make_brand_assets.py` (`src/mhs/web/static/brand/`).

- **Name:** CareBack. "CareBack Health" only where a longer legal or domain form is needed.
- **Mark:** a C that loops back to a check (concept B). **Wordmark:** "Care" in the foreground color, "Back" in primary blue, Manrope.
- **Color:** primary #1A5CDF; the red pen (coral) circles problems, the brand's signature device.
- **Type:** Manrope for headings and figures, DM Sans for text.
- **Tone:** a fighter and advocate for the member; the findings stay careful.
- **Address:** carebackhealth.com (healthcareback.com and myhealthspend.com forward there).

## 9. Asset outlines

### Short presentation (about 8 slides)

1. **Title:** CareBack. In your corner on every medical bill.
2. **One visit, three stories:** the bill, the EOB and the payment, weeks apart, never compared.
3. **The questions you shouldn't have to answer alone:** the four from §2.
4. **Why it matters:** the sourced figures (§2).
5. **What CareBack does:** Check, Flag, Back you up, Plan ahead.
6. **The Riverview example:** $348 against $198, the red pen on $150.
7. **How we fight fair:** the four promises.
8. **Where we are and what's next:** early access, the launch gate, how to join. **(owner: the ask, and who the deck is for)**

### Short video (60 to 90 seconds)

| Time | Picture | Words |
| --- | --- | --- |
| 0:00 | A kitchen table of envelopes: a bill, an EOB, an HSA receipt | "Every doctor's visit leaves three pieces of paper." |
| 0:10 | The three laid side by side; the figures don't match | "They arrive weeks apart, and nobody checks them against each other." |
| 0:20 | The red pen circles $150 | "Until now. CareBack lines them up and circles where they disagree." |
| 0:35 | The app: a visit's status, a finding with its documents | "Every finding shows its numbers and where they came from." |
| 0:50 | A drafted letter; the member edits and copies it | "When something's off, CareBack helps you ask. You decide what's sent." |
| 1:05 | The four promises, one line each | "Your identity stays out of it. Your data leaves with you." |
| 1:15 | Wordmark and address | "CareBack. In your corner on every medical bill. carebackhealth.com" |

Use only fictional documents (`samples/demo/` or the landing example) on screen.

## 10. Open questions for the owner

*Answered 2026-11-25: who is behind CareBack and the price. Don founded it after finding billing errors in his own care; it is free, with no fee or cut of savings, open source (MIT, public repository), and a community service that aims to partner with a leading nonprofit if it proves its value. Advocating through the member's own AI agent (A2A, MCP or Poppy) is the direction, not built. On paying, the position is that the HSA is the most efficient way to pay, with no comment on taxes. The story is [TALK_TRACK.md](TALK_TRACK.md); the mission and ethos are [ABOUT.md](ABOUT.md), which lists what still needs confirming.*

1. **Signature line:** "In your corner on every medical bill", "We've got your back", or another? (The talk track closes on "we've got your back".)
2. ~~Who is behind CareBack~~ answered; see ABOUT.md.
3. ~~Price~~ free; ABOUT.md note 5 asks whether to say "ever".
4. **Launch audience and timing:** invitation list first, or public once the gate opens? Which audience in §3 leads?
5. **Error-rate statistics:** worth a research pass for sourced figures (§2)?
6. **The owner's own results:** may a rounded version be told as the founding story (§7)?
7. **Early access:** which of §4's capabilities are on for invited members?
8. **The presentation's audience:** prospective members, partners, funders or the attorney?
9. **Channels:** which social networks, and are the handles secured (REBRAND_PLAN §8)?
