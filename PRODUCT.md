# Product

<!-- impeccable:product-schema 1 -->

*CareBack (code name `mhs`; formerly My Health Spend, ADR-060). Written by `/impeccable init` on 2026-11-25 from the repository's docs and the owner's answers. The detail lives in `docs/VISION.md`, `docs/ROADMAP.md`, `docs/DECISIONS.md` and `docs/gtm/BACKGROUND.md`; this file is the summary design work starts from.*

## Platform

web

A responsive, server-rendered web app (FastAPI and Jinja templates). There is no native app. The phone layout (ADR-041) is supported, but it isn't the main place the work happens (see Operating Context).

## Users

**Primary: the household's bill manager** (owner's answer, 2026-11-25). This is the one person who handles the medical bills, EOBs and HSA for themselves, a partner and children, often on a high-deductible plan with an HSA. Their job is to make sure every visit was billed and paid correctly, to find what doesn't line up, and to raise it with the provider or insurer.

Other audiences the product serves, but design doesn't center on: people 55 and over with complex or repeated care (the founder's own situation), people who already suspect a bill is wrong, and adult children handling a parent's bills (not yet confirmed as a launch audience).

Who can use it today: early access by invitation. Self-service sign-up is built but switched off until the launch gate (consent, privacy notice, breach plan and attorney review) is passed.

## Product Purpose

Every visit leaves three records: the provider's bill, the insurer's explanation of benefits (EOB) and the payment, often from an HSA. They arrive weeks apart, in different formats, and nobody checks them against each other. CareBack puts the three side by side for every visit, checks that the money adds up, shows where they disagree with the amount and the documents, and helps the member ask the provider or insurer about it.

Success, per VISION.md: few false findings (at most 5% marked wrong by members), extracted amounts at least 95% correct before the member confirms, documents matched to the right visit, and dollars recovered or avoided per household tracked over time. The figure that matters most is trust: one wrong "you were overcharged" costs more than ten missed ones.

## Positioning

CareBack reconciles the whole visit: bill, EOB and payment, including the HSA. It does this for the whole household across the plan year, and it shows its evidence for every finding. Bill-review and negotiation services look at one bill at a time, usually for a fee or a share of the savings. HSA apps store receipts but never see claims.

CareBack is free, with no fee and no cut of what comes back. It is open source (MIT) and run as a community service; if it proves its value, the aim is to partner with a leading nonprofit to keep it free. It doesn't call itself a nonprofit. The member stays in charge: CareBack drafts and tracks, and the member decides what is sent.

## Operating Context

- **Desktop, sitting down** (owner's answer, 2026-11-25). The main use is a focused session at a laptop to review visits, read findings and act on them. The phone is mostly for getting documents in: snapping or forwarding a bill.
- **Documents in:** upload PDFs or photos of bills, statements and EOBs; HSA exports (CSV, XLS, XLSX); insurer claims exports (CSV); email forwarding; JSON import. The member reviews and confirms what was read.
- **Work done in the app:**
  - visits with one of nine statuses;
  - a visit page in five sections;
  - findings, closed as "real problem" or "wrong";
  - each provider's ledger;
  - dispute cases with drafted letters, a call log and follow-ups;
  - Plan ahead estimates;
  - HSA and tax: likely-qualified expenses, receipts and contribution limits;
  - the household view, with a view switch between members.
- **The real situation:** documents that don't agree, weeks of waiting for an EOB, phone calls to billing offices, and money that matters to the household.

## Capabilities and Constraints

- **Terminology:**
  - "Visit": the unit everything attaches to.
  - "Bill", "EOB", "payment".
  - "Finding": stays "a potential discrepancy" or "worth a closer look" until confirmed, always with its amount.
  - "Member", "household", "case".
  - "CareBack": one word, capital B.
- **Money:** integer cents inside the app, with a $1.00 tolerance on the three money checks (ADR-015).
- **Privacy:**
  - Identifiers are removed or tokenized, and dates shifted, before anything is read by AI.
  - No advertising, pixels or third-party analytics, ever (PRV-08).
  - Members can export or delete their data.
  - Pages are CSP-clean: no inline styles, scripts or event handlers, and only same-origin resources.
- **Information, not advice:** HSA and tax suggestions are possibilities with a disclaimer (CMP-04). On paying, the position is that the HSA is the most efficient way to pay, with no comment on taxes.
- **The member decides:** imports never overwrite a member's edit. Letters are drafted on request and never stored or sent by CareBack.
- **Not yet available:**
  - AI extraction for real households (it waits on the production project and the data-processing agreement);
  - connecting an insurer account (only a test insurer today);
  - open sign-up.
  - Advocating through a member's own AI agent (A2A, MCP, Poppy) is the stated direction, not built.
- **Undecided:**
  - the signature line;
  - whether adult children handling a parent's bills are a launch audience;
  - whether the founder's own results may be published.

## Brand Commitments

- **Name and voice:**
  - CareBack. Tone: a fighter and advocate in the member's corner, with careful findings.
  - Traits: clear, in your corner, careful.
  - "Back" never promises money back. Allowed: "we've got your back", "help you ask for it back". Not allowed: "get your money back", "recover $X", savings counters.
- **Binding visual standard:**
  - `docs/UI_GUIDE.md` (tokens, Manrope and DM Sans, the red-pen motif) and the CareBack mark, a C that loops back to a check (`src/mhs/web/static/brand/`).
  - Lines in use: "In your corner on every medical bill" and "We've got your back".
- **Public copy:** never mentions the old name, except a member notice explaining the change.

## Evidence on Hand

- **Statistics, sourced and dated** (`docs/gtm/BACKGROUND.md` §2):
  - health is 18% of US GDP;
  - household health spending figures from the BLS;
  - people 55 and over account for 57% of health spending while being 30% of the population;
  - ACA Marketplace deductibles rose 37% from 2025 to 2026 (Marketplace plans only).
- **The founder's story:** `docs/gtm/TALK_TRACK.md` and `docs/gtm/ABOUT.md`, with Don's photo at `src/mhs/web/static/landing/don-huovinen.jpg`.
- **Fictional samples only, labelled as fictional:**
  - the landing page's Riverview visit ($348 billed, $198 owed, $150 worth a closer look);
  - `samples/demo/`, `samples/walkthrough/`, `samples/household-ingest.json`, `samples/tax-ingest.json`.
- **Absent, and must not be invented:** testimonials, customer counts, savings results, press, an unsourced error rate for medical bills, and the founder's own dollar results (not cleared for publication).

## Product Principles

1. **Accuracy beats speed.** Every finding shows its numbers and the documents behind it, and stays a question until confirmed.
2. **The visit is the unit.** Every document, line and payment attaches to a visit, and every dollar is accounted for.
3. **The member decides.** CareBack checks, drafts and tracks; the member confirms what was read and chooses what is sent.
4. **Private by design.** Identities stay out of AI, nothing is sold or tracked, and the data leaves with the member.
5. **In your corner, honestly.** A bold stance, careful claims: no promised savings, no unverified statistics.

## Accessibility & Inclusion

- **Standard:** WCAG 2.2 AA (owner's answer, 2026-11-25).
- **Already in the project:**
  - controls at least 44px tall on phones (ADR-041);
  - text contrast checked against the UI guide's tokens;
  - motion that respects reduced-motion settings and can be paused (the red pen, WCAG 2.2.2);
  - pages that read complete without JavaScript;
  - layout tests at 375 and 1280 px.
- **Readers:** many members are 55 and over, so plain language and legible figures matter, even though design centers on the bill manager.
