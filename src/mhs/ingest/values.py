"""Reading amounts and dates as documents print them (ING-03). Pure functions; money in integer cents."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

AMOUNT = re.compile(r"^\(?-?\$?\s*-?[\d,]*\.?\d+\)?(\s*CR)?$", re.I)
DATE_FORMATS = ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%m-%d-%Y")
DATE_IN_TEXT = re.compile(
    r"\b(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}-\d{1,2}-\d{4}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? \d{1,2}, \d{4})\b"
)


def parse_amount(text: str) -> int | None:
    """'$1,234.56' -> 123456; '(45.00)', '-45.00' and '45.00 CR' -> -4500. None if it isn't an amount."""
    t = (text or "").strip()
    if not t or not AMOUNT.match(t) or not re.search(r"\d", t):
        return None
    negative = t.startswith("(") and t.endswith(")") or "-" in t or t.upper().endswith("CR")
    digits = re.sub(r"(?i)cr|[()$,\s-]", "", t)
    try:
        value = Decimal(digits)
    except InvalidOperation:
        return None
    cents = int((value * 100).quantize(Decimal("1")))
    return -cents if negative else cents


def parse_date(text: str) -> str | None:
    """A printed date as ISO 'YYYY-MM-DD', or None."""
    t = re.sub(r"\s+", " ", (text or "").strip().replace("Sept ", "Sep ")).replace(".", "")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_date_range(text: str) -> tuple[str, str] | None:
    """'03/01/2026 - 03/04/2026' or '2026-03-01 to 2026-03-04' -> (start, end); a single date gives (d, d)."""
    found = [parse_date(m) for m in DATE_IN_TEXT.findall(text or "")]
    found = [d for d in found if d]
    if not found:
        return None
    return (found[0], found[1]) if len(found) > 1 else (found[0], found[0])


def dollars(cents: int | None) -> float | None:
    """Cents back to ingest dollars."""
    return None if cents is None else float(Decimal(cents) / 100)


def today() -> str:
    return date.today().isoformat()
