"""Learning from the member's corrections, per document layout (ING-06, ADR-051).

Pure functions over scrubbed text (identifiers are already tokens) and extraction records. The worker records, for
each amount and date on a document, the words in front of it (`value_labels`); when the member confirms a corrected
field, the app keeps those words as that field's label for the layout (`learn`); the next document of the same
layout is read with them after the rules or the AI (`apply`). Hints are household records and never cross layouts.
"""

import re

from mhs.ingest.extract import DATE, MONEY
from mhs.ingest.values import parse_amount, parse_date

HINT = "layout_hint"  # household record kind
LEARNED = 0.9  # confidence of a field read with a learned label
MONEY_FIELDS = ("billed", "allowed", "adjustment", "insurer_paid", "deductible", "copay", "coinsurance", "not_covered",
                "patient_responsibility", "balance_due", "insurance_paid", "patient_paid")
DATE_FIELDS = ("service_start", "service_end", "processed_date", "statement_date", "due_date")
_TOKEN = re.compile(r"tok_[A-Za-z0-9_]+|\[[A-Z_]+\d*\]")
_VALUE = re.compile(rf"(?P<money>{MONEY})|(?P<date>{DATE})")


def _clean(label: str) -> str:
    label = _TOKEN.sub(" ", label)
    label = re.sub(r"[\s:#$|.\-–]+$", "", label)
    label = re.sub(r"\s+", " ", label).strip()
    words = label.split(" ")
    return " ".join(words[-5:]) if any(c.isalpha() for c in label) else ""


def layout_key(doc_type: str, text: str) -> str:
    """The document type and its issuer: the first line that names someone (the letterhead), normalized."""
    for line in text.splitlines():
        s = _TOKEN.sub("", line).strip()
        if len(s) > 3 and not re.search(r"[:$]|\d{2}/\d{2}|\d{4}-\d{2}|page \d", s, re.IGNORECASE) \
                and sum(c.isalpha() for c in s) >= 4:
            issuer = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]
            return f"{doc_type}:{issuer}"
    return f"{doc_type}:unknown"


def value_labels(text: str) -> dict[str, list[str]]:
    """Each amount (cents, as text) and date (ISO) on the document with the words in front of it on its line."""
    out: dict[str, list[str]] = {}
    for line in text.splitlines():
        start = 0
        for m in _VALUE.finditer(line):
            label = _clean(line[start:m.start()])
            start = m.end()
            if not label:
                continue
            key = str(parse_amount(m.group("money"))) if m.group("money") else parse_date(m.group("date"))
            if key and key != "None" and label not in out.setdefault(key, []):
                out[key].append(label)
    return out


def learn(extraction: dict, corrections: list[dict], hint: dict | None = None) -> dict | None:
    """The layout's hint updated with the labels behind the member's corrected values; None when nothing to learn."""
    labels = extraction.get("value_labels") or {}
    key = extraction.get("layout_key")
    if not key or not labels:
        return None
    fields = dict((hint or {}).get("fields") or {})
    changed = False
    for c in corrections:
        name, value = c.get("field"), c.get("confirmed")
        if name not in MONEY_FIELDS + DATE_FIELDS or value is None:
            continue
        found = labels.get(str(value))
        if found and len(found) == 1:  # a value printed behind one label only; two would be a guess
            fields[name] = found[0]
            changed = True
    if not changed:
        return None
    return {"id": hint_id(key), "layout": key, "fields": fields,
            "learned_from": int((hint or {}).get("learned_from", 0)) + 1}


def hint_id(key: str) -> str:
    return "hint-" + re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")[:80]


def apply(text: str, extraction: dict, hint: dict | None) -> list[str]:
    """Read each field the layout has a learned label for; returns the fields it filled or changed."""
    if not hint or hint.get("layout") != extraction.get("layout_key"):
        return []
    changed = []
    fields = extraction.setdefault("fields", {})
    for name, label in (hint.get("fields") or {}).items():
        pattern = MONEY if name in MONEY_FIELDS else DATE
        words = r"\s+".join(re.escape(w) for w in label.split(" "))
        m = re.search(rf"(?im){words}[\s:#$|.\-–]*({pattern})", _TOKEN.sub(" ", text))
        if not m:
            continue
        value = parse_amount(m.group(1)) if name in MONEY_FIELDS else parse_date(m.group(1))
        if value is None:
            continue
        current = fields.get(name) or {}
        if current.get("value") != value:
            fields[name] = {"value": value, "confidence": LEARNED,
                            "note": "read with the label you corrected on an earlier document from this sender"}
            changed.append(name)
    return changed
