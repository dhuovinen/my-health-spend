"""The plan's cost sharing (REC-06) and plain-language claim codes (REC-09), ADR-050.

Pure functions over record dicts, money in integer cents. No database or web imports. The pre-visit estimate
(core/estimate.py, ADR-053) uses the same accumulators and the same expected-share rule.
"""

import re
from dataclasses import dataclass, field

from mhs.core.lines import TOLERANCE, fmt

SERVICE_TYPES = {
    "preventive": "Preventive care",
    "primary_care": "Primary care",
    "specialist": "Specialist",
    "urgent_care": "Urgent care",
    "emergency": "Emergency room",
    "other": "Other",
}
SHARE_KEYS = ("deductible", "copay", "coinsurance")


# ---------- accumulators ----------

@dataclass
class Accumulators:
    """What the insurer has applied so far this plan year, in network: per member and for the family."""
    deductible: dict[str, int] = field(default_factory=dict)
    oop: dict[str, int] = field(default_factory=dict)
    family_deductible: int = 0
    family_oop: int = 0

    def add(self, member: str, deductible: int, oop: int) -> None:
        self.deductible[member] = self.deductible.get(member, 0) + deductible
        self.oop[member] = self.oop.get(member, 0) + oop
        self.family_deductible += deductible
        self.family_oop += oop


@dataclass
class Terms:
    """The plan's in-network terms that the check and the estimate need. Amounts None when not in Settings."""
    deductible: int | None = None  # individual
    family_deductible: int | None = None
    oop: int | None = None
    family_oop: int | None = None
    rate: float | None = None  # coinsurance, e.g. 0.2
    copays: dict[str, int] = field(default_factory=dict)
    hdhp: bool = False  # deductible before copays (IRS rule for HSA-eligible plans)
    confirmed: bool = False  # the member said these terms match the plan documents


def terms_of(plan: dict, member_id: str | None = None) -> Terms:
    t = Terms(rate=plan.get("coinsurance_rate"), copays=dict(plan.get("copays") or {}),
              hdhp=bool(plan.get("hsa_eligible_plan")), confirmed=bool(plan.get("terms_confirmed")))
    for limit in plan.get("limits") or []:
        if limit.get("network") not in ("in_network", "combined"):
            continue
        if limit.get("member_id") and limit["member_id"] != member_id:
            continue
        key = {("deductible", "individual"): "deductible", ("deductible", "family"): "family_deductible",
               ("out_of_pocket_max", "individual"): "oop", ("out_of_pocket_max", "family"): "family_oop"
               }.get((limit.get("type"), limit.get("level")))
        if key and (getattr(t, key) is None or limit.get("member_id")):
            setattr(t, key, limit["amount"])
    return t


def _left(limit: int | None, used: int) -> int | None:
    return None if limit is None else max(limit - used, 0)


def _min_known(*values: int | None) -> int | None:
    known = [v for v in values if v is not None]
    return min(known) if known else None


def deductible_left(t: Terms, acc: Accumulators, member: str) -> int | None:
    """An embedded individual deductible ends at the individual or the family amount, whichever comes first."""
    return _min_known(_left(t.deductible, acc.deductible.get(member, 0)), _left(t.family_deductible, acc.family_deductible))


def oop_left(t: Terms, acc: Accumulators, member: str) -> int | None:
    return _min_known(_left(t.oop, acc.oop.get(member, 0)), _left(t.family_oop, acc.family_oop))


# ---------- the expected share ----------

@dataclass
class Expected:
    deductible: int = 0
    copay: int = 0
    coinsurance: int = 0
    steps: list[str] = field(default_factory=list)  # the math, one sentence each
    missing: str = ""  # why it can't be worked out; empty when it can

    @property
    def total(self) -> int:
        return self.deductible + self.copay + self.coinsurance


def expected_share(t: Terms, allowed: int, service_type: str | None, acc: Accumulators, member: str) -> Expected:
    """What the plan's terms say the member pays on an allowed amount, given the year so far (REC-06, PRE-02)."""
    e = Expected()
    if service_type == "preventive":
        e.steps.append("Preventive care: the plan pays it in full, so you owe $0.00")
        return e
    copay = t.copays.get(service_type) if service_type else None
    ded_left = deductible_left(t, acc, member)
    if copay is not None and not t.hdhp:
        e.copay = min(copay, allowed)
        e.steps.append(f"{SERVICE_TYPES.get(service_type, service_type)} copay: {fmt(e.copay)}")
    else:
        if ded_left is None:
            e.missing = "Add the plan's in-network deductible in Settings"
            return e
        e.deductible = min(allowed, ded_left)
        rest = allowed - e.deductible
        if ded_left == 0:
            e.steps.append("Deductible already met")
        else:
            e.steps.append(f"Deductible: {fmt(e.deductible)} of the {fmt(ded_left)} left")
        if rest > 0:
            if copay is not None:
                e.copay = min(copay, rest)
                e.steps.append(f"{SERVICE_TYPES.get(service_type, service_type)} copay after the deductible: "
                               f"{fmt(e.copay)}")
            elif t.rate is None:
                e.missing = "Add the plan's coinsurance rate in Settings"
                return e
            else:
                e.coinsurance = round(rest * t.rate)
                e.steps.append(f"Coinsurance: {round(t.rate * 100)}% of the {fmt(rest)} left after the deductible "
                               f"= {fmt(e.coinsurance)}")
    left = oop_left(t, acc, member)
    if left is not None and e.total > left:
        over = e.total - left
        for key in ("coinsurance", "copay", "deductible"):
            take = min(over, getattr(e, key))
            setattr(e, key, getattr(e, key) - take)
            over -= take
        e.steps.append(f"Capped at the {fmt(left)} left before the out-of-pocket maximum")
    return e


# ---------- REC-06: the check per claim ----------

@dataclass
class ShareCheck:
    claim_id: str
    result: str  # pass | fail | flag | cleared | info | na
    detail: str
    amount: int = 0


def claim_order(claim: dict) -> tuple:
    """The insurer's processing order: EOB date, then claim number (TC-REC-06-4)."""
    return claim["date"], claim.get("claim_number") or "", claim["id"]


def _counts(claim: dict) -> bool:
    return claim.get("claim_status") != "denied" and claim.get("network_status") != "out_of_network"


def check_claims(claims: list[dict], visits: dict[str, dict], plans: dict[str, dict]) -> dict[str, ShareCheck]:
    """Replay each plan year's claims in processing order and compare each with the plan's terms."""
    out: dict[str, ShareCheck] = {}
    by_plan: dict[str, list[dict]] = {}
    for c in claims:
        by_plan.setdefault(c.get("plan_id") or "", []).append(c)
    for plan_id, plan_claims in by_plan.items():
        plan = plans.get(plan_id)
        acc = Accumulators()
        for c in sorted(plan_claims, key=claim_order):
            visit = visits.get(c["visit_id"], {})
            member = visit.get("member_id") or ""
            if plan is None:
                out[c["id"]] = ShareCheck(c["id"], "na", "No plan on file for this claim")
                continue
            if _counts(c):
                out[c["id"]] = _check_one(c, visit, terms_of(plan, member or None), acc, member)
                share = sum(c.get(k) or 0 for k in SHARE_KEYS)
                acc.add(member, c.get("deductible") or 0, share)
            else:
                why = "Denied claim" if c.get("claim_status") == "denied" else "Out-of-network claim"
                out[c["id"]] = ShareCheck(c["id"], "na", f"{why}: the plan's in-network terms don't apply")
    return out


def _check_one(c: dict, visit: dict, t: Terms, acc: Accumulators, member: str) -> ShareCheck:
    if c.get("allowed") is None or not any(c.get(k) is not None for k in SHARE_KEYS):
        return ShareCheck(c["id"], "na", "The EOB doesn't break your share into deductible, copay and coinsurance")
    exp = expected_share(t, c["allowed"], visit.get("service_type"), acc, member)
    if exp.missing:
        return ShareCheck(c["id"], "na", exp.missing + " to check this claim against your plan")
    actual = {k: c.get(k) or 0 for k in SHARE_KEYS}
    diff = sum(actual.values()) - exp.total
    label = f"Claim {c['claim_number']}: " if c.get("claim_number") else ""
    math = "; ".join(exp.steps)
    parts = [f"{k} {fmt(actual[k])} (plan says {fmt(getattr(exp, k))})" for k in SHARE_KEYS
             if actual[k] != getattr(exp, k)]
    if diff <= 0 or abs(diff) < TOLERANCE:
        if diff < 0 and abs(diff) >= TOLERANCE:
            return ShareCheck(c["id"], "info", f"{label}you were charged {fmt(-diff)} less than the plan's terms "
                                               f"suggest ({math}); no overcharge")
        if parts and diff == 0:
            return ShareCheck(c["id"], "info", f"{label}your share matches the plan's total of {fmt(exp.total)}, "
                                               f"split differently: " + ", ".join(parts))
        result = "pass" if diff == 0 else "cleared"
        return ShareCheck(c["id"], result, f"{label}your share of {fmt(sum(actual.values()))} matches the plan's terms "
                                           f"({math})", abs(diff))
    detail = (f"{label}the EOB charges you {fmt(sum(actual.values()))}, but the plan's terms come to {fmt(exp.total)} "
              f"({math}). Differences: {', '.join(parts)}. Ask the insurer to reprocess the claim")
    if visit.get("service_type") == "preventive":
        detail = (f"{label}preventive care should cost you $0.00, but the EOB charges you {fmt(sum(actual.values()))}. "
                  "Ask the insurer to reprocess it as preventive; if the visit also treated a problem, that part can "
                  "be charged")
    if not t.confirmed:
        detail += (". This is a flag until you confirm your plan's terms in Settings, since wrong terms make every "
                   "claim look wrong")
    return ShareCheck(c["id"], "fail" if t.confirmed else "flag", detail, diff)


# ---------- REC-09: claim codes ----------

@dataclass
class CodeNote:
    code: str
    text: str
    appealable: bool = False
    known: bool = True
    where: str = ""  # "claim" or "line 2 (99213)"


_CODE = re.compile(r"^\s*(?:(CO|PR|OA|PI|CR)\s*-?\s*)?([A-Z]{0,2}\d{1,4}[A-Z]?)\s*$", re.IGNORECASE)


def explain(code: str, table: dict) -> CodeNote:
    """A code like CO-45, PR-1, 97 or N19 in plain words; unknown codes say so (TC-REC-09-3)."""
    m = _CODE.match(code or "")
    if not m or not table:
        return CodeNote(code, "Unknown code: it isn't in MHS's table yet. Ask the insurer what it means.", known=False)
    group, reason = (m.group(1) or "").upper(), m.group(2).upper()
    entry = (table.get("reasons") or {}).get(reason) or (table.get("remarks") or {}).get(reason)
    if entry is None:
        return CodeNote(code, "Unknown code: it isn't in MHS's table yet. Ask the insurer what it means.", known=False)
    text = entry["text"]
    if group and (g := (table.get("groups") or {}).get(group)):
        text = f"{text} {g}"
    return CodeNote(code, text, bool(entry.get("appealable")))


def code_notes(claims: list[dict], table: dict) -> list[CodeNote]:
    out, seen = [], set()
    for c in claims:
        for where, codes in [("claim", c.get("remark_codes") or [])] + [
                (f"line {i + 1}" + (f" ({l['code']})" if l.get("code") else ""), l.get("remark_codes") or [])
                for i, l in enumerate(c.get("lines") or [])]:
            for code in codes:
                note = explain(code, table)
                note.where = where
                if (code, where) not in seen:
                    seen.add((code, where))
                    out.append(note)
    return out


def _group(code: str) -> str:
    m = _CODE.match(code or "")
    return (m.group(1) or "").upper() if m else ""


def appealable_amount(claim: dict, table: dict) -> tuple[int, list[str]]:
    """What the member is charged under codes that look appealable, and those codes. A CO (contractual) code is
    the provider's to absorb, so it isn't money the member would appeal for."""
    amount, codes = 0, []
    for line in claim.get("lines") or []:
        hits = [c for c in line.get("remark_codes") or [] if _group(c) != "CO" and explain(c, table).appealable]
        if hits:
            amount += line.get("not_covered") or line.get("patient_responsibility") or 0
            codes += hits
    claim_hits = [c for c in claim.get("remark_codes") or [] if _group(c) != "CO" and explain(c, table).appealable]
    if claim_hits and (claim.get("claim_status") == "denied" or not amount):
        amount = max(amount, claim.get("not_covered") or claim.get("patient_responsibility") or 0)
        codes += claim_hits
    return amount, list(dict.fromkeys(codes))
