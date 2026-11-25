"""Read an insurance card from its OCR text (ING-11, ADR-061). Pure functions: no OCR, database or web imports.

The front and the back are text (one string per side). The rules look for the labels cards use ("Member ID",
"Group", "RxBIN", "Subscriber", "PCP $30", "Eff. Date", "Payer ID"), the shape of the value next to or under a label,
and position (the insurer in the top band of the front, phone numbers and addresses on the back). Every field comes
back with a confidence from 0 to 1: a label with a value of the right shape is high, a shape found without its label
or a position-only guess is low, and a field the rules don't find is simply absent. Nothing is guessed.

The caller (the application tier) turns identifier fields (`IDENTIFIER_FIELDS`, person names) into vault tokens
before anything is stored; this module never stores or sends anything.
"""

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from mhs.ingest.values import parse_date

REFERENCE = Path(__file__).resolve().parent.parent / "data" / "reference" / "insurers.json"

# Fields whose values are identifiers (PRV-01): the application tier stores them only as vault tokens.
IDENTIFIER_FIELDS = ("group_number", "member_number", "rx_group")

HIGH, MEDIUM, LOW = 0.92, 0.75, 0.5  # label + shape, label with the value on the next line, shape or position only
CHECK_BELOW = 0.7  # the review marks a field "check" under this
MIN_SIGNALS = 2  # fewer recognized signals than this: "this doesn't look like an insurance card"

NAME_WORD = r"[A-Za-z][A-Za-z'.-]*"
NAME = rf"{NAME_WORD}(?:[ ]+{NAME_WORD}){{1,3}}"
# Words that end a name when OCR puts the next label on the same line after a single space.
NAME_STOP = {"member", "id", "group", "grp", "subscriber", "dependents", "dependent", "eff", "effective", "plan",
             "date", "rx", "rxbin", "rxpcn", "rxgrp", "payer", "copay", "pcp", "dob", "coverage", "number", "no"}
PHONE = r"(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}"
ZIP_LINE = r"[A-Za-z][A-Za-z .'-]+,?\s+[A-Z]{2}\s+\d{5}(?:-\d{4})?"
ADDRESS = rf"(?:P\.?\s?O\.?\s*Box\s+\d+|\d{{1,6}}\s+[A-Za-z0-9 .'-]+?)(?:,|\s{{2,}}|\s)\s*{ZIP_LINE}"
URL = re.compile(r"\b(?:https?://)?(?:www\.)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[a-z]{2,}(?:/[\w./-]*)?", re.I)

SERVICES = {  # plan.copays key -> label pattern; the value is the first $ amount after the label
    "primary_care": r"\b(?:PCP|Primary(?:\s+Care)?|Office\s+Visit)\b",
    "specialist": r"\b(?:Spec(?:ialist)?\.?|SPC)\b",
    "urgent_care": r"\b(?:UC|Urgent\s+Care)\b",
    "emergency": r"\b(?:ER|Emergency(?:\s+Room)?)\b",
    "preventive": r"\bPreventive\b",
}
CONTACT_LABELS = [  # (pattern, label), first match wins
    (r"provider\s+(?:services|service|support)", "Provider services"),
    (r"pharmacy|\brx\b|prescription", "Pharmacy help"),
    (r"nurse|24\s*/\s*7|health\s*line", "Nurse line"),
    (r"prior\s*auth|pre-?cert|pre-?auth", "Prior authorization"),
    (r"behavioral|mental|substance", "Behavioral health"),
    (r"member\s+(?:services|service|support)|customer\s+(?:service|care)|for\s+members", "Member services"),
    (r"claims?", "Claims"),
    (r"tty|hearing", "TTY"),
]
COVERAGE_MARKERS = r"\b(?:copay|pcp|rxbin|rx\s*bin|medical|hospital|deductible|member\s+id|ppo|hmo|epo|pos)\b"


@dataclass
class Field:
    value: object
    confidence: float
    side: str = "front"  # which side of the card it came from

    @property
    def check(self) -> bool:
        return self.confidence < CHECK_BELOW


@dataclass
class Person:
    name: str
    role: str = "member"  # member, subscriber or dependent
    subscriber: bool = False
    member_number: Field | None = None
    confidence: float = HIGH


@dataclass
class Contact:
    label: str
    phone: str = ""
    address: str = ""
    url: str = ""
    confidence: float = HIGH


@dataclass
class CardReading:
    kind: str = "medical"  # medical, dental, vision (refused) or unknown
    looks_like_card: bool = False
    fields: dict[str, Field] = field(default_factory=dict)  # insurer, plan_name, plan_type, group_number, ...
    copays: dict[str, Field] = field(default_factory=dict)  # service type -> cents
    limits: list[dict] = field(default_factory=list)  # {type, level, amount (cents), confidence}
    people: list[Person] = field(default_factory=list)
    contacts: list[Contact] = field(default_factory=list)
    has_back: bool = False
    refusal: str = ""  # why the card isn't read (vision, not a card), in plain words

    def value(self, key: str):
        f = self.fields.get(key)
        return f.value if f else None


@lru_cache(maxsize=1)
def insurers() -> list[dict]:
    return json.loads(REFERENCE.read_text())["insurers"]


def lines_of(text: str) -> list[str]:
    return [re.sub(r"[ \t]+$", "", ln).lstrip() for ln in (text or "").replace("\f", "\n").splitlines() if ln.strip()]


def _trim_name(raw: str) -> str:
    words = []
    for w in raw.split():
        if w.lower().strip(".:") in NAME_STOP:
            break
        words.append(w)
    return " ".join(words)


def tidy_name(name: str) -> str:
    """'PAT SAMPLE' -> 'Pat Sample'; a name already in mixed case stays as printed."""
    return " ".join(w.capitalize() for w in name.split()) if name.isupper() else name


def _is_name(text: str) -> bool:
    words = text.split()
    return 2 <= len(words) <= 4 and all(re.fullmatch(NAME_WORD, w) and w.lower().strip(".") not in NAME_STOP
                                        for w in words)


def _after(lines: list[str], label: str, value: str, flags=re.I) -> tuple[str, float] | None:
    """The value after a label on the same line (high confidence) or at the start of the next line (medium)."""
    pattern = re.compile(rf"(?:{label})\s*[:#]?\s*(?P<v>{value})", flags)
    only_label = re.compile(rf"(?:{label})\s*[:#]?\s*$", flags)
    for i, ln in enumerate(lines):
        m = pattern.search(ln)
        if m and m.group("v"):
            return m.group("v").strip(), HIGH
        if only_label.search(ln) and i + 1 < len(lines):
            m = re.match(rf"\s*(?P<v>{value})", lines[i + 1], flags)
            if m:
                return m.group("v").strip(), MEDIUM
    return None


def _clean_id(raw: str) -> str | None:
    """A member or group number as the card prints it: 8 to 14 letters and digits with an optional -NN suffix."""
    value = raw.strip().strip(".,;:").upper()
    base = re.sub(r"-\d{2}$", "", value)
    if re.fullmatch(r"[A-Z0-9]{8,14}", base) and re.search(r"\d", base):
        return value
    return None


def _money(raw: str) -> int | None:
    try:
        return int(round(float(raw.replace(",", "")) * 100))
    except ValueError:
        return None


def _read_insurer(front: list[str], reading: CardReading, text: str) -> None:
    top = front[:6]
    for entry in insurers():
        for alias in sorted(entry["aliases"], key=len, reverse=True):
            if any(re.search(rf"\b{re.escape(alias)}\b", ln, re.I) for ln in top):
                reading.fields["insurer"] = Field(entry["name"], 0.95)
                return
    for ln in top[:4]:
        if ln.endswith(":") or ":" in ln or re.search(r"\d", ln) or not 1 <= len(ln.split()) <= 6:
            continue
        if re.search(r"\b(?:member|id|group|card|copay|rx|subscriber)\b", ln, re.I):
            continue
        reading.fields["insurer"] = Field(ln.strip(), LOW + 0.1)
        return


def _read_plan(front: list[str], reading: CardReading, text: str) -> None:
    insurer = reading.value("insurer")
    m = re.search(r"\b(PPO|HMO|EPO|POS|HDHP)\b", "\n".join(front[:10]), re.I)
    if m:
        reading.fields["plan_type"] = Field(m.group(1).upper(), HIGH)
    if re.search(r"\bHDHP\b|high[- ]deductible|\bHSA[- ]?(?:eligible|qualified|compatible)\b", text, re.I):
        reading.fields["hsa_eligible_plan"] = Field(True, MEDIUM)
    for ln in front[:8]:
        if ln == insurer or ":" in ln or re.search(r"\d", ln) or len(ln.split()) > 6:
            continue
        if insurer and ln.lower() == str(insurer).lower():
            continue
        if re.search(r"\b(?:plan|ppo|hmo|epo|pos|choice|select|advantage|medical|dental|care|connect)\b", ln, re.I) \
                and not re.search(r"\b(?:member|group|card|id)\b", ln, re.I):
            if insurer and ln.lower().startswith(str(insurer).lower()) and ln.lower() != str(insurer).lower():
                ln = ln[len(str(insurer)):].strip() or ln
            reading.fields["plan_name"] = Field(ln.strip(), MEDIUM)
            return


def _names_after(lines: list[str], label: str):
    """Every person's name that follows a label, on its line or the next one."""
    for i, ln in enumerate(lines):
        for m in re.finditer(rf"(?:{label})\s*[:]\s*(?P<v>{NAME})", ln, re.I):
            name = _trim_name(m.group("v"))
            if _is_name(name):
                yield name, HIGH
        if re.search(rf"(?:{label})\s*[:]?\s*$", ln, re.I) and i + 1 < len(lines):
            name = _trim_name(lines[i + 1])
            if _is_name(name):
                yield name, MEDIUM


def _read_people(front: list[str], reading: CardReading) -> None:
    people: dict[str, Person] = {}

    def person(name: str, role: str, conf: float) -> Person:
        key = " ".join(name.lower().split())
        p = people.get(key)
        if p is None:
            p = people[key] = Person(tidy_name(name), role, confidence=conf)
        return p

    for label, role in ((r"(?<![A-Za-z])(?:Member|Insured|Patient)(?:\s+Name)?|(?<!Plan )(?<![A-Za-z])Name", "member"),
                        (r"Subscriber(?:\s+Name)?|Policy\s*holder", "subscriber")):
        for name, conf in _names_after(front, label):
            p = person(name, role, conf)
            if role == "subscriber":
                p.subscriber = True
                if p.role == "member" and not p.member_number and len(people) > 1:
                    pass
            break
    for i, ln in enumerate(front):
        m = re.search(rf"\bDep(?:endent)?s?\.?(?:\s*\(\w+\))?\s*:\s*(?P<v>[^\n]*?)(?=\s{{3,}}|$)", ln, re.I)
        if not m:
            continue
        chunk = [m.group("v")]
        for nxt in front[i + 1:i + 4]:  # a list of names can continue on the lines below
            if ":" not in nxt and not re.search(r"\d", nxt) and _is_name(_trim_name(nxt.split(",")[0])):
                chunk.append(nxt)
            else:
                break
        for part in re.split(r"[,;/]|\s+and\s+|\s*&\s*", ", ".join(chunk)):
            name = _trim_name(part.strip())
            if _is_name(name):
                person(name, "dependent", HIGH if m.group("v").strip() else MEDIUM)
    # A row that names a person with an ID printed beside it ("PAT SAMPLE   XJK123456789-01").
    for ln in front:
        m = re.search(rf"(?P<n>{NAME})\s{{2,}}(?P<id>[A-Z0-9]{{8,14}}-\d{{2}})\b", ln)
        if m and _is_name(_trim_name(m.group("n"))) and _clean_id(m.group("id")):
            name = _trim_name(m.group("n"))
            p = person(name, "member", MEDIUM)
            p.member_number = Field(_clean_id(m.group("id")), HIGH)
    reading.people = list(people.values())


def _read_ids(front: list[str], back: list[str], reading: CardReading) -> None:
    for side, lines in (("front", front), ("back", back)):
        found = _after(lines, r"(?:Member|Subscriber|Insured|Policy)\s*(?:ID|Number|No\.?|#)|(?<![A-Za-z])(?<!Payer )(?<!Group )ID\s*(?:#|Number|No\.?)?",
                       r"[A-Za-z0-9-]{8,16}")
        clean = _clean_id(found[0]) if found else None
        if clean and "member_number" not in reading.fields:
            reading.fields["member_number"] = Field(clean, found[1], side)
        group = _after(lines, r"(?<!Rx)(?<!Rx )\b(?:Group|Grp)\s*(?:Number|No\.?|#)?", r"[A-Za-z0-9-]{4,14}")
        if group and "group_number" not in reading.fields and re.search(r"\d", group[0]) \
                and not group[0].lower().startswith(("number", "name")):
            reading.fields["group_number"] = Field(group[0].upper().strip("-"), group[1], side)
        payer = _after(lines, r"Payer\s*ID", r"[A-Za-z0-9]{3,10}")
        if payer and "payer_id" not in reading.fields:
            reading.fields["payer_id"] = Field(payer[0].upper(), payer[1], side)
        for key, label, value in (("rx_bin", r"Rx\s*BIN", r"[0-9OIl]{6}"), ("rx_pcn", r"Rx\s*PCN", r"[A-Za-z0-9]{2,12}"),
                                  ("rx_group", r"Rx\s*(?:Grp|Group)", r"[A-Za-z0-9]{3,12}")):
            got = _after(lines, label, value)
            if got and key not in reading.fields:
                v = got[0].upper()
                if key == "rx_bin":
                    v = v.replace("O", "0").replace("I", "1").replace("L", "1")
                reading.fields[key] = Field(v, got[1], side)
    if "member_number" not in reading.fields and reading.people:
        withid = next((p for p in reading.people if p.member_number), None)
        if withid:
            reading.fields["member_number"] = Field(withid.member_number.value, MEDIUM)
    holder = next((p for p in reading.people if p.role == "member"), None) or (reading.people[0] if reading.people else None)
    number = reading.fields.get("member_number")
    if holder and number and holder.member_number is None:
        holder.member_number = Field(number.value, number.confidence, number.side)
    if not any(p.subscriber for p in reading.people) and holder:
        sub = _after(front, r"Subscriber(?:\s+Name)?", NAME)
        if sub is None and reading.people and len(reading.people) == 1:
            pass  # one person on the card: not marked subscriber unless the card says so


def _read_money_terms(front: list[str], reading: CardReading) -> None:
    for key, label in SERVICES.items():
        pattern = re.compile(rf"{label}[^$\n]{{0,28}}?\$\s*(\d{{1,4}}(?:\.\d\d)?)", re.I)
        for ln in front:
            m = pattern.search(ln)
            if m:
                cents = _money(m.group(1))
                if cents is not None:
                    reading.copays[key] = Field(cents, HIGH)
                break
    for ln in front:
        for kind, label in (("deductible", r"Deductible|Ded\."), ("out_of_pocket_max",
                                                                  r"Out[- ]of[- ]Pocket(?:\s+Max(?:imum)?)?|OOP(?:\s+Max)?")):
            head = re.search(rf"(?:{label})", ln, re.I)
            if not head:
                continue
            rest = ln[head.end():]
            # "Deductible Individual $3,200   Family $6,400": one label, an amount per level
            pairs = re.findall(r"(?:\(?(Ind(?:ividual)?|Fam(?:ily)?)\.?\)?\s*)?[:]?\s*\$\s*([\d,]{2,9}(?:\.\d\d)?)", rest, re.I)
            for lvl, amount in pairs:
                cents = _money(amount)
                level = "family" if lvl.lower().startswith("fam") else "individual"
                if cents and not any(x["type"] == kind and x["level"] == level for x in reading.limits):
                    reading.limits.append({"type": kind, "level": level, "network": "in_network", "amount": cents,
                                           "confidence": HIGH})
    coins = re.search(r"Coins(?:urance)?\s*[:]?\s*(\d{1,2})\s*%", "\n".join(front), re.I)
    if coins:
        reading.fields["coinsurance_pct"] = Field(int(coins.group(1)), HIGH)


def _read_dates(front: list[str], reading: CardReading) -> None:
    got = _after(front, r"Eff(?:ective)?\.?\s*(?:Date)?|Coverage\s*(?:Start|Begins)|Issued", r"[A-Za-z0-9/,. -]{6,20}")
    if got:
        m = re.match(r"(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}-\d{1,2}-\d{4}|[A-Za-z]{3,9}\.? \d{1,2}, \d{4})",
                     got[0])
        iso = parse_date(m.group(1)) if m else None
        if iso:
            reading.fields["effective_date"] = Field(iso, got[1])


def _contact_label(before: str, previous: str) -> str:
    for text in (before, previous):
        for pattern, label in CONTACT_LABELS:
            if re.search(pattern, text, re.I):
                return label
    text = re.sub(r"[^A-Za-z/ ]", " ", before).strip()
    return " ".join(text.split()[:5]).capitalize() or "Phone"


def _read_contacts(front: list[str], back: list[str], reading: CardReading) -> None:
    seen: set[tuple[str, str]] = set()
    for lines in (back, front):
        for i, ln in enumerate(lines):
            for m in re.finditer(PHONE, ln):
                digits = re.sub(r"\D", "", m.group(0))[-10:]
                before = ln[:m.start()].strip(" :-.\t")
                previous = lines[i - 1] if i and not re.search(PHONE, lines[i - 1]) and not before else ""
                label = _contact_label(before, previous)
                if (label, digits) in seen or re.search(r"\b(?:fax)\b", before, re.I):
                    continue
                seen.add((label, digits))
                reading.contacts.append(Contact(label, phone=f"{digits[:3]}-{digits[3:6]}-{digits[6:]}",
                                                confidence=HIGH if before or previous else MEDIUM))
    for lines in (back, front):
        for i, ln in enumerate(lines):
            m = re.search(rf"(?P<l>Claims?|Submit\s+claims\s+to|Appeals?|Grievances?)[^:\n]{{0,25}}:\s*(?P<v>.*)$", ln, re.I)
            if not m:
                continue
            parts = [m.group("v").strip()] if m.group("v").strip() else []
            for nxt in lines[i + 1:i + 4]:  # the address can run over the next lines, ending at the ZIP
                if re.search(r"\b[A-Z]{2}\s+\d{5}", ", ".join(parts)) or ":" in nxt or re.search(PHONE, nxt):
                    break
                parts.append(nxt.strip())
            value = ", ".join(parts)
            if re.search(r"\b[A-Z]{2}\s+\d{5}", value):
                label = "Appeals address" if re.match(r"appeal|grievance", m.group("l"), re.I) else "Claims address"
                if not any(c.label == label for c in reading.contacts):
                    reading.contacts.append(Contact(label, address=re.sub(r"\s{2,}", " ", value), confidence=HIGH))
    site = next((URL.search(ln) for ln in back + front if URL.search(ln)), None)
    if site:
        reading.contacts.append(Contact("Website", url=site.group(0), confidence=HIGH))
    for ln in back + front:
        m = re.search(r"\bNetwork\s*:\s*(?P<v>[^\n]{2,60}?)(?=\s{3,}|$)", ln, re.I)
        if m:
            reading.contacts.append(Contact("Network", address=m.group("v").strip(), confidence=MEDIUM))
            break


def _kind(front: list[str], back: list[str], text: str) -> str:
    top = " ".join(front[:8])
    medical = bool(re.search(r"rx\s*bin|\bpcp\b|\bmedical\b|\bppo\b|\bhmo\b|\bepo\b", text, re.I))
    if re.search(r"\bdental\b", top, re.I) and not re.search(r"rx\s*bin|\bmedical\b", top, re.I):
        return "dental"
    if re.search(r"\bvision\b|\beye\s*care\b", top, re.I) and not medical:
        return "vision"
    return "medical"


def read_card(front_text: str, back_text: str = "", ocr_confidence: float = 1.0) -> CardReading:
    """The reading of one card. `ocr_confidence` (0 to 1, the engine's mean word confidence) scales every field, so a
    poor photo marks more fields "check" instead of passing them as sure."""
    front, back = lines_of(front_text), lines_of(back_text)
    both = "\n".join(front + back)
    reading = CardReading(has_back=bool(back))
    reading.kind = _kind(front, back, both)
    if reading.kind == "vision":
        reading.refusal = "CareBack reads medical and dental cards. Type a vision plan in on Coverage."
        return reading
    _read_insurer(front, reading, both)
    _read_plan(front, reading, both)
    _read_ids(front, back, reading)
    _read_people(front, reading)
    _read_ids(front, back, reading)  # again: a person's row may have supplied the member ID
    _read_money_terms(front, reading)
    _read_dates(front, reading)
    _read_contacts(front, back, reading)
    if re.search(r"\bsecondary\b|\bsupplement(?:al)?\b", " ".join(front[:8]), re.I):
        reading.fields["coverage_order"] = Field("secondary", LOW)
    if reading.kind == "dental":
        reading.fields["coverage_kind"] = Field("dental", HIGH)
    signals = sum(k in reading.fields for k in ("member_number", "group_number", "rx_bin", "plan_type",
                                                 "effective_date", "payer_id")) \
        + bool(reading.copays) + bool(reading.contacts) + (reading.fields.get("insurer") is not None
                                                           and reading.fields["insurer"].confidence >= 0.9)
    reading.looks_like_card = signals >= MIN_SIGNALS
    if not reading.looks_like_card:
        reading.refusal = "This doesn't look like an insurance card. Try a clearer photo, or type the plan in on Coverage."
    if ocr_confidence < 1.0:
        scale = max(0.0, min(1.0, ocr_confidence))
        for f in list(reading.fields.values()) + list(reading.copays.values()):
            f.confidence = round(f.confidence * scale, 2)
        for lim in reading.limits:
            lim["confidence"] = round(lim["confidence"] * scale, 2)
        for p in reading.people:
            p.confidence = round(p.confidence * scale, 2)
            if p.member_number:
                p.member_number.confidence = round(p.member_number.confidence * scale, 2)
        for c in reading.contacts:
            c.confidence = round(c.confidence * scale, 2)
    return reading


def public_contact_lines(text: str) -> set[int]:
    """Indexes (in `lines_of(text)`) of the lines that are the insurer's public contact details: a labelled phone
    number, the claims or appeals address, a website, the payer ID or the network. The scrubber keeps these (ADR-061);
    everything else on a card is the member's."""
    lines = lines_of(text)
    keep: set[int] = set()
    label = re.compile("|".join(p for p, _ in CONTACT_LABELS) + r"|payer\s*id|network|appeals?|grievances?|submit\s+claims", re.I)
    for i, ln in enumerate(lines):
        if re.search(r"member\s*id|subscriber|group|dependents?|rx\s*(?:bin|pcn|grp|group)", ln, re.I):
            continue
        if URL.search(ln):
            keep.add(i)
        if label.search(ln) and not re.search(r"member\s*(?:id|name)", ln, re.I):
            keep.add(i)
            tail = i
            for j in range(i + 1, min(i + 4, len(lines))):  # the number or address under a label-only line
                if ":" in lines[j] or label.search(lines[j]):
                    break
                keep.add(j)
                tail = j
                if re.search(r"\b[A-Z]{2}\s+\d{5}", lines[j]) or re.search(PHONE, lines[j]):
                    break
    return keep


def reading_dict(reading: CardReading, tokenize) -> dict:
    """The reading as a JSON-safe dict for the scan record, with every identifier (member IDs, group number,
    pharmacy group, people's names) replaced by `tokenize(kind, value)`: only tokens are stored (ADR-061)."""
    def fld(f: Field, kind: str | None = None) -> dict:
        value = f.value
        if kind and isinstance(value, str):
            value = tokenize(kind, value)
        return {"value": value, "confidence": f.confidence, "side": f.side}

    kinds = {"group_number": "group_number", "member_number": "member_id", "rx_group": "group_number"}
    return {
        "kind": reading.kind, "looks_like_card": reading.looks_like_card, "has_back": reading.has_back,
        "refusal": reading.refusal,
        "fields": {k: fld(f, kinds.get(k)) for k, f in reading.fields.items()},
        "copays": {k: fld(f) for k, f in reading.copays.items()},
        "limits": list(reading.limits),
        "people": [{"name": tokenize("name", p.name), "role": p.role, "subscriber": p.subscriber,
                    "confidence": p.confidence,
                    "member_number": fld(p.member_number, "member_id") if p.member_number else None}
                   for p in reading.people],
        "contacts": [{"label": c.label, "phone": c.phone, "address": c.address, "url": c.url,
                      "confidence": c.confidence} for c in reading.contacts],
    }
