"""Write samples/tax-ingest.json: a made-up household for the HSA and tax features (TAX-01 to TAX-10, ADR-043).

The Example household: Robin (the HSA holder, born 1969, so the 55+ catch-up applies), Casey (spouse), Jamie (24,
a tax dependent in 2025 but not in 2026) and Max (14, a dependent both years). The HSA opened on 2025-03-01; Robin had
self-only HSA-eligible coverage in 2025 and in January to June 2026, then family coverage from July 2026. A
limited-purpose FSA covers 2026 dental and vision care. What the sample shows:

- a 2025 office visit paid by card before the HSA opened (not in the receipt vault), one after it ($120.00, in the
  vault), and a 2025 dental cleaning paid by card and reimbursed from the HSA in January 2026;
- 2026 HSA payments for an office visit, a lab test, vitamins (likely not qualified: TAX-07), and Jamie's urgent
  care (the HSA may not pay for a non-dependent adult child: TAX-09), plus an HSA pharmacy payment not matched to a
  visit;
- massage therapy paid by card (needs a letter of medical necessity), Max's eye exam and glasses paid by card (in
  the vault), a dental cleaning paid from the LPFSA, and two unpaid 2026 visits for the "which account pays" advice;
- 2025 and 2026 contributions: 2026 is $300.00 over the monthly pro rata limit ($7,575.00) and within the
  last-month rule's $9,750.00; two $1.00 paper-statement fees (B-17).

Every name, provider, amount and claim number is synthetic. Usage (the file is committed):

    uv run tools/make_tax_sample.py [--out samples/tax-ingest.json]
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MEMBERS = [
    {"id": "mem-robin", "name": "Robin Example", "relationship": "self", "birth_year": 1969},
    {"id": "mem-casey", "name": "Casey Example", "relationship": "spouse", "birth_year": 1971},
    {"id": "mem-jamie", "name": "Jamie Example", "relationship": "child", "birth_year": 2002,
     "tax_dependent": {"2025": True, "2026": False}},
    {"id": "mem-max", "name": "Max Example", "relationship": "child", "birth_year": 2012,
     "tax_dependent": {"2025": True, "2026": True}},
]
EVERYONE = [m["id"] for m in MEMBERS]
PLANS = [
    {"id": "plan-2025", "plan_year": 2025, "insurer": "Example Health", "plan_name": "HDHP Self", "coverage_order": "primary",
     "coverage_start": "2025-01-01", "coverage_end": "2025-12-31", "hsa_eligible_plan": True, "member_ids": ["mem-robin"],
     "limits": []},
    {"id": "plan-2026-self", "plan_year": 2026, "insurer": "Example Health", "plan_name": "HDHP Self",
     "coverage_start": "2026-01-01", "coverage_end": "2026-06-30", "hsa_eligible_plan": True, "member_ids": ["mem-robin"],
     "limits": []},
    {"id": "plan-2026-family", "plan_year": 2026, "insurer": "Example Health", "plan_name": "HDHP Family",
     "coverage_order": "primary", "coverage_start": "2026-07-01", "coverage_end": "2026-12-31", "hsa_eligible_plan": True,
     "member_ids": EVERYONE, "limits": []},
]
ACCOUNTS = [
    {"id": "acct-hsa", "name": "HSA", "type": "hsa", "opened": "2025-03-01", "member_ids": ["mem-robin"]},
    {"id": "acct-card", "name": "Family Visa", "type": "credit_card"},
    {"id": "acct-lpfsa", "name": "Dental and vision FSA", "type": "lpfsa", "plan_year": 2026, "member_ids": EVERYONE,
     "run_out_end": "2027-03-31", "balance": 300, "balance_as_of": "2026-10-01"},
]
PROVIDERS = [
    {"id": "prov-pcp", "name": "Example Family Practice", "kind": "physician_practice", "network_status": "in_network"},
    {"id": "prov-derm", "name": "Example Dermatology", "kind": "physician_practice", "network_status": "in_network"},
    {"id": "prov-lab", "name": "Example Lab Services", "kind": "lab", "network_status": "in_network"},
    {"id": "prov-urgent", "name": "Example Urgent Care", "kind": "physician_practice", "network_status": "in_network"},
    {"id": "prov-dental", "name": "Example Dental Group", "kind": "physician_practice", "network_status": "not_applicable"},
    {"id": "prov-eye", "name": "Example Eye Care", "kind": "retailer", "network_status": "not_applicable"},
    {"id": "prov-massage", "name": "Example Massage Studio", "kind": "other", "network_status": "not_applicable"},
    {"id": "prov-vitamins", "name": "Example Health Foods", "kind": "retailer", "network_status": "not_applicable"},
    {"id": "prov-pharmacy", "name": "Example Pharmacy", "kind": "pharmacy", "network_status": "in_network"},
]

# id, date, provider, member, plan, category, description, how it is billed, amount owed
VISITS = [
    ("v-2025-02-10-pcp", "2025-02-10", "prov-pcp", "mem-robin", "plan-2025", "provider_visit", "Office visit, before the HSA opened", "eob", 90),
    ("v-2025-05-14-derm", "2025-05-14", "prov-derm", "mem-robin", "plan-2025", "provider_visit", "Dermatology office visit", "eob", 120),
    ("v-2025-09-03-dental", "2025-09-03", "prov-dental", "mem-max", None, "service", "Dental cleaning", "bill", 80),
    ("v-2026-01-20-pcp", "2026-01-20", "prov-pcp", "mem-robin", "plan-2026-self", "provider_visit", "Office visit copay and deductible", "eob", 150),
    ("v-2026-03-05-lab", "2026-03-05", "prov-lab", "mem-robin", "plan-2026-self", "provider_visit", "Blood work", "eob", 60),
    ("v-2026-04-11-vitamins", "2026-04-11", "prov-vitamins", "mem-robin", None, "supplements", "Vitamins", "receipt", 35),
    ("v-2026-05-02-massage", "2026-05-02", "prov-massage", "mem-casey", None, "service", "Massage therapy, 60 minutes", "bill", 90),
    ("v-2026-07-08-dental", "2026-07-08", "prov-dental", "mem-robin", None, "service", "Dental cleaning", "bill", 60),
    ("v-2026-08-12-urgent", "2026-08-12", "prov-urgent", "mem-jamie", "plan-2026-family", "provider_visit", "Urgent care office visit", "eob", 125),
    ("v-2026-08-20-eye", "2026-08-20", "prov-eye", "mem-max", None, "equipment", "Eye exam and eyeglasses", "receipt", 210),
    ("v-2026-09-15-dental", "2026-09-15", "prov-dental", "mem-casey", None, "service", "Dental filling", "bill", 180),
    ("v-2026-10-02-pcp", "2026-10-02", "prov-pcp", "mem-casey", "plan-2026-family", "provider_visit", "Office visit", "eob", 95),
]
# payment id, date, provider, account, amount
PAYMENTS = [
    ("pay-2025-02-20-pcp", "2025-02-20", "prov-pcp", "acct-card", 90),
    ("pay-2025-05-30-derm", "2025-05-30", "prov-derm", "acct-card", 120),
    ("pay-2025-09-03-dental", "2025-09-03", "prov-dental", "acct-card", 80),
    ("pay-2026-02-05-pcp", "2026-02-05", "prov-pcp", "acct-hsa", 150),
    ("pay-2026-03-20-lab", "2026-03-20", "prov-lab", "acct-hsa", 60),
    ("pay-2026-04-11-vitamins", "2026-04-11", "prov-vitamins", "acct-hsa", 35),
    ("pay-2026-05-02-massage", "2026-05-02", "prov-massage", "acct-card", 90),
    ("pay-2026-06-30-pharmacy", "2026-06-30", "prov-pharmacy", "acct-hsa", 24),
    ("pay-2026-07-08-dental", "2026-07-08", "prov-dental", "acct-lpfsa", 60),
    ("pay-2026-08-25-urgent", "2026-08-25", "prov-urgent", "acct-hsa", 125),
    ("pay-2026-08-20-eye", "2026-08-20", "prov-eye", "acct-card", 210),
]


def documents() -> list[dict]:
    docs = []
    for vid, when, provider, member, plan, category, description, kind, owed in VISITS:
        later = f"{when[:8]}{min(int(when[8:]) + 7, 28):02d}"
        if kind == "eob":
            docs.append({"id": f"eob-{vid[2:]}", "type": "eob", "date": later, "plan_id": plan, "provider_id": provider,
                         "visit_id": vid, "claim_number": f"EXT{vid[2:12].replace('-', '')}{vid[-3:].upper()}",
                         "claim_status": "processed", "network_status": "in_network", "billed": owed * 2,
                         "allowed": owed, "adjustment": owed, "insurer_paid": 0, "deductible": owed,
                         "patient_responsibility": owed})
        elif kind == "bill":
            docs.append({"id": f"bill-{vid[2:]}", "type": "provider_bill", "date": when, "provider_id": provider,
                         "balance_due": owed, "lines": [{"visit_id": vid, "description": description,
                                                         "billed_charge": owed, "patient_amount": owed}]})
        else:
            item = "Vitamin D3 2000 IU, 120 ct" if category == "supplements" else description
            docs.append({"id": f"rcpt-{vid[2:]}", "type": "receipt", "date": when, "provider_id": provider,
                         "visit_id": vid, "total": owed, "items": [{"description": item, "quantity": 1, "amount": owed}]})
    for pid, when, provider, account, amount in PAYMENTS:
        docs.append({"id": pid, "type": "payment", "date": when, "kind": "payment", "provider_id": provider,
                     "account_id": account, "amount": amount})
    docs.append({"id": "reimb-2026-01-15-dental", "type": "account_reimbursement", "date": "2026-01-15",
                 "from_account_id": "acct-hsa", "amount": 80, "payment_ids": ["pay-2025-09-03-dental"]})

    def contribution(when, kind, amount, tax_year=None):
        doc = {"id": f"hsa-{when}-{kind.split('_')[1]}", "type": "account_transaction", "date": when,
               "account_id": "acct-hsa", "kind": kind, "amount": amount,
               "description": f"{'Employer' if kind.endswith('employer') else 'Payroll'} contribution"}
        if tax_year:
            doc["tax_year"] = tax_year
            doc["description"] += f", Tax year: {tax_year}"
        return doc

    for month in range(3, 13):  # 2025: $360 a month from March, $500 from the employer
        docs.append(contribution(f"2025-{month:02d}-15", "contribution_employee", 360))
    docs.append(contribution("2025-03-15", "contribution_employer", 500))
    docs.append(contribution("2026-03-31", "contribution_employee", 300, tax_year=2025))
    for month in range(1, 11):  # 2026: $687.50 a month, $1,000 from the employer
        docs.append(contribution(f"2026-{month:02d}-15", "contribution_employee", 687.5))
    docs.append(contribution("2026-01-15", "contribution_employer", 1000))
    for month in (8, 9):  # B-17: a paper-statement fee
        docs.append({"id": f"hsa-2026-{month:02d}-28-fee", "type": "account_transaction", "date": f"2026-{month:02d}-28",
                     "account_id": "acct-hsa", "kind": "fee", "amount": 1, "description": "Paper statement fee"})
    return docs


def sample() -> dict:
    visits = []
    for vid, when, provider, member, plan, category, description, kind, owed in VISITS:
        v = {"id": vid, "date": when, "provider_id": provider, "member_id": member, "category": category,
             "description": description}
        if plan:
            v["plan_id"] = plan
        if kind == "bill":
            v["payment_path"] = "self_pay"
        visits.append(v)
    return {
        "schema_version": "0.1",
        "source": {"prepared_by": "tools/make_tax_sample.py", "prepared_on": "2026-10-18",
                   "notes": "Made-up household for the HSA and tax features (ADR-043). Every name, provider, amount "
                            "and claim number is invented."},
        "plans": PLANS, "accounts": ACCOUNTS, "members": MEMBERS, "providers": PROVIDERS, "visits": visits,
        "documents": documents(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "samples" / "tax-ingest.json")
    args = ap.parse_args()
    args.out.write_text(json.dumps(sample(), indent=1) + "\n")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
