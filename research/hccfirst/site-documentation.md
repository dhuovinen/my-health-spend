# HCC FIRST: site documentation

As seen 2026-10-10. Summaries in our words; short quotes in quotation marks.

## Site map

| Path | Purpose | In sitemap |
| --- | --- | --- |
| `/` | Home: value proposition, how it works, testimonials, pricing, learn and employer teasers | Yes |
| `/about` | Founder story, what they do and won't do, data handling, who's behind it | Yes |
| `/faq` | ~25 questions in six groups | Yes |
| `/shop-for-services` | 5-step preview of an unbuilt price-shopping feature | No (linked in nav) |
| `/employers` | Employer sponsorship pitch (explicitly not yet a product) | Yes |
| `/learn` | "Know Before You Pay": six free interactive modules + one members-only game | Yes |
| `/learn/*` (6 pages) | The modules | Yes |
| `/signup`, `/login` | Account creation and sign-in | Signup only |
| `/privacy`, `/terms`, `/hipaa-notice` | Legal | Yes |
| `/vault`, `/admin`, `/api`, `/auth`, `/mfa`, … | Logged-in app (blocked in robots.txt) | No |

Top navigation: About · FAQ · Shop Services · Pricing · Sign in. Footer: About, FAQ, Contact (email),
For employers, Know Before You Pay, Sign in, Terms, Privacy, HIPAA notice.

## Core offer

**One line:** upload a medical bill (ideally with the matching EOB); they review the two together and tell
you, in a sentence, what is okay to pay, what to question, and what to leave alone for now. Reviews are
done "using both AI and human experts" (About), and the structured data describes the service as bills
"reviewed by AI and experts".

**Positioning hooks**
- Flat subscription vs. the percentage-of-savings model common in bill negotiation (home banner contrasts
  "from $10/mo" with "25% of your savings").
- "Peace of mind" is the headline emotion, not savings.
- "Don't pay yet" is presented as a legitimate, frequent answer (e.g. waiting on the EOB).

**What you upload**
- Provider bill (hospital, physician, itemized, statement)
- Health plan EOB
- Optional extras: denial letters, payment receipts, anything tied to the same visit

**What they do (3 steps, home page)**
1. Organize: match bills and insurance statements to the same visit.
2. Check the math: compare what the provider billed with what the plan processed.
3. Tell you what to do: a plain-English one-sentence answer, with the reason when it's "don't pay yet".

**Output format seen in examples:** a card per bill with provider, visit date, document type, a status
badge, and a one-sentence verdict. Three home-page examples, one per tier:

| Example | Tier | Status | What it shows |
| --- | --- | --- | --- |
| Internal Medicine Group, statement | Free | Okay to pay | Okay to pay $126.02; plan already applied its share |
| Riverside Imaging Center, bill + EOB | Basic | Checked against your EOB | Billed $4,240 · plan's rate $1,050 · plan paid $800 · yours $250 |
| University Medical Center, hospital bill | Concierge | Negotiation in progress | Original balance $4,318; a negotiator is working it; written outcome before you approve |

A second example card shows a $4,318 hospital bill "In review" because the EOB is still needed.

## Pricing (home page, 2026-10-10)

| | Free | Basic ("Most popular") | Concierge |
| --- | --- | --- | --- |
| Price | $0, no card | $10/mo or $100/yr ($8.33/mo, "save 16%") | $35/mo or $340/yr ($28.33/mo, "save 19%") |
| Tagline | Get organized, first 5 reviews free | Understand every bill before you pay | Have us handle qualifying hospital bills |
| Includes | Secure bill and EOB vault · 5 free bill reviews · payment and spending tracker · HSA and FSA tagging · Know Before You Pay | Everything in Free + review every bill · compare bills with EOBs · findings and next steps · provider lookup (name, specialty, facility) | Everything in Basic + human negotiation on qualifying facility bills · one authorization to start · written outcome before approval |

**Negotiation fee (Concierge):** nothing up front; if a bill is reduced and you approve the result,
10% of the savings, capped at $200 per bill; no reduction, no fee. Only hospital/facility bills above an
in-app threshold qualify; physician and small bills "generally aren't worth negotiating".

**Negotiation mechanics (FAQ/Terms):** opt in bill by bill; sign one account-level authorization; for each
provider, make a short phone call giving the provider permission to talk to HCC FIRST (they supply the
script); they never accept a settlement for you; a written Case Summary (original balance, negotiated
balance, savings, exact fee) must be approved before any fee. You always pay the provider directly; money
paid to HCC FIRST never satisfies a provider balance.

## Testimonials (home, "Real bills. Real savings.")

Six first-name testimonials, all hospital/ER bills, all negotiation outcomes:

| Bill | State | Saved |
| --- | --- | --- |
| ER visit | FL | $1,389 (80%), $1,739 → $350 |
| Hospital | FL | $1,260 (45%) |
| Hospital | TN | $625 (32%) |
| Hospital | MO | $1,248 (38%) |
| Hospital | OH | $668 (23%) |
| Hospital | TX | $2,207 (39%) |

Footnote: results vary; savings are reductions from the amount due after insurance. Not independently
verifiable; no third-party reviews found.

## About page

- Founder's motivation: checking a bill shouldn't need a professional or cost more than the bill.
- The "whole job" framing: between the provider bill and the plan statement sits the number that is
  genuinely yours, and nobody has to show it to you plainly.
- Three things they do: review the paperwork (AI + humans); tell you plainly in one sentence; make the call
  on qualifying hospital bills with authorization.
- Four things they won't do: promise savings; sell your information (employer doesn't see documents
  either); guess (they say "still waiting on your health plan" often); act without asking.
- Data: a vault only you can open, held to HIPAA-like handling standards, while stating they're not a
  covered entity.
- Founder: **Jeff Brown**, ~30 years in healthcare (provider reimbursement, health-plan operations,
  cost containment; national insurers, hospitals, self-funded employer plans). Company: Healthcare Consumer
  First, LLC, Birmingham, Alabama.

## FAQ (summary by section)

- **Getting started:** bill alone is enough; EOB lets them separate charges from what's actually yours.
  Uninsured/self-pay bills reviewed on their own terms. A review usually takes a few minutes. US only.
- **What you get:** restates tiers. Plans can be changed or cancelled any time; cancellation stops renewal.
- **Money:** prices on home page; negotiation fee as above; they never take money to pay providers; no
  charge without an approved written summary; no card for Free.
- **Negotiation:** facility bills above a threshold; opt-in per bill; one authorization + a per-provider
  permission call; never accept on your behalf; no fee if it fails.
- **Privacy and security:** only you see documents; used only for the review and authorized
  negotiations; never sold or used for ads; "HIPAA-aware" explanation; employer never sees anything;
  account deletion removes documents, with legally required records retained.
- **Practical:** **one account = one person; shared household accounts aren't built yet** (acting for
  someone else is allowed with legal authority). Not insurance, not a law firm, not credit repair or debt
  settlement. Won't stop collections; see a lawyer for litigation. If they get it wrong, every review shows
  what it was based on; email them. Contacts: info@ and privacy@hccfirst.com.

## Know Before You Pay (learning library)

Free, no account. Intro: learn how bills, plans and prices work before you pay. Six modules plus one
members-only game:

| Module | Format | Content |
| --- | --- | --- |
| Anatomy of a bill | Sample bill (Riverside Medical Center, $3,160 charges → $964.54 due, all deductible); tap each of 6 numbers | Explains total charges (opening price), insurance adjustment (contractual write-off you usually don't owe in network), allowed amount ("the price that actually matters"), plan paid (can be $0 when covered), applied to deductible, amount due, which **should match the EOB**; if not, ask why |
| Anatomy of an EOB | Matching sample EOB; tap 6 lines | EOB isn't a bill; provider charge should match the bill's total; plan discount; allowed amount is what you and the plan split; plan paid; your responsibility should equal the bill's amount due |
| Where your money goes first | Slider: $2,000 deductible, 20% coinsurance, $1,000 allowed visit | Five stops ($0/$500/$1,000/$1,500/$2,000 met) show you-pay vs plan-pays shifting from $1,000/$0 to $200/$800; lesson: same visit, cost depends on where you are in the year |
| Same scan, three places | Tap 3 sites (bars illustrative) | Hospital outpatient (facility fee, highest), hospital-owned off-campus clinic (facility fees after acquisition, middle), independent center (no facility fee, lowest); ask about other sites |
| Spot the problem | Itemized ER bill, 6 lines; tap the suspicious one | Duplicate same-day metabolic panel is the error; ER level 3 is normal; you need an itemized bill "with CPT codes" |
| Myth or fact | 6 two-choice cards | Write-off ≠ discount; EOB isn't a bill; $0 plan payment usually means deductible, not denial; you can ask for an itemized bill; price varies by site of care; collections doesn't make a wrong bill right |
| Behind the Bill | Members-only game | "Pick a category" about what the system never explains (not viewed) |

## Shop Services (preview, explicitly not live)

Banner: "a walkthrough of something we're building, not a feature you can use today." Framed as a better
choice "for both your wallet and your employer's."

1. **Photograph the order:** snap the physician's order slip, like a bill.
2. **We read it back:** they state what they think was ordered (example: MRI right knee without
   contrast) and you confirm or correct.
3. **Places and prices:** facility cards with type, distance, amenities, **cash price** and **insurance
   allowed** range (illustrative: independent centers $425–$610 cash / $640–$850 allowed vs hospital
   outpatient $1,150 cash / $865–$1,235 allowed). Note: facilities "without a star have not shared
   pricing." An expandable explainer covers allowed amount vs cash price, warns that cash isn't always
   cheaper if you've met your deductible, and tells you to **ask your health plan** where you are in the year.
4. **You pick one:** you call, ask and decide; the choice is recorded.
5. **Send it on, if you want:** optional "Email this to my employer" showing savings vs the hospital
   option; restates there is no employer dashboard or report.

## Employers page

Addressed to an employer an employee referred. Employer would pay subscriptions; each employee owns their
account, which stays theirs if they leave. Employer never sees documents, providers, dates, amounts or
findings: no dashboard, no aggregate reporting ("not built", not switched off). Candidly states it's **a
conversation, not a product**: no self-serve enrollment, eligibility file, admin console or signed
agreement yet. CTA: email with headcount.

## Signup and sign-in

- Signup: "Create your vault." Required PHI-consent checkbox (agree to Privacy Policy and HIPAA Notice),
  Google or Apple sign-up, or full name + email + mailing email ("agreements and receipts go here") +
  password (min. 6 characters). States they will **never ask for access to your medical records**.
- Sign-in: Google, Apple, or email/password; forgot-password; MFA route exists (robots.txt).
- Deep links: `/signup?plan=basic_monthly`, `/signup?plan=concierge_monthly`.

## Legal pages (key points)

**HIPAA notice (effective 2026-07-30):** they are not a covered entity, so uploaded documents aren't
HIPAA-governed in their hands. Self-description: "HIPAA-aware". What governs them instead: the FTC Health
Breach Notification Rule (they say they're a vendor of personal health records), state consumer
health-data laws, the FTC Act, and their own agreements. Where HIPAA does touch them: provider contact
needs your authorization; BAAs with their vendors; possibly a business associate if offered through an
employer plan. Commitments: access control, encryption in transit and at rest, logging, least privilege;
no sale, no ad targeting, nothing to employers. Address: 1500 1st Ave N, Birmingham, AL 35203.

**Privacy policy (effective 2026-01-01):** collects account data (including date of birth), documents,
communications, usage/device data with "privacy-conscious analytics". Uses include comparing bills to EOBs,
finding errors and savings, contacting providers/insurers/billers/**collection agencies**/**financial
assistance programs** on your behalf, payment arrangements, success-fee calculation, and improving the
service with de-identified data. Shares with providers etc. at your direction, with service providers
(storage, hosting, payments, e-signature, analytics, support, messaging, security), advisors, and in a
business sale. Not for under-18s. Data processed in the US. Deletion has a recovery window; some records
retained. Email/SMS used with minimal health detail; SMS STOP/HELP.

**Terms (effective 2026-01-01):** 18+, US. Service scope includes organizing documents, reviewing for
inconsistencies and savings, requesting documents, comparing bills with insurance, contacting providers,
insurers, billers, **financial assistance programs** and collectors, and assisting with negotiation,
**payment arrangements and disputes**. Not medical/legal/tax/insurance advice; not an insurer, producer,
law firm, accountant, credit repair or debt settlement company. No guarantee of results. Labels like
"okay to pay"/"do not pay yet" are administrative guidance only. Success fee only on approved, documented
savings. Liability capped at 12 months of fees; arbitration and class-action waiver; Alabama law,
Jefferson County venue.
