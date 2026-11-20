# User test guide

A step-by-step walk through the whole app as a member, with made-up data you import or upload, and what you should see at each step. Each step has a box to tick and a place to note what went wrong. It works on staging (`https://mhs-app-685050015174.us-east4.run.app`) and on the local stack (`http://127.0.0.1:3063`); where they differ, it says so.

**All the data is synthetic.** Never use real documents on staging.

| Part | What you try | Time |
| --- | --- | --- |
| [0](#part-0-before-you-start) | Sign in and get the files | 5 min |
| [1](#part-1-the-upload-story) | Upload a statement, an EOB, a phone photo and an HSA export (the demo story) | 15 min |
| [2](#part-2-import-the-walkthrough-household) | Import a second household member with ten visits | 5 min |
| [3](#part-3-checking-claims-against-the-plan) | Plan cost-sharing checks, before and after you confirm the plan's terms | 10 min |
| [4](#part-4-denials-and-claim-codes) | A denied line and what the codes mean, then a dispute case | 10 min |
| [5](#part-5-corrected-eobs-refunds-and-a-second-insurer) | A corrected EOB, a refund to the wrong account, a second insurer | 10 min |
| [6](#part-6-plan-ahead) | Estimates before a visit | 10 min |
| [7](#part-7-learning-from-your-corrections) | Three EOBs from an insurer the app doesn't know yet | 15 min |
| [8](#part-8-the-rest-of-the-app) | Home, Household, Providers, Charges over time, HSA and tax, Help | 15 min |
| [9](#part-9-your-account-consent-and-privacy) | Account, consent, privacy notice, export | 10 min |
| [10](#part-10-on-a-phone) | The phone layout | 5 min |

## Part 0: before you start

- [ ] **A demo household.** On staging, once:
  ```bash
  PROJECT_ID=mhs-staging-512010 tools/gcp/admin.sh demo-setup
  ```
  Locally: `docker compose exec app mhs-admin demo-setup`. It creates "Sample household" with the member `demo@example.com` (Jordan Sample), Jordan's 2026 plan (Example Health HDHP: $1,700 deductible, 20% coinsurance) and an HSA. Running it again gives a new password and authenticator code; your data stays.
- [ ] **Sign in** with `demo@example.com`, the printed password and, if the code is required, the 6-digit code from your authenticator app. To sign in without the code on staging: `PROJECT_ID=mhs-staging-512010 tools/gcp/admin.sh require-code off`.
- [ ] **The files** are in the project folder on your Mac:
  - `samples/demo/`: `1-riverbend-statement.pdf`, `2-riverbend-eob.pdf`, `3-lakeside-eob-photo.png`, `4-hsa-transactions.csv`
  - `samples/walkthrough/`: `walkthrough-ingest.json`, `granite-eob-1.pdf`, `granite-eob-2.pdf`, `granite-eob-3.pdf`
- [ ] Use a desktop browser window about 1280 px wide.

**Finding your way around.**

| Where | What's there |
| --- | --- |
| Top menu | Home, Visits, Plan ahead, Household, Coverage, Providers, Cases, HSA and tax |
| Blue **Add** button (top right) | The Uploads page. Its "Import it" link, under the upload box, opens the Import page |
| **?** and gear icons (top right) | Help and Settings |
| Round avatar with your initial (top right) | The account menu: Account and sign-in, Your consent, Your data and access log, Privacy notice, Sign out |
| **Coverage** | Your insurance plans: what each covers, progress toward deductibles and out-of-pocket maximums, the claims behind it, and **Edit this plan** |
| Providers page → **Charges over time** | Charges per provider and code |
| Phone: bar at the bottom | Home, Visits, Add, Plan, and **More** for everything else |

On the local laptop app (Release 0, no sign-in) the blue button says **Import** and there's no account menu.

**Starting over.** Imports and uploads can't be undone one by one. To start fresh on staging, make a second demo household with its own email; the walkthrough file works in it too:

```bash
PROJECT_ID=mhs-staging-512010 tools/gcp/admin.sh demo-setup --household "Walkthrough 2" --email demo2@example.com
```

Locally, `docker compose --profile test down -v` wipes everything.

**Dates.** Today's date matters for two things: a visit less than 30 days old is "Awaiting EOB" rather than "Missing documents", and a planned visit whose date has passed asks whether it happened. The expected results below were worked out for mid-November 2026.

## Part 1: the upload story

Jordan saw Riverbend Orthopedics on 14 August for a knee. The statement asked for $480.00 and Jordan paid it from the HSA. The insurer's EOB then said Jordan owed only $300.00. Separately, Jordan photographed an MRI EOB from Lakeside Imaging. [DEMO.md](DEMO.md) tells the same story in more detail.

| # | Do | You should see | OK? |
| --- | --- | --- | --- |
| 1.1 | **Home** | "Getting started": a progress bar and six steps, the finished ones ticked green, the next one highlighted with **Do this next**; under it, "No visits yet" | ☐ |
| 1.2 | **Add** (top right) → choose `1-riverbend-statement.pdf` → **Upload** | The row says *Reading*, then shows **Review** within a few seconds (refresh if needed) | ☐ |
| 1.3 | **Review** | "Read from the pdf text layer"; type Provider statement; amount due $480.00; two lines (99214, 73562); the page in two parts, *Who and what* (Provider, then the provider name read from the document, Patient) and *What the document says*; the provider name marked **Check**, with "From the letterhead · 50% sure" under it; fields read with confidence show no percentage | ☐ |
| 1.3a | **Change when fields are marked** (top of the page) → Settings, *Reviewing uploads*: "less than 100% sure" and "On every field" → **Save** → back to the review | More fields marked **Check**, and every field shows how sure the reader was; set it back to 80% and "Only on fields marked Check" | ☐ |
| 1.4 | **Confirm and add to my visits** | The visit opens: Riverbend Orthopedics, Aug 14, 2026, **Balance outstanding**, missing the EOB | ☐ |
| 1.5 | Upload `2-riverbend-eob.pdf` → **Review** | Recognised as an EOB; the Aug 14 visit already chosen ("Matched automatically"); billed $480.00, discount $180.00, allowed $300.00, you owe $300.00 | ☐ |
| 1.6 | **Confirm** | The visit is **Discrepancy found**: "Bill matches EOB · **Missed adjustment**", $180.00 | ☐ |
| 1.7 | Upload `3-lakeside-eob-photo.png` → **Review** | "Read from the photo, OCR (…)": *documentai* on staging, *tesseract* locally. Lakeside Imaging, $800.00 yours | ☐ |
| 1.8 | **Confirm** | A new visit, **Balance outstanding**, $800.00 | ☐ |
| 1.9 | Upload `4-hsa-transactions.csv` | Goes straight to **Check import** (no review needed); **Save import** | ☐ |
| 1.10 | Open the Riverbend visit | Payments applied: $300.00, and $180.00 marked "more than owed"; a second finding, **Overpayment** $180.00; "credit due to you $180.00" | ☐ |

## Part 2: import the walkthrough household

The file adds **Alex Sample**, Jordan's spouse. Alex's plan is Granite PPO 1000 from Granite Mutual ($1,000 deductible, 20% coinsurance, copays of $25 primary care and $60 specialist), plus a secondary plan from September. Alex has ten visits, each built to show one feature. Jordan gets one planned visit.

| # | Do | You should see | OK? |
| --- | --- | --- | --- |
| 2.1 | **Add** → **Import it** (the link under the upload box) → choose `walkthrough-ingest.json` → **Check** | "What will change": 1 member, 2 plans, 1 account, 10 providers, 12 visits, 18 documents, all new; no problems | ☐ |
| 2.2 | **Save import** | "Import saved." | ☐ |
| 2.3 | **Visits** | Ten visits for Alex Sample, Feb to Nov 2026, with these statuses: | ☐ |

| Visit | Provider | Status now | Why |
| --- | --- | --- | --- |
| Feb 10 | Lakeside Family Medicine | Complete | $25 copay, as the plan says |
| Mar 5 | Bennett Radiology | Complete | Meets the $1,000 deductible, plus 20% |
| Apr 14 | Northgate Dermatology | Balance outstanding | Copay too high (Part 3) |
| May 20 | Cedar Valley Labs | Balance outstanding | Deductible charged again (Part 3) |
| Jun 2 | Lakeside Family Medicine | Balance outstanding | Copay on preventive care (Part 3) |
| Jun 18 | Hillcrest Imaging Center | Discrepancy found | A denied line (Part 4) |
| Jul 8 | Riverside Physical Therapy | Needs review | A corrected EOB (Part 5) |
| Aug 12 | Summit Eye Associates | Discrepancy found | Refund to the wrong account (Part 5) |
| Sep 15 | Maple Street Orthopedics | Complete | Two insurers, adds up (Part 5) |
| Nov 4 | Harbor Cardiology | Awaiting EOB | Second insurer's EOB not in yet (Part 5) |

The Nov 4 visit turns to "Missing documents" after Dec 4.

## Part 3: checking claims against the plan

MHS checks each EOB's deductible, copay and coinsurance against the plan's terms, in the order the insurer processed them. Until you confirm the terms in Settings, a difference is only "worth a closer look", because wrong terms would make every claim look wrong.

| # | Do | You should see | OK? |
| --- | --- | --- | --- |
| 3.1 | Open **Apr 14, Northgate Dermatology** | Under What's wrong, a **?** item "Your share matches your plan · Cost sharing differs from your plan": copay $75.00 (plan says $60.00), "a flag until you confirm your plan's terms" | ☐ |
| 3.2 | Open **May 20, Cedar Valley Labs** | A flag: deductible $300.00 (plan says $0.00), "Deductible already met", coinsurance should be 20% of $300.00 = $60.00 | ☐ |
| 3.3 | Open **Jun 2, Lakeside Family Medicine** (Annual physical) | A flag: "preventive care should cost you $0.00", charged $25.00 | ☐ |
| 3.4 | Open **Feb 10** and **Mar 5** | In "checks passed", "Your share matches your plan" with the math, for example "Deductible: $1,000.00 of the $1,000.00 left; Coinsurance: 20% of the $600.00 … = $120.00" | ☐ |
| 3.5 | **Coverage** (top menu) → the Granite Mutual card | An insurance-card summary (Granite Mutual, Granite PPO 1000, Primary, covers Alex Sample); **What you pay**: 20% coinsurance, copays of $25.00 primary care, $60.00 specialist, $75.00 urgent care; "Check these terms against your plan documents" with **Confirm these terms** | ☐ |
| 3.6 | **Confirm these terms** (opens **Edit this plan**) → tick **These terms match my plan documents** → **Save plan** | Back on the card: "Saved." at the top and "✓ You confirmed these terms…" | ☐ |
| 3.6b | **Home** | Getting started now has all six steps ticked and disappears | ☐ |
| 3.6c | **Coverage**, Granite Mutual card → **2026 so far** and **Claims under this plan** | Alex's deductible $1,300.00 of $1,000.00 in red ("$300.00 more than the limit"), out-of-pocket $1,905.00 of $4,000.00; ten claims, each linking to its visit | ☐ |
| 3.7 | **Visits** | Apr 14, May 20 and Jun 2 are now **Discrepancy found**, at $15.00, $240.00 and $25.00 | ☐ |
| 3.8 | Open one of them | The finding is now ✕ with **Open a case** and **Close this finding** | ☐ |
| 3.9 | On Jun 2, **Change this visit** → Kind of service → set **Primary care** → **Save** | The preventive finding goes away; the copay now matches ($25.00) | ☐ |
| 3.10 | Set it back to **Preventive care** | The finding is back | ☐ |

## Part 4: denials and claim codes

| # | Do | You should see | OK? |
| --- | --- | --- | --- |
| 4.1 | Open **Jun 18, Hillcrest Imaging Center** | **Discrepancy found**; finding "Denial explained · **Denial looks appealable**", $250.00, naming PR-50 (not medically necessary) and ending "Information, not legal advice" | ☐ |
| 4.2 | Documents → the EOB card → **What the codes mean** | Each code once, with where it was printed: CO-45 "claim, line 1 (76700)" (the plan discount, you don't owe it); PR-50 "line 2 (99214)" marked **Can often be corrected or appealed**; N130 (check your plan documents) | ☐ |
| 4.3 | **Line by line** | Two EOB lines: 76700 paid by the plan; 99214 not covered, $250.00 | ☐ |
| 4.4 | On the denial finding, **Open a case** | The case page: with **Granite Mutual** (the insurer), the finding and the lines | ☐ |
| 4.5 | Draft the **Appeal to the insurer** letter | A letter with the claim number GM-10006 and the amounts; nothing is saved or sent | ☐ |
| 4.6 | Back on the visit | **In dispute**, and an appeal deadline 180 days after the EOB date | ☐ |
| 4.7 | **Cases** | The open case listed with $250.00 at issue | ☐ |

## Part 5: corrected EOBs, refunds and a second insurer

| # | Do | You should see | OK? |
| --- | --- | --- | --- |
| 5.1 | Open **Jul 8, Riverside Physical Therapy** | **Needs review**; a box "A newer EOB arrived for claim GM-10007 (corrected)", "You corrected the one on file…", and a table, yours beside the newer: allowed $600.00 → $450.00, you owe $120.00 → $90.00 | ☐ |
| 5.2 | **Use the newer EOB** | The visit is **Discrepancy found**: **Overpayment** $30.00 (Alex paid $120.00); under the EOB card, "1 earlier version of this EOB" | ☐ |
| 5.3 | **Case history** | "Earlier EOB, since replaced" and "EOB corrected" | ☐ |
| 5.4 | Open **Aug 12, Summit Eye Associates** | **Discrepancy found**: "Refund went back to the right account · **Refund belongs in the HSA**", $80.00: deposit it back into the HSA as a returned mistaken distribution | ☐ |
| 5.5 | Who pays what | $200.00 paid from the HSA ($80.00 more than owed), and the $80.00 refund to the Visa card | ☐ |
| 5.6 | Open **Sep 15, Maple Street Orthopedics** | **Complete**; Documents shows "Second insurer: claim EH-55009", paid $40.00, your cost after both plans $10.00; checks passed include "Second insurer adds up: The first plan left $50.00; the second insurer paid $40.00; you owe $10.00" | ☐ |
| 5.7 | Where the billed amount went | Plan discount $150.00, insurer paid $200.00, second insurer paid $40.00, your share (not broken down) $10.00; billed $400.00 | ☐ |
| 5.8 | Open **Nov 4, Harbor Cardiology** | **Awaiting EOB**; "You're also covered by a second plan: wait for its EOB before paying what the first plan left"; the checklist shows "Second insurer's EOB · Expected" | ☐ |
| 5.9 | In the checklist, set the second insurer's EOB to **Not needed** → **Set** | The status changes to **Balance outstanding** ($70.00) | ☐ |

## Part 6: plan ahead

| # | Do | You should see | OK? |
| --- | --- | --- | --- |
| 6.1 | **Plan ahead** (top menu; **Plan** in the phone's bottom bar) | Two planned visits: Summit Eye Associates (Nov 3, **Did it happen?**) and Oakview Imaging (Dec 16) | ☐ |
| 6.2 | Open **Oakview Imaging, MRI of the left knee** (Jordan) | "What you'll likely owe" through insurance, with the steps. With Part 1 done: $720.00 ($600.00 deductible left, plus 20% of $600.00). Without it: $1,200.00 | ☐ |
| 6.3 | **Cash or insurance** | Paying cash ($650.00) costs less, and a question to ask the plan whether cash counts toward the deductible | ☐ |
| 6.4 | **Which account should pay** and **Ask before the visit** | An HSA recommendation; questions about network, codes, prior authorization, balance billing and a good-faith estimate (the provider's network status is unknown), cash price, itemized bill; the "Information, not legal, tax or medical advice" note | ☐ |
| 6.5 | **Coverage** → Jordan's plan (Example Health) → **Edit this plan** → "Cash counts toward deductible" → **No** → **Save plan**; reopen the MRI | The cash text now says paying cash leaves the deductible still to meet | ☐ |
| 6.6 | Open **Summit Eye Associates, Annual eye exam** (Alex) | "Did this visit happen?"; the estimate is the $60.00 specialist copay | ☐ |
| 6.7 | **No, it was cancelled** | It leaves the Plan ahead list | ☐ |
| 6.8 | **Plan a visit**: tomorrow's date, a new provider "Test Clinic", for Alex, Specialist, allowed 200 → **Plan it** | The new plan's page: $60.00, the copay | ☐ |
| 6.9 | Enter the allowed amount as `lots` and save | An error: "isn't an amount" | ☐ |

## Part 7: learning from your corrections

Granite Mutual's EOBs use labels the app doesn't recognise yet ("Contracted rate", "Granite remitted", "Member portion"). Correct the first one and the app learns where to look on the next.

| # | Do | You should see | OK? |
| --- | --- | --- | --- |
| 7.1 | Upload `granite-eob-1.pdf` → **Review** | An EOB; provider Westfield Allergy; date of service 2026-05-06; claim GM-20511; the patient matched to Alex Sample; but **billed, allowed, plan paid and you owe empty** | ☐ |
| 7.2 | Type them in: Billed **412.00**, Allowed **286.00**, Plan paid **228.80**, You owe (EOB) **57.20**. Choose the **Granite Mutual** plan → **Confirm** | A new visit for Alex at Westfield Allergy | ☐ |
| 7.3 | Upload `granite-eob-2.pdf` → **Review** | A note: "Some fields were read with labels you corrected on earlier documents from this sender…"; billed $398.00, allowed $271.00, plan paid $216.80, you owe $54.20, each noted "read with the label you corrected…" | ☐ |
| 7.4 | Confirm it; upload `granite-eob-3.pdf` → **Review** | Brookside Podiatry, all four amounts filled ($335.00, $240.00, $192.00, $48.00). A different provider, same insurer: the learning goes with the insurer's layout | ☐ |
| 7.5 | Upload `1-riverbend-statement.pdf` again | Refused as already uploaded: the same file is never added twice | ☐ |

## Part 8: the rest of the app

| # | Do | You should see | OK? |
| --- | --- | --- | --- |
| 8.1 | **Home** | The summary and $ at stake; the nine statuses with counts; **Needs your attention**, most dollars first, each reason cut to two lines; the year's visits, where a visit's missing documents read "Needs: Provider bill, Payment proof" and no amount at issue shows "—" | ☐ |
| 8.2 | **The year in detail**, bottom of Home | Three cards side by side: HSA, Plan limits and where the billed dollars went. Alex's deductible bar is red, with "$300.00 more than the limit: worth a closer look" (the deductible charged twice in Part 3) | ☐ |
| 8.3 | **Showing** switch (top of Home) → **Alex Sample** | Home, Visits and Household show only Alex's visits; switch back to the family | ☐ |
| 8.4 | **Household** | A row each for Jordan and Alex, with their totals, and the family's | ☐ |
| 8.5 | **Providers** → Riverbend Orthopedics | The ledger, the $180.00 credit due, payments and how they're split | ☐ |
| 8.6 | **Providers** → **Charges over time** | Charges over time per provider and code | ☐ |
| 8.7 | **HSA and tax** | Likely-qualified tags per visit, contributions against the 2026 limit, the receipt vault, the year-end summary, and the disclaimer | ☐ |
| 8.8 | A finding, e.g. Apr 14's copay → **Close this finding** → **It was wrong** (reason: "testing") | The finding shows "Closed by you"; the visit's link "how often the findings were wrong" opens **Finding accuracy**, which counts it as wrong | ☐ |
| 8.9 | **Help** (the ? icon) | Every status and check explained, including the new ones | ☐ |

## Part 9: your account, consent and privacy

| # | Do | You should see | OK? |
| --- | --- | --- | --- |
| 9.1 | The avatar (top right) | A menu with your name, **Account and sign-in**, **Your consent**, **Your data and access log**, **Privacy notice** and **Sign out**; a click elsewhere or Escape closes it | ☐ |
| 9.1a | **Settings** (the gear icon) → **Insurance plans** | A short list of your plans with whether their terms are confirmed, and **Open Coverage**: plans are edited on Coverage now | ☐ |
| 9.1b | **Account and sign-in** | Recovery codes, sign-in accounts, links to consent, privacy notice and your data | ☐ |
| 9.2 | **Privacy notice** | What's collected, how it's protected, who else sees it, your choices; marked as a draft for the attorney. Also open it signed out: it's public | ☐ |
| 9.3 | **Your consent** | Two unticked boxes: collection, and AI sharing, separately | ☐ |
| 9.4 | Tick the first only → **Save my choice** | "Saved." and the history lists your choice | ☐ |
| 9.5 | Untick everything → **Save** → try an upload | The upload is refused: "MHS can't take documents from you without your consent". Tick it again afterwards | ☐ |
| 9.6 | Avatar → **Your data and access log** | The access log of what you viewed and changed; **Export** (asks for your password) | ☐ |
| 9.7 | **Add** → **Connect your insurer instead** (beside the page title) | "No insurer is set up for connection on this server yet" (none is configured) | ☐ |
| 9.8 | *Optional, owners only:* `tools/gcp/admin.sh owner --email demo@example.com on`, sign in again with the code, open `/admin` | Counts only, the code setting, sign-in providers, and **Consent before collection** | ☐ |

## Part 10: on a phone

Staging works on a real phone: open the app's address in the phone's browser. Locally, use the browser's device toolbar at 375 px.

| # | Do | You should see | OK? |
| --- | --- | --- | --- |
| 10.1 | Home, a visit, Plan ahead, Uploads | A bar at the bottom (Home, Visits, Add, Plan, More); nothing scrolls sideways; buttons big enough to tap | ☐ |
| 10.1b | **More** | A list: Household, Coverage, Providers, Charges over time, Cases, HSA and tax, Import a file, Settings, Help; tapping outside closes it | ☐ |
| 10.1c | The avatar (top right) | The same account menu as on a computer | ☐ |
| 10.2 | **Add** → **Take a photo of a bill or EOB** (staging, real phone) | The camera opens; the photo uploads and is read by OCR | ☐ |

## Writing down what you find

For anything that isn't as described, note the part and step (for example "5.2"), what you saw (a screenshot helps) and the time. On staging, the app's logs for that moment are in the Google Cloud console under Cloud Run → `mhs-app` → Logs; they never contain document text.

Regenerate the walkthrough files after changing them: `uv run tools/make_walkthrough_sample.py`.
