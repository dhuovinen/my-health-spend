# My Health Spend guided test results

November 20, 2026 · Signed-in Sample household on [My Health Spend](https://myhealthspend.com/) · USER_TEST_GUIDE.md, Parts 3–10

I rated each instruction on how easy it was to follow in the live interface. The result records whether the expected behavior was observed. Granite’s plan terms were confirmed before this run, so the initial unconfirmed state was unavailable. The walkthrough used synthetic records.

## Part 3 — Checking claims against the plan

| Step | Ease of following the instruction | Observed result |
|---|---|---|
| 3.1 | Easy to find from Visits by date and provider. | Northgate showed $75 charged versus a $60 plan copay. The finding was already a discrepancy because Granite’s terms were confirmed. |
| 3.2 | Easy to open Cedar Valley Labs. The deductible math is clear once you find the finding. | $300 deductible charged after it was met. The expected 20% coinsurance was $60, with $240 at issue. It was already a discrepancy. |
| 3.3 | Easy. The date distinguishes the two Lakeside Family Medicine visits. | The annual physical showed $25 charged versus $0 expected. It was already a discrepancy. |
| 3.4 | Some effort. Open the collapsed checks-passed section on each visit. | February showed the $25 primary-care copay. March showed $1,000 deductible plus $120 coinsurance, for $1,120. |
| 3.5 | Some effort. Scroll past another plan to reach Granite. | The Granite PPO 1000 card showed Alex, 20% coinsurance, and the listed copays. Its confirmed message had already replaced the confirmation prompt. |
| 3.6 | The instruction is clear. The named confirmation action was unavailable for Granite. | The confirmed state was visible. The save transition and “Saved” message were unverified for this plan. |
| 3.6b | Easy to return to Home. | Getting started was absent. Its disappearance immediately after confirmation was unverified. |
| 3.6c | Some effort. Progress and claims sit below the introductory sections, and claims must be expanded. | Alex showed $1,300 of $1,000, $300 over the limit, and $1,905 of $4,000 out of pocket. The plan displayed 10 claims with visit links. |
| 3.7 | Easy to find the three dated rows. | Discrepancies showed $15, $240, and $25 respectively. |
| 3.8 | Easy to find the finding actions. The check label and result contradict each other at a glance. | The failed finding exposed **Open a case** and **Close this finding**. |
| 3.9 | Some effort. **Change this visit** is collapsed, and there are several **Save** buttons on the page. | Changing the service to Primary care cleared the preventive finding. The passed check explained the $25 copay. |
| 3.10 | Easy once the editor’s location is known. | Restored Preventive care and verified that the $25 finding and **Discrepancy found** returned. |

**Usability 3/5.** The calculations are understandable and reproducible. Lead each finding with the result and next action, for example **“Copay $15 higher than your plan”**. Put the check name and calculations in the supporting detail. On Coverage, put **Review plan terms** and **Edit plan** near the plan name and give users a way to jump straight to their plan.

## Part 4 — Denials and claim codes

| Step | Ease of following the instruction | Observed result |
|---|---|---|
| 4.1 | Easy from Visits. The denial stands out under **What’s wrong**. | The $250 PR-50 denial was labeled appealable and explained in plain language. |
| 4.2 | Some effort. **What the codes mean** is inside the EOB card in Documents. | CO-45 was tied to the claim and line 1, and PR-50 and N130 to line 2. PR-50 carried the correction or appeal label. |
| 4.3 | Easy to find **Line by line**. The result diverges from the guide. | The section said it needs both a provider bill and an EOB. It showed neither EOB line independently, even though the document’s code guide identified 76700 and 99214. |
| 4.4 | Easy from the denial finding. Another **Open a case** button also exists on the visit. | Opened a synthetic case with Granite Mutual. It showed the $250 finding and the EOB. The case flagged the missing provider bill and payment proof. |
| 4.5 | Easy. The suggested appeal type was already selected. | **Draft the letter** generated an editable draft with GM-10006 and $250. The draft included placeholders and on-screen instructions telling the member to ask the provider or appeal. I left it as a draft. |
| 4.6 | Easy from the case’s visit link. | The visit showed **In dispute**, with a December 28, 2026 deadline, 180 days after July 1. |
| 4.7 | Easy from Cases. | Hillcrest appeared as open with Granite Mutual and $250 at issue. |

**Usability 3/5.** Show the insurer’s line items as soon as the EOB is available and add the bill comparison when the bill arrives. Generate insurer-facing prose that states what is being appealed and what the member is requesting. Put instructions, disclaimers, and unfilled placeholders in a separate checklist beside the draft.

## Part 5 — Corrected EOBs, refunds, and a second insurer

| Step | Ease of following the instruction | Observed result |
|---|---|---|
| 5.1 | Very easy. The comparison appears in a prominent notice. | Riverside showed **Needs review**, allowed amount $600 → $450, and member share $120 → $90. |
| 5.2 | Easy. **Use the newer EOB** is explicit. | Accepted the corrected EOB. The visit showed a $30 overpayment and retained an earlier EOB version. |
| 5.3 | Easy from **Case history**. | Both **Earlier EOB, since replaced** and **EOB corrected** were present. |
| 5.4 | Easy to locate the August Summit visit. The check label initially reads as though the refund went to the right account. | **Refund belongs in the HSA** identified the $80 issue and described the next step. |
| 5.5 | Easy via **Who pays what**. The user has to combine the payment rows to see the full path. | $200 came from the HSA, including $80 over the amount owed. An $80 refund went to Visa. |
| 5.6 | Some effort. The second EOB is in Documents, and the reconciliation is under the collapsed passed checks. | Maple Street was **Complete**. EH-55009 and the passed check showed $50 remaining after the first insurer, $40 paid by the second, and $10 owed. |
| 5.7 | Some effort. **Where the billed amount went** is inside **Who pays what**. | $150 discount + $200 first insurer + $40 second insurer + $10 member share reconciled to the $400 bill. |
| 5.8 | Easy to open Harbor and see the waiting status. The checklist is farther down. | The page said to wait for the second insurer. Its EOB was **Expected**. |
| 5.9 | Some effort. Each document has its own generic **Set** button. | **Not needed** switched Harbor to **Balance outstanding**, $70 unpaid. Restored **As usual** and confirmed **Awaiting EOB** returned. |

**Usability 4/5.** The corrected-EOB comparison and history met the excellent standard. Bring that clarity to refunds with a short summary such as **“$80 paid from HSA → refunded to Visa”**, followed by the next action. Keep the second insurer’s expected document and payment guidance together, and explain the effect of **Not needed** next to the control.

## Part 6 — Plan ahead

| Step | Ease of following the instruction | Observed result |
|---|---|---|
| 6.1 | Easy. The upcoming and past visits are both visible in the list. | Summit showed **Did it happen?** and Oakview showed the December 16 planned visit. |
| 6.2 | Very easy. The insurance estimate is the first major number. | Oakview showed $720, with $600 of deductible and $120 of coinsurance. |
| 6.3 | Easy to find the cash comparison. The comparison itself is in prose. | Cash was $650, $70 less, with a prompt to ask about deductible credit. |
| 6.4 | Easy to find the account recommendation and call checklist. | The page suggested HSA payment and listed questions about network, codes, prior authorization, balance billing, a good-faith estimate, cash price, and an itemized bill. |
| 6.5 | Some effort. Switch pages, expand the plan editor, save, and return to Oakview. | Setting **No** said a cash payment leaves $600 of deductible to meet. Restored **I don’t know**. |
| 6.6 | Easy. The question is prominent above the estimate. | Summit showed **Did this visit happen?** and a $60 specialist copay. |
| 6.7 | Easy. The cancellation button is explicit. | Cancelled the synthetic Summit visit. It left the planned visits list. |
| 6.8 | Some effort. Several fields sit between the list and **Plan it**. The guide specifies the required inputs. | Created Test Clinic for Alex with a $200 allowed amount. The estimate was a $60 specialist copay. |
| 6.9 | Some effort. Open the visit editor and locate the amount among the existing inputs. | Saving `lots` showed **“Expected allowed amount: ‘lots’ isn’t an amount.”** The valid estimate had already been saved in 6.8. |

**Usability 4/5.** Give cash and insurance their own side-by-side price cards with deductible impact directly below. Move the planning form behind a prominent **Plan a visit** action and put format errors beside the corresponding input. An immediate **Undo** after cancellation would make the list behavior easier to recover from.

## Part 7 — Learning from corrections

| Step | Ease of following the instruction | Observed result |
|---|---|---|
| 7.1 | **Add → Uploads** was easy to find. The guide assumes the fixture PDFs are already on the testing device. | Located the exact synthetic fixture in the project repository. Chrome blocked attaching the PDF before it reached the app. |
| 7.2 | The guide provides clear field names and exact values. | Blocked by 7.1. The live review screen and first correction were unverified. |
| 7.3 | The instruction clearly says to review the second file for reused labels and amounts. | Blocked by 7.1. Learning from the first correction was unverified. |
| 7.4 | The instruction clearly distinguishes a different provider with the same insurer. | Blocked by 7.1. Cross-provider learning was unverified. |
| 7.5 | The exact duplicate file is clearly identified. | Blocked by the same file-picker restriction. Duplicate-file handling was unverified. |

**Usability unrated.** The upload entry point was clear. The browser restriction prevented evaluation of the learning flow. Bundle the sample PDFs with the guide for an easier test setup. On a rerun, check whether each learned value explains which document label produced it and gives the user an obvious way to correct it.

## Part 8 — The rest of the app

| Step | Ease of following the instruction | Observed result |
|---|---|---|
| 8.1 | Easy to see the summary. Visit rows require the extra **Show visits** action. | Home showed totals, status counts, and **Needs your attention**. Visit rows showed missing documents and a dash for no amount at issue. The dashboard explicitly prioritizes near deadlines and overdue follow-ups ahead of dollar amounts. |
| 8.2 | Some effort. Scroll beneath the main dashboard. | The detail area showed plan limits and Alex’s $300 overage on the deductible, alongside the HSA and billed-dollar summaries. |
| 8.3 | The control and member names are clear. The action stops the workflow. | Selecting Alex on Home opened a raw `Forbidden` page at `/view`. Browser Back recovered Home. Cross-page persistence could not be verified. |
| 8.4 | Easy from the top menu after returning to the app. | Household showed Alex, Jordan, and Family rows with totals. |
| 8.5 | Easy. The provider name links directly to its ledger. | Riverbend showed $180 credit due, payment splits, and ledger entries. |
| 8.6 | Easy to open the chart. The guide implies a filter the page does not expose. | The chart offered Provider, Member, and Amount controls. I saw no service-code filter. |
| 8.7 | Easy to reach. The headings are clear, but the page is long. | The receipt vault, year-end summary, contributions and limits, qualification language, and disclaimer were present. |
| 8.8 | Easy to mark the Northgate finding wrong after opening the collapsed close control. The report link was harder to use. | The finding showed **Closed by you** and the reason “testing.” The link did not navigate in my attempts. Opening its observed destination directly showed **Finding accuracy**, with one cost-sharing finding marked wrong. |
| 8.9 | Easy to open by the question-mark icon. The help is extensive. | Help included the status and check sections, including denial and second-insurer explanations. |

**Usability 3/5.** Fix the Alex filter first. Keep Home visible and show any failure inline with a way to recover. Confirm the filter carries through Visits and Household. Then make **Finding accuracy** reachable from the visit link and either add service-code access to the chart or update the guide’s expectation.

## Part 9 — Account, consent, and privacy

| Step | Ease of following the instruction | Observed result |
|---|---|---|
| 9.1 | Easy with the guide’s “top right” cue. | All account destinations and **Sign out** were present. Escape and an outside click closed the menu. |
| 9.1a | Easy. **Insurance plans** is a visible Settings jump link. | The plans showed confirmation states and **Open Coverage**. |
| 9.1b | Easy. The page headings and controls are recognizable. | Recovery codes, sign-in accounts, consent, privacy, and data links were present. |
| 9.2 | Easy to find through the avatar menu. | The signed-in notice showed the draft label and the expected data, protections, sharing, and choices sections. Signed-out access was unverified. |
| 9.3 | Easy to find. The choices are visually distinct, with long labels. | Collection and AI sharing were separate and both unchecked. |
| 9.4 | The checkbox and **Save my choice** are easy to identify. | Pending confirmation to change collection consent on the signed-in account. Persistence and history were unverified. |
| 9.5 | The guide’s sequence is clear. | Pending the same consent confirmation and working file attachment. Upload refusal and consent restoration were unverified. |
| 9.6 | Easy to find the export form and log. A separate delete form also asks for a password. | The log was visible and export asked for a password. The browser tab title included raw access-log markup. The export download was unverified. |
| 9.7 | Easy to find through Uploads, although the title link gives no advance indication the connection is unavailable. | The page showed no configured insurer and directed users back to uploading EOBs. |
| 9.8 | Optional owner setup requires access outside the member UI. | Skipped. No owner privileges or server settings were changed. |

**Usability 3/5.** Fix the tab title so it reads **Your data and access log** and contains no log entries. Separate **Export** from **Delete my account** and give collection and AI sharing short headings with distinct explanations. When connections are unavailable, give the user a direct **Upload an EOB** action.

## Part 10 — Phone layout

| Step | Ease of following the instruction | Observed result |
|---|---|---|
| 10.1 | Easy. **Home**, **Visits**, **Add**, and **Plan** stayed within reach. | At 375 × 812, Home, a visit, Plan ahead, and Uploads fit the page width. The bottom navigation controls were 44 pixels high. Uploads had a 437-pixel table inside a 288-pixel container, requiring sideways scrolling within that section. |
| 10.1b | Easy. **More** is visibly labeled in the bottom bar. | All listed destinations were available and an outside click closed the menu. |
| 10.1c | Easy. The avatar remained in the top right. | The same account destinations were available. |
| 10.2 | The guide clearly calls for a real phone and the camera. | Unverified on the desktop browser. The attachment restriction also affected the file-based upload steps. |

**Usability 4/5 for the layout tested.** Stack recent uploads into mobile cards so filename, type, and status are visible together. The camera, upload, and OCR flow still needs a real-phone run before rating that workflow.

## Test changes and follow-up

The June 2 service type, Harbor’s secondary-EOB expectation, and Jordan’s cash-deductible setting were restored to their starting values. The guided test left a synthetic Hillcrest dispute open, accepted Riverside’s corrected EOB, cancelled Summit’s planned visit, created the Test Clinic estimate, and marked the Northgate finding wrong with reason “testing.” The appeal draft was generated for inspection only.

The most urgent issues are the raw **Forbidden** result from the household switch and the access-log entries exposed in the browser title. The next highest-impact usability changes are to expose EOB line items without a bill, sharpen the result labels on discrepancies, and generate a clean insurer-facing appeal draft.
