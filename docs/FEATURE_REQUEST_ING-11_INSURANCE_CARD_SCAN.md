# FEATURE REQUEST — ING-11: Scan an insurance card

> **Status: REQUESTED. NOT BUILT. NOT SCHEDULED.**
> Label: `feature-request` · ID: **ING-11** · Area: Ingestion and document capture · Proposed priority: P2
> Requested 2026-11-24 by the owner. Write an ADR in `docs/DECISIONS.md` before building it: it adds a document type, new plan fields and identifiers that go through the vault.

## The request

Let a member scan their health insurance card, front and back, and have MHS read what is printed on it: the insurer, the group number, the insured (subscriber), the type of insurance and every member listed. The back usually carries the phone numbers and addresses the member needs (member services, claims address, pharmacy help), so it is scanned too. The result fills in the insurance plan on the Coverage page, so the member doesn't type the plan in by hand.

## Why

- Setting up a plan today means typing the insurer, plan name, members and copays into the Coverage form (`_plan_editor.html`). Most of that is printed on the card the member already carries.
- Onboarding (UX-09) asks for plans before the first upload. A photo of the card is the fastest way through that step, especially on a phone (UX-10).
- Dispute letters and call notes (DSP-02, DSP-03) already ask for the member ID "on your insurance card" (`web/letters.py`) and need the insurer's phone and claims address. Today they come only from uploaded EOBs, or not at all.
- REC-06 checks copays against the plan's terms; cards often print the copays, which gives the member a starting point before any EOB arrives (REC-15 needs at least 3 EOBs).

## What the card is read for

| Field | Usually on | Where it goes |
| --- | --- | --- |
| Insurer (payer) name and logo text | Front | Plan `insurer` |
| Plan or product name (e.g. "Choice Plus") | Front | Plan `plan_name` |
| Insurance type: network type (PPO, HMO, EPO, POS), HDHP / HSA-eligible marking, and coverage kind (medical, dental, vision, pharmacy) | Front | New plan field `plan_type`, `coverage_kind`; HDHP sets `hsa_eligible_plan` as a suggestion |
| Group number | Front | New plan field `group_number` (identifier, through the vault) |
| Member ID, with any per-person suffix (-01, -02) | Front | `member_number` per person (identifier, through the vault); feeds DSP letters |
| Subscriber (the insured, the policyholder) | Front | Marks which household member is the subscriber |
| Every member (dependents) listed | Front | Matched to household members; plan `member_ids` |
| Effective date | Front | Plan `coverage_start` and the plan year |
| Copays printed (PCP, specialist, urgent care, ER) and any deductible printed | Front | Plan `copays` (the keys REC-06 checks) and limits, as suggestions |
| Pharmacy: RxBIN, RxPCN, RxGroup | Front or back | New plan fields, shown on Coverage |
| Payer ID for claims (EDI) | Back | New plan field `payer_id` |
| Member services, provider services, pharmacy help, nurse line, prior authorization and behavioral health phone numbers | Back | New plan field `contacts` (label, phone) |
| Claims mailing address, appeals address, website | Back | `contacts`; offered to dispute letters as the insurer's address |
| Network or partner name ("Network: …", a BlueCard suitcase) | Either | `contacts` note; later for in-network checks |

Anything not read is left empty for the member to type. Nothing is guessed.

## How it works for the member

1. On the Coverage page, on the onboarding plan step and on Uploads: **"Scan your insurance card."**
2. Take or choose a photo of the **front**, then the **back** (phone camera opens directly; JPG, PNG, HEIC or a PDF scan accepted, ING-01). The back can be skipped and added later.
3. MHS shows both sides above a form, the same review pattern as documents (ING-05): each read field with its confidence, low ones marked "check".
4. MHS says which plan this is: **a new plan**, or **an update to an existing plan** (same insurer and group number). For an update it shows what changed (a new plan year, a new member, a changed copay).
5. Names on the card are matched to household members. A name that matches nobody offers "Add as a household member" or "Not in this household."
6. The member confirms. Only then is the plan created or updated, marked as the member's edit (ADR-011, `Store.upsert(..., edited=True)`), so a re-import doesn't overwrite it. The "These terms match my plan documents" box is **not** ticked by a card scan: copays on a card are a summary, not the plan's terms.
7. Coverage shows the card's contacts with tap-to-call links, and the card images (both sides) under the plan.

A second card for the same plan (a dependent's card, a replacement card, next year's card) updates the plan, never makes a duplicate. A card marked secondary, or for a second plan covering the same people, offers coverage order "secondary" (ALC-05).

## Privacy (must hold, per CLAUDE.md's upload rule)

A card is mostly identifiers, so it is handled more strictly than a bill:

- OCR runs in the application tier (`ingest/ocr.py`), as for photos today.
- Member ID, group number, names and the subscriber are read in the application tier and stored only as vault tokens (PRV-01, PRV-03). Members are linked through the pseudonymous person ID (PRV-02).
- Only the scrubbed text reaches the worker. If Claude extraction is on for the household, it receives only that scrubbed text, with dates shifted (PRV-05). Insurer phone numbers, addresses and payer ID are the insurer's public contact details, not the member's: the scrubber needs a rule that keeps them, the same way the provider's letterhead is kept (TESTING.md scenario 19), so this needs a test.
- The card images are originals (ING-10): stored unchanged and encrypted, viewable only by the household's members, included in export and removed by delete (PRV-09). Re-identified values (the real member ID) appear only on the signed-in member's own pages and in letters drafted on request, never stored in a letter, logged or queued.
- Consent applies: `collect_for` / `may_collect` gate the scan like any other way data comes in.
- The access log records the scan and the confirmation (counts and actions only).

## Acceptance criteria (draft test cases)

| Case | Given | Then |
| --- | --- | --- |
| TC-ING-11-1 | A synthetic card front and back (made with `tests/pdfs.py` `make_image`) for a new insurer | Insurer, plan name, plan type, group number, member ID, subscriber, two dependents, effective date, three copays, member services phone and claims address are read; the review form shows each with a confidence; nothing is saved until Confirm |
| TC-ING-11-2 | Confirm on TC-1 | A plan exists with those values, its members ticked, marked as a member edit; `terms_confirmed` is false |
| TC-ING-11-3 | The same card scanned again, then next year's card | The first changes nothing ("already on file"); the second offers an update showing the new plan year and changed copays |
| TC-ING-11-4 | A card naming a person not in the household | "Add as a household member" and "Not in this household" are offered; neither is done without the member's choice |
| TC-ING-11-5 | Outbound capture with Claude extraction on (TC-PLT-04-1 style) | No name, member ID or group number leaves the application tier; the insurer's phone and address may |
| TC-ING-11-6 | Front only, back skipped | The plan is saved from the front; contacts are empty; "Add the back of the card" is offered on Coverage |
| TC-ING-11-7 | A dispute letter for a visit on that plan | The letter has the member ID and the insurer's claims address from the card, drafted in the application tier |
| TC-ING-11-8 | A blurry or non-card photo | "This doesn't look like an insurance card" or empty fields with "check"; the member can type the plan in |
| TC-ING-11-9 | Layout tests at 375 and 1280 px | The scan steps and the review fit with no horizontal scroll; controls at least 44px; the new page is in `tests/test_ux_layout.py` `PAGES` |

## Out of scope for this request

- Checking eligibility with the insurer live (X12 270/271) or through the insurer connection (ING-09).
- A digital card wallet (Apple or Google Wallet) or showing the card at the front desk.
- Reading the plan's full Summary of Benefits and Coverage; the card is a starting point, not the plan's terms.
- Dental, vision or pharmacy-only reconciliation; those cards are read and filed, and reconciled only when MHS supports those claims.

## Likely changes when built (for the ADR and the estimate)

- ING-02: a new document type, "insurance card", which never enters reconciliation.
- A two-sided upload (one card, two images) in `web/household/intake.py` and the Release 0 import path, plus a camera-first form on phones.
- Card layout rules in `ingest/` (labels such as "Member ID", "Group", "RxBIN", "Subscriber", "Dependents") and a Claude prompt for the same fields; recorded responses in `tests/fixtures/ai`.
- Plan record fields: `plan_type`, `coverage_kind`, `group_number` (token), `payer_id`, `rx` (bin, pcn, group), `contacts`, `card_documents`, and per-member `member_number` (token) and `subscriber`. A new migration for the Release 1 tables.
- Coverage page: card images and contacts; "Scan your insurance card" on Coverage, onboarding (UX-09) and Uploads.
- `PagesHost.identifiers` reads the member ID from the card when no confirmed upload has one.
- A synthetic card set for tests and the harness; never a real card.

## Open questions for the owner

1. Should a card's copays fill the plan's copays automatically (as suggestions to confirm), or only be shown beside the form?
2. Keep the card images after the plan is saved, or let the member choose to discard them?
3. Read dental and vision cards now as separate plans, or medical (with pharmacy) only at first?
4. Priority: P2 (proposed), or move it into onboarding work ahead of other Release 2 items?
