"""Replace identifiers in document text with vault tokens before it leaves the application tier (PRV-01, PRV-04).

Identifiers are normalized first (PRV-03), so "SMITH, PAT" and "Pat Smith" get one token and "W123-456" and
"W123456" another. Two scrubbers, picked with MHS_SCRUBBER:

- `rules`: the household's member names and aliases, labelled identifiers (patient, member ID, account number,
  date of birth) and patterns (SSN, phone, email, street address).
- `presidio` (ADR-029): the same rules first, then Microsoft Presidio's entity detection (spaCy names and places,
  phone, email, SSN, card and bank numbers) for what the rules missed, such as a stranger's name in a letter.
  Presidio reads the original text once, so the same document always scrubs the same way. The household's own
  providers and insurers, and names with a word like Clinic or Imaging in them, are left in place, because
  extraction needs them.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
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
STATES = (r"(?:A[KLRZ]|C[AOT]|D[CE]|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEINOST]|N[CDEHJMVY]|O[HKR]|P[AR]|RI|S[CD]|"
          r"T[NX]|UT|V[AIT]|W[AIVY])")
ZIP = rf"{STATES}\s+\d{{5}}(?:-\d{{4}})?\b"
CITY = r"[A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)?"
# A person's name after words that introduce one ("Dear Aisha Okafor", "spoke with ...", "I, ..."); doctors are
# left to Presidio, and the household's providers are kept.
CUE_NAME = re.compile(r"(?:\b(?:Dear|Mr|Mrs|Ms|Mx|Miss|spoke (?:with|to)|on behalf of|husband|wife|spouse|son|daughter|"
                      r"mother|father|guardian)\.?|\bI,)[ \t]+(?P<name>[A-Z][a-z'’-]+(?:[ \t]+[A-Z]\.)?"
                      r"(?:[ \t]+[A-Z][a-z'’-]+){1,2})\b")
PATTERNS = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("phone", re.compile(r"(?<![\d$.,/-])(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b")),
    ("address", re.compile(r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?(?:[A-Z][a-zA-Z]+\s+){1,3}"
                           r"(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Blvd|Boulevard|Ct|Court|Way|Pl|Place|"
                           r"Pkwy|Parkway|Cir|Circle|Ter|Terrace|Hwy|Highway)\b\.?(?:,?\s+(?:Apt|Unit|Suite|Ste|#)\s*"
                           r"[\w-]+)?" rf"(?:,\s*{CITY}(?=,|\s*$|\s+{STATES}\b))?(?:,?\s+{ZIP})?", re.M)),
    ("address", re.compile(rf"\b{CITY},\s+{ZIP}|(?<=, ){ZIP}")),  # city, state and ZIP on their own
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
    found: list[tuple[str, str]] = field(default_factory=list)  # (kind, text as printed) of every replacement


class Scrubber:
    """The rules scrubber. `keep` lists names that aren't identifiers here (the household's providers, insurers)."""

    name = "rules"

    def __init__(self, tokenize: Tokenize, known_names: list[str], keep: list[str] = ()):
        self.tokenize = tokenize
        self.known_names = [n for n in known_names if n and n.strip()]
        self.keep = [k for k in keep if k and k.strip()]

    def _kept(self, value: str) -> bool:
        """A provider or insurer the household already has, which isn't an identifier: the whole name, or at
        least two words of it ("Lakeside Family" of "Lakeside Family Medicine"). One word alone isn't enough."""
        v = normalize("other", value)
        if not v:
            return True
        for k in (normalize("other", k) for k in self.keep):
            if k in v or (v in k and len(v.split()) >= 2):
                return True
        return False

    def _token(self, out: Scrubbed, kind: str, value: str) -> str:
        token = self.tokenize(kind, normalize(kind, value))
        out.tokens[token] = kind
        out.found.append((kind, value))
        return token

    def scrub(self, text: str) -> Scrubbed:
        return self._rules(text)[0]

    def _rules(self, text: str) -> tuple[Scrubbed, "_Edited"]:
        out, edited = Scrubbed(text), _Edited(text)
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
        edited.sub(LABEL_LINE, labelled)
        names += [m.group("name") for m in CUE_NAME.finditer(edited.text) if not self._kept(m.group("name"))]
        for kind, value in found:  # the same identifier repeated elsewhere in the text, unlabelled
            if len(value) >= 4:
                edited.sub(re.compile(rf"(?<![\w-]){re.escape(value)}(?![\w-])"),
                           lambda m, k=kind, v=value: self._token(out, k, v))
        for name in sorted(set(names), key=len, reverse=True):
            if (pattern := name_pattern(name)) is not None:
                edited.sub(pattern, lambda m: self._token(out, "name", m.group(0)))
        for kind, pattern in PATTERNS:
            edited.sub(pattern, lambda m, k=kind: self._token(out, k, m.group(0)))
        out.text = edited.text
        return out, edited


class _Edited:
    """Text being scrubbed, and where each of its characters was in the original (None inside a token), so a span
    found on the original text can still be placed after the rules have replaced other parts of it."""

    def __init__(self, text: str):
        self.text = text
        self.origin: list[int | None] = list(range(len(text)))

    def sub(self, pattern: re.Pattern, repl: Callable[[re.Match], str]) -> None:
        """pattern.sub(repl, text), keeping track of the original offsets of what's left."""
        text, origin, pos = [], [], 0
        for m in pattern.finditer(self.text):
            old, new = m.group(0), repl(m)
            if new == old:
                continue
            head = len(os.path.commonprefix([old, new]))  # a label kept in front of its value stays original
            tail = len(os.path.commonprefix([old[head:][::-1], new[head:][::-1]]))
            text += [self.text[pos:m.start()], new]
            origin += (self.origin[pos:m.start() + head] + [None] * (len(new) - head - tail)
                       + self.origin[m.end() - tail:m.end()])
            pos = m.end()
        text.append(self.text[pos:])
        origin += self.origin[pos:]
        self.text, self.origin = "".join(text), origin

    def _at(self, start: int, end: int) -> int | None:
        """Where original[start:end] is in the text now, if none of it has been replaced."""
        try:
            at = self.origin.index(start)
        except ValueError:
            return None
        return at if self.origin[at:at + end - start] == list(range(start, end)) else None

    def intact(self, start: int, end: int) -> bool:
        return self._at(start, end) is not None

    def replace(self, start: int, end: int, new: str) -> None:
        at = self._at(start, end)
        self.text = self.text[:at] + new + self.text[at + end - start:]
        self.origin[at:at + end - start] = [None] * len(new)


# --- Presidio (ADR-029) ------------------------------------------------------------------------

SPACY_MODEL = "en_core_web_md"
ENTITIES = {  # Presidio entity -> vault kind. Dates stay (ADR-022); driver's licence and URL rules are too noisy.
    "PERSON": "name", "PHONE_NUMBER": "phone", "EMAIL_ADDRESS": "email", "US_SSN": "ssn", "US_ITIN": "ssn",
    "CREDIT_CARD": "card_number", "US_BANK_NUMBER": "account_number", "IBAN_CODE": "account_number",
    "LOCATION": "address",
}
MIN_SCORE = {"PHONE_NUMBER": 0.4, "US_BANK_NUMBER": 0.4}
DEFAULT_MIN_SCORE = 0.5
# Words that make a name a practice, lab or facility rather than a person or a place. spaCy reads a practice named
# after its founder ("Kessler Orthopedics", "Bennett Radiology") as a person.
ORG_WORDS = re.compile(
    r"\b(?:associates|care|cardiology|center|centre|chiropractic|clinics?|dental|dentistry|dermatology|diagnostics|"
    r"group|health|healthcare|hospitals?|imaging|labs?|laborator(?:y|ies)|medical|medicine|oncology|optometry|"
    r"orthopa?edics|partners|pathology|pediatrics|pharmacy|physicians|podiatry|practice|radiology|rehab(?:ilitation)?|"
    r"surgery|surgical|therapy|urology|inc|llc|pllc)\b", re.I)


@lru_cache(maxsize=1)
def presidio_analyzer():
    """Loaded once per process (the spaCy model takes a second or two)."""
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)  # it warns about every unmapped spaCy label
    nlp = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": SPACY_MODEL}],
    }).create_engine()
    return AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    """Presidio's spans can run past the value: stop at a line break or a column gap, drop edge punctuation."""
    span = text[start:end]
    cut = re.search(r"\n|\s{3,}|\t", span)
    if cut:
        end = start + cut.start()
    while end > start and not text[end - 1].isalnum() and text[end - 1] != ".":
        end -= 1
    while start < end and not text[start].isalnum() and text[start] not in "(+":
        start += 1
    return start, end


class PresidioScrubber(Scrubber):
    name = "presidio"

    def __init__(self, tokenize: Tokenize, known_names: list[str], keep: list[str] = (), analyzer=None):
        super().__init__(tokenize, known_names, keep)
        self.analyzer = analyzer or presidio_analyzer()

    def _spans(self, text: str) -> list[tuple[int, int, str, str]]:
        """(start, end, kind, value) for each entity Presidio finds that isn't a token or a kept name."""
        spans = []
        for r in self.analyzer.analyze(text, language="en", entities=list(ENTITIES)):
            if r.score < MIN_SCORE.get(r.entity_type, DEFAULT_MIN_SCORE):
                continue
            start, end = _trim(text, r.start, r.end)
            value = text[start:end]
            if len(value) < 2 or "tok_" in value:
                continue
            if r.entity_type in ("PERSON", "LOCATION") and (self._kept(value) or _organisation(text, start, end)):
                continue
            spans.append((start, end, ENTITIES[r.entity_type], value))
        return _non_overlapping(spans)

    def scrub(self, text: str) -> Scrubbed:
        # Presidio reads the original text, once. Run on text that already holds random tokens, spaCy's answer
        # changed from upload to upload: a bare letterhead above a tokenized address read as a person about one
        # time in four, and the visit lost its provider.
        spans = self._spans(text)
        # People Presidio finds join the known names first, so the rules catch every spelling of them
        # ("Maria Gonzalez", "GONZALEZ, MARIA") under one token (PRV-03).
        people = [v for _, _, kind, v in spans if kind == "name" and len(v.split()) > 1]
        rules = Scrubber(self.tokenize, self.known_names + people, self.keep)
        out, edited = rules._rules(text)
        for start, end, kind, value in spans:  # what the rules missed, where they left it whole
            if edited.intact(start, end):
                edited.replace(start, end, self._token(out, kind, value))
        out.text = edited.text
        return out


def _organisation(text: str, start: int, end: int) -> bool:
    """The name, with any capitalized words right after it on the line ("Greene Physical" + "Therapy"), is a
    practice, lab or facility. Extraction needs those, and they aren't the household's identifiers."""
    after = re.match(r"(?: [A-Z][\w&'’.-]*)*", text[end:]).group(0)
    return ORG_WORDS.search(text[start:end] + after) is not None


def _non_overlapping(spans: list[tuple]) -> list[tuple]:
    """Longest span wins where Presidio's recognizers overlap."""
    chosen: list[tuple] = []
    for s in sorted(spans, key=lambda s: (s[1] - s[0]), reverse=True):
        if all(s[1] <= c[0] or s[0] >= c[1] for c in chosen):
            chosen.append(s)
    return chosen


SCRUBBERS: dict[str, type[Scrubber]] = {"rules": Scrubber, "presidio": PresidioScrubber}


def scrubber_class(name: str = "rules") -> type[Scrubber]:
    try:
        cls = SCRUBBERS[name]
    except KeyError:
        raise ValueError(f"unknown scrubber {name!r}; known: {', '.join(SCRUBBERS)}") from None
    if cls is PresidioScrubber:
        presidio_analyzer()  # load the model now, so a broken install fails at start-up, not on an upload
    return cls
