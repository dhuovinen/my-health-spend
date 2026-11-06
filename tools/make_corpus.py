"""Generate the synthetic extraction corpus: PDFs with a text layer and a ground-truth JSON beside each.

    uv run python tools/make_corpus.py            # writes tests/corpus/ and tests/corpus-holdout/

At least 5 documents of each of the 8 ING-02 types (TEST_PLAN "Extraction corpus"), 56 in all, in several layouts
per type and with wording the layout rules weren't written against, so the accuracy run (PLT-02, TC-ING-02-1,
TC-ING-03-1) measures something. tests/corpus/ is the development set the rules were fixed against;
tests/corpus-holdout/ (55 more, other wording) was written once and is never used to tune them, so its result is
the honest PLT-02 figure. Seeded, so both are the same on every run. Every name, number and address
is made up.
"""

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.pdfs import make_pdf  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "tests" / "corpus"
RNG = random.Random(20261016)
PATIENTS = ["Pat Example", "Jordan Rivera", "Morgan Lee", "Casey Brooks", "Avery Chen", "Riley Novak", "Sam Ortiz"]
PROVIDERS = ["Riverbend Orthopedics", "Lakeside Family Medicine", "Bennett Radiology", "Northgate Dermatology",
             "Hillcrest Imaging Center", "Maple Street Pediatrics", "Summit Eye Associates", "Cedar Valley Labs"]
INSURERS = ["Example Health", "Bluewater Health Plan", "Granite Mutual"]
SERVICES = [("99213", "Office visit"), ("99214", "Office visit, extended"), ("73721", "MRI knee"),
            ("80053", "Metabolic panel"), ("11102", "Skin biopsy"), ("92014", "Eye exam"), ("71046", "Chest x-ray")]


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def day(d: date, style: str) -> str:
    return {"us": d.strftime("%m/%d/%Y"), "iso": d.isoformat(), "long": d.strftime("%b %-d, %Y")}[style]


def amounts() -> dict:
    billed = RNG.randrange(150, 2400) * 100 + RNG.choice([0, 50])
    allowed = int(billed * RNG.uniform(0.35, 0.8)) // 100 * 100
    share = RNG.choice([0, 2500, 3000, 4500, 6000, int(allowed * 0.2) // 100 * 100])
    share = min(share, allowed)
    return {"billed": billed, "adjustment": billed - allowed, "allowed": allowed, "insurer_paid": allowed - share,
            "patient_responsibility": share}


def eob(n: int, layout: str) -> tuple[str, dict]:
    patient, provider, insurer = RNG.choice(PATIENTS), RNG.choice(PROVIDERS), RNG.choice(INSURERS)
    dos = date(2026, 1, 5) + timedelta(days=RNG.randrange(0, 330))
    processed = dos + timedelta(days=RNG.randrange(10, 40))
    claim = f"{RNG.choice('ABCEHK')}{RNG.randrange(10**7, 10**8)}"
    a = amounts()
    code, service = RNG.choice(SERVICES)
    style = RNG.choice(["us", "us", "long"])
    member_id = f"W{RNG.randrange(10**8, 10**9)}"
    if layout == "labels":
        text = f"""{insurer}
EXPLANATION OF BENEFITS          THIS IS NOT A BILL
Patient: {patient}     Member ID: {member_id}
Provider: {provider}
Claim number: {claim}
Date of service: {day(dos, style)}
Date processed: {day(processed, style)}
Amount billed: {money(a['billed'])}
Plan discount: {money(a['adjustment'])}
Allowed amount: {money(a['allowed'])}
Plan paid: {money(a['insurer_paid'])}
Your responsibility: {money(a['patient_responsibility'])}
"""
    elif layout == "table":
        text = f"""{insurer}
Explanation of Benefits - This is not a bill
Member: {patient}   ID #: {member_id}
Claim #: {claim}     Processed {day(processed, style)}
Provided by: {provider}
Date of Service   Service   Billed   Discount   Allowed   Plan Paid   You Owe
{day(dos, 'us')} {code} {service} {money(a['billed'])} {money(a['adjustment'])} {money(a['allowed'])} {money(a['insurer_paid'])} {money(a['patient_responsibility'])}
Totals {money(a['billed'])} {money(a['adjustment'])} {money(a['allowed'])} {money(a['insurer_paid'])} {money(a['patient_responsibility'])}
"""
    else:  # "narrative": another insurer's wording
        text = f"""{insurer}
Your Explanation of Benefits
This is not a bill. Keep this notice for your records.
For: {patient}
Claim ID: {claim}
Service provider: {provider}
Service date: {day(dos, style)}
Amount charged by provider: {money(a['billed'])}
Network discount: {money(a['adjustment'])}
Your plan's allowed amount: {money(a['allowed'])}
Your plan paid: {money(a['insurer_paid'])}
Your share: {money(a['patient_responsibility'])}
"""
    truth = {"doc_type": "eob", "fields": {"patient": patient, "provider": provider, "claim_number": claim,
                                           "service_start": dos.isoformat(), **a}}
    return text, truth


def statement(n: int, layout: str) -> tuple[str, dict]:
    patient, provider = RNG.choice(PATIENTS), RNG.choice(PROVIDERS)
    dos = date(2026, 1, 5) + timedelta(days=RNG.randrange(0, 300))
    stmt = dos + timedelta(days=RNG.randrange(20, 60))
    account = str(RNG.randrange(10**5, 10**7))
    code, service = RNG.choice(SERVICES)
    charge = RNG.randrange(80, 900) * 100
    due = RNG.choice([charge, charge // 4 // 100 * 100, 4500, 12000])
    style = RNG.choice(["us", "long"])
    if layout == "labels":
        text = f"""{provider}
455 River Road, Springfield
Statement date: {day(stmt, style)}
Account number: {account}
Patient: {patient}
Due date: {day(stmt + timedelta(days=30), style)}
{day(dos, 'us')} {code} {service} {money(charge)} {money(charge - due)} {money(due)}
Amount due: {money(due)}
"""
    elif layout == "summary":
        text = f"""{provider}
PATIENT STATEMENT
Guarantor: {patient}      Account #: {account}
Statement Date {day(stmt, style)}
Previous balance {money(0)}
New charges {money(charge)}
Insurance payments ({money(charge - due)})
Please pay this amount {money(due)}
Pay by {day(stmt + timedelta(days=25), style)}
"""
    else:  # "ledger": the practice ledger layout Release 0's converter reads
        ins = charge - due
        text = f"""{provider} Statement Date
{stmt.strftime('%m/%d/%Y')} {account} {money(due)}
{patient} Last Appt Date: {dos.strftime('%m/%d/%Y')}
{dos.strftime('%m/%d/%Y')} Jane Doe, MD {service} {money(charge)} {money(due)}
Example Health states a coinsurance of {money(due)}
Example Health {money(ins)}{(dos + timedelta(days=12)).strftime('%m/%d/%Y')}
Due From Patient: {money(due)}
"""
    truth = {"doc_type": "provider_statement",
             "fields": {"patient": patient, "provider": provider, "statement_date": stmt.isoformat(),
                        "balance_due": due, **({"account_number": account} if layout != "ledger" else {})}}
    return text, truth


def itemized(n: int) -> tuple[str, dict]:
    patient, provider = RNG.choice(PATIENTS), RNG.choice(["Mercy General Hospital", "St. Example Medical Center"])
    dos = date(2026, 2, 1) + timedelta(days=RNG.randrange(0, 250))
    stmt = dos + timedelta(days=30)
    rows = [("0450", "99284", "ER visit level 4", 1, RNG.randrange(600, 1800) * 100),
            ("0300", "80053", "Metabolic panel", 1, RNG.randrange(40, 200) * 100),
            ("0636", "J1885", "Ketorolac injection", 2, RNG.randrange(10, 60) * 100)]
    total = sum(r[4] for r in rows)
    paid = int(total * 0.6) // 100 * 100
    lines = "\n".join(f"{dos.strftime('%m/%d/%Y')} {cpt} {desc} {units} {money(amt)}" for rev, cpt, desc, units, amt in rows)
    text = f"""{provider}
ITEMIZED STATEMENT
Patient: {patient}
Account number: {RNG.randrange(10**6, 10**8)}
Statement date: {stmt.strftime('%m/%d/%Y')}
Date Rev code CPT/HCPCS Description Units Charge
{lines}
Total charges: {money(total)}
Insurance payments: {money(paid)}
Amount due: {money(total - paid)}
"""
    truth = {"doc_type": "itemized_bill", "fields": {"patient": patient, "provider": provider,
                                                     "statement_date": stmt.isoformat(), "balance_due": total - paid}}
    return text, truth


def filed(kind: str, n: int) -> tuple[str, dict]:
    p, d = RNG.choice(PATIENTS), date(2026, RNG.randrange(1, 12), RNG.randrange(1, 28))
    texts = {
        "hsa_statement": f"""Example Bank Health Savings Account
Quarterly statement {d.strftime('%m/%d/%Y')}
Account holder: {p}
Beginning balance {money(RNG.randrange(100, 5000) * 100)}
Contributions {money(RNG.randrange(100, 900) * 100)}
Distributions ({money(RNG.randrange(10, 400) * 100)})
Interest {money(RNG.randrange(1, 30) * 10)}
Ending balance {money(RNG.randrange(100, 5000) * 100)}
""",
        "card_transaction": f"""Purchase receipt
Merchant: {RNG.choice(PROVIDERS)}
Card ending 4{RNG.randrange(100, 999)}
Authorization {RNG.randrange(100000, 999999)}   Approved
Date {d.strftime('%m/%d/%Y')}
Purchase amount {money(RNG.randrange(10, 400) * 100)}
""",
        "pharmacy_receipt": f"""Example Pharmacy #{RNG.randrange(100, 999)}
Rx # {RNG.randrange(1000000, 9999999)}   Refill {RNG.randrange(0, 5)} of 5
{RNG.choice(['Atorvastatin 20 mg', 'Amoxicillin 500 mg', 'Lisinopril 10 mg'])}   Qty {RNG.choice([30, 60, 90])}
Filled {d.strftime('%m/%d/%Y')}
Your copay {money(RNG.choice([500, 1000, 1500]))}
""",
        "good_faith_estimate": f"""GOOD FAITH ESTIMATE
Under the No Surprises Act you have the right to receive this estimate.
Patient: {p}
Provider: {RNG.choice(PROVIDERS)}
Scheduled service {d.strftime('%m/%d/%Y')}
Expected charges {money(RNG.randrange(300, 4000) * 100)}
""",
        "other": RNG.choice([
            f"Dear {p},\nThis is a reminder of your appointment on {d.strftime('%m/%d/%Y')} at 10:30 AM.\nPlease arrive 15 minutes early.\n",
            "Notice of Privacy Practices\nThis notice describes how medical information about you may be used and disclosed.\nPlease review it carefully.\n",
            f"Patient satisfaction survey\nTell us about your visit on {d.strftime('%m/%d/%Y')}.\nYour feedback helps us improve.\n",
        ]),
    }
    return texts[kind], {"doc_type": kind, "fields": {}}


def holdout_eob(n: int) -> tuple[str, dict]:
    """Held-out EOB wording: written once, never used to tune the rules."""
    patient, provider, insurer = RNG.choice(PATIENTS), RNG.choice(PROVIDERS), RNG.choice(INSURERS)
    dos = date(2026, 1, 5) + timedelta(days=RNG.randrange(0, 330))
    claim = f"{RNG.randrange(10**9, 10**10)}"
    a = amounts()
    if n % 2 == 0:
        text = f"""{insurer} Member Services
EXPLANATION OF BENEFITS
Patient name: {patient}
Claim number {claim}
Provider name: {provider}
Visit date: {dos.strftime('%B %-d, %Y')}
Total billed by provider {money(a['billed'])}
Your plan's discount {money(a['adjustment'])}
Plan's allowed amount {money(a['allowed'])}
What your plan paid {money(a['insurer_paid'])}
Amount you owe the provider {money(a['patient_responsibility'])}
THIS IS NOT A BILL
"""
    else:
        text = f"""Claim Summary  |  {insurer}
Patient   {patient}
Claim   {claim}
Rendered by   {provider}
Service dates   {dos.strftime('%m/%d/%y')} - {dos.strftime('%m/%d/%y')}
Charges {money(a['billed'])}
Savings {money(a['adjustment'])}
Covered amount {money(a['allowed'])}
Paid to provider {money(a['insurer_paid'])}
Patient responsibility {money(a['patient_responsibility'])}
This is not a bill.
"""
    return text, {"doc_type": "eob", "fields": {"patient": patient, "provider": provider, "claim_number": claim,
                                                "service_start": dos.isoformat(), **a}}


def holdout_statement(n: int) -> tuple[str, dict]:
    patient, provider = RNG.choice(PATIENTS), RNG.choice(PROVIDERS)
    stmt = date(2026, 2, 1) + timedelta(days=RNG.randrange(0, 280))
    account = f"{RNG.randrange(100, 999)}-{RNG.randrange(1000, 9999)}"
    due = RNG.randrange(30, 900) * 100
    if n % 2 == 0:
        text = f"""INVOICE
{provider}
Invoice date: {stmt.strftime('%m/%d/%Y')}
Acct No: {account}
Bill to: {patient}
Balance forward {money(0)}
Total balance due {money(due)}
Questions about your bill? Call our billing office.
"""
    else:
        text = f"""{provider}  -  Billing Statement
Statement Dt  {stmt.strftime('%m/%d/%Y')}
Patient Acct  {account}
Patient Name  {patient}
Current Balance  {money(due)}
Amount Enclosed  ________
"""
    return text, {"doc_type": "provider_statement",
                  "fields": {"patient": patient, "provider": provider, "statement_date": stmt.isoformat(),
                             "balance_due": due, "account_number": account}}


def holdout() -> list[tuple[str, str, dict]]:
    docs = [(f"eob-{i:02d}", *holdout_eob(i)) for i in range(10)]
    docs += [(f"statement-{i:02d}", *holdout_statement(i)) for i in range(10)]
    for kind, count in (("hsa_statement", 5), ("card_transaction", 5), ("pharmacy_receipt", 5),
                        ("good_faith_estimate", 5), ("other", 5)):
        docs += [(f"{kind.replace('_', '-')}-{i:02d}", *filed(kind, i)) for i in range(count)]
    docs += [(f"itemized-{i:02d}", *itemized(i)) for i in range(5)]
    return docs


def build() -> list[tuple[str, str, dict]]:
    docs = []
    for i in range(12):
        docs.append((f"eob-{i:02d}", *eob(i, ["labels", "table", "narrative"][i % 3])))
    for i in range(12):
        docs.append((f"statement-{i:02d}", *statement(i, ["labels", "summary", "ledger"][i % 3])))
    for i in range(6):
        docs.append((f"itemized-{i:02d}", *itemized(i)))
    for kind, count in (("hsa_statement", 5), ("card_transaction", 5), ("pharmacy_receipt", 5),
                        ("good_faith_estimate", 5), ("other", 6)):
        for i in range(count):
            docs.append((f"{kind.replace('_', '-')}-{i:02d}", *filed(kind, i)))
    return docs


def write(out: Path, docs) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*"):
        old.unlink()
    for name, text, truth in docs:
        (out / f"{name}.pdf").write_bytes(make_pdf(text))
        (out / f"{name}.json").write_text(json.dumps(truth, indent=2) + "\n")
    print(f"wrote {len(docs)} documents to {out}")


def main() -> None:
    write(OUT, build())
    RNG.seed(4242)  # the held-out set: other values and wording the rules were never tuned on
    write(OUT.with_name("corpus-holdout"), holdout())


if __name__ == "__main__":
    main()
