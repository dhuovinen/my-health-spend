# The original PDFs compared with the CSV

These nine PDFs were replaced by PDFs generated from the CSV (`../pdfs/`) because of what this comparison found. Each PDF was read in full and compared, field by field, with `../healthcare_billing_eob_hsa_reconciliation_v3.csv`. Because claim numbers don't line up, rows are paired by event: the same person having the same kind of care.

**Result: no PDF fully agrees with the CSV, and no service date agrees anywhere.** They tell the same story about the same five Trumans, but they aren't the same records. Who owes what mostly holds; dates, provider names, billed amounts and claim numbers don't. The PDFs cover only the Trumans.

## Scores

| PDF | Fields that agree | Main differences |
| --- | --- | --- |
| ImmediateCare invoice | 8 of 12 | Date, provider name, code, HSA date |
| ClearSkin invoice | 7 of 12 | Date, provider name, billed, claim number, HSA date |
| Pediatric Associates invoice | 7 of 12 | Date, a different practice, billed, claim numbers, HSA date |
| SmileCraft invoice | 5 of 12 | Date, dentist, an extra code, all amounts but the $0.00 owed, claim number. Three of the five are "no HSA payment" |
| Apex Vision invoice | 4 of 12 | Date, provider name, code, three amounts, claim number, HSA date |
| Summit Orthopedics invoice | 4 of 12 | Date, a different practice, $70.00 less owed, claim numbers, HSA date and amount |
| Consolidated invoices | Same as the four standalone invoices it repeats | See below |
| EOB | 14 readable rows: person 14, code 12, owed 10, allowed 4, billed 1, date 0 | One row is cut off; 8 claim numbers belong to other events in the CSV |
| HSA statement | 5 payments: ID 5, amount 4, date 0 | Total $739.00, against $809.00 in the CSV |

The 12 fields are person, service date, provider, codes, billed, allowed, plan paid, you owe, claim number, HSA ID, HSA date and HSA amount. Only the Apex invoice prints its HSA details, so the other invoices' HSA fields come from the HSA statement.

## What does agree

Apart from the Summit and Tri-County ankle visit, the total owed matches on every visit that appears in both. That visit explains the whole difference in the totals:

| | PDFs | CSV | Difference |
| --- | --- | --- | --- |
| Family owes | $804.00 (adding the EOB's rows) | $874.00 | $70.00 |
| Paid from the HSA | $739.00 | $809.00 | $70.00 |
| Paid outside the HSA | $65.00 splint, personal Visa | $65.00 splint, personal Amex | Card only |

The five HSA transaction IDs, the $65.00 gap, and the people and their ages also agree.

## Invoices

| | Apex Vision | ClearSkin | ImmediateCare | Pediatric Associates | SmileCraft | Summit |
| --- | --- | --- | --- | --- | --- | --- |
| **Person** | Mark | Lucas | Sarah | Maya | Mark | Chloe |
| **Date, PDF** | 02/10 | 05/02 | 03/11 | 05/19 | 03/04 | 04/14 |
| Date, CSV | 05-18 | 08-18 | 07-22 | 11-04 | 04-14 | 09-28 |
| **Provider, PDF** | Apex Vision Institute, Dr. Raymond Vance | ClearSkin Pediatric Dermatology, Dr. Aris Thorne | ImmediateCare Urgent Care, Dr. Thomas Bell | Pediatric Associates of Oakridge, Dr. Angela Brooks | SmileCraft Family Dental, Dr. Elena Cruz | Summit Orthopedics & Sports Medicine, Dr. Brian Vance |
| Provider, CSV | Apex Eye Care LLC, at Apex Vision Institute | ClearSkin Dermatology Group, at ClearSkin Specialty Clinic | ImmediateCare Walk-In, at ImmediateCare Metro East | Dr. Timothy Sterling and Lakeside Pediatric Lab, at Lakeside Pediatric Associates | Drs. Miller & Chen DDS, at SmileCraft Dental Center | Tri-County Orthopedics, at Tri-County Surgi & Sports Clinic |
| **Codes, PDF** | 92015 | 99203 | 99214 | 99213, 87880 | D0120, D1110, D0272 | 99213, 73610, L4396 |
| Codes, CSV | 92014 | 99203 | 99203 | 99213, 87880 | D0120, D1110 | 99213, 73610, L4396 |
| **Billed, PDF** | $165.00 | $290.00 | $245.00 | $200.00 | $210.00 | $455.00 |
| Billed, CSV | $195.00 | $310.00 | $245.00 | $285.00 | $195.00 | $610.00 |
| **Allowed, PDF** | $85.00 | $195.00 | $160.00 | $169.00 | $145.00 | $270.00 |
| Allowed, CSV | $120.00 | $195.00 | $160.00 | $169.00 | $130.00 | $340.00 |
| **Plan paid, PDF** | $75.00 | $0.00 | $0.00 | $0.00 | $145.00 | $0.00 |
| Plan paid, CSV | $110.00 | $0.00 | $0.00 | $0.00 | $130.00 | $0.00 |
| **You owe, PDF** | $10.00 | $195.00 | $160.00 | $169.00 | $0.00 | $270.00 |
| You owe, CSV | $10.00 | $195.00 | $160.00 | $169.00 | $0.00 | $340.00 |
| **Claim, PDF** | 1003 | 1013 | 1007 | 1015, 1016 | 1004 | 1009, 1010, 1011 |
| Claim, CSV | 1004 | 1012 | 1007 | 1014 | 1003 | 1010 |
| **HSA ID** (same in both) | 9001 | 9004 | 9002 | 9005 | none | 9003 |
| **HSA date, PDF** | 02/27 | 05/22 | 04/03 | 06/11 | none | 05/06 |
| HSA date, CSV | 06-12 | 09-15 | 08-14 | 11-28 | none | 10-25 |
| **HSA amount, PDF** | $10.00 | $195.00 | $160.00 | $169.00 | none | $205.00 |
| HSA amount, CSV | $10.00 | $195.00 | $160.00 | $169.00 | none | $275.00 |

Pediatric Associates' $169.00 only agrees in total: the visit and test are $115.00 and $54.00 in the PDF, $145.00 and $24.00 in the CSV. SmileCraft and Apex have swapped claim numbers: 1003 and 1004 are one way round in the PDFs and the other in the CSV.

## Consolidated invoices

`Truman Family Healthcare Provider Patient Invoices.pdf` holds four statements in one file: ImmediateCare, Summit, ClearSkin and Pediatric Associates. Its amounts match the standalone invoices, so it compares with the CSV the same way. It also disagrees with the standalone invoices in small ways:

- ClearSkin is due 06/05 here and 06/18 standalone, and has no statement date here.
- The $65.00 Summit splint is called a "copay" here and a DME charge standalone.
- Some service descriptions and header details differ.

## EOB

| Event | PDF: date, provider, billed / allowed / paid / owed, claim | CSV: the same | Owed agrees |
| --- | --- | --- | --- |
| Mark, preventive | 01/15, Dr. Mehta, 285 / 190 / 190 / 0, 1001 | 02-10, Dr. Vance, 320 / 185 / 185 / 0, 1001 | Yes |
| Mark, lipid panel | 01/15, Pine Valley Lab, 95 / 38 / 38 / 0, 1002 | 02-10, Quest, 115 / 38.50 / 38.50 / 0, 1002 | Yes |
| Mark, vision | 02/10, Apex, 165 / 85 / 75 / 10, 1003 | 05-18, Apex Eye Care, 195 / 120 / 110 / 10, 1004 | Yes |
| Sarah, preventive | 01/22, Dr. Mehta, 285 / 190 / 190 / 0, 1005 | 03-05, Dr. Price, 320 / 185 / 185 / 0, 1005 | Yes |
| Sarah, metabolic panel | 01/22, Pine Valley Lab, 110 / 42 / 42 / 0, 1006 | 03-05, Quest, 130 / 42 / 42 / 0, 1006 | Yes |
| Sarah, urgent care | 03/11, ImmediateCare, 245 / 160 / 0 / 160, 1007 | 07-22, ImmediateCare, 245 / 160 / 0 / 160, 1007 | Yes |
| Chloe, well-child | 02/18, Pediatric Assoc, 260 / 175 / 175 / 0, 1008 | 06-10, Dr. Sterling, 290 / 170 / 170 / 0, 1009 | Yes |
| Chloe, ankle exam | 04/14, Summit, 185 / 130 / 0 / 130, 1009 | 09-28, Tri-County, 275 / 180 / 0 / 180, 1010 | **No** |
| Chloe, X-ray | 04/14, Summit, 150 / 75 / 0 / 75, 1010 | 09-28, Tri-County, 195 / 95 / 0 / 95, 1010 | **No** |
| Chloe, splint | 04/14, Summit, 120 / 65 / 0 / 65, 1011 | 09-28, Tri-County, 140 / 65 / 0 / 65, 1010 | Yes |
| Lucas, well-child | Cut off: only "02/18" shows at the foot of page 1 | 06-10, Dr. Sterling, 290 / 170 / 170 / 0, 1011 | Can't tell |
| Lucas, dermatology | 05/02, ClearSkin, 290 / 195 / 0 / 195, 1013 | 08-18, ClearSkin, 310 / 195 / 0 / 195, 1012 | Yes |
| Maya, well-child | 02/18, Pediatric Assoc, 260 / 175 / 175 / 0, 1014 | 06-10, Dr. Sterling, 290 / 170 / 170 / 0, 1013 | Yes |
| Maya, sick visit | 05/19, Pediatric Assoc, 140 / 115 / 0 / 115, 1015 | 11-04, Dr. Sterling, 220 / 145 / 0 / 145, 1014 | **No** |
| Maya, strep test | 05/19, Pediatric Assoc, 60 / 54 / 0 / 54, 1016 | 11-04, Lakeside Lab, 65 / 24 / 0 / 24, 1014 | **No** |
| Mark, Sarah and Maya, dental | Not on the EOB | Claims 1003, 1008, 1015 | |

The EOB covers January to May and was issued June 8, so 11 of the CSV's 19 Truman rows have service dates after its period.

**The EOB's printed totals are wrong, even allowing for the missing row:**

| | Billed | Allowed | Plan paid | Deductible | You owe |
| --- | --- | --- | --- | --- | --- |
| Printed total | $2,765.00 | $1,729.00 | $975.00 | $744.00 | $754.00 |
| The 14 readable rows | $2,650.00 | $1,689.00 | $885.00 | $794.00 | $804.00 |
| Printed minus rows | +$115.00 | +$40.00 | +$90.00 | −$50.00 | −$50.00 |

The missing row can't explain this: it would have to add $90.00 of plan payment on only $40.00 allowed, and a negative amount owed. Each row does add up (allowed = plan paid + you owe). The $744.00 deductible used to date is wrong for the same reason.

## HSA statement

| ID | PDF: date, payee, amount, claim | CSV: the same |
| --- | --- | --- |
| 9001 | 02/27, Apex Vision Institute, $10.00, 1003 | 06-12, Apex Eye Care, $10.00, 1004 |
| 9002 | 04/03, ImmediateCare, $160.00, 1007 | 08-14, ImmediateCare Walk-In, $160.00, 1007 |
| 9003 | 05/06, Summit, **$205.00**, 1009 and 1010 | 10-25, Tri-County, **$275.00**, 1010 |
| 9004 | 05/22, ClearSkin, $195.00, 1013 | 09-15, ClearSkin, $195.00, 1012 |
| 9005 | 06/11, Pediatric Assoc, $169.00, 1015 and 1016 | 11-28, Lakeside (two providers), $169.00, 1014 |

The statement covers January to June, so four of the CSV's five payments fall after it. Its balances work ($2,850.00 + $1,800.00 − $739.00 = $3,911.00), and the CSV has no balances or deposits to compare them with.

**Its gap calculation doesn't add up.** It says $754.00 owed − $739.00 paid = $65.00, which is really $15.00. The $65.00 is right only with the $804.00 the EOB's rows add up to. "91.4%" is also wrong: $739.00 of $754.00 is 98.0%.

## Missing altogether

- **Hendersons:** no PDFs for any of their 33 rows.
- **File names:** none of the PDF names in the CSV's last three columns exist in this folder.
- **Trumans:** no document for Sarah's or Maya's dental visits, and no separate invoice for the preventive visits, labs or well-child visits.
