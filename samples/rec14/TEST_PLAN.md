# REC-14 test plan

Tests [REC-14](../../docs/My%20Health%20Spend%20(MHS)%20Product%20Requirements.md) and [ADR-045](../../docs/DECISIONS.md) on the running app: repeat services are compared across visits and changes are flagged as "worth a closer look". The case numbers are from [docs/TEST_PLAN.md](../../docs/TEST_PLAN.md). All the data is made up.

## How to run it

```bash
uv run tools/run_rec14_check.py
```

It creates a new household in the running stack, imports `rec14-ingest.json` on the Import page, uploads PDFs as a member would, and reads what each page shows. It compares that with `rec14-expected.json` and writes `harness-output/rec14/`: `results.md`, screenshots and the login. It exits with 1 if anything differs. After changing the data, run `uv run tools/make_rec14_sample.py`.

## The data

52 visits and 101 documents for Riley Test and Sam Test. Each case has its own provider, so its visits can't affect another case. Every visit has an EOB with line detail and is paid in full unless the case says otherwise, so a visit should stay Complete with nothing at issue even when flagged. Plans have a $10,000.00 deductible unless the case says otherwise.

## Pass criteria for every visit

- Exactly the flags listed below, with the listed amounts and wording. Every other visit in the case has none.
- The status and dollars at issue don't change: flagged visits are Complete with nothing at issue.
- The Visits row counts the flags, and the "Worth a closer look" filter lists only flagged visits.

## Cases

"→" is the next visit in the series. Amounts are per line.

| Case | Provider | Data | Expected |
| --- | --- | --- | --- |
| Control | Control Clinic | Allowed $400.00 on 3 visits | No flags |
| TC-REC-14-1 | Case One Infusion | Allowed $400.00 → $250.00; deductible not met | "Allowed amount changed" on the second visit, naming both dates, both amounts and $150.00, "Worth a closer look" and the common reasons |
| TC-REC-14-2 | Case Two Practice | Billed $150.00 → $150.10; allowed unchanged | "Billed amount changed", $0.10 |
| TC-REC-14-3 | Case Three Infusion | Allowed $400.00 twice; share $400.00 → $80.00; no deductible on the second | No flag; a note that the deductible explains it |
| TC-REC-14-4 | Case Four Infusion | Allowed $400.00 twice; share $400.00 → $250.00; deductible not met | "Your share changed", $150.00 |
| TC-REC-14-5 | Case Five Person, Group One and Two, Plan, Year | Allowed $400.00 → $250.00, for another person, another provider group, another plan, and in the next plan year | No flag in any of the four |
| TC-REC-14-6 | Case Six Units, Modifier | 2 units for $200.00 → 1 unit for $100.00; 99214 → 99214-25 at a lower price | No flag: the same price per unit; a different modifier isn't compared |
| TC-REC-14-7 | Case Seven Series, Short | Four visits with A and B, then A, B and C; separately, two visits and then A, B and C | "Codes changed in a series" naming C on the fifth visit; no flag with only two earlier visits |
| TC-REC-14-8 | Case Eight Totals, Unconfirmed | Claims with no line detail; a PDF EOB at a lower price, read but not confirmed | No flag, and the unconfirmed upload makes no visit |
| TC-REC-14-9 | Case Nine Infusion | Allowed $400.00 twice, then $250.00 three times; close the flag as "It was wrong"; import again | One flag, on the first $250.00 visit; it stays closed after the import and counts on Finding accuracy |
| TC-REC-14-10 | Case One Infusion | Open the flagged visit at 375px and 1280px | Both visits in words, the common reasons and the next step; a link to the earlier visit; no sideways scroll or browser errors |

**Beyond the listed cases:** rules in ADR-045 and how documents really arrive.

| Case | Provider | Data | Expected |
| --- | --- | --- | --- |
| Tolerance | Extra Tolerance | Share $400.00 → $399.50 | No flag: the share keeps the $1.00 tolerance |
| Both change | Extra Both | Allowed $400.00 → $250.00 and billed $500.00 → $600.00 | Two flags |
| Back again | Extra Back | Allowed $400.00 → $250.00 → $400.00 | One flag on each change |
| Denied claim | Extra Denied | A denied claim at $0.00 allowed | No flag |
| Deductible reached | Extra Deductible | $500.00 deductible, reached during the second visit | No flag; a note that the deductible explains it |
| Statement lines | Extra Statements | Imported statements with no EOB: billed $400.00 → $250.00 | "Billed amount changed", $150.00 |
| Uploaded EOBs | Upload Eob Clinic | Two PDF EOBs uploaded and confirmed as read: allowed $400.00 → $250.00 | "Allowed amount changed" on the second visit |
| Uploaded statements | Upload Statement Clinic | Two PDF statements uploaded and confirmed as read: charges $400.00 → $250.00 | "Billed amount changed" on the second visit |

## Results, 2026-11-06

Run on `main` at `477e48a`, on a separate stack so other work couldn't disturb it. I also made the expectations wrong on purpose and the checker caught each one, then viewed the flagged visit and the filtered Visits page at both widths.

**All of TC-REC-14-1 to 10 pass, and so do seven of the eight further cases. Uploaded statements fail.**

| Case | Result |
| --- | --- |
| Control | Pass |
| TC-REC-14-1 changed allowed amount | Pass |
| TC-REC-14-2 ten-cent billed change | Pass |
| TC-REC-14-3 the deductible explains it | Pass |
| TC-REC-14-4 changed share | Pass |
| TC-REC-14-5 person, group, plan, year | Pass, all four |
| TC-REC-14-6 units, modifier | Pass, both |
| TC-REC-14-7 series, too short | Pass, both |
| TC-REC-14-8 no lines, unconfirmed | Pass, both |
| TC-REC-14-9 one flag, stays closed, Finding accuracy | Pass |
| TC-REC-14-10 at 375px and 1280px | Pass, both |
| Worth a closer look filter | Pass |
| Tolerance, both change, back again, denied claim, deductible reached | Pass |
| Statement lines, imported | Pass |
| Uploaded EOBs | Pass |
| **Uploaded statements** | **Fail** |

## Problems found

1. **Uploaded statements are never compared (the failure above).** A visit created from an uploaded statement has no plan, because `web/household/intake.py` doesn't pass one to `visit_for`, and REC-14 only compares visits on the same plan. So a changed billed amount on uploaded statements isn't flagged until an EOB adds the plan. The imported statements pass because their visits name a plan.
2. **A table heading can become the provider.** The letterhead "Upload Statement Clinic" was treated as an identifier and hidden, and `_provider` in `ingest/extract.py` then took the next line it could use: the heading row. It filed the statement under a provider called "Date Code Description Charges Insurance Adjustments Payments Balance", so statements from different clinics could land under one false provider. "Riverbend Orthopedics" in the same layout read correctly. Nothing warned the member, though they would see it when reviewing.
3. **The Release 1 top navigation now wraps at 1280px.** Adding Charges pushes the nav and the app's name to two lines when signed in. It's cosmetic, and came with UX-11.
4. **"No open findings" appears directly above a flag** on a flagged visit. That is accurate, since a flag isn't a finding (ADR-045), but it reads oddly next to a question mark under "What's wrong".

## Not covered

- Flags from real documents: this data and the upload cases are made up, and in simple layouts.
- Claims from an insurer's export have no line detail, so REC-14 can't compare them. That is by design (ADR-045).
- Family-wide EOBs can't be read yet, so their claims aren't compared.
