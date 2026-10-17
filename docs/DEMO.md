# Demo: Release 1 on a laptop

A ten-minute walkthrough of My Health Spend on the local Docker Compose stack, with made-up documents in [`samples/demo/`](../samples/demo/). Every name, number and address in them is synthetic; never demo with the real `data/` folder.

## The story

Jordan Sample saw **Riverbend Orthopedics** on 14 August 2026 for a knee: an office visit and an X-ray, $480.00 in charges. The statement came first, on 10 September, and asked for the full **$480.00**; Jordan paid it with the HSA card on 15 September. Then the insurer's EOB arrived: the in-network discount was $180.00, the allowed amount $300.00, all of it deductible, so Jordan owed **$300.00**. The bill ignored the network discount, and $180.00 was overpaid. Separately, Jordan photographed the EOB for an MRI at **Lakeside Imaging** (22 September) with a phone: $800.00 owed, not billed yet.

| File | What it is | What the app does with it |
| --- | --- | --- |
| `1-riverbend-statement.pdf` | Provider statement, $480.00 due | Reads it, asks Jordan to check and confirm; makes the visit and the bill |
| `2-riverbend-eob.pdf` | EOB, "THIS IS NOT A BILL", you owe $300.00 | Knows it's an EOB, matches it to the visit by score; the visit turns to **Discrepancy found** (a missed adjustment) |
| `3-lakeside-eob-photo.png` | Phone photo of the MRI EOB, you owe $800.00 | Reads the photo with Tesseract OCR; a new visit, **Balance outstanding** |
| `4-hsa-transactions.csv` | HSA administrator's export: contributions and the $480.00 card payment | Imports the payment against Riverbend; contributions go to the HSA account |

`uv run tools/make_demo_pack.py` rewrites the pack from the text in that script (and `tests/pdfs.py`); `tests/test_r1_demo.py::test_demo_story` runs the whole story through the upload pipeline.

## Before the demo (once, about 5 minutes)

You need Docker Desktop running, port 3063 free, and an authenticator app on your phone (Google Authenticator, Microsoft Authenticator, 1Password and the like).

```bash
docker compose up --build -d
```

The first build takes a few minutes (Tesseract and the spaCy model). If it hangs on `docker-credential-desktop`, see CLAUDE.md "Gotchas". Then create the demo household:

```bash
docker compose exec app mhs-admin demo-setup
```

It creates the household "Sample household" and the member `demo@example.com` (Jordan Sample), and fills in Settings the way a member would before uploading: Jordan as a household member, the 2026 plan (Example Health, HDHP with a $1,700 deductible and 20% coinsurance) and the HSA account. It prints, once:

```text
Sign in at http://127.0.0.1:3063
  email:    demo@example.com
  password: <generated>
Add this to an authenticator app (shown once):
  QR code: http://127.0.0.1:3063/enrol/<token>
           (opens once, within 15 minutes; or type the secret below into the app)
  secret:  <base32 secret>
```

Open the **QR code** link, click **Show my QR code** and scan it with the phone. The page shows the code once and the link stops working; if it expired or was used, run `demo-setup` again. Keep the password and the phone at hand.

Running `demo-setup` again is safe: it reuses the household and member, gives a new password and authenticator code (the old ones stop working), and puts the Settings records back as they started. Documents already uploaded stay; to start the story from an empty household, see [Reset](#reset).

## Walkthrough

Use a desktop browser window about 1280 px wide. Each step says what to point at. Checked end to end on the compose stack on 2026-10-16, at 1280 px and at 375 px; the reconciliation steps (4, 6 to 9) updated for phase 1.4 on 2026-10-17 and covered by `test_demo_story`.

1. **Sign in.** http://127.0.0.1:3063: email and password, then the 6-digit code from the phone. *Point at:* nothing of the household is shown until the code is accepted (MFA, PRV-11); sessions end after 15 idle minutes.
2. **An empty household.** Home says "No visits yet" (its button offers the ingest-file import; skip it, uploads are the Release 1 path). Open **Settings** (the gear). *Point at:* "Primary insurer Example Health, Example HDHP 1700, plan year 2026, covers Jordan Sample"; the $1,700.00 deductible and $5,000.00 out-of-pocket maximum; Jordan under household members; the HSA under payment accounts. This is all the setup a household does.
3. **Upload the statement.** **Uploads** → choose `samples/demo/1-riverbend-statement.pdf`, leave "Let the app decide", **Upload**. The row shows *Reading*, then a **Review** button a few seconds later; open it. *Point at:* "Read from the pdf text layer"; type Provider statement (99% sure); patient "(on the document: Jordan Sample)" already matched to the household member; amount due $480.00, statement date 2026-09-10; the two service lines (99214 office visit, 73562 knee X-ray); the provider name marked **check** at 50% because it came from the letterhead, not a label. *Privacy point:* the worker that read the document never saw the name, account number, phone or address, only tokens; the review page puts the real values back in the application tier ([below](#showing-what-the-worker-saw-optional)). **Confirm and add to my visits.** The visit opens: Riverbend Orthopedics, Aug 14, 2026, **Balance outstanding** $480.00, "Missing: EOB", and the finding "Claim filed with insurance: … the provider may not have filed with your insurance". The visit is more than 30 days old; within 30 days of a visit the app says **Awaiting EOB** instead and advises waiting for the insurer's decision before paying (REC-02).
4. **Upload the EOB.** `2-riverbend-eob.pdf`, then **Review**. *Point at:* recognised as an EOB ("THIS IS NOT A BILL" means it can never be taken for a bill); provider, patient, the 2026 plan and the Aug 14 visit are already chosen; billed $480.00, plan discount $180.00, allowed $300.00, deductible $300.00, you owe $300.00. The visit is preselected by its match score, "Matched automatically (100%): same provider, same date of service, same person, same billed amount $480.00" (MAT-05). **Confirm.** The visit is now **Discrepancy found**, with the plain explanation under the badge. *Point at:* "You owe per EOB $300.00" beside "Provider billed you $480.00", and the finding "✕ Bill matches EOB · **Missed adjustment**: Statement of 2026-09-10 asks $480.00, EOB says you owe $300.00. The statement doesn't apply the plan's $180.00 discount … — $180.00". Below it: "Where the billed amount went" (plan discount $180.00, deductible $300.00, billed $480.00), and "Bill lines and EOB lines": 99214 and 73562 each paired with the EOB's line (MAT-06). The document checklist shows the EOB and the bill received and payment proof expected.
5. **Upload the phone photo.** `3-lakeside-eob-photo.png` (a slightly turned, soft photo of a printed EOB), then **Review**. *Point at:* "Read from the photo, OCR (tesseract)": the text was read from the image in the application tier and scrubbed like the PDF; Lakeside Imaging, $1,850.00 billed, $800.00 yours, the MRI line. **Confirm.** The new visit is **Balance outstanding**: "$800.00 unpaid per insurer" and "Unpaid $800.00 — pay from HSA", known before Lakeside's bill arrives.
6. **Upload the HSA export.** `4-hsa-transactions.csv`. A table needs no review: it goes straight to **Check import**, "What will change: Documents 5 new" (the card payment and four account transactions). **Save import** ("Import saved."). *Point at,* on the Riverbend visit: "Payments applied": $300.00 and $180.00 "more than owed" from the Sep 15 HSA payment, and a second finding "✕ Paid matches what you owe · **Overpayment**: You paid $180.00 more than you owe for this visit … Ask Riverbend Orthopedics for a refund or a credit" (REC-03); "Where your share stands": you owe $300.00, paid $480.00, **credit due to you $180.00** (identity 3). The card payment found its provider from the merchant name on the export.
7. **Home.** *Point at:* "$ at stake $180.00, overpayments and bill/EOB mismatches"; visits by status, all nine listed, one Discrepancy found and one Balance outstanding; "$ at stake" counts the $180.00 once, though it shows as both the bill's excess and the overpayment; HSA "Unpaid — pay from HSA · 1 visit $800.00"; "Needs attention" with both visits; plan limits: Jordan's in-network deductible $1,100.00 of $1,700.00 and out-of-pocket $1,100.00 of $5,000.00, from the two EOBs; "Where 2026's billed dollars went" adds up both EOBs.
8. **Providers → Riverbend Orthopedics.** *Point at:* "You owe per insurer $300.00", "Paid in 2026 $480.00", difference -$180.00, the finding "Overpaid $180.00: a credit due to you", "Where your share stands with this provider" (credit due to you $180.00), and "Payments and how they're split", where a payment's split across visits can be changed by hand (ALC-04). That's the story: Jordan calls Riverbend with the EOB and asks for $180.00 back.
9. **Dispute and resolve** (optional). Back on the Riverbend visit, **Open a dispute** with a note ("Called billing, asked for a refund"): the visit is **In dispute**. When the refund comes, an imported refund clears the overpayment; or **Close the dispute** with "I accept it as it is": the visit is **Resolved**, and its findings show "Closed by you". Settings → **Reconciliation** sets how many days the app waits for an EOB (30 by default).
10. **Phone width** (optional). In the browser's device toolbar choose a 375 px wide phone and reload Home, a visit, Uploads and Settings: brand, help, settings and sign-out on one row and the five pages on the next; the figures two to a row; wide tables scroll inside their cards; nothing scrolls sideways (UX-10). The stack binds 127.0.0.1 only, so a real phone can't reach it.

### Showing what the worker saw (optional)

The scrubbed text queued for the worker, with tokens in place of identifiers:

```bash
docker compose exec postgres psql -U postgres -d mhs -c "SELECT payload->>'text' FROM app.jobs ORDER BY id LIMIT 1"
```

Compare it with the statement PDF: the street address, "Sample, Jordan", the account number and the phone number are `tok_…` tokens; dates, amounts, codes and the provider's name are not (PRV-01, PRV-04).

## Reset

To run the story again from an empty household, delete the stack's data and start over (this removes every volume of the local stack, synthetic data only):

```bash
docker compose --profile test down -v
```

Then `docker compose up -d` and `mhs-admin demo-setup` again, and remove the old "My Health Spend" entry from the authenticator app.

## If something goes wrong

| Symptom | Fix |
| --- | --- |
| "That code didn't work" | Use the current code (it changes every 30 seconds) and check the laptop's clock; each code works once. Five wrong tries lock the account for 15 minutes: `demo-setup` again unlocks it |
| The enrolment link says "used or has expired" | Run `demo-setup` again for a new link (15 minutes, one use) |
| An upload is refused as "already uploaded" | That file is in the household already; [reset](#reset) to start over |
| A document stays on *Reading* | `docker compose logs worker`; the worker must be running |
| The build hangs on `docker-credential-desktop` | CLAUDE.md "Gotchas" has the `DOCKER_CONFIG` workaround |
