# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["pypdf>=5"]
# ///
"""Build an MH$ ingest JSON file from an insurer claims CSV, an HSA transaction export and
provider patient statements (PDF).

Usage:
    uv run tools/build_ingest.py \
        --settings data/settings.json \
        --claims data/source/2026-10-09/claims.csv \
        --hsa data/source/2026-10-09/TransactionHistory.xls \
        --statements data/source/2026-10-09/patient-statements \
        --out data/ingest-2026.json

Statement parsing supports the "Statement / Due From Patient" layout used by Southeastern Retina
Specialists (one service line per row, insurer postings and patient payments beneath it).

Provider names are mapped through the `aliases` in the settings file. Unmapped names get a stub
provider (and a warning) so nothing is dropped; add an alias and re-run to fix them.
"""

import argparse
import csv
import html
import json
import os
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

HSA_ACCOUNT_ID = "acct-hsa"
CLAIM_PLAN = {"Medical": "plan-2026-medical", "Dental": "plan-2026-dental"}
CLAIM_STATUS = {"Approved": "processed", "Denied": "denied", "Pending": "pending"}
PATIENT_PAYMENT_METHODS = {"credit card", "visa", "mastercard", "amex", "discover", "check", "cash", "hsa", "patient payment"}
MONEY = r"\$([\d,]+\.\d{2})"
POSTING_END = re.compile(r"\(?\$[\d,]+\.\d{2}\)?\d{2}/\d{2}/\d{4}$")
CARD_TXN = re.compile(r"\(Card Transaction ID: ([^)]+)\)")
TAX_YEAR = re.compile(r"Tax year: (\d{4})")

warnings: list[str] = []


def money(text: str) -> Decimal:
    """'$1,332.00' -> 1332.00, '($3.95)' -> -3.95."""
    t = text.strip().replace("$", "").replace(",", "")
    if t.startswith("(") and t.endswith(")"):
        return -Decimal(t[1:-1])
    return Decimal(t or "0")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class Members:
    def __init__(self, members: list[dict]):
        self.records = members
        self.by_alias = {n.lower(): m["id"] for m in members for n in [m["name"], *m.get("aliases", [])]}

    def resolve(self, name: str, source: str) -> str:
        name = re.sub(r"\s*\(\d{4}-\d{2}-\d{2}\)$", "", name).strip()  # drop date of birth
        mid = self.by_alias.get(name.lower())
        if mid:
            return mid
        mid = "mbr-" + slug(name)
        warnings.append(f"Unmapped member name {name!r} in {source}; created stub {mid}. Add it to members in settings.")
        self.records.append({"id": mid, "name": name, "aliases": [name]})
        self.by_alias[name.lower()] = mid
        return mid


class Providers:
    def __init__(self, providers: list[dict]):
        self.records = providers
        self.by_alias = {}
        for p in providers:
            for name in [p["name"], *p.get("aliases", [])]:
                self.by_alias[name.lower()] = p["id"]

    def resolve(self, name: str, source: str) -> str:
        pid = self.by_alias.get(name.lower())
        if pid:
            return pid
        pid = "prov-" + slug(name)
        warnings.append(f"Unmapped provider name {name!r} in {source}; created stub {pid}. Add it as an alias in settings.")
        self.records.append({"id": pid, "name": name, "network_status": "unknown", "aliases": [name]})
        self.by_alias[name.lower()] = pid
        return pid


def read_claims(path: Path, providers: Providers, members: Members):
    visits, eobs, seen = [], [], set()
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            pid = providers.resolve(row["Provided By"], path.name)
            plan_id = CLAIM_PLAN.get(row["Claim Type"])
            if not plan_id:
                warnings.append(f"Unknown claim type {row['Claim Type']!r} on claim {row['Claim Number']}; skipped.")
                continue
            service_date = row["Service Date"]
            visit_id = f"v-{service_date}-{pid.removeprefix('prov-')}"
            if visit_id in seen:
                visit_id += f"-{row['Claim Number']}"
            seen.add(visit_id)
            visits.append({
                "id": visit_id,
                "date": service_date,
                "provider_id": pid,
                "member_id": members.resolve(row["Patient"], path.name),
                "plan_id": plan_id,
                "category": "provider_visit",
                "description": f"{row['Claim Type']} claim {row['Claim Number']}",
            })
            m = {k: money(row[k]) for k in ["Billed", "Plan Discount", "Allowed", "Plan Paid", "Additional Savings",
                                           "Deductible", "Coinsurance", "Copay", "Not Covered", "Your Cost"]}
            eobs.append({
                "id": f"eob-{row['Claim Number']}",
                "type": "eob",
                "date": row["Processed Date"],
                "plan_id": plan_id,
                "provider_id": pid,
                "visit_id": visit_id,
                "claim_number": row["Claim Number"],
                "claim_status": CLAIM_STATUS.get(row["Status"], "pending"),
                "received_date": row["Claim Received"],
                "network_status": "unknown",
                "billed": m["Billed"],
                "allowed": m["Allowed"],
                "adjustment": m["Plan Discount"],
                "insurer_paid": m["Plan Paid"],
                "additional_savings": m["Additional Savings"],
                "deductible": m["Deductible"],
                "copay": m["Copay"],
                "coinsurance": m["Coinsurance"],
                "not_covered": m["Not Covered"],
                "patient_responsibility": m["Your Cost"],
                "notes": f"Insurer status: {row['Status']}. Source: {path.name}",
            })
    return visits, eobs


def read_hsa(path: Path, providers: Providers):
    """The HSA export is an HTML table saved with an .xls extension, newest row first."""
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", text, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) >= 4 and re.match(r"\d{1,2}/\d{1,2}/\d{4}$", cells[0]):
            rows.append(cells)
    rows.reverse()  # oldest first

    docs, balance, per_day = [], None, {}
    for cells in rows:
        when = datetime.strptime(cells[0], "%m/%d/%Y").date().isoformat()
        desc, amount, balance_after = cells[1], money(cells[2]), money(cells[3])
        per_day[when] = per_day.get(when, 0) + 1
        base_id = f"hsa-{when}-{per_day[when]}"

        if desc.startswith("Balance Forward"):
            balance = balance_after
        elif balance is not None and balance + amount != balance_after:
            warnings.append(f"HSA running balance breaks at {when} {desc!r}: {balance} + {amount} != {balance_after}")
            balance = balance_after
        else:
            balance = balance_after

        card = CARD_TXN.search(desc)
        if card:
            merchant = desc.split(", ")[0]
            pid = providers.resolve(merchant, path.name)
            docs.append({
                "id": f"pay-hsa-{card.group(1)}",
                "type": "payment",
                "date": when,
                "kind": "refund" if amount > 0 else "payment",
                "provider_id": pid,
                "account_id": HSA_ACCOUNT_ID,
                "amount": abs(amount),
                "reference": card.group(1),
                "account_balance_after": balance_after,
                "notes": f"HSA card: {desc}",
            })
            continue

        if desc.startswith("Balance Forward"):
            kind = "balance_forward"
        elif desc.startswith("Employee Contribution"):
            kind = "contribution_employee"
        elif desc.startswith("Employer Contribution"):
            kind = "contribution_employer"
        elif desc.startswith("Interest"):
            kind = "interest"
        elif "Fee" in desc:
            kind = "fee"
        else:
            kind = "other"
            warnings.append(f"Unclassified HSA transaction {when} {desc!r}; stored as 'other'.")
        doc = {
            "id": base_id,
            "type": "account_transaction",
            "date": when,
            "account_id": HSA_ACCOUNT_ID,
            "kind": kind,
            "amount": abs(amount),
            "description": desc,
            "account_balance_after": balance_after,
        }
        if tax_year := TAX_YEAR.search(desc):
            doc["tax_year"] = int(tax_year.group(1))
        docs.append(doc)
    return docs


def read_statements(folder: Path, providers: Providers, members: Members, visits: list[dict],
                    plan_ids: set[str], out_dir: Path):
    from pypdf import PdfReader

    visit_by_key = {(v["provider_id"], v["date"]): v for v in visits}
    new_visits, bills, seen = [], [], set()
    for pdf in sorted(folder.glob("*.pdf")):
        text = "\n".join(page.extract_text() or "" for page in PdfReader(pdf).pages)
        lines, buf = [], None
        for raw in (l.strip() for l in text.splitlines()):
            if not raw:
                continue
            if buf is not None:  # a posting wrapped over several lines
                buf += " " + raw
                if POSTING_END.search(buf):
                    lines.append(buf)
                    buf = None
                continue
            if raw.startswith("(Insurance Adjustment)") and not POSTING_END.search(raw):
                buf = raw
                continue
            lines.append(raw)

        header = re.match(r"^(.+?) Statement Date", lines[0]) if lines else None
        if not header:
            warnings.append(f"{pdf.name}: not a recognised statement layout; skipped.")
            continue
        pid = providers.resolve(header.group(1), pdf.name)
        stmt_date = due = member_id = last_payment = None
        items: list[dict] = []
        for i, line in enumerate(lines):
            if stmt_date is None and (m := re.search(r"(\d{2}/\d{2}/\d{4}) \d+ " + MONEY + "$", line)):
                stmt_date = datetime.strptime(m.group(1), "%m/%d/%Y").date()
            elif m := re.match(r"^(.+?) Last Appt Date:", line):
                member_id = members.resolve(m.group(1), pdf.name)
            elif m := re.match(r"^(\d{2}/\d{2}/\d{4}) Last Payment\(s\) Received$", line):
                if i + 1 < len(lines) and (n := re.match(r"^(.+?) " + MONEY + "$", lines[i + 1])):
                    last_payment = {"date": datetime.strptime(m.group(1), "%m/%d/%Y").date().isoformat(),
                                    "method": n.group(1), "amount": money(n.group(2))}
            elif m := re.match(r"^(\d{2}/\d{2}/\d{4}) (.+?) " + MONEY + " " + MONEY + "$", line):
                who_what = re.match(r"^(.+?, (?:MD|DO|OD|DMD|DDS|NP|PA|PA-C)) (.+)$", m.group(2))
                items.append({
                    "date": datetime.strptime(m.group(1), "%m/%d/%Y").date().isoformat(),
                    "rendering_provider": who_what.group(1) if who_what else None,
                    "description": who_what.group(2) if who_what else m.group(2),
                    "charge": money(m.group(3)), "balance": money(m.group(4)),
                    "adjustment": Decimal(0), "insurance_paid": Decimal(0),
                    "patient_amount": Decimal(0), "patient_amount_type": None, "patient_paid": Decimal(0),
                })
            elif m := re.match(r"^(.+?) states a (deductible|coinsurance|copay) of " + MONEY + "$", line):
                if items:
                    it = items[-1]
                    it["patient_amount"] += money(m.group(3))
                    kind = m.group(2)
                    it["patient_amount_type"] = kind if it["patient_amount_type"] in (None, kind) else "mixed"
            elif m := re.match(r"^\(Insurance Adjustment\) .*?(\()?\$([\d,]+\.\d{2})\)?\d{2}/\d{2}/\d{4}$", line):
                if items:
                    items[-1]["adjustment"] += -money(m.group(2)) if m.group(1) else money(m.group(2))
            elif m := re.match(r"^(.+?) (\()?\$([\d,]+\.\d{2})\)?\d{2}/\d{2}/\d{4}$", line):
                if items:
                    amount = -money(m.group(3)) if m.group(2) else money(m.group(3))
                    key = "patient_paid" if m.group(1).lower() in PATIENT_PAYMENT_METHODS else "insurance_paid"
                    items[-1][key] += amount
            elif m := re.match(r"^Due From Patient: " + MONEY + "$", line):
                due = money(m.group(1))

        if stmt_date is None or due is None:
            warnings.append(f"{pdf.name}: statement date or amount due not found; skipped.")
            continue
        bill_id = f"bill-{pid.removeprefix('prov-')}-{stmt_date.isoformat()}"
        if bill_id in seen:
            warnings.append(f"{pdf.name}: duplicate of {bill_id}; skipped.")
            continue
        seen.add(bill_id)

        by_date: dict[str, list[dict]] = {}
        for it in items:
            expected = it["charge"] - it["adjustment"] - it["insurance_paid"] - it["patient_paid"]
            if expected != it["balance"]:
                warnings.append(f"{pdf.name}: {it['date']} {it['description']!r} does not add up "
                                f"(charge - adjustments - payments = {expected}, balance shows {it['balance']}).")
            by_date.setdefault(it["date"], []).append(it)

        bill_lines = []
        for service_date, its in by_date.items():
            visit = visit_by_key.get((pid, service_date))
            if not visit:
                plan_id = f"plan-{service_date[:4]}-medical"
                visit = {
                    "id": f"v-{service_date}-{pid.removeprefix('prov-')}",
                    "date": service_date,
                    "provider_id": pid,
                    **({"member_id": member_id} if member_id else {}),
                    **({"plan_id": plan_id} if plan_id in plan_ids else {}),
                    "category": "provider_visit",
                    "description": "From provider statement; no insurer claim in this import",
                }
                visit_by_key[(pid, service_date)] = visit
                new_visits.append(visit)
            bill_lines.append({
                "visit_id": visit["id"],
                "description": "; ".join(it["description"] for it in its),
                "billed_charge": sum(it["charge"] for it in its),
                "insurance_paid": sum(it["insurance_paid"] for it in its),
                "adjustment": sum(it["adjustment"] for it in its),
                "patient_amount": sum(it["patient_amount"] for it in its),
                "patient_paid": sum(it["patient_paid"] for it in its),
                "balance": sum(it["balance"] for it in its),
                "items": [{k: (v if k != "patient_amount_type" else (v or "unknown")) for k, v in it.items()
                           if k != "date" and v is not None} for it in its],
            })
        total = sum(l["balance"] for l in bill_lines)
        if total != due:
            warnings.append(f"{pdf.name}: line balances total {total} but statement says due {due}.")
        bill = {
            "id": bill_id,
            "type": "provider_bill",
            "date": stmt_date.isoformat(),
            "file": os.path.relpath(pdf, out_dir),
            "provider_id": pid,
            "balance_due": due,
            "lines": bill_lines,
            "notes": f"Parsed from {pdf.name}",
        }
        if "(PAR)" in text:
            bill["network_status_shown"] = "in_network"
        if last_payment:
            bill["last_payment_received"] = last_payment
        bills.append(bill)
    return new_visits, bills


def to_json(o):
    if isinstance(o, Decimal):
        return float(o)
    raise TypeError(type(o))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--settings", type=Path, required=True)
    ap.add_argument("--claims", type=Path)
    ap.add_argument("--hsa", type=Path)
    ap.add_argument("--statements", type=Path, help="Folder of provider patient-statement PDFs")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    settings = json.loads(args.settings.read_text())
    providers = Providers(settings.get("providers", []))
    members = Members(settings.get("members", []))
    visits, documents = [], []
    if args.claims:
        v, eobs = read_claims(args.claims, providers, members)
        visits += v
        documents += eobs
    if args.statements:
        v, bills = read_statements(args.statements, providers, members, visits,
                                   {p["id"] for p in settings.get("plans", [])}, args.out.parent)
        visits += v
        documents += bills
    if args.hsa:
        documents += read_hsa(args.hsa, providers)

    out = {
        "schema_version": "0.1",
        "source": {
            "prepared_by": "tools/build_ingest.py",
            "prepared_on": date.today().isoformat(),
            "notes": "Built from: " + ", ".join(p.name for p in [args.settings, args.claims, args.statements, args.hsa] if p),
        },
        "plans": settings.get("plans", []),
        "accounts": settings.get("accounts", []),
        "members": members.records,
        "providers": providers.records,
        "provider_relationships": settings.get("provider_relationships", []),
        "visits": sorted(visits, key=lambda v: v["date"]),
        "documents": documents,
    }
    args.out.write_text(json.dumps(out, indent=2, default=to_json) + "\n")
    print(f"Wrote {args.out}: {len(visits)} visits, {len(documents)} documents, {len(providers.records)} providers")
    for w in warnings:
        print("WARNING:", w, file=sys.stderr)


if __name__ == "__main__":
    main()
