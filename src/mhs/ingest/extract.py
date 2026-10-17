"""Classify a document and extract its fields from scrubbed text (ING-02, ING-03, ING-04). Runs in the worker.

Pure functions over text in which identifiers are already tokens. Every field carries a confidence; a field the
document doesn't show is None with confidence 0 and is never guessed (TC-ING-03-3). Layout rules come first
(the statement layout Release 0's converter reads); label rules cover EOBs and statements in general. The Claude
extractor (ingest/ai.py, ADR-028) returns the same Extraction and goes through the same checks.
"""

import re
from dataclasses import asdict, dataclass, field

from mhs.ingest.values import parse_amount, parse_date, parse_date_range

TYPES = {
    "provider_statement": "Provider statement",
    "itemized_bill": "Itemized bill",
    "eob": "EOB (explanation of benefits)",
    "hsa_statement": "HSA/FSA statement",
    "card_transaction": "Card transaction",
    "pharmacy_receipt": "Pharmacy receipt",
    "good_faith_estimate": "Good faith estimate",
    "other": "Other",
}
EXTRACTED = ("eob", "provider_statement", "itemized_bill")  # types with field extraction; the rest are kept as filed
REVIEW_THRESHOLD = 0.8

CUES = {
    "eob": [("explanation of benefits", 4), ("this is not a bill", 6), ("eob", 2), ("claim number", 1),
            ("amount allowed", 2), ("allowed amount", 2), ("plan paid", 2), ("paid by plan", 2), ("plan discount", 1),
            ("you may owe", 2), ("your responsibility", 1), ("patient responsibility", 1), ("network discount", 1)],
    "provider_statement": [("statement date", 3), ("amount due", 2), ("balance due", 2), ("due from patient", 3),
                           ("please pay", 2), ("pay this amount", 3), ("remit", 1), ("make checks payable", 2),
                           ("account number", 1), ("statement", 1)],
    "itemized_bill": [("itemized", 5), ("rev code", 3), ("revenue code", 3), ("cpt", 2), ("hcpcs", 2), ("ndc", 1),
                      ("units", 1)],
    "hsa_statement": [("health savings account", 5), ("hsa", 2), ("contribution", 2), ("distribution", 2),
                      ("beginning balance", 2), ("ending balance", 2), ("interest", 1)],
    "card_transaction": [("card ending", 4), ("authorization", 2), ("approved", 1), ("merchant", 2), ("purchase", 1)],
    "pharmacy_receipt": [("pharmacy", 4), ("rx #", 3), ("rx#", 3), ("refill", 2), ("qty", 1), ("ndc", 1)],
    "good_faith_estimate": [("good faith estimate", 8), ("no surprises act", 3), ("expected charges", 3),
                            ("estimated", 1)],
}

MONEY = r"\(?-?\$?\s?[\d,]+\.\d{2}\)?(?:\s*CR)?"
DATE = (r"(?:\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}|"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? \d{1,2}, \d{4})")
# Column headers of a table-style EOB (a header row, then service rows and a totals row), as field names.
EOB_COLUMNS = {
    "billed": r"billed|charges?|amount billed|provider charged",
    "adjustment": r"discount|plan discount|network discount|adjustments?",
    "allowed": r"allowed|allowed amount|amount allowed",
    "insurer_paid": r"plan paid|paid by plan|insurance paid|plan payment|plan pays",
    "deductible": r"deductible",
    "copay": r"copay",
    "coinsurance": r"coinsurance",
    "not_covered": r"not covered|non-?covered",
    "patient_responsibility": r"you owe|your responsibility|patient responsibility|your cost|your share|you pay",
}
EOB_LABELS = {
    "billed": r"amount billed|billed amount|provider charged|total charges|amount charged|charges|billed",
    "adjustment": r"plan discount|network discount|discount|provider adjustment|adjustment",
    "allowed": r"amount allowed|allowed amount|allowed",
    "insurer_paid": r"plan paid|paid by plan|plan payment|insurance paid|amount paid by (?:your )?plan|plan's share",
    "deductible": r"deductible",
    "copay": r"copay(?:ment)?",
    "coinsurance": r"coinsurance",
    "not_covered": r"not covered|amount not covered|non-?covered",
    "patient_responsibility": r"your responsibility|you owe|you may owe|patient responsibility|"
                              r"member responsibility|what you owe|your (?:total )?cost|your share",
}
STATEMENT_LABELS = {
    "balance_due": r"amount due|balance due|due from patient|total due|please pay|pay this amount|new balance|"
                   r"total amount due",
    "billed": r"total charges|charges this statement|new charges",
    "insurance_paid": r"insurance payments?|insurance paid|paid by insurance",
    "adjustment": r"adjustments?|insurance adjustments?",
    "patient_paid": r"patient payments?|your payments?|payments received",
}


@dataclass
class Field:
    value: object = None
    confidence: float = 0.0
    note: str = ""


@dataclass
class Extraction:
    doc_type: str
    type_confidence: float
    layout: str = ""
    fields: dict[str, Field] = field(default_factory=dict)
    lines: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_record(self) -> dict:
        return asdict(self)


def classify(text: str) -> tuple[str, float]:
    low = text.lower()
    scores = {t: sum(w for cue, w in cues if cue in low) for t, cues in CUES.items()}
    if "this is not a bill" in low:  # TC-ING-02-3: never a provider statement
        scores["eob"] += 10
    if scores["itemized_bill"] >= 5 and scores["provider_statement"] >= 2:
        scores["provider_statement"] -= 2  # an itemized bill also says "amount due"
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    (top, best), (_, second) = ranked[0], ranked[1]
    if best < 3:
        return "other", 0.3
    return top, round(min(0.99, 0.5 + (best - second) / (best + 2)), 2)


def _label_value(text: str, labels: str, value: str) -> str | None:
    m = re.search(rf"(?im)^.*?\b(?:{labels})\b[^\n\d$(-]{{0,40}}?[:\s]\s*({value})", text)
    return m.group(1) if m else None


def _money_field(text: str, labels: str) -> Field:
    raw = _label_value(text, labels, MONEY)
    cents = parse_amount(raw) if raw else None
    return Field(cents, 0.95, "") if cents is not None else Field(None, 0.0, "not on document")


def _text_field(text: str, labels: str, confidence: float = 0.9) -> Field:
    # The label starts a line or a column (after a wide gap): "Guarantor: Pat Example      Account #: 556677".
    m = re.search(rf"(?im)(?:^|\s{{3,}}|\t)\s*(?:{labels})\s*[:#]\s*([^\n]+?)\s*(?:\s{{3,}}.*)?$", text)
    value = m.group(1).strip() if m else None
    return Field(value, confidence, "") if value else Field(None, 0.0, "not on document")


def _date_field(text: str, labels: str) -> Field:
    raw = _label_value(text, labels, DATE + r"(?:\s*(?:-|to|through|thru)\s*" + DATE + ")?")
    rng = parse_date_range(raw) if raw else None
    return Field(rng[0], 0.95, "") if rng else Field(None, 0.0, "not on document")


def _service_dates(text: str) -> tuple[Field, Field]:
    raw = _label_value(text, r"dates? of service|service dates?|dos|date\(s\) of service",
                       DATE + r"(?:\s*(?:-|to|through|thru)\s*" + DATE + ")?")
    rng = parse_date_range(raw) if raw else None
    if not rng:
        return Field(None, 0.0, "not on document"), Field(None, 0.0, "not on document")
    return Field(rng[0], 0.95), Field(rng[1], 0.95)


def _provider(text: str) -> Field:
    f = _text_field(text, r"provider(?: name)?|provided by|rendering provider|service provider|facility|"
                          r"practice|billing provider|remit to")
    if f.value:
        return f
    for line in text.splitlines():  # letterhead: the first line that isn't a label, date or amount
        s = line.strip()
        if s and not re.search(r"[:$]|\d{2}/\d{2}|tok_|statement|explanation|page \d", s, re.I) and len(s) > 3:
            return Field(s, 0.5, "from the letterhead")
    return Field(None, 0.0, "not on document")


def _lines(text: str) -> list[dict]:
    """Service lines: a date, an optional CPT/HCPCS code with modifier, a description and amounts (ING-04)."""
    out = []
    pattern = re.compile(rf"^\s*(?P<date>{DATE})\s+(?:(?P<code>\d{{5}}|[A-Z]\d{{4}})(?:-(?P<mod>[A-Z0-9]{{2}}))?\s+)?"
                         rf"(?P<desc>.*?)\s+(?P<amounts>(?:{MONEY}\s*)+)$", re.M)
    for m in pattern.finditer(text):
        amounts = [parse_amount(a) for a in re.findall(MONEY, m.group("amounts"))]
        line = {"service_date": parse_date(m.group("date")), "description": m.group("desc").strip(),
                "amounts": amounts}
        if m.group("code"):
            line["code"] = m.group("code") + (f"-{m.group('mod')}" if m.group("mod") else "")
        out.append(line)
    return out


def extract_eob(text: str) -> Extraction:
    x = Extraction("eob", 0.0, "eob labels")
    f = x.fields
    f["patient"] = _text_field(text, r"patient(?: name)?|member(?: name)?|for")
    f["provider"] = _provider(text)
    f["claim_number"] = _text_field(text, r"claim (?:number|no\.?|#|id)|claim")
    f["service_start"], f["service_end"] = _service_dates(text)
    f["processed_date"] = _date_field(text, r"date processed|processed date|processed(?: on)?|date of (?:this )?notice|statement date")
    for name, labels in EOB_LABELS.items():
        f[name] = _money_field(text, labels)
    low = text.lower()
    status = "denied" if re.search(r"\bdenied\b", low) else "processed"
    f["claim_status"] = Field(status, 0.7 if status == "processed" else 0.9)
    network = ("out_of_network" if re.search(r"out[- ]of[- ]network", low)
               else "in_network" if re.search(r"\bin[- ]network\b", low) else None)
    f["network_status"] = Field(network, 0.8) if network else Field(None, 0.0, "not on document")
    columns = _table_columns(text)
    for line in _lines(text):
        a = line.pop("amounts")
        keys = columns if columns and len(columns) == len(a) else ["billed", "allowed", "insurer_paid",
                                                                     "patient_responsibility"]
        line.update({k: v for k, v in zip(keys, a)})
        x.lines.append(line)
    if columns and (totals := _totals_row(text, len(columns))):
        for name, cents in zip(columns, totals):  # a table-style EOB: the totals row holds the header amounts
            if f[name].value is None:
                f[name] = Field(cents, 0.9, "from the totals row")
    if f["service_start"].value is None and x.lines and x.lines[0].get("service_date"):
        dates = sorted(l["service_date"] for l in x.lines if l.get("service_date"))
        f["service_start"], f["service_end"] = Field(dates[0], 0.85, "from the service lines"), Field(dates[-1], 0.85)
    _check_eob(x)
    return x


def _table_columns(text: str) -> list[str]:
    """The money columns of a table header row, in order, e.g. Billed, Discount, Allowed, Plan Paid, You Owe."""
    for line in text.splitlines():
        found = []
        for name, labels in EOB_COLUMNS.items():
            for m in re.finditer(rf"(?i)(?<![a-z])(?:{labels})(?![a-z])", line):
                found.append((m.start(), name))
                break
        if len({n for _, n in found}) >= 3:
            ordered, seen = [], set()
            for _, name in sorted(found):
                if name not in seen:
                    ordered.append(name)
                    seen.add(name)
            return ordered
    return []


def _totals_row(text: str, count: int) -> list[int] | None:
    m = re.search(rf"(?im)^\s*(?:claim )?totals?\b[^\n$\d(-]*((?:{MONEY}\s*)+)$", text)
    if not m:
        return None
    amounts = [parse_amount(a) for a in re.findall(MONEY, m.group(1))]
    return amounts if len(amounts) == count and None not in amounts else None


def _check_eob(x: Extraction) -> None:
    """Lower confidence where the numbers don't hold together, and say why (ING-05, REC-01)."""
    v = {k: x.fields[k].value for k in ("billed", "adjustment", "allowed", "insurer_paid", "patient_responsibility")}
    if None not in (v["billed"], v["adjustment"], v["allowed"]) and v["billed"] - v["adjustment"] != v["allowed"]:
        x.warnings.append(f"Billed minus discount isn't the allowed amount (off by "
                          f"${abs(v['billed'] - v['adjustment'] - v['allowed']) / 100:,.2f}).")
        for k in ("billed", "adjustment", "allowed"):
            x.fields[k].confidence = min(x.fields[k].confidence, 0.6)
    if None not in (v["allowed"], v["insurer_paid"], v["patient_responsibility"]):
        extra = sum(x.fields[k].value or 0 for k in ("not_covered",))
        if v["allowed"] - v["insurer_paid"] + extra != v["patient_responsibility"]:
            x.warnings.append("Allowed minus plan paid isn't what you owe; check the amounts.")
            for k in ("insurer_paid", "patient_responsibility"):
                x.fields[k].confidence = min(x.fields[k].confidence, 0.6)
    _check_line_total(x, "billed", "billed")


def _check_line_total(x: Extraction, line_key: str, total_key: str) -> None:
    """TC-ING-04-3: lines that don't add up to the header total are flagged before confirmation."""
    amounts = [l.get(line_key) for l in x.lines]
    total = x.fields.get(total_key, Field()).value
    if x.lines and None not in amounts and total is not None and sum(amounts) != total:
        x.warnings.append(f"Lines differ from the total by ${abs(sum(amounts) - total) / 100:,.2f}.")


def extract_statement(text: str, doc_type: str = "provider_statement") -> Extraction:
    if ser := _ser_statement(text):
        return ser
    x = Extraction(doc_type, 0.0, "statement labels")
    f = x.fields
    f["patient"] = _text_field(text, r"patient(?: name)?|guarantor(?: name)?|for")
    f["provider"] = _provider(text)
    f["account_number"] = _text_field(text, r"(?:patient )?(?:account|acct\.?)(?: number| no\.?| #)?")
    f["statement_date"] = _date_field(text, r"statement date|date of statement|billing date")
    f["due_date"] = _date_field(text, r"due date|payment due|please pay by|due by")
    for name, labels in STATEMENT_LABELS.items():
        f[name] = _money_field(text, labels)
    notice = re.search(r"(second notice|past due|final notice|collections?)", text, re.I)
    f["notice"] = Field(notice.group(1).capitalize(), 0.9) if notice else Field(None, 0.0, "not on document")
    for line in _lines(text):
        a = line.pop("amounts")
        # Charge first and balance last; three amounts are charge, payments/adjustments, balance.
        line["charge"] = a[0]
        if len(a) >= 2:
            line["balance"] = a[-1]
        if len(a) == 5:
            line.update(insurance_paid=a[1], adjustment=a[2], patient_paid=a[3])
        x.lines.append(line)
    if x.lines and f["billed"].value is None:
        f["billed"] = Field(sum(l["charge"] for l in x.lines), 0.7, "sum of the lines")
    _check_line_total(x, "charge", "billed")
    return x


# --- the statement layout Release 0's converter reads (tools/build_ingest.py) ---

POSTING_END = re.compile(r"\(?\$[\d,]+\.\d{2}\)?\d{2}/\d{2}/\d{4}$")
PATIENT_METHODS = {"credit card", "visa", "mastercard", "amex", "discover", "check", "cash", "hsa", "patient payment"}
SER_MONEY = r"\$([\d,]+\.\d{2})"


def _m(s: str) -> int:
    return parse_amount(s) or 0


def _ser_statement(text: str) -> Extraction | None:
    """'<Practice> Statement Date' layout: one service line per row, insurer postings and payments beneath it."""
    raw_lines, lines, buf = [l.strip() for l in text.splitlines()], [], None
    for raw in raw_lines:
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
        return None
    x = Extraction("provider_statement", 0.0, "statement: practice ledger layout")
    f = x.fields
    f["provider"] = Field(header.group(1).strip(), 0.95)
    f["patient"] = Field(None, 0.0, "not on document")
    f["statement_date"] = Field(None, 0.0, "not on document")
    f["balance_due"] = Field(None, 0.0, "not on document")
    items = []
    for i, line in enumerate(lines):
        if f["statement_date"].value is None and (m := re.search(r"(\d{2}/\d{2}/\d{4}) \d+ " + SER_MONEY + "$", line)):
            f["statement_date"] = Field(parse_date(m.group(1)), 0.95)
        elif m := re.match(r"^(.+?) Last Appt Date:", line):
            f["patient"] = Field(m.group(1).strip(), 0.9)
        elif m := re.match(r"^(\d{2}/\d{2}/\d{4}) (.+?) " + SER_MONEY + " " + SER_MONEY + "$", line):
            who = re.match(r"^(.+?, (?:MD|DO|OD|DMD|DDS|NP|PA|PA-C)) (.+)$", m.group(2))
            items.append({"service_date": parse_date(m.group(1)),
                          "rendering_provider": who.group(1) if who else None,
                          "description": who.group(2) if who else m.group(2),
                          "charge": _m(m.group(3)), "balance": _m(m.group(4)), "adjustment": 0,
                          "insurance_paid": 0, "patient_amount": 0, "patient_paid": 0})
        elif m := re.match(r"^(.+?) states a (deductible|coinsurance|copay) of " + SER_MONEY + "$", line):
            if items:
                items[-1]["patient_amount"] += _m(m.group(3))
        elif m := re.match(r"^\(Insurance Adjustment\) .*?(\()?\$([\d,]+\.\d{2})\)?\d{2}/\d{2}/\d{4}$", line):
            if items:
                items[-1]["adjustment"] += -_m(m.group(2)) if m.group(1) else _m(m.group(2))
        elif m := re.match(r"^(.+?) (\()?\$([\d,]+\.\d{2})\)?\d{2}/\d{2}/\d{4}$", line):
            if items:
                amount = -_m(m.group(3)) if m.group(2) else _m(m.group(3))
                key = "patient_paid" if m.group(1).lower() in PATIENT_METHODS else "insurance_paid"
                items[-1][key] += amount
        elif m := re.match(r"^Due From Patient: " + SER_MONEY + "$", line):
            f["balance_due"] = Field(_m(m.group(1)), 0.95)
    for it in items:
        expected = it["charge"] - it["adjustment"] - it["insurance_paid"] - it["patient_paid"]
        if expected != it["balance"]:
            x.warnings.append(f"{it['service_date']} {it['description']!r} doesn't add up: charge less adjustments "
                              f"and payments is ${expected / 100:,.2f}, the balance shows ${it['balance'] / 100:,.2f}.")
        x.lines.append({k: v for k, v in it.items() if v is not None})
    if x.lines and f["balance_due"].value is not None and sum(l["balance"] for l in x.lines) != f["balance_due"].value:
        x.warnings.append("Line balances don't add up to the amount due.")
    if "(PAR)" in text:
        f["network_status"] = Field("in_network", 0.8)
    return x


def check(x: Extraction) -> None:
    """The arithmetic checks, for extractions made any way (layout rules or AI)."""
    if x.doc_type == "eob":
        _check_eob(x)
    elif x.doc_type in ("provider_statement", "itemized_bill"):
        _check_line_total(x, "charge", "billed")


def extract(text: str, forced_type: str | None = None) -> Extraction:
    doc_type, confidence = (forced_type, 1.0) if forced_type else classify(text)
    if doc_type == "eob":
        x = extract_eob(text)
    elif doc_type in ("provider_statement", "itemized_bill"):
        x = extract_statement(text, doc_type)
        x.doc_type = doc_type
    else:
        x = Extraction(doc_type, confidence, "", warnings=[f"{TYPES.get(doc_type, doc_type)} documents are kept with "
                                                           "your uploads; their fields aren't read yet."])
    x.type_confidence = confidence
    return x
