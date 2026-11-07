"""Write samples/harness/pdfs/ from the harness CSV: every invoice, EOB and HSA statement its columns name.

The CSV is the source of truth (samples/harness/README.md). Every date, name, code and amount comes from it, and
totals are added up here, so the documents agree with it and with themselves. A real document also has details the
CSV doesn't hold; these are derived, always the same: the statement date (3 days after adjudication), the due date
(30 days later) and account and member numbers. To test catching errors, put them in the CSV or list them in an
answer key rather than editing a PDF. Rewrites the folder:

    uv run tools/make_harness_pdfs.py
"""

import argparse
import csv
import hashlib
import io
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.pdfs import make_pdf  # noqa: E402

FOLDER = ROOT / "samples" / "harness"
LINES_PER_PAGE = 56
INSURER = "Aegis Health Plans"
CUSTODIAN = "EquiHealth HSA Bank"
OUTSIDE_HSA = {"Direct Personal CC": "personal credit card", "Direct Personal Checking": "personal check"}


def read_master(folder: Path = FOLDER) -> list[dict]:
    [path] = folder.glob("*.csv")
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))


def cents(value: str) -> int:
    return round(float(value or 0) * 100)


def usd(c: int) -> str:
    return f"-${-c / 100:,.2f}" if c < 0 else f"${c / 100:,.2f}"


def us_date(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%m/%d/%Y")


def later(iso: str, days: int) -> str:
    return (date.fromisoformat(iso) + timedelta(days=days)).isoformat()


def number(*parts: str, digits: int = 7) -> str:
    return str(int(hashlib.sha256("|".join(parts).encode()).hexdigest(), 16))[:digits]


def is_tranche(r: dict) -> bool:
    """A later payment on a charge already counted: it bills and allows nothing (St. Jude's second row)."""
    return not cents(r["Billed_Charge"]) and not cents(r["Negotiated_Allowed_Amount"])


def surname_first(name: str) -> str:
    first, *rest = name.split()
    return f"{' '.join(rest)}, {first}"


def subscriber(rows: list[dict]) -> str:
    return next(r["Member_Name"] for r in rows if r["Member_Relationship"] == "Primary Subscriber")


def total(rows: list[dict], key: str) -> int:
    return sum(cents(r[key]) for r in rows)


def paginate(head: list[str], body: list[str], foot: list[str], table_head: list[str] = ()) -> list[str]:
    """Pages of text. A row is kept with the line after it when that line is indented (the EOB's two-line rows)."""
    pages, page = [], list(head)
    for i, line in enumerate(body):
        keep_with_next = i + 1 < len(body) and body[i + 1].startswith(" ")
        if len(page) + (2 if keep_with_next else 1) > LINES_PER_PAGE:
            pages.append("\n".join(page))
            page = list(table_head)
        page.append(line)
    if len(page) + len(foot) > LINES_PER_PAGE:
        pages.append("\n".join(page))
        page = []
    pages.append("\n".join(page + list(foot)))
    return pages


def invoice_pages(rows: list[dict], family: list[dict]) -> list[str]:
    charges = [r for r in rows if not is_tranche(r)]
    first = charges[0]
    statement = later(max(r["EOB_Adjudication_Date"] for r in charges), 3)
    claims = ", ".join(dict.fromkeys(r["EOB_Claim_Number"] for r in charges))
    providers = list(dict.fromkeys(r["Provider_Name"] for r in charges))
    billed, allowed = total(charges, "Billed_Charge"), total(charges, "Negotiated_Allowed_Amount")
    insurance, owed = total(charges, "Insurance_Paid_Amount"), total(charges, "Total_Member_Responsibility")
    head = [providers[0], "PATIENT STATEMENT", first["Facility_Name"], f"Statement date: {us_date(statement)}",
            f"Account number: {number(providers[0], first['Member_Name'])}",
            f"Patient: {surname_first(first['Member_Name'])}", f"Guarantor: {subscriber(family)}",
            f"Date of service: {us_date(first['Date_of_Service'])}", f"Primary insurance: {INSURER}",
            f"Claim number: {claims}", f"Due date: {us_date(later(statement, 30))}", "",
            "Date Code Description Charges Insurance Adjustments Payments Balance"]
    body, payments, received = [], [], 0
    for r in rows:  # paid outside the HSA, or from it by the statement date: the statement already shows them
        how = next((v for k, v in OUTSIDE_HSA.items() if r["HSA_Disbursement_Status"].startswith(k)), None)
        paid = cents(r["Total_Member_Responsibility"]) if how else cents(r["HSA_Amount_Paid"])
        if not how and r["HSA_Payment_Date"] > statement:
            paid = 0
        if paid:
            payments.append(f"Payment received, {how}: {usd(-paid)}" if how else
                            f"Payment received {us_date(r['HSA_Payment_Date'])}, HSA debit card: {usd(-paid)}")
            received += paid
        if not is_tranche(r):
            charge, insurer = cents(r["Billed_Charge"]), cents(r["Insurance_Paid_Amount"])
            adjustment = charge - cents(r["Negotiated_Allowed_Amount"])
            body.append(f"{us_date(r['Date_of_Service'])} {r['CPT_HCPCS_Code']} {r['Service_Description'][:38]} "
                        f"{usd(charge)} {usd(insurer)} {usd(adjustment)} {usd(paid)} "
                        f"{usd(charge - insurer - adjustment - paid)}")
    foot = ["", f"Total charges: {usd(billed)}", f"Contractual adjustments: {usd(billed - allowed)}",
            f"Allowed amount: {usd(allowed)}", f"Insurance payments: {usd(insurance)}",
            f"Patient responsibility: {usd(owed)}", *payments, f"Amount due: {usd(owed - received)}"]
    return paginate(head, body, foot)


def eob_pages(family: list[dict]) -> list[str]:
    rows = sorted((r for r in family if not is_tranche(r)), key=lambda r: (r["Date_of_Service"], r["EOB_Claim_Number"]))
    holder = subscriber(family)
    issued = later(max(r["EOB_Adjudication_Date"] for r in rows), 3)
    head = [INSURER, "EXPLANATION OF BENEFITS", "THIS IS NOT A BILL", f"Subscriber: {holder}",
            f"Member ID: AEG-{number(holder)}", f"Issue date: {us_date(issued)}", "Coverage period: 2026 plan year", "",
            "ADJUDICATED CLAIMS", "Date, claim, patient, provider, code; then billed, allowed, plan paid, deductible, copay, coinsurance, you owe"]
    body = []
    for r in rows:
        body.append(f"{us_date(r['Date_of_Service'])} {r['EOB_Claim_Number']} {r['Member_Name']} "
                    f"{r['Provider_Name']} {r['CPT_HCPCS_Code']}")
        body.append(f"  Billed {usd(cents(r['Billed_Charge']))} Allowed {usd(cents(r['Negotiated_Allowed_Amount']))} "
                    f"Paid {usd(cents(r['Insurance_Paid_Amount']))} Deduct. {usd(cents(r['Member_Deductible']))} "
                    f"Copay {usd(cents(r['Member_Copay']))} Coins. {usd(cents(r['Member_Coinsurance']))} "
                    f"You owe {usd(cents(r['Total_Member_Responsibility']))}")
    foot = ["", "TOTALS", f"Total billed: {usd(total(rows, 'Billed_Charge'))}",
            f"Total allowed: {usd(total(rows, 'Negotiated_Allowed_Amount'))}",
            f"Total plan paid: {usd(total(rows, 'Insurance_Paid_Amount'))}",
            f"Total deductible: {usd(total(rows, 'Member_Deductible'))}",
            f"Total copay: {usd(total(rows, 'Member_Copay'))}",
            f"Total coinsurance: {usd(total(rows, 'Member_Coinsurance'))}",
            f"Total you owe: {usd(total(rows, 'Total_Member_Responsibility'))}",
            "Do not pay this statement. Your providers will bill you for the amount you owe."]
    return paginate(head, body, foot, ["Date, claim, patient, provider, code; then billed, allowed, plan paid, deductible, copay, coinsurance, you owe"])


def hsa_pages(family: list[dict]) -> list[str]:
    grouped = defaultdict(list)
    for r in family:
        if r["HSA_Transaction_ID"] and cents(r["HSA_Amount_Paid"]):
            grouped[(r["HSA_Payment_Date"], r["HSA_Transaction_ID"], r["Provider_Name"], r["Member_Name"])].append(r)
    holder = subscriber(family)
    last = max(key[0] for key in grouped)
    head = [CUSTODIAN, "HSA ACTIVITY STATEMENT", f"Account holder: {holder}",
            f"HSA account number: HSA-{number('hsa', holder, digits=10)}", f"Period: 01/01/2026 to {us_date(last)}", "",
            "DISBURSEMENTS", "Date Transaction Payee Patient Claim Amount"]
    body = [f"{us_date(when)} {txn} {provider} {member} "
            f"{', '.join(dict.fromkeys(r['EOB_Claim_Number'] for r in rows))} {usd(total(rows, 'HSA_Amount_Paid'))}"
            for (when, txn, provider, member), rows in sorted(grouped.items())]
    foot = ["", f"Number of disbursements: {len(grouped)}", f"Total disbursements: {usd(total(family, 'HSA_Amount_Paid'))}",
            "Contributions and balances aren't shown in this test data."]
    return paginate(head, body, foot, ["Date Transaction Payee Patient Claim Amount"])


def documents(rows: list[dict]) -> dict[str, list[str]]:
    """File name -> pages of text, for every document the CSV names."""
    out, invoices = {}, defaultdict(list)
    for r in rows:
        invoices[(r["Family"], r["Provider_Invoice_Asset_PDF"])].append(r)
    for (family, name), group in invoices.items():
        out[name] = invoice_pages(group, [r for r in rows if r["Family"] == family])
    for family in dict.fromkeys(r["Family"] for r in rows):
        part = [r for r in rows if r["Family"] == family]
        out[part[0]["Insurance_EOB_Asset_PDF"]] = eob_pages(part)
        out[part[0]["HSA_Statement_Asset_PDF"]] = hsa_pages(part)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=FOLDER / "pdfs")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for old in args.out.glob("*.pdf"):
        old.unlink()
    docs = documents(read_master())
    for name, pages in docs.items():
        (args.out / name).write_bytes(make_pdf(*pages))
    print(f"{len(docs)} PDFs in {args.out}")


if __name__ == "__main__":
    main()
