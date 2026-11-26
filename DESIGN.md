---
name: CareBack
description: In your corner on every medical bill. The bill, the EOB and the payment side by side, with the gap circled.
colors:
  primary: "#1A5CDF"
  primary-ink: "#FFFFFF"
  primary-tint: "#E5EFFF"
  ink: "#151F30"
  muted-ink: "#58616F"
  app-ground: "#F3F5F9"
  surface: "#FFFFFF"
  quiet-band: "#F2F5FB"
  hero-mist: "#EEF2F7"
  night-desk: "#131D2D"
  hairline: "#D9DEE7"
  field-edge: "#6E7787"
  red-pen: "#B42318"
  red-pen-wash: "#FDECEA"
  coral: "#DD574B"
  warn: "#9A5B00"
  warn-wash: "#FFF4E0"
  info: "#1D5FBF"
  info-wash: "#E8F0FC"
  good: "#1A7F37"
  good-wash: "#E7F5EA"
  idle: "#5B6673"
  idle-wash: "#EEF0F3"
typography:
  display:
    fontFamily: "Manrope, DM Sans, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "56px"
    fontWeight: 750
    lineHeight: "64px"
    letterSpacing: "-0.5px"
  headline:
    fontFamily: "Manrope, DM Sans, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "40px"
    fontWeight: 750
    lineHeight: "50px"
    letterSpacing: "-0.3px"
  title:
    fontFamily: "Manrope, DM Sans, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "36px"
    fontWeight: 750
    lineHeight: 1.25
  subtitle:
    fontFamily: "Manrope, DM Sans, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    lineHeight: 1.5
  body:
    fontFamily: "DM Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: "26px"
  label:
    fontFamily: "DM Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "12.5px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0.03em"
  figure:
    fontFamily: "Manrope, DM Sans, sans-serif"
    fontWeight: 700
    fontFeature: "tnum"
rounded:
  button: "5px"
  tile: "6px"
  card: "7px"
  pill: "999px"
spacing:
  gutter: "16px"
  card-inset: "18px 19px"
  section: "96px"
  section-phone: "64px"
  container-app: "1180px"
  container-landing: "1200px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-ink}"
    rounded: "{rounded.button}"
    padding: "7px 14px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    padding: "7px 14px"
  button-landing:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-ink}"
    rounded: "{rounded.button}"
    height: "46px"
    padding: "0 22px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
    padding: "{spacing.card-inset}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    height: "40px"
    padding: "6px 9px"
  status-discrepancy:
    backgroundColor: "{colors.red-pen-wash}"
    textColor: "{colors.red-pen}"
    rounded: "{rounded.pill}"
    typography: "{typography.label}"
  status-complete:
    backgroundColor: "{colors.good-wash}"
    textColor: "{colors.good}"
    rounded: "{rounded.pill}"
    typography: "{typography.label}"
  nav-link-active:
    backgroundColor: "{colors.primary-tint}"
    textColor: "{colors.primary}"
    rounded: "{rounded.tile}"
---

# Design System: CareBack

*Recorded by `/impeccable document` on 2026-11-25 from `docs/UI_GUIDE.md`, `src/mhs/web/static/style.css` (the app) and `landing.css` (the landing page). The UI guide stays the brand standard: if the two disagree, fix this file. The frontmatter holds the light theme; dark values are in `.impeccable/design.json` and the stylesheets.*

## Overview

**Creative North Star: "The Advocate's Desk"**

CareBack looks like a well-kept desk with someone on your side sitting at it. Three documents from one visit lie side by side: the provider's bill, the insurer's EOB and the payment. The advocate points at the one place they disagree and names the amount. Everything on the desk is in order: hairline rules, quiet blue-gray grounds, figures that line up. That order is what makes the one mark that matters, the red pen around a finding, impossible to miss.

The app is a working surface for a household's bill manager sitting at a laptop. It is dense where the work is (visit rows, line comparisons, ledgers) and calm everywhere else, and the brand shows in exact details rather than decoration. The landing page is the same desk shown to a newcomer: bigger type, the red pen drawn live, the documents lining up. It is bolder, but it uses the same palette, type and restraint.

The stance is a fighter's; the evidence is careful. Components are **confident and firm** (owner, 2026-11-25): one clear blue action per view, weight 600 or more on anything you press, and nothing hesitant about what to do next. Findings stay measured: a potential discrepancy, with its amount.

**Key Characteristics:**
- Three records side by side, and the gap circled in red.
- One blue action color; red only for findings.
- Manrope for headings and every figure, DM Sans for reading.
- Flat, hairline-ruled surfaces; shadows only on what floats.
- Small, consistent corners (5, 6 and 7px).
- Status always said in words; color only groups.
- Light and dark themes from the same tokens.

## Colors

A cool, blue-gray desk with one confident blue for action and a red pen kept for findings.

### Primary
- **Advocate Blue** (#1A5CDF; #7EA8FF on dark): the one action color. It's used for primary buttons, active navigation, links, focus rings, "Back" in the wordmark and the mark's tile. If it's blue, you can act on it.
- **Blue Tint** (#E5EFFF): the selected tab, active nav item and soft emphasis behind blue text.

### Secondary
- **Red Pen** (#B42318; #FF8A80 on dark): findings first, meaning the discrepancy status, the amount at issue and the circled gap. It also marks errors the member must fix (an alert in words), and the destructive button's text. It never marks an action or a brand flourish.
- **Red Pen Wash** (#FDECEA): the fill behind red-pen text, such as status pills and finding alerts.
- **Coral** (#DD574B): the drawn red-pen stroke in illustration, at 24px and up only, never for text.

### Neutral
- **Ink** (#151F30): text and headings.
- **Muted Ink** (#58616F): supporting text, labels, table headers and captions.
- **App Ground** (#F3F5F9): the app's page background, which cards sit on.
- **Surface** (#FFFFFF): cards, the top bar, fields and the phone tab bar.
- **Quiet Band** (#F2F5FB): hover rows, alternate bands and nav hover.
- **Hero Mist** (#EEF2F7): the landing hero's ground behind the photo.
- **Night Desk** (#131D2D): dark bands (the app's hero, the landing's "How we fight fair") and the dark theme's ground.
- **Hairline** (#D9DEE7): rules and card borders only.
- **Field Edge** (#6E7787): field borders and quiet button edges. It's darker than a hairline so controls read as controls.

### Status (the nine visit statuses and case states)
- **Warn** (#9A5B00 on #FFF4E0): a balance outstanding, or needs review (dashed border).
- **Info** (#1D5FBF on #E8F0FC): missing documents, or in dispute (solid border).
- **Good** (#1A7F37 on #E7F5EA): matched, resolved or complete.
- **Idle** (#5B6673 on #EEF0F3): waiting, or awaiting the EOB or documents.

### Named Rules
**The One Blue Rule.** Advocate Blue means "you can act here". It's never decoration, never a heading color in the app, and never used for a status.

**The Red Pen Rule.** Red is the advocate's pen: a finding, an error that blocks the member, or a destructive action, always with words. A screen with none of those has no red.

**The Status Says Its Word Rule.** Every status pill carries its label; color only groups statuses. Two statuses that share a color are told apart by a border (solid for in dispute, dashed for needs review).

## Typography

**Display Font:** Manrope (with DM Sans, then the system sans)
**Body Font:** DM Sans (with -apple-system, Segoe UI, Roboto, Helvetica, Arial)

**Character:** Manrope is geometric and sure, used for the voice and the numbers. DM Sans is soft and very readable, used for the explanation. Both are self-hosted, because the security policy allows fonts only from the site itself.

### Hierarchy
- **Display** (750, 56px, 64px line height; 38px on phones): the landing hero headline only.
- **Headline** (750, 40px, 50px; 30px on phones): landing section heads.
- **Title** (750, 36px, 1.25): the app's page title (h1).
- **Subtitle** (700, 18px, 1.5): app card and section heads (h2).
- **Body** (400, 16px, 26px): everything you read. Landing ledes go to 17–18px. Nothing is ever below 12px.
- **Label** (600, 12.5px, 0.03em, uppercase): table column headers. On the landing page, eyebrows are 12px, 750, 1.5px tracking, uppercase, in blue with a dot.
- **Figure** (Manrope 700, tabular numerals): every amount, count and date that must line up. Tiles use 1.6rem; the landing's big figures go to 28–30px.

### Named Rules
**The Figures in Manrope Rule.** DM Sans has no tabular digits, so any number that sits in a column or beside another number is set in Manrope with tabular numerals (`.num`). A misaligned dollar amount undermines trust in a finding.

**The 12px Floor Rule.** No text is smaller than 12px, including captions, fine print and badges.

## Layout

- **App:** one centered column, at most 1180px wide with 16px gutters, under a sticky top bar. Pages open with a page head (title on the left, actions on the right), then a summary (the dark hero or a row of four tiles), then cards in an auto-fitting grid (minimum 300–320px). Lists of visits are full-width rows in one bordered container, with a 4px left edge reserved for status.
- **Phones (860px and narrower, ADR-041):** the top nav hides and the pages move to a fixed bottom tab bar, 56px tall, within thumb reach. Every control is at least 44px. Grids collapse to one column, and visit rows to three.
- **Landing:** sections at most 1200px wide, 96px above and below (64px on phones), with section heads at most 720px wide. It alternates the white ground with Quiet Band, ending on Night Desk and a blue closing band.
- **Rhythm:** spacing is set in rem steps around 0.25, 0.5, 0.75, 1, 1.25 and 1.5rem in the app; cards are padded 1.1rem by 1.2rem.

## Elevation & Depth

Flat by default. Depth comes from tonal layering: white cards on the App Ground, Quiet Band for hover and bands, and Night Desk for emphasis. Hairlines separate surfaces. Shadows appear only on things that float above the page.

### Shadow Vocabulary
- **Card rest** (`box-shadow: 0 1px 2px rgba(16, 24, 40, .06)`): a barely-there lift under app cards in light mode; none in dark mode.
- **Menu** (`box-shadow: 0 10px 28px rgba(16, 24, 40, .14)`): the account menu and other floating menus.
- **Landing float** (`box-shadow: 0 12px 40px rgba(21, 31, 48, .09)`): the landing's document cards and the "CareBack found" card over the hero photo.

### Named Rules
**The Hairlines Over Shadows Rule.** Separate with a 1px Hairline, not a shadow. A shadow means "this floats"; nothing that sits in the page flow gets more than the card-rest shadow.

**The No Gradients Rule.** No gradients, except the landing hero's fade from Hero Mist into the photo.

## Shapes

Small, consistent corners: 5px on buttons and fields, 6px on tiles, chips and nav pills, 7px on cards and containers. Status badges and filter strips are full pills (999px). The mark's tile uses a 14/64 radius. Icons are Lucide outline at a 2px stroke, inlined as SVG. The red pen's loop is the brand's one hand-drawn shape: a wobbly ellipse that circles a figure and is never a decorative frame.

## Components

### Buttons
Confident and firm: you always know what the next step is.
- **Shape:** gently squared (5px).
- **Primary:** Advocate Blue fill, white text, weight 600, padded 0.45rem by 0.9rem. In the app, 40px tall on desktop and at least 44px on phones. On the landing page, 46px tall, padded 0 22px.
- **Secondary:** a white surface with a 1px Field Edge border and Ink text, weight 600.
- **Hover / Focus:** hover darkens slightly (brightness 0.97 in the app; the landing mixes 14% Ink into the blue). Focus is a 2px Advocate Blue outline, offset 2px, on every control.
- **Small:** 0.8rem and weight 500 on desktop; it grows to 0.9rem and 44px on phones.
- **Danger:** a secondary button with Red Pen text, used only for destructive or finding-related actions.
- **Direction (owner, 2026-11-25):** each view has one filled primary action. Other actions are secondary, never a second blue button. Labels are verbs ("Upload a bill", "Draft the letter").

### Status badges and chips
- **Badge:** a pill, 0.78rem, weight 600, in the status color on its wash. Each of the nine visit statuses and the case states has its own class, and the label always names the status.
- **Chip:** 6px corners, 0.78rem, for tags and secondary flags in the same status colors.
- **Status strip:** pill links with a count, hairline-bordered, turning blue on hover. Statuses with a count of zero fade to 55%.

### Cards / Containers
- **Corner Style:** 7px.
- **Background:** Surface on App Ground (Hero Mist in dark mode).
- **Shadow Strategy:** card rest only (see Elevation).
- **Border:** a 1px Hairline.
- **Internal Padding:** 1.1rem by 1.2rem.
- **Tiles:** summary figures (a muted label over a 1.6rem Manrope value). An "at issue" tile takes a Red Pen border and figure.

### Inputs / Fields
- **Style:** a white surface, a 1px Field Edge border, 5px corners, padded 0.4rem by 0.55rem, 40px tall on desktop so labels in a row line up, and 44px on phones.
- **Focus:** a 2px Advocate Blue outline, offset 2px.
- **Error:** an alert block in Red Pen on its wash above the form, in words.

### Navigation
- **Desktop:** a sticky white top bar with a hairline bottom edge. The wordmark sits on the left, then text links in Muted Ink (weight 500) with 6px pill backgrounds. The active link is Advocate Blue on Blue Tint at weight 600, and the account and icon buttons sit on the right.
- **Phones:** a fixed bottom tab bar, 56px tall, with a 24px icon over a 0.75rem label. The active tab is blue, and the "Add" tab is blue and bold with a larger icon.

### Visit row (signature component)
A full-width grid row for each visit: date, provider (weight 600), the member, then right-aligned Manrope figures (billed, owed, paid) and the status badge. A 4px left edge is reserved for status color. Rows share hairlines inside one 7px container and turn Quiet Band on hover. On phones each row reflows to three columns.

### The red pen (signature motif)
A Coral, hand-drawn loop around the figure that matters ("$150.00 worth a closer look"). On the landing page it draws itself when it scrolls into view, loops on an 8-second cycle only while on screen, and can be paused ("Pause the red pen", WCAG 2.2.2). With reduced motion or no JavaScript, it is simply drawn. In the app the same idea is static: red-pen text on its wash around the amount at issue.

## Do's and Don'ts

### Do:
- **Do** put the three records of a visit (bill, EOB, payment) side by side, and circle or color only the gap.
- **Do** set every amount in Manrope with tabular numerals, right-aligned in columns.
- **Do** name the amount next to every finding, and say "potential discrepancy" or "worth a closer look" until it's confirmed.
- **Do** give each view one filled Advocate Blue action, with a verb label.
- **Do** keep every control at least 44px tall on phones, and the 2px blue focus ring on everything focusable.
- **Do** label every status in words; use color only to group.
- **Do** label fictional samples as fictional wherever they appear.

### Don't:
- **Don't** use red for brand accents, emphasis or anything decorative; it belongs to findings, blocking errors and destructive actions.
- **Don't** use a second accent color, gradients, glows, or shadows on things that sit in the page.
- **Don't** set text below 12px, or put Coral on text.
- **Don't** promise money back or show savings counters; the visual system never dramatizes recovered dollars.
- **Don't** recolor, outline or shadow the mark, or put it on a photo without its blue tile.
- **Don't** use inline styles, inline scripts or third-party assets; every page stays CSP-clean.
