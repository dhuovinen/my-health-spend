"""Repeat services across visits (REC-14, ADR-045): worth a closer look, never a discrepancy.

For one person, provider group and plan within a plan year, each code (with its modifiers, per unit) is compared with
its most recent earlier occurrence. A change is flagged on the first visit it appears, because the next visit is
compared with this one. Prices have no tolerance; the member's share keeps the $1.00 tolerance (ADR-015).
Pure functions; no database or web imports. Money in integer cents.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from mhs.core.lines import TOLERANCE, split_code

REASONS = "Common reasons: a new contract, an added service, a different dose."
NEXT_STEP = "Compare the two visits, and ask the provider or your insurer if the change isn't clear."
SERIES = 3  # visits with the same codes before a changed set of codes is worth a look
NAMES = {"allowed": "allowed amount", "billed": "billed amount", "share": "your share"}


@dataclass
class Flag:
    visit_id: str
    kind: str  # allowed | billed | share | codes
    detail: str
    amount: int = 0
    earlier_visit: str = ""
    explained: bool = False  # the deductible explains it: said on the visit, not flagged


@dataclass
class _Line:
    units: float = 0
    billed: int | None = None
    allowed: int | None = None
    share: int | None = None
    deductible: int | None = None


@dataclass
class _Visit:
    id: str
    date: str
    lines: dict[str, _Line] = field(default_factory=dict)  # by code with its modifiers
    deductible: int = 0


def _key(code: str | None) -> str:
    base, mods = split_code(code)
    return "-".join([base, *sorted(mods)]) if base else ""


def _add(total: int | None, value: int | None) -> int | None:
    return total if value is None else (total or 0) + value


def _lines_of(vr) -> dict[str, _Line]:
    """Line detail from the visit's confirmed documents: the EOBs' lines, else the latest statement's service lines."""
    out: dict[str, _Line] = {}
    claims = [c for c in vr.claims if c.get("claim_status") not in ("denied", "pending")]
    for line in (line for c in claims for line in c.get("lines") or []):
        if key := _key(line.get("code")):
            n = out.setdefault(key, _Line())
            n.units += line.get("units") or 1
            n.billed = _add(n.billed, line.get("billed"))
            n.allowed = _add(n.allowed, line.get("allowed"))
            n.share = _add(n.share, line.get("patient_responsibility"))
            n.deductible = _add(n.deductible, line.get("deductible"))
    if out or not vr.bill_lines:
        return out
    newest = vr.bill_lines[0][0]["id"]
    for bill, bill_line in vr.bill_lines:
        for item in (bill_line.get("items") or []) if bill["id"] == newest else []:
            if key := _key(item.get("code")):
                n = out.setdefault(key, _Line())
                n.units += item.get("units") or 1
                n.billed = _add(n.billed, item.get("charge"))
    return out


def _unit(amount: int | None, units: float) -> int | None:
    return None if amount is None else round(amount / (units or 1))


def _money(c: int) -> str:
    return f"${c / 100:,.2f}"


def _nice(iso: str) -> str:
    import datetime

    d = datetime.date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def _flag(now: _Visit, was: _Visit, kind: str, code: str, old: int, new: int) -> Flag:
    return Flag(now.id, kind, f"The {NAMES[kind]} for {code} was {_money(old)} on {_nice(was.date)} and {_money(new)} on "
                              f"{_nice(now.date)}, a difference of {_money(abs(new - old))}. Worth a closer look. "
                              f"{REASONS} {NEXT_STEP}", abs(new - old), was.id)


def _compare(series: list[_Visit], deductible_limit: int | None) -> list[Flag]:
    flags, latest, used = [], {}, 0
    run, run_codes = 0, None
    for visit in series:
        used += visit.deductible
        for code, line in visit.lines.items():
            before = latest.get(code)
            if before:
                was, old = before
                for kind, a, b in (("allowed", old.allowed, line.allowed), ("billed", old.billed, line.billed)):
                    a, b = _unit(a, old.units), _unit(b, line.units)
                    if a is not None and b is not None and a != b:
                        flags.append(_flag(visit, was, kind, code, a, b))
                flags.extend(_share(visit, was, code, old, line, used, deductible_limit))
            latest[code] = (visit, line)
        codes = frozenset(visit.lines)
        if run_codes is not None and codes != run_codes and run >= SERIES and codes & run_codes:
            added, dropped = sorted(codes - run_codes), sorted(run_codes - codes)
            change = "; ".join(filter(None, (f"added {', '.join(added)}" if added else "",
                                             f"dropped {', '.join(dropped)}" if dropped else "")))
            flags.append(Flag(visit.id, "codes", f"This visit's codes differ from the {run} before it in the series: "
                                                 f"{change}. Worth a closer look. {REASONS} {NEXT_STEP}",
                              0, series[series.index(visit) - 1].id))
        run = run + 1 if codes == run_codes else 1
        run_codes = codes
    return flags


def _share(visit, was, code, old, line, used, limit) -> list[Flag]:
    """A changed share on an unchanged allowed amount, unless the deductible being met between the visits explains it
    (REC-07): nothing of it applied to this visit's line, or the plan's deductible is reached by now."""
    a, b = _unit(old.share, old.units), _unit(line.share, line.units)
    allowed_a, allowed_b = _unit(old.allowed, old.units), _unit(line.allowed, line.units)
    if a is None or b is None or allowed_a is None or allowed_a != allowed_b or abs(a - b) < TOLERANCE:
        return []
    met = bool(old.deductible) and (line.deductible == 0 or (limit is not None and used >= limit))
    if met:
        return [Flag(visit.id, "share", f"Your share for {code} was {_money(a)} on {_nice(was.date)} and {_money(b)} on "
                                        f"{_nice(visit.date)}. Meeting the deductible between the visits explains the "
                                        "difference.", abs(a - b), was.id, explained=True)]
    return [_flag(visit, was, "share", code, a, b)]


def repeat_flags(visits: list, deductibles: dict[str, int] = {}) -> list[Flag]:  # noqa: B006
    """Flags for a plan year's VisitResults. deductibles: a plan's individual in-network deductible by plan id."""
    series = defaultdict(list)
    for vr in sorted(visits, key=lambda v: (v.visit["date"], v.id)):
        member, plan = vr.visit.get("member_id"), vr.visit.get("plan_id")
        lines = _lines_of(vr)
        if member and plan and lines and not vr.carry_in:
            spent = sum(c.get("deductible") or 0 for c in vr.claims)
            series[(member, vr.group_id, plan)].append(_Visit(vr.id, vr.visit["date"], lines, spent))
    return [f for (_, _, plan), one in series.items() for f in _compare(one, deductibles.get(plan))]
