# HCC FIRST: UX and design

As seen 2026-10-10 on desktop (1024 wide) and mobile (375 wide).

## Information architecture

- Small marketing site: Home, About, FAQ, Shop Services, Pricing (anchor on Home), Sign in. Secondary
  entry points (Learn, Employers, legal) live in the footer.
- **Home is the whole sales page:** hook → three example outcomes → "two documents, one answer" → what you
  upload → three-step process → sample result card → Concierge teaser → testimonials → pricing → Learn
  teaser → employer teaser → trust line → footer.
- The logged-in product is called the **vault**; signup says "Create your vault".
- Learn is a separate, ungated content hub that works as an SEO and education funnel (each module has
  schema.org Article data marked free to access).

## Visual design

- **Palette:** very dark green header and footer bands, warm off-white page, deep green primary buttons,
  pale green cards and badges. Calm and institutional rather than fintech-bright.
- **Type:** serif display headings (Source Serif 4) over a clean sans body (Public Sans). The serif gives
  an editorial, trustworthy feel; this is a deliberate counterpoint to "app" aesthetics.
- **Logo:** "H1" monogram tile + "HCC FIRST" wordmark with a small-caps "HEALTHCARE CONSUMER FIRST"
  tagline.
- **Components:** rounded cards with thin borders; pill badges for status ("Okay to pay", "In review",
  "Negotiation in progress") and tier ("Free/Basic/Concierge"); numbered step rows with icons; a pricing
  grid with monthly/annual toggles and a "Most popular" tag; a tabbed example carousel (Free / Basic /
  Concierge) in the hero.
- Plenty of white space, short line lengths, large type on mobile.

## Interaction patterns

- **Example outcome cards** in the hero let a visitor see what an answer looks like before signing up;
  a carousel shows one per tier.
- **Tap-to-explain documents:** the bill and EOB modules render a realistic document and reveal one plain
  explanation per tapped line, with an "n of 6" progress counter.
- **Slider simulation** (deductible module) with five stops and a live "you pay / plan pays" readout plus
  a one-sentence takeaway per stop.
- **Find-the-error game** and **two-choice quiz** with immediate feedback (different wording for right vs
  wrong answers).
- **Product preview as a stepper:** Shop Services is a 5-step walkthrough with Back/Next, gated choice
  ("Choose one of the three above to continue"), and inline disclaimers that buttons are mock-ups.
- **Progressive disclosure** everywhere: expandable "What these two numbers mean", "View details" on
  result cards.
- **Auth:** Google and Apple one-tap plus email; a required PHI-consent checkbox at the top of signup.

## Tone of voice

- Plain, short, second person; "we" is used sparingly and candidly.
- Heavy use of **negative commitments** ("we won't promise savings", "we won't guess", "we won't act
  without asking") and admissions ("this is a conversation, not a product", "not every bill ends this
  cleanly").
- Answers framed as **one sentence you can act on**. Verdict vocabulary: okay to pay, don't pay yet,
  question this, leave alone for now.
- Legal pages are unusually readable and argumentative ("We would rather tell you exactly what we are…").

## Trust devices

- Candor as a brand: explicit "HIPAA-aware" rather than a compliance badge, with a full explainer page.
- No card required; first 5 reviews free; success fee only after a written outcome you approve.
- Employer firewall stated three times (home, FAQ, employers page, Shop Services step 5).
- Founder bio with 30 years of payer/provider experience; Birmingham street address.
- Testimonials with dollar and percent savings (first name + state only).

## Mobile

Responsive single-column layout; the nav wraps onto two lines at 375 px (no hamburger menu); buttons go
full-width; hero example card follows the CTA. Readable and uncluttered.

## Tech stack (observable)

- Next.js (App Router / React Server Components, Turbopack build) hosted on **Vercel** (us-east `iad1`),
  HSTS enabled.
- Learn modules are data-driven components (bill/EOB "anatomy", slider, two-choice, find-the-line) whose
  content ships in the page payload, which suggests a reusable content engine.
- No third-party ad or tracking scripts seen in the page HTML; the privacy policy mentions
  "privacy-conscious analytics".
- Robots.txt explicitly allows AI crawlers (GPTBot, ClaudeBot, PerplexityBot, …) on public pages and blocks
  app routes, so they're optimizing for AI-search discoverability.

## UX takeaways for MH$

1. A **one-sentence verdict per item** is the core UX unit. MH$ shows statuses and checks; adding a
   plain-language sentence ("Okay: you owe $45.21, already paid" / "Ask the provider: billed $180, EOB
   says $100") would make the visit cards actionable at a glance.
2. **Show an example result before signup.** Our hero could do this with the sample data.
3. Their **interactive document anatomy** is a strong pattern for MH$'s help (?) section: we could annotate
   the user's own EOB and statement rather than a fake one.
4. Candid limitation statements build trust; we should adopt the same voice for "possible HSA
   opportunity, eligibility not confirmed".
