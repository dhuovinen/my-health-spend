"""Replace identifiers in document text with vault tokens before it leaves the application tier (PRV-01, PRV-04).

Identifiers are normalized first (PRV-03), so "SMITH, PAT" and "Pat Smith" get one token and "W123-456" and
"W123456" another. This first scrubber knows the household's member names and aliases, labelled identifiers
(patient, member ID, account number, date of birth) and patterns (SSN, phone, email, street address); Presidio
can replace it behind the same interface (ADR-029, ADR-033).
"""

import re
from dataclasses import dataclass, field
from typing import Callable

from mhs.ingest.values import parse_date

Tokenize = Callable[[str, str], str]  # (kind, normalized value) -> token
SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}

LABELLED = [
    # (kind, label pattern); the value runs to the end of the line or to a wide gap before the next column.
    ("member_id", r"(?:member|subscriber|patient|insured|policy\s*holder)\s*(?:id|identification)\s*(?:number|no\.?|#)?"
                  r"|id\s*(?:number|no\.?|#)|health\s*plan\s*id"),
    ("account_number", r"(?:patient\s*)?(?:account|acct\.?)\s*(?:number|no\.?|#)?|guarantor\s*(?:number|no\.?|#)"),
    ("dob", r"date\s*of\s*birth|birth\s*date|dob"),
    ("ssn", r"ssn|social\s*security\s*(?:number|no\.?|#)?"),
    ("name", r"patient(?:\s*name)?|member(?:\s*name)?|subscriber(?:\s*name)?|insured(?:\s*name)?|guarantor(?:\s*name)?"
             r"|responsible\s*party|patient/member|for"),
]
LABEL_LINE = re.compile(r"(?P<label>\b(?:" + "|".join(f"(?:{p})" for _, p in LABELLED) + r"))\s*[:#]\s*(?P<value>[^\n]*?)"
                        r"(?=\s{3,}|\t|$)", re.I | re.M)
PATTERNS = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("phone", re.compile(r"(?<![\d$.,/-])(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b")),
    ("address", re.compile(r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?(?:[A-Z][a-zA-Z]+\s+){1,3}"
                           r"(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Blvd|Boulevard|Ct|Court|Way|Pl|Place|"
                           r"Pkwy|Parkway|Cir|Circle|Ter|Terrace|Hwy|Highway)\b\.?(?:,?\s+(?:Apt|Unit|Suite|Ste|#)\s*"
                           r"[\w-]+)?")),
]


def normalize(kind: str, value: str) -> str:
    """One spelling per identifier (PRV-03)."""
    v = value.strip()
    if kind == "name":
        if "," in v:  # "Smith, Pat A." -> "Pat A. Smith"
            last, _, first = v.partition(",")
            v = f"{first} {last}"
        parts = [p for p in re.sub(r"[^a-z0-9 ]+", " ", v.lower()).split()]
        suffix = [p for p in parts if p in SUFFIXES]
        parts = [p for p in parts if p not in SUFFIXES and len(p) > 1]  # drop middle initials
        return " ".join(parts + suffix)
    if kind in ("member_id", "account_number"):
        return re.sub(r"[\s.-]+", "", v).upper()
    if kind in ("ssn", "phone"):
        return re.sub(r"\D", "", v)[-10:] if kind == "phone" else re.sub(r"\D", "", v)
    if kind == "dob":
        return parse_date(v) or v
    if kind == "email":
        return v.lower()
    return re.sub(r"\s+", " ", v.lower())


def name_pattern(name: str) -> re.Pattern | None:
    """Matches a person's name as printed: any case, flexible spacing, optional middle initial, or 'Last, First'."""
    parts = normalize("name", name).split()
    parts = [p for p in parts if p not in SUFFIXES]
    if len(parts) < 2:
        return None
    first, last = re.escape(parts[0]), re.escape(parts[-1])
    middle = r"(?:\s+[a-z]\.?)?"
    return re.compile(rf"\b(?:{first}{middle}\s+{last}|{last}\s*,\s*{first}{middle})\b", re.I)


@dataclass
class Scrubbed:
    text: str
    tokens: dict[str, str] = field(default_factory=dict)  # token -> kind


class Scrubber:
    def __init__(self, tokenize: Tokenize, known_names: list[str]):
        self.tokenize = tokenize
        self.known_names = [n for n in known_names if n and n.strip()]

    def _token(self, out: Scrubbed, kind: str, value: str) -> str:
        token = self.tokenize(kind, normalize(kind, value))
        out.tokens[token] = kind
        return token

    def scrub(self, text: str) -> Scrubbed:
        out = Scrubbed(text)
        names = list(self.known_names)

        def labelled(m: re.Match) -> str:
            label, value = m.group("label"), m.group("value").strip()
            if not value or value.startswith("tok_"):
                return m.group(0)
            kind = next(k for k, p in LABELLED if re.fullmatch(p, label, re.I))
            if kind == "name":
                if not re.search(r"[A-Za-z]{2,}", value) or re.search(r"\d{2,}", value):
                    return m.group(0)  # "For: services in March" isn't a name
                names.append(value)
            elif kind == "dob" and not parse_date(value):
                return m.group(0)
            if kind != "name":
                found.append((kind, value))
            return m.group(0).replace(value, self._token(out, kind, value), 1)

        found: list[tuple[str, str]] = []  # labelled identifiers other than names
        out.text = LABEL_LINE.sub(labelled, out.text)
        for kind, value in found:  # the same identifier repeated elsewhere in the text, unlabelled
            if len(value) >= 4:
                out.text = re.sub(rf"(?<![\w-]){re.escape(value)}(?![\w-])",
                                  lambda m, k=kind, v=value: self._token(out, k, v), out.text)
        for name in sorted(set(names), key=len, reverse=True):
            if (pattern := name_pattern(name)) is not None:
                out.text = pattern.sub(lambda m: self._token(out, "name", m.group(0)), out.text)
        for kind, pattern in PATTERNS:
            out.text = pattern.sub(lambda m, k=kind: self._token(out, k, m.group(0)), out.text)
        return out
