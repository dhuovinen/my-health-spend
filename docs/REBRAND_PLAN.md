# Rebranding plan: My Health $pend → CareBack

*Drafted 2026-11-25 on `feat/careback-rebrand`, following [ADR-060](DECISIONS.md) and [naming.md](../naming.md). Nothing here is built yet.*

**Unchanged:** the brand color (#1A5CDF, with every token in [UI_GUIDE.md](UI_GUIDE.md)), the fonts (Manrope for headings, DM Sans for text), shape, iconography (Lucide outline, 2px), and the house rules on findings, statistics and samples. **Changing:** the name, the mark, the wordmark, and the words that carry the brand's tone. Code and infrastructure names stay `mhs` (ADR-060).

Icon concepts (B chosen): [brand/icon-concepts.html](brand/icon-concepts.html) (open it in a browser), with the drafts [concept A](brand/concept-a-heart-back.svg) and [concept B](brand/concept-b-c-loop.svg).

Landing mockups (self-contained HTML, open in a browser): [option 1, light update](brand/mockups/landing-option-1-light.html) (the real page with §4 applied; "Highlight changes" marks each edit) and [option 2, carte blanche](brand/mockups/landing-option-2-carte-blanche.html) (§5).

---

## 1. What the brand has to say

| | My Health $pend | CareBack |
| --- | --- | --- |
| Idea | Three separate stories, one clear picture. | Same idea, plus a stance: **someone in your corner.** |
| Traits | Clear, on your side, careful. | Clear, **in your corner**, careful. "On your side" turns into a posture you can see. |
| Tone | Calm explainer. | Fighter and advocate (owner, 2026-11-25), **with careful findings**. The brand can be bold; a finding stays "a potential discrepancy" with its amount. |
| Signature line | "Your health. Your money. Your clarity." | Candidates: **"We've got your back."** · "In your corner on every medical bill." · "Your bills, checked. Your money, backed." |

**The one guardrail the new name pushes against.** "CareBack" suggests *money back*, but UI_GUIDE.md says "Promise no savings". So no copy says or implies the member *will* get money back. Allowed: "help you ask for it back", "find what may be owed to you", "we've got your back". Not allowed: "Get your money back", "Recover $X", savings counters. Add this rule to UI_GUIDE.md under **Findings language**, with examples.

## 2. Identity assets

### 2.1 The mark

| | Concept A: heart with a return arrow | Concept B: a C that loops back to a check |
| --- | --- | --- |
| What it is | Today's white heart on a blue tile, with the `$` replaced by a return arrow (Lucide `undo-2` geometry). | The letter C drawn as an arrow that turns back on itself, closing on a check mark. |
| Meaning | Care (heart) + back (arrow). | CareBack's initial + "back" + "settled". |
| Strength | Continuity: members, the staging site and the landing navbar already show this heart. It's the least disruptive change. | Ownable and specific. The heart is in nearly every health logo, and the fictional insurer on the hero photo uses a shield, which is the other cliché. |
| Risk | Generic; the arrow is small inside the heart at 16 px. | New, so members have to learn it. The arrowhead needs a designer's pixel pass at 16 px. |
| Fits | The light update (§4). | The carte blanche (§5). |

**Decided 2026-11-25: the owner chose concept B.** It is the mark for both landing approaches, so approach 1 ships with it too. The arrowhead was redrawn the same day to follow the curve's direction and to be narrower so it reads at small sizes. A final 16 px hinted version is still to come when the asset files are made (§2.3).

### 2.2 The wordmark

- **Care**Back set in Manrope 750: "Care" in `foreground`, "Back" in `primary` (#7EA8FF on dark). The color split replaces the blue `$`; every letter stays a letter, as ADR-060 requires.
- A one-color version for places that can't show two colors: OAuth consent screens, authenticator apps, plain-text email, favicons.
- Outline the production wordmark from Manrope into SVG paths (`wordmark.svg`, `wordmark-dark.svg`), so it renders the same wherever the font isn't loaded.
- **Name rules** (they replace the line in UI_GUIDE.md): "CareBack" everywhere people see it, one word with a capital B. Never "Care Back", "Careback" or "CAREBACK" in running text. "CareBack Health" only where a longer legal or domain form is needed. Alt text and `aria-label` use "CareBack". Code keeps `mhs`.

### 2.3 Files to produce

The global rule (Rule 5) requires a tab icon, and the app has none of these except `favicon.svg`:

| File | Size | Used by |
| --- | --- | --- |
| `static/brand/mark.svg` | vector master | Everything below is exported from it. UI_GUIDE.md notes that a vector master is still missing. |
| `static/favicon.svg` | 64 viewBox | Browser tabs, both apps (replaces the heart-and-`$`). |
| `static/favicon.ico` | 16, 32, 48 | Older browsers, and the bare `/favicon.ico` request browsers make whatever the HTML says. |
| `static/apple-touch-icon.png` | 180×180, no transparency | iPhone home screen. The phone layout (ADR-041) makes this worth having. |
| `static/icon-192.png`, `icon-512.png`, `icon-maskable-512.png` | | Android home screen, through a new `site.webmanifest` (name "CareBack", `theme_color` #1A5CDF). |
| `static/landing/mark.svg` | | Replaces `landing/mark.png` (212 px PNG) in the landing navbar and footer. |
| `static/brand/wordmark.svg`, `wordmark-dark.svg` | | Landing, email, decks. |
| `static/og-image.png` | 1200×630 | Link previews: the landing page has `og:title` but no image, so shared links show none today. |
| `oauth-logo.png` | 120×120 | The Google consent screen. Microsoft and Apple get their own sizes from the same master. Not served by the app. |

Add `<link rel="apple-touch-icon">`, `<link rel="manifest">` and `<meta name="theme-color">` to `base.html`, `landing.html` and the standalone household templates (sign-in, enrol, sign-up). Update the app-registry entries (`my-health-spend` and `my-health-spend-r1`): `branding.icon` and `branding.theme_color`, plus the display name.

## 3. What changes in the app (both approaches)

Found with `grep` over `src/`, `tests/`, `tools/` and the project files on 2026-11-25. Text only: no route, setting or schema changes.

| Where | Now | Becomes |
| --- | --- | --- |
| `templates/base.html` | `<title>… · MH$`, brand link with the `$` span | `… · CareBack`, wordmark with mark |
| `templates/home.html` | `<h1>` "My Health $pend" | "CareBack" |
| `templates/help.html` | "How My Health $pend checks…" | "How CareBack checks…" |
| `templates/landing.html` | 10 uses, page title, meta, og tags, FAQ, footer | §4 or §5 |
| `household/templates/terms.html`, `privacy_notice.html` | "My Health Spend" | "CareBack". Both are attorney drafts: send the renamed versions with a note, and name the operating entity once it is formed. |
| `household/auth.py` `TOTP_ISSUER` | "My Health Spend" | "CareBack". New enrolments only; existing authenticator entries keep the old label and keep working. |
| `web/app.py`, `household/app.py` FastAPI `title` | "My Health Spend" | "CareBack" (not shown; docs are off; change for consistency). |
| `household/privacy.py` export README and `prepared_by` | "My Health Spend export" | "CareBack export". Check that `import` doesn't match on this string before changing it. |
| `data/settings_file.py` `prepared_by` | "My Health Spend Settings page" | "CareBack Settings page" (same check). |
| `static/style.css`, `landing.css` | `.dollar` rules | Rename to `.wordmark b` (or `.brand-back`) and drop `.dollar`. |
| `pyproject.toml` `description`, `schema/mhs-ingest.schema.json` `title` | old name | CareBack (package name stays `mhs`). |
| `compose.yaml`, `tools/gcp/*.sh` | `myhealthspend.com` names | Add `carebackhealth.com`; keep the old domain as a forwarding host (ADR-058). |
| Tests: `test_web.py`, `test_r1_demo.py`, `test_r1_hosts.py`, `test_gcp_scripts.py` | assert the old name or host | Assert "CareBack". Add a test that no template contains "Health $pend" or "Health Spend", so the old name can't creep back in. |
| `docs/UI_GUIDE.md` | "Name" rule, `$` wordmark row, favicon note | §2.2 rules, the new mark, the money-back guardrail. The two linked style-guide artifacts get a CareBack revision. |
| `CLAUDE.md`, `NOTES.md`, `docs/DEMO.md`, `docs/USER_TEST_GUIDE.md` | Title and member-facing steps | CareBack. Older dated docs stay as they are (ADR-060). |

**Emails and other outbound text.** Check sign-up, enrolment and forwarded-email replies for a sender name or signature, and any `@myhealthspend.com` intake address. Keep the old addresses receiving until members have been told the new one.

## 4. Landing page, approach 1: light update

**No mention of the old name** (owner, 2026-11-25): the page never says "My Health Spend" or "My Health $pend", not even to explain the change. Visitors forwarded from the old domain land on CareBack with no notice; existing members hear about it at sign-in (§7).

Keep the structure, the hero photo, the three floating review cards, the "three stories" band, the steps, the question list, the sample dialog and the CSS. Change the name, sharpen the stance in a few lines, and fix what's out of date. About a day's work, including tests and the layout check at 375 and 1280 px.

| Section | Now | Light update |
| --- | --- | --- |
| `<title>`, meta, og | "My Health $pend \| From medical billing chaos to clarity" | "CareBack \| We've got your back on medical bills" · description: "CareBack puts your medical bill, your insurer's explanation of benefits and your payments side by side, shows where they disagree, and helps you ask about it." Add `og:image`. |
| Navbar | `$` wordmark, "Explore My Health $pend" | New lockup; button "Explore CareBack". |
| Hero eyebrow | "Your health. Your money. Your clarity." | **"We've got your back."** |
| Hero `<h1>` | "Medical bills. Insurance claims. *Let's make sense of it all.*" | Keep it; it works. Optional variant: "…*Let's see what doesn't add up.*" |
| Hero paragraph | "…My Health $pend helps connect the dots, so you can see where they disagree." | "…CareBack connects the dots, shows you where they disagree, and helps you ask the right people about it." |
| Floating cards | Understand the bill / Check the coverage / Follow the money | Keep. |
| Band | "…= Your health spend, understood." | "= **Your visit, understood.**" (drops the old name's phrase). |
| Step 03 | "Next on our roadmap: compare insurance and self-pay options…" | **Out of date:** Plan ahead (PRE-01 to PRE-07) and disputes (DSP) are merged and on staging. New text: "See what needs a follow-up, draft the letter, and plan your next visit before you book it." Confirm with the owner what is switched on for early-access members before claiming it. |
| FAQ | Five answers naming My Health $pend; "What about my next appointment?" calls Plan ahead a vision | Rename throughout; rewrite the Plan-ahead answer as present tense if it is on. |
| Closing | "Meet a clearer way to understand your health spend." | "Bring one visit. We'll show you what lines up and what doesn't." |
| Footer | "© My Health $pend. Your health. Your money." | "© CareBack. In your corner." |

## 5. Landing page, approach 2: carte blanche

*The mockup differs from the outline below in two places: the hero keeps the photo and puts the red pen on a "CareBack found" card over it, and the closing band is `primary` blue rather than `dark-surface`, so the page ends on the action color. The "Who is behind CareBack?" answer is left for the owner. No mention of the old name (owner, 2026-11-25).*

**Built 2026-11-25** (owner chose approach 2 over approach 1) in `templates/landing.html`, `static/landing.css` and `static/landing.js`, on `feat/careback-rebrand`. Differences from the mockup:

- The red pen loops (owner, 2026-11-25). Each loop draws, holds for about five seconds, fades and draws again, on an 8-second cycle, but only while it is on screen. A "Pause the red pen" link on the hero card stops every loop and leaves them drawn (WCAG 2.2.2), and the browser remembers that choice. With reduced motion, or with no JavaScript, the loops are simply drawn and the link doesn't show. The documents still line up only once.
- "Who is behind CareBack?" waits for the owner's answer. Until then the fourth question is today's "Can I upload my medical bills today?", which follows `signup_open` (ADR-059).
- "Get started" shows only while sign-up is open. Otherwise the closing button is the app's own link ("Sign in" on Release 1, "Open the app" on Release 0).
- The sample dialog is gone: the "One visit. Three stories." section shows the same fictional example on the page itself.

Same tokens, fonts, shape and rules; everything else is open. The core value and capabilities don't change: reconcile the bill, the EOB and the payment per visit; show findings with their numbers; help the member act (disputes, letters); plan ahead; HSA and tax. Built standalone like today (ADR-047), CSP-clean, no tracking, works without JavaScript, and respects `prefers-reduced-motion`.

### The idea: "In your corner"

Today's page explains a problem. The new page **takes a side**. Its visual signature is a device the brand already owns: **the red pen** (the circles and "What?" notes on the hero photo, and the `red-pen` and `coral` tokens). In the new page the red pen is CareBack's hand: it circles the problem, writes the amount next to it, and the circle carries through the page as the reader scrolls.

### Page structure

1. **Hero: the problem, circled.** Headline: **"Somebody should check your medical bills. Now somebody does."** Subhead: "CareBack lines up your provider's bill, your insurer's EOB and what you paid, and circles where they don't agree." Visual: the existing billing-chaos photo, kept as the opening frame (it's good), with the red-pen circles drawn in SVG over it on load, one at a time. CTA "See a sample visit"; secondary "Sign in".
2. **"Three stories" made literal.** One fictional visit as three side-by-side documents (a bill, an EOB, a receipt), built in HTML, not an image, so it is crisp and readable on phones. As it scrolls into view, the three figures line up in a row: $348 · $198 · $198, and the red pen circles the **$150** gap with the note "worth a closer look". This replaces the `+ + =` band and does the work the sample dialog does today, without a click. The dialog stays for the deeper view.
3. **"What CareBack does for you": four verbs, one per real capability.** Each card shows a small slice of the real app's UI (redrawn, fictional data):
   - **Check**: every visit's bill, EOB and payments matched line by line, with a status per visit.
   - **Flag**: findings that show their numbers and documents (duplicates, rate and copay mismatches, uncredited payments, cost sharing against your plan).
   - **Back you up**: a dispute case with a drafted letter and a contact log. You decide what is sent.
   - **Plan ahead**: estimate your share before a visit, and see what your HSA can cover (with the tax disclaimer).
4. **"How we fight fair": the trust band.** On `dark-surface`. Four short promises the product already keeps: *Every finding shows its evidence. · "Potential discrepancy" until it's confirmed. · Your identifiers are removed before anything is read by AI. · Export or delete your data any time.* This answers the "is this safe to give my medical bills?" question that blocks sign-up, and it is all true today (PRV-05, the scrubber, export and delete).
5. **The questions people ask themselves.** Keep today's four-question list; it's the strongest copy on the page. Retitle it "Questions you shouldn't have to answer alone."
6. **FAQ.** Today's, renamed and current, plus "Will CareBack get my money back?" (an honest no-promise answer) and "Who is behind CareBack?" (nonprofit, open source, or whatever is true at launch: the owner's call). Like approach 1, the page never mentions the old name.
7. **Closing.** "Bring us one visit." Primary CTA "Get started" (when `signup_open`) or "Request early access"; secondary "See a sample".

### Visual system additions (inside the UI guide)

- **Red-pen strokes** as SVG paths with a hand-drawn wobble, drawn with `stroke-dashoffset` (a CSS animation in `landing.css`, no inline styles). `coral` only, 24 px and up, as the guide already says. This is the one new motif.
- **The return-arrow or C-loop** from the mark, reused as a section divider and bullet, and nowhere else.
- **Big figures in Manrope** with tabular digits for the $348 / $198 / $150 sequence.
- **No new colors and no gradients** apart from the existing hero fade.

### Effort and risks

About 4 to 6 days: the copy (with the owner), the HTML illustrations, the SVG strokes and their animation, phone layout at 375 px, `test_ux_layout.py` checks for the new links, and a fresh screenshot pass in both themes. Risks: the animation must not be needed to understand the page (it works with reduced motion and with no JavaScript), and every capability card must match what's switched on for early-access members.

### Which to choose

Ship **approach 1 with the rename** (it unblocks the domain switch and the OAuth screens), then build **approach 2 on its own branch** and switch over when it's ready. Approach 1 is where the page lands if approach 2 stalls.

## 6. Domains, sign-in and outside services

In this order, because each step depends on the one before it:

1. **DNS and Cloud Run**: map `carebackhealth.com` and `www.` (and `app.` if used) to the service; managed certificates ([GCP_SETUP.md](GCP_SETUP.md) "Custom domain"). Map `healthcareback.com` to the same service, to be forwarded. **Done 2026-11-25:** both domains verified in Search Console (TXT records at Hostinger), Cloud Run domain mappings for the bare domains and `www` (Google's A, AAAA and `ghs.googlehosted.com` CNAME records replaced Hostinger's parking records), certificates issued. All four forward to the main address.
2. **Done 2026-11-25 for Google and Microsoft** (callback added beside the old ones, `carebackhealth.com` an authorized domain on Google; the consent-screen name, logo and the Microsoft display name are still the old ones). Apple isn't configured on staging. **OAuth: add, don't replace.** Add callback URLs on `carebackhealth.com` to the Google, Microsoft and Apple clients **beside** the existing ones (Apple also needs the new domain verified). Then change the consent-screen app name and logo. A new name or logo on Google's consent screen can send the app back through brand verification, so do it early and expect a wait.
3. **Done 2026-11-25** (`PUBLIC_URL=https://carebackhealth.com tools/gcp/deploy.sh app admin`; every old address forwards with a 307, and both providers accept the new callback). **Switch the main address**: `MHS_PUBLIC_URL=https://carebackhealth.com`. ADR-058's forwarding then sends `myhealthspend.com` and `healthcareback.com` (307, same path) to it.
4. **Email**: set up `carebackhealth.com` mail (SPF, DKIM, DMARC) before sending anything from it; keep `myhealthspend.com` addresses receiving.
5. **Old domain**: keep `myhealthspend.com` registered and forwarding for at least two years.

## 7. Telling people

- **Existing members** (invitation-only today, so few): a short note at their next sign-in: "My Health $pend is now CareBack. Same account and data. Your authenticator app may still show the old name; your codes keep working, or re-enrol from Account to update the label."
- **The attorney**: the renamed Terms and Privacy notice drafts, and the entity name once known.
- **App-registry** and anywhere the app is listed: new display name and icon.

## 8. Gates before the public switch

Code work can start now; these gate step 6.3 (making CareBack the public address):

- [ ] USPTO search for "CareBack" in classes 36, 42 and 44 (naming.md). A conflict means a new ADR; the domains and forwarding cost little to point elsewhere.
- [ ] Say-aloud test with five people (naming.md step 3).
- [ ] App Store, Google Play and social handles checked.
- [x] Owner picks the mark: concept B, the C-loop (2026-11-25).
- [ ] Owner picks the signature line (§1).

## 9. Order of work

| # | Step | Branch | Depends on |
| --- | --- | --- | --- |
| 1 | Owner picks the mark (done: B) and the line; mark gets its final 16 px version | | §8 gates 4 and 5 |
| 2 | Produce the asset files (§2.3); update UI_GUIDE.md and its artifacts. **Done 2026-11-25** (`tools/make_brand_assets.py`), except the two style-guide artifacts linked from UI_GUIDE.md | `feat/careback-rebrand` | 1 |
| 3 | App text, templates, tests and the no-old-name test (§3). **Done 2026-11-25** (`tests/test_brand_name.py`). Still open: send the renamed terms and privacy notice to the attorney; the domain rows wait for step 6 | `feat/careback-rebrand` | 2 |
| 4 | Landing page: approach 2 (§5) was chosen over approach 1. **Built 2026-11-25** | `feat/careback-rebrand` | 2 |
| 5 | Verify: `uv run pytest`, `tests/test_ux_layout.py` at 375 and 1280 px, both themes, then merge | | 3, 4 |
| 6 | Domains, OAuth, main address, email (§6) | ops | 5 and the §8 gates |
| 7 | Tell members and the attorney (§7) | | 6 |
