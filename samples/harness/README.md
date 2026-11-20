# Test harness data

Made-up data for `tools/run_harness.py`, which runs it through the real app and reports what the app concluded. Nothing here is about a real person; the provider names are only names.

```bash
uv run tools/run_harness.py
```

The results go to `harness-output/` (git-ignored, because the report holds passwords): `results.png` is a screenshot of the results, `report.html` has every table, the logins and the page screenshots. The stack stays running at http://127.0.0.1:3063. Get a harness member's password and current 6-digit sign-in code with:

```bash
uv run tools/run_harness.py login <email>
```

Each run makes six new households; `docker compose --profile test down -v` wipes them, with everything else in the local stack.

## What's here

| File or folder | What it is | How the harness uses it |
| --- | --- | --- |
| `healthcare_billing_eob_hsa_reconciliation_v3.csv` | **The source of truth:** 52 records, two families, and the expected answers | Split per family, converted to a claims export and an HSA export, uploaded; its status columns are the expected results |
| `pdfs/` | 47 PDFs generated from the CSV: the 43 invoices, 2 EOBs and 2 HSA statements its last three columns name | Uploaded one by one and confirmed exactly as extracted; nothing is filled in for a field the app couldn't read |
| `original-pdfs/` | The nine earlier Truman PDFs, unchanged, and [their comparison with the CSV](original-pdfs/PDF_VS_CSV.md) | Not used: they're different data |

Each family runs three ways, in separate households. From the CSV, each visit is compared with the CSV's amounts and status. From the PDFs, each invoice should make one visit at the amount due it prints, since the app can't yet read a family-wide EOB or HSA payments from a PDF. Invoices and exports together, as a member would use the app, the invoices' visits should join the claims and payments, and each visit is compared with the CSV's amounts and status. After changing the CSV, regenerate the PDFs:

```bash
uv run tools/make_harness_pdfs.py
```

The PDFs are plain text documents, not styled like real ones. Details the CSV doesn't hold are derived and always come out the same: the statement date (3 days after adjudication), the due date (30 days later), and account and member numbers. Invoices use the column order the app reads (charges, insurance, adjustments, payments, balance). A statement shows a payment only if it was made outside the HSA, or from the HSA by the statement date. To test catching errors, put them in the CSV or an answer key; don't edit a PDF.

## The CSV's fields

The Trumans have 19 records and the Hendersons 33. There are 28 columns.

| # | Field | Type | Description and example |
| --- | --- | --- | --- |
| 1 | Family | Text | Cohort (The Trumans, The Hendersons) |
| 2 | Member_Name | Text | Patient (Mark Truman, James Henderson) |
| 3 | Member_Age | Integer | 46, 44, 17, 14, 12 for the Trumans; 48, 47, 16, 15, 13 for the Hendersons |
| 4 | Member_Relationship | Text | Primary Subscriber, Spouse, Dependent Child |
| 5 | Date_of_Service | Date (ISO) | YYYY-MM-DD |
| 6 | Provider_Name | Text | Billing practitioner or entity (Dr. Robert Vance, MD; Summit Orthopedic Group) |
| 7 | Provider_Specialty | Text | Internal Medicine, Ambulatory Surgery Facility |
| 8 | Facility_Name | Text | Oakridge Medical Associates, St. Jude Hospital |
| 9 | CPT_HCPCS_Code | Text | 99396, 29881, L1005 |
| 10 | Service_Description | Text | The procedure, in words |
| 11 | Billed_Charge | Currency | The provider's undiscounted list price |
| 12 | Negotiated_Allowed_Amount | Currency | The in-network amount the payer allows |
| 13 | Insurance_Paid_Amount | Currency | What the insurer paid |
| 14 | Member_Deductible | Currency | Applied to the deductible |
| 15 | Member_Copay | Currency | Fixed copayment, if any |
| 16 | Member_Coinsurance | Currency | Cost share after the deductible, in dollars |
| 17 | Total_Member_Responsibility | Currency | Deductible + copay + coinsurance |
| 18 | EOB_Claim_Number | Text | EOB-TRU-1001, EOB-HEN-2003 |
| 19 | EOB_Adjudication_Date | Date (ISO) | When the claim was adjudicated |
| 20 | HSA_Transaction_ID | Text | HSA-TRU-9002, or empty if unlinked |
| 21 | HSA_Payment_Date | Date (ISO) | When the debit cleared |
| 22 | HSA_Amount_Paid | Currency | Paid from the HSA |
| 23 | HSA_Disbursement_Status | Text | Settled via HSA, Split Payment, Covered 100% by Plan, Direct Personal CC |
| 24 | Reconciliation_Match_Status | Text | The expected result: Fully Reconciled, Matched (Zero Owed), Partially Reconciled / Multi-Tranche, Timing / Adjudication Mismatch, Unreconciled / Out-of-Pocket Direct |
| 25 | Audit_Realism_Notes | Text | Why a split, lag or out-of-pocket payment happened |
| 26 | Provider_Invoice_Asset_PDF | Text | Named invoice (invoice_immediatecare_sarah_truman.pdf) |
| 27 | Insurance_EOB_Asset_PDF | Text | Named EOB (eob_aegis_health_the_trumans.pdf) |
| 28 | HSA_Statement_Asset_PDF | Text | Named HSA statement (hsa_equihealth_statement_the_trumans.pdf) |

## How the CSV becomes uploads

The master isn't a layout any insurer exports, so `tools/run_harness.py` converts it, and those choices affect the results:

- Rows are added up per claim, provider, date and person, since the app keeps one record per claim. A claim number used by two providers gets a `-2` on the second.
- A row that bills and allows $0.00 is treated as a later payment on a charge already counted, not a new charge.
- The CSV's words become the app's nine statuses through `EXPECTED_STATUS` in the tool. That mapping is the harness's interpretation; change it there if you read a status differently.
- The plan isn't in the CSV. The Trumans get the $6,400 family deductible their EOB prints, the Hendersons the $4,000 in a note on David's claim.

## Notes on this data

These print at the top of the report (`DATA_NOTES` in the tool): St. Jude's repeated $556.00, Maya Truman's dates that can be later than the run date, and why only the visit and amount owed are compared for the PDF households.
