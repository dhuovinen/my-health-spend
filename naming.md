# Naming: replacing "My Health Spend"

*Decided 2026-11-25 and recorded as ADR-060 in `docs/DECISIONS.md`.*

## Decision

**The brand is CareBack.** It replaces "My Health Spend" / "My Health $pend", and the `$` wordmark goes.

| Domain | Status | Role |
| --- | --- | --- |
| carebackhealth.com | Registered | Main address: it spells the brand ("CareBack Health"). |
| healthcareback.com | Registered | Redirect to the main address. Reads as "healthcare back", which supports the message. |
| myhealthspend.com | Owned | Redirect to the main address. |
| careback.com | Listed for sale (HugeDomains) | Not bought. Worth a price check later; if bought, it becomes the main address. |

Why CareBack: it carries the fighter-and-advocate tone the owner asked for in one word that needs no explanation, with two meanings: *we've got your back* and *getting your money back*. It uses "Care", stands on its own, and covers what comes next (Plan ahead, HSA and tax, disputes).

The rest of this file is the reasoning that led here.

## The problem

"My Health Spend" (styled **My Health $pend**, domain myhealthspend.com) describes the product well, but an HSA administrator already ships a mobile app called MyHealthSpend. Keeping the name would confuse members, could look like we are affiliated with an HSA company (the opposite of our independence), and carries trademark risk. We need a new brand before Release 2 opens sign-up to other households.

## What the name has to carry

The objective on the landing page does not change: one visit produces a provider bill, an insurer's EOB and a payment, often weeks apart; nobody reconciles the three, so the member is left to catch the errors. The service puts the three side by side, shows where they disagree with a dollar amount, and helps the member get the money back.

## The ethos (owner's answers, 2026-11-25)

| Question | Answer |
| --- | --- |
| Tone | **Fighter and advocate.** In the member's corner against billing errors. |
| Audience | **Individuals and their households only.** No provider, employer or advocate-firm offering to stay neutral for. |
| "Open" in the name | Welcome, and may be a good idea (open source, open books). |
| Visual twist | Not needed. The `$` in "My Health $pend" was too cute and may go. |
| Form | The name stands on its own, with no descriptor needed to explain it. |
| myhealthspend.com | Kept as a redirect to the new domain. |
| Words to consider | **Care** and **Health**, among others. |

Still true from the product's principles: the fight is backed by evidence. Every finding shows its numbers and documents, and the member decides what is sent. The brand can be bold; the findings stay careful.

The service is nonprofit and open source today but may be acquired or charge nominal fees, so the name avoids ".org"-only identities, "Foundation" and anything that becomes untrue if the owner changes.

## Criteria

1. Says "on your side" and "getting what's fair back", not "pay here" or "insurance".
2. Understood by an ordinary person without explanation (this is what ruled out Plumb).
3. Stands alone: short, easy to spell when heard aloud.
4. Distinct from HSA, insurer and bill-negotiation brands. "Bill" names are crowded: ClearBill (a contingency-fee bill-fighting service), BillDecoder, BillProof, Billscope.
5. Broad enough for what comes next: Plan ahead, HSA and tax, disputes.
6. A .com or clean variant is available, and the name is clear in USPTO classes 36, 42 and 44.

## The candidates

| # | Name | Why it fits | Watch out for |
| --- | --- | --- | --- |
| 1 | **CareBack** | Two meanings in one word: *we've got your back*, and *getting your money back*. Uses "Care". Friendly but clearly on the member's side; covers recovering overpayments and HSA refunds. | Could be heard as "care back" (getting care back). Nothing found under the name in a quick search. |
| 2 | **OpenClaim** | "Open" for open source and open books; "claim" is both the insurance claim we check and *staking your claim* to what you're owed. Fighter tone without hostility. | Some may think it *files* claims (like Reimbursify). Nothing found under the name. |
| 3 | **Due Care** (DueCare) | "Due care" is the legal duty of care; "due" is also what you're owed, and only what's due. A quietly pointed name: we hold providers and insurers to their duty. | Close to Duly Health and Care (an Illinois provider group). Legal phrase may make trademark harder. |
| 4 | **Fair Shake** | Plain-spoken American idiom for being treated fairly; instantly understood, scrappy, and on the underdog's side. | Common phrase, so a .com and trademark may be harder; likely needs a variant domain. |
| 5 | **Pushback** | Says exactly what the member gets to do. Bold, modern, one word. | Generic word, weaker as a trademark; reads negative out of context. |
| 6 | **OpenAdvocate** | States the ethos outright: an advocate, and open. Pairs with nonprofit and open source; still true after an acquisition. | Long (four syllables); "advocate" can suggest a paid human advocate service. Nothing found under the name. |
| 7 | **Backstop** | The thing that catches what everyone else missed: provider, insurer and HSA. Sporty, protective, one word. | Less obviously about health or money without context. Nothing found as "Backstop Health". |
| 8 | **Square Deal** | Teddy Roosevelt's fighting phrase for fair treatment of ordinary people; "square" also means accounts that balance. | "Square Health" exists in insurer claims, and Square (Block) is a payments brand. |
| 9 | **CareCounter** | *Counter* as in counting every dollar and as in countering a wrong charge. Uses "Care". | "Counter" can read as a shop counter. Nothing found under the name. |
| 10 | **Countercharge** | The fighter's name: a charge against a wrong charge. Memorable, unmistakably about disputing bills. | The most aggressive; sits uneasily with "a potential discrepancy, not a confirmed error". Better as a dispute-feature name than the brand. |

### Ruled out

- **Plumb** (too obscure, per the owner) and the rest of the first round's calm names: **TrueUp, Second Look, Itemized, Settled, Candor**.
- **Clean Bill, Openbill**: "ClearBill" already runs a bill-fighting service; too close.
- **Opencare** (Toronto dentist-booking company), **Open Health** (several agencies), **HealthRight** (HealthRIGHT 360), **Health Advocate** (an existing advocacy company), **AdvoCare** (supplements), **Rally** (Rally Health, UnitedHealth), **Tally** (Tally Health), **Truebill** (Rocket Money).
- **Granted**: already a healthcare-advocate app for denied claims.

## Shortlist recommendation

1. **CareBack** — the best fit for "fighter and advocate" that's still warm, and it uses "Care". It works with no explanation.
2. **OpenClaim** — the best home for "open"; strong if open source is going to be part of the pitch to members.
3. **Fair Shake** — the plainest-spoken; the strongest if the domain and trademark can be had.

## Next steps

Done: domains carebackhealth.com and healthcareback.com registered (2026-11-25).

1. USPTO search for "CareBack" (classes 36, 42, 44), and a state charity-name check if the nonprofit is formed under it.
2. Handles: App Store and Google Play names, and social accounts. `tools/name_check.sh` checks whether domains are registered, using whois (edit its list, or pass domains as arguments). A domain it shows as taken may still be for sale.
3. Say it aloud to five people who haven't seen it; ask what they think it does and who it's for.
4. ADR-060 is written. Update `docs/UI_GUIDE.md` (and drop the `$` wordmark), the landing page, `MHS_PUBLIC_URL` set to carebackhealth.com with healthcareback.com and myhealthspend.com forwarding to it (ADR-058's redirect), the Google, Microsoft and Apple OAuth client display names, and the privacy notice and consent drafts going to the attorney.

*Availability notes come from quick web searches on 2026-11-25, not a trademark search.*
