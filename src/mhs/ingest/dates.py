"""Date shifting for content sent to outside AI services (PRV-05, ADR-022, ADR-034 condition).

Every date in the scrubbed text moves by one offset per person, in its printed format, so intervals between dates
stay intact (TC-PRV-05-1) and the model reads an ordinary document. The worker shifts the text just before the
AI call and shifts the dates in the answer back, so everything stored keeps real dates (TC-PRV-05-2). Offsets are
random, kept per household and person in the records database, and never sent anywhere.
"""

import re
import secrets
from datetime import date, datetime, timedelta

MIN_DAYS, MAX_DAYS = 30, 365
MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
# (pattern, strptime format, strftime format); the printed format is kept when shifting.
FORMATS = [
    (r"\b\d{4}-\d{2}-\d{2}\b", "%Y-%m-%d", "%Y-%m-%d"),
    (r"\b\d{1,2}/\d{1,2}/\d{4}\b", "%m/%d/%Y", "%m/%d/%Y"),
    (r"\b\d{1,2}/\d{1,2}/\d{2}\b(?!/)", "%m/%d/%y", "%m/%d/%y"),
    (r"\b\d{1,2}-\d{1,2}-\d{4}\b", "%m-%d-%Y", "%m-%d-%Y"),
    (rf"\b(?:{MONTHS})[a-z]*\.? \d{{1,2}}, \d{{4}}\b", None, None),
]
DATE_ANY = re.compile("|".join(f"(?:{p})" for p, _, _ in FORMATS))
TOKEN = re.compile(r"tok_[a-z2-7]{26}")
PERSON_LABEL = re.compile(r"(?im)\b(?:patient(?:\s*name)?|member(?:\s*name)?|guarantor|for|insured)\s*[:#]\s*(tok_[a-z2-7]{26})")


def _shift_one(raw: str, days: int) -> str:
    for pattern, parse, out in FORMATS:
        if re.fullmatch(pattern, raw):
            if parse is None:  # "Sep 28, 2026" or "September 28, 2026"
                long = len(raw.split()[0].rstrip(".")) > 3
                fmt = "%B %d, %Y" if long else "%b %d, %Y"
                try:
                    d = datetime.strptime(raw.replace(".", "").replace("Sept ", "Sep "), fmt).date()
                except ValueError:
                    return raw
                shifted = d + timedelta(days=days)
                return shifted.strftime(fmt).replace(" 0", " ")
            try:
                d = datetime.strptime(raw, parse).date()
            except ValueError:
                return raw  # not a real date (e.g. 13/45/2026): leave it
            shifted = (d + timedelta(days=days)).strftime(out)
            if parse.startswith("%m") and re.search(r"(?:^|[/-])\d(?:[/-]|$)", raw):
                shifted = re.sub(r"(^|[/-])0(\d)", r"\1\2", shifted)  # "9/5/2026" stays unpadded like the original
            return shifted
    return raw


def shift_text(text: str, days: int) -> str:
    """Every date in the text moved by `days`, each in its own printed format."""
    return DATE_ANY.sub(lambda m: _shift_one(m.group(0), days), text)


def shift_iso(value: str | None, days: int) -> str | None:
    if not value:
        return value
    try:
        return (date.fromisoformat(value) + timedelta(days=days)).isoformat()
    except ValueError:
        return value


def unshift_extraction(record: dict, days: int, date_fields: tuple[str, ...]) -> None:
    """Move the dates in an extraction record back by `days` (the answer was read in the shifted calendar)."""
    for name in date_fields:
        f = record.get("fields", {}).get(name)
        if f and isinstance(f.get("value"), str):
            f["value"] = shift_iso(f["value"], -days)
    for line in record.get("lines", []):
        if isinstance(line.get("service_date"), str):
            line["service_date"] = shift_iso(line["service_date"], -days)
    record["warnings"] = [shift_text(w, -days) for w in record.get("warnings", [])]


def person_key(text: str) -> str:
    """Whose dates these are: the patient's token, else the first token in the text, else the household."""
    if m := PERSON_LABEL.search(text):
        return m.group(1)
    if m := TOKEN.search(text):
        return m.group(0)
    return "household"


def new_offset() -> int:
    days = MIN_DAYS + secrets.randbelow(MAX_DAYS - MIN_DAYS + 1)
    return days if secrets.randbelow(2) else -days


def offset_for(records, key: str) -> int:
    """The person's offset in days, created on first use. `records` is the household's HouseholdRecords."""
    rec = records.get("date_offset", key)
    if rec is None:
        rec = {"id": key, "days": new_offset()}
        records.put("date_offset", rec)
    return rec["days"]
