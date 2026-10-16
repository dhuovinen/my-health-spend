"""HSA and FSA administrator exports: CSV, XLSX, and the HTML-table ".xls" some administrators send (ING-08).

The three formats of the same data give identical transactions. Ids come from each transaction's content, so
importing an export that overlaps an earlier one adds nothing twice (TC-ING-07-5). Card payments become payment
records against the merchant's provider; contributions, interest and fees become account transactions.
"""

import csv
import hashlib
import html
import io
import re
from dataclasses import dataclass, field

from mhs.ingest.resolve import Providers, hsa_account
from mhs.ingest.values import dollars, parse_amount, parse_date

CARD_TXN = re.compile(r"\(Card Transaction ID: ([^)]+)\)")
TAX_YEAR = re.compile(r"Tax year: (\d{4})")
HEADERS = {
    "date": ("date", "transaction date", "posted date", "post date", "trans date"),
    "description": ("description", "transaction", "details", "payee", "memo", "merchant", "transaction description"),
    "amount": ("amount", "transaction amount", "amt"),
    "debit": ("debit", "withdrawal", "withdrawals", "distribution", "distributions"),
    "credit": ("credit", "deposit", "deposits", "contribution", "contributions"),
    "balance": ("balance", "running balance", "available balance", "balance after"),
}


@dataclass
class HsaRow:
    date: str
    description: str
    amount: int  # cents; negative leaves the account
    balance: int | None


@dataclass
class HsaExport:
    rows: list[HsaRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    format: str = ""


def is_hsa_export(name: str, data: bytes) -> bool:
    """True when the file looks like a transaction export (by extension and a date/amount table)."""
    if not name.lower().endswith((".csv", ".xls", ".xlsx")):
        return False
    export = parse_export(name, data)
    return not export.errors and bool(export.rows)


def _cells(name: str, data: bytes) -> tuple[list[list[str]], str]:
    if data[:2] == b"PK":
        from openpyxl import load_workbook

        sheet = load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
        rows = []
        for row in sheet.iter_rows(values_only=True):
            rows.append(["" if v is None else (v.strftime("%m/%d/%Y") if hasattr(v, "strftime") else str(v)) for v in row])
        return rows, "xlsx"
    if data[:4] == b"\xd0\xcf\x11\xe0":
        raise ValueError("This is an old binary Excel file; save it as CSV or XLSX and upload that.")
    text = data.decode("utf-8-sig", errors="replace")
    if re.search(r"<t[rd][\s>]", text, re.I):
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I):
            rows.append([html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                         for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)])
        return rows, "html"
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect)], "csv"


def _columns(header: list[str]) -> dict[str, int]:
    cols = {}
    for i, cell in enumerate(header):
        c = re.sub(r"\s+", " ", cell.strip().lower())
        for key, names in HEADERS.items():
            if c in names and key not in cols:
                cols[key] = i
    return cols


def parse_export(name: str, data: bytes) -> HsaExport:
    out = HsaExport()
    try:
        cells, out.format = _cells(name, data)
    except ValueError as e:
        out.errors.append(str(e))
        return out
    except Exception:  # noqa: BLE001 - a damaged workbook
        out.errors.append("The file couldn't be read as a CSV, XLS or XLSX export.")
        return out
    cells = [r for r in cells if any(c.strip() for c in r)]
    header_at, cols = None, {}
    for i, row in enumerate(cells[:15]):
        found = _columns(row)
        if "date" in found and ("description" in found or "amount" in found):
            header_at, cols = i, found
            break
    if header_at is None and cells and parse_date(cells[0][0]) and len(cells[0]) >= 4:
        # The administrator's HTML ".xls" has no header row: date, description, amount, balance.
        header_at, cols = -1, {"date": 0, "description": 1, "amount": 2, "balance": 3}
    if header_at is None:
        out.errors.append("No header row with Date, Description and Amount columns was found.")
        return out
    missing = [k for k in ("date", "description") if k not in cols]
    if "amount" not in cols and not ("debit" in cols or "credit" in cols):
        missing.append("amount")
    if missing:
        out.errors.append(f"Missing column(s): {', '.join(missing)}. Nothing was imported.")
        return out

    def cell(row, key):
        i = cols.get(key)
        return row[i] if i is not None and i < len(row) else ""

    for n, row in enumerate(cells[header_at + 1:], start=header_at + 2):
        when = parse_date(cell(row, "date"))
        if not when:
            continue  # totals, footers, blank lines
        if "amount" in cols:
            amount = parse_amount(cell(row, "amount"))
        else:
            amount = (parse_amount(cell(row, "credit")) or 0) - abs(parse_amount(cell(row, "debit")) or 0)
        if amount is None:
            out.warnings.append(f"Row {n} ({when}): amount {cell(row, 'amount')!r} isn't a number; skipped.")
            continue
        out.rows.append(HsaRow(when, cell(row, "description").strip(), amount, parse_amount(cell(row, "balance"))))
    if len(out.rows) >= 2 and out.rows[0].date > out.rows[-1].date:
        out.rows.reverse()  # newest first in the export; work oldest first
    if not out.rows:
        out.errors.append("No transactions were found in the file.")
    balance = None
    for r in out.rows:
        if r.balance is None:
            continue
        if balance is not None and not r.description.startswith("Balance Forward") and balance + r.amount != r.balance:
            out.warnings.append(f"The running balance breaks on {r.date} ({r.description!r}): "
                                f"{balance / 100:,.2f} + {r.amount / 100:,.2f} isn't {r.balance / 100:,.2f}.")
        balance = r.balance
    return out


def _txn_id(prefix: str, r: HsaRow) -> str:
    digest = hashlib.sha256(f"{r.date}|{r.description}|{r.amount}|{r.balance}".encode()).hexdigest()[:10]
    return f"{prefix}-{r.date}-{digest}"


def to_ingest(export: HsaExport, providers: list[dict], accounts: list[dict]) -> tuple[dict, list[str]]:
    """Ingest records (dollars) for an export, and notes for the preview."""
    resolver = Providers(providers)
    account_id, new_account = hsa_account(accounts)
    docs, notes = [], []
    for r in export.rows:
        desc = r.description
        if card := CARD_TXN.search(desc):
            merchant = desc.split(", ")[0].strip() or "Unknown merchant"
            docs.append({
                "id": f"pay-hsa-{card.group(1)}", "type": "payment", "date": r.date,
                "kind": "refund" if r.amount > 0 else "payment", "provider_id": resolver.resolve(merchant),
                "account_id": account_id, "amount": dollars(abs(r.amount)), "reference": card.group(1),
                **({"account_balance_after": dollars(r.balance)} if r.balance is not None else {}),
                "notes": f"HSA card: {desc}",
            })
            continue
        low = desc.lower()
        if low.startswith("balance forward"):
            kind = "balance_forward"
        elif "employer" in low and "contribution" in low:
            kind = "contribution_employer"
        elif "contribution" in low:
            kind = "contribution_employee"
        elif low.startswith("interest") or " interest" in low:
            kind = "interest"
        elif "fee" in low:
            kind = "fee"
        elif r.amount < 0 and (m := re.match(r"(?:payment to|distribution to|bill pay(?:ment)? to)\s+(.+)", desc, re.I)):
            payee = m.group(1).split(",")[0].strip()
            docs.append({
                "id": _txn_id("pay-hsa", r), "type": "payment", "date": r.date, "kind": "payment",
                "provider_id": resolver.resolve(payee), "account_id": account_id, "amount": dollars(abs(r.amount)),
                **({"account_balance_after": dollars(r.balance)} if r.balance is not None else {}),
                "notes": f"HSA distribution: {desc}",
            })
            continue
        else:
            kind = "other"
            notes.append(f"{r.date} {desc!r} isn't a recognised transaction; kept as 'other'.")
        doc = {"id": _txn_id("hsa", r), "type": "account_transaction", "date": r.date, "account_id": account_id,
               "kind": kind, "amount": dollars(abs(r.amount)), "description": desc}
        if r.balance is not None:
            doc["account_balance_after"] = dollars(r.balance)
        if tax_year := TAX_YEAR.search(desc):
            doc["tax_year"] = int(tax_year.group(1))
        docs.append(doc)
    for p in resolver.new.values():
        notes.append(f"New provider {p['name']!r} from the export. If it's one you already have, add the name as "
                     "an alias in Settings and import again.")
    data = {"schema_version": "0.1", "documents": docs}
    if resolver.new:
        data["providers"] = list(resolver.new.values())
    if new_account:
        data["accounts"] = [new_account]
    return data, notes
