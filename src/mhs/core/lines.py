"""Line-level money: the adjudication and cost-sharing identities, adjudication buckets, bill-to-EOB line pairing
and duplicate charges (REC-01, ALC-01, MAT-06, REC-04; ADR-014, ADR-035).

Pure functions over plain record dicts (money in integer cents). No database or web imports.
"""

import re
from dataclasses import dataclass, field
from itertools import combinations

TOLERANCE = 100  # ADR-015: a difference under $1.00 per check is cleared within tolerance
TOLERANCE_CAP = 500  # cleared amounts per provider per plan year are flagged past $5.00

COST_SHARE = ("deductible", "copay", "coinsurance", "not_covered")
# ALC-01 adjudication buckets, in the order they are shown. Settlement items (payments, write-offs, still owed)
# never appear here (ADR-014).
BUCKETS = {
    "plan_adjustment": "Plan discount",
    "other_savings": "Other savings",
    "primary_paid": "Insurer paid",
    "secondary_paid": "Second insurer paid",
    "deductible": "Deductible",
    "copay": "Copay",
    "coinsurance": "Coinsurance",
    "not_covered": "Not covered",
    "member_unspecified": "Your share (not broken down)",
    "self_pay_discount": "Self-pay discount",
    "member_responsibility": "Your share",
    "unexplained": "Doesn't add up",
}
REPEAT_MODIFIERS = {"76", "77", "91", "59", "XE", "XP", "XS", "XU"}
BUNDLED_REMARKS = {"97", "CO-97", "CO97", "B15", "N19"}


def fmt(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def judge(diff: int, tolerance: bool = True) -> str:
    """pass, cleared (under $1.00, ADR-015) or fail."""
    if diff == 0:
        return "pass"
    return "cleared" if tolerance and abs(diff) < TOLERANCE else "fail"


# ---------- identities (REC-01) ----------

def adjustment_of(rec: dict) -> int | None:
    """The plan's contractual adjustment: printed, or billed − allowed when only the allowed amount is shown."""
    if rec.get("adjustment") is not None:
        return rec["adjustment"]
    if rec.get("billed") is not None and rec.get("allowed") is not None:
        return rec["billed"] - rec["allowed"]
    return None


def identity_1(rec: dict) -> int | None:
    """Billed − (plan adjustment + other savings + primary paid + secondary paid + member responsibility).
    None when the record doesn't carry enough to check."""
    if rec.get("billed") is None or rec.get("patient_responsibility") is None or rec.get("insurer_paid") is None:
        return None
    adj = adjustment_of(rec) or 0
    parts = adj + rec.get("additional_savings", 0) + rec["insurer_paid"] + rec.get("secondary_paid", 0) \
        + rec["patient_responsibility"]
    return rec["billed"] - parts


def identity_2(rec: dict) -> int | None:
    """Member responsibility − (deductible + copay + coinsurance + not covered); None if not broken down."""
    if rec.get("patient_responsibility") is None or not any(rec.get(k) is not None for k in COST_SHARE):
        return None
    return rec["patient_responsibility"] - sum(rec.get(k) or 0 for k in COST_SHARE)


@dataclass
class Difference:
    where: str  # "claim EX123", "line 2 (80053)"
    what: str  # plain-language description with the numbers
    amount: int
    result: str  # pass | cleared | fail


def claim_differences(claim: dict) -> list[Difference]:
    """Identities 1 and 2 for a claim and each of its lines, and the lines against the claim's totals."""
    out = []
    label = f"claim {claim['claim_number']}" if claim.get("claim_number") else "the EOB"
    for where, rec in [(label, claim)] + [(_line_label(i, l), l) for i, l in enumerate(claim.get("lines") or [])]:
        d1 = identity_1(rec)
        if d1:
            out.append(Difference(where, f"billed {fmt(rec['billed'])} differs from plan discount + savings + "
                                         f"insurer paid + your cost by {fmt(d1)}", abs(d1), judge(d1)))
        d2 = identity_2(rec)
        if d2:
            out.append(Difference(where, f"your cost {fmt(rec['patient_responsibility'])} differs from deductible + "
                                         f"copay + coinsurance + not covered by {fmt(d2)}", abs(d2), judge(d2)))
    lines = claim.get("lines") or []
    for key, name in (("billed", "billed"), ("insurer_paid", "insurer paid"), ("patient_responsibility", "your cost")):
        if lines and claim.get(key) is not None and all(l.get(key) is not None for l in lines):
            diff = claim[key] - sum(l[key] for l in lines)
            if diff:
                out.append(Difference(label, f"the lines' {name} add up to {fmt(claim[key] - diff)}, the claim "
                                             f"says {fmt(claim[key])}", abs(diff), judge(diff)))
    return out


def _line_label(i: int, line: dict) -> str:
    return f"line {i + 1}" + (f" ({line['code']})" if line.get("code") else "")


def self_pay_difference(line: dict) -> int | None:
    """Self-pay bill: billed − (self-pay discount + member responsibility)."""
    billed = line.get("billed_charge")
    if billed is None:
        return None
    discount = line.get("self_pay_discount", line.get("adjustment", 0)) or 0
    return billed - discount - line["patient_amount"]


# ---------- adjudication buckets (ALC-01) ----------

def buckets(rec: dict) -> dict[str, int]:
    """Split an EOB line (or a claim without lines) into buckets that always sum to its billed amount.
    Whatever the identities can't place lands in "unexplained", so every cent is in exactly one bucket."""
    billed = rec.get("billed") or 0
    out = {k: 0 for k in BUCKETS}
    out["plan_adjustment"] = adjustment_of(rec) or 0
    out["other_savings"] = rec.get("additional_savings") or 0
    out["primary_paid"] = rec.get("insurer_paid") or 0
    out["secondary_paid"] = rec.get("secondary_paid") or 0
    resp = rec.get("patient_responsibility") or 0
    for k in COST_SHARE:
        out[k] = rec.get(k) or 0
    out["member_unspecified"] = resp - sum(out[k] for k in COST_SHARE)
    out["unexplained"] = billed - sum(v for k, v in out.items() if k != "unexplained")
    return {k: v for k, v in out.items() if v}


def self_pay_buckets(line: dict) -> dict[str, int]:
    billed = line.get("billed_charge") or line["patient_amount"]
    discount = line.get("self_pay_discount", line.get("adjustment", 0)) or 0
    out = {"self_pay_discount": discount, "member_responsibility": line["patient_amount"]}
    out["unexplained"] = billed - discount - line["patient_amount"]
    return {k: v for k, v in out.items() if v}


def add_buckets(*parts: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for p in parts:
        for k, v in p.items():
            out[k] = out.get(k, 0) + v
    return {k: out[k] for k in BUCKETS if out.get(k)}


# ---------- line pairing (MAT-06) ----------

def split_code(code: str | None) -> tuple[str, set[str]]:
    """'99214-25' -> ('99214', {'25'}). Codes are compared without case and spaces."""
    parts = re.split(r"[-\s:]+", (code or "").strip().upper())
    return parts[0], {p for p in parts[1:] if p}


@dataclass
class LinePair:
    bill: list[dict]  # bill items (statement lines), each with "_index"
    eob: list[dict]  # EOB lines, each with "_index"
    how: str  # code | modifier | charge | bundled | panel
    notes: list[str] = field(default_factory=list)

    @property
    def charge(self) -> int:
        return sum(b.get("charge") or 0 for b in self.bill)

    @property
    def billed(self) -> int:
        return sum(e.get("billed") or 0 for e in self.eob)


@dataclass
class LineMatch:
    pairs: list[LinePair]
    bill_only: list[dict]
    eob_only: list[dict]

    @property
    def complete(self) -> bool:
        return not self.bill_only and not self.eob_only


def _bundled(line: dict) -> bool:
    remarks = {str(r).upper().replace(" ", "") for r in line.get("remark_codes") or []}
    return bool(remarks & BUNDLED_REMARKS) or "bundled" in (line.get("description") or "").lower()


def _same_date(a: dict, b: dict) -> bool:
    da, db = a.get("service_date"), b.get("service_date")
    return not da or not db or da == db


def pair_lines(bill_items: list[dict], eob_lines: list[dict]) -> LineMatch:
    """Pair each bill line with its EOB line(s) by code, date and charge (MAT-06)."""
    bill = [{**b, "_index": i} for i, b in enumerate(bill_items)]
    eob = [{**e, "_index": i} for i, e in enumerate(eob_lines)]
    pairs: list[LinePair] = []

    def take(b_list, e_list, how, notes=()):
        pairs.append(LinePair(list(b_list), list(e_list), how, list(notes)))
        for b in b_list:
            bill.remove(b)
        for e in e_list:
            eob.remove(e)

    # 1. same code and modifiers, same date; prefer the same charge
    for b in list(bill):
        code = split_code(b.get("code"))
        if not code[0]:
            continue
        found = [e for e in eob if split_code(e.get("code")) == code and _same_date(b, e)]
        if found:
            e = next((e for e in found if e.get("billed") == b.get("charge")), found[0])
            notes = [] if e.get("billed") in (None, b.get("charge")) else [
                f"charge {fmt(b.get('charge') or 0)} on the bill, {fmt(e['billed'])} on the EOB"]
            take([b], [e], "code", notes)
    # 2. same base code, different modifier (99214 vs 99214-25)
    for b in list(bill):
        base, mods = split_code(b.get("code"))
        if not base:
            continue
        e = next((e for e in eob if split_code(e.get("code"))[0] == base and _same_date(b, e)), None)
        if e:
            take([b], [e], "modifier", [f"modifier differs: {b['code']} on the bill, {e['code']} on the EOB"])
    # 3. components the insurer bundled into a paired line (one bill line to many EOB lines)
    for e in [e for e in eob if _bundled(e)]:
        host = max((p for p in pairs if any(_same_date(b, e) for b in p.bill)), key=lambda p: p.charge, default=None)
        if host:
            host.eob.append(e)
            host.how = "bundled"
            host.notes.append(f"{e.get('code') or e.get('description') or 'a component'} bundled into "
                              f"{host.bill[0].get('code') or 'this line'} by the insurer (not paid separately)")
            eob.remove(e)
    # 4. several bill lines billed as one EOB line, or one bill line as several, by charge on the same date
    for e in list(eob):
        if e.get("billed") is None:
            continue
        same_day = [b for b in bill if _same_date(b, e) and b.get("charge") is not None]
        group = _subset_with_sum(same_day, e["billed"], "charge")
        if group and len(group) > 1:
            take(group, [e], "panel", [f"{len(group)} bill lines processed as one EOB line "
                                       f"({e.get('code') or e.get('description') or 'a panel'})"])
    for b in list(bill):
        if b.get("charge") is None:
            continue
        same_day = [e for e in eob if _same_date(b, e) and e.get("billed") is not None]
        group = _subset_with_sum(same_day, b["charge"], "billed")
        if group and len(group) > 1:
            take([b], group, "split", [f"one bill line processed as {len(group)} EOB lines"])
    # 5. same date and charge when a code is missing on one side
    for b in list(bill):
        e = next((e for e in eob if _same_date(b, e) and b.get("charge") is not None
                  and e.get("billed") == b.get("charge")
                  and not (split_code(b.get("code"))[0] and split_code(e.get("code"))[0])), None)
        if e:
            take([b], [e], "charge", ["paired by date and charge (no code on one side)"])
    return LineMatch(pairs, bill, eob)


def _subset_with_sum(items: list[dict], target: int, key: str, limit: int = 8) -> list[dict] | None:
    """The smallest group of items whose key adds up to target (small statements only)."""
    items = items[:limit]
    for size in range(1, len(items) + 1):
        for group in combinations(items, size):
            if sum(i[key] for i in group) == target:
                return list(group)
    return None


# ---------- duplicate charges (REC-04) ----------

def duplicate_items(items: list[dict]) -> list[tuple[dict, dict]]:
    """(first, second) pairs of lines on one statement with the same code and date, unless a repeat modifier or
    units say it was done twice."""
    out = []
    for i, a in enumerate(items):
        base, mods = split_code(a.get("code"))
        if not base:
            continue
        for b in items[i + 1:]:
            b_base, b_mods = split_code(b.get("code"))
            if b_base != base or a.get("service_date") != b.get("service_date"):
                continue
            if (mods | b_mods) & REPEAT_MODIFIERS or (a.get("units") or 1) > 1 or (b.get("units") or 1) > 1:
                continue
            out.append((a, b))
            break
    return out
