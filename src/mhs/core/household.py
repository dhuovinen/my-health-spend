"""Household view (UX-06): each member's totals for a plan year, and the family's.

Pure functions over the engine's VisitResults. The family total is the sum of the rows, a row for visits with no
member included, so the two always agree (TC-UX-06-1).
"""

from dataclasses import dataclass, field

from mhs.core.reconcile import STATUS_ORDER, VisitResult

NOBODY = ""  # the row key for visits not assigned to a member


@dataclass
class PersonTotals:
    member_id: str  # NOBODY for visits without a member, "family" for the total
    name: str
    visits: int = 0
    billed: int = 0
    insurer_paid: int = 0
    paid: int = 0  # paid by the household and applied to these visits, net of refunds
    still_owed: int = 0
    at_issue: int = 0  # open findings, the same dollars once (ADR-035, ADR-041)
    attention: int = 0  # visits whose status needs the member (In dispute to Balance outstanding)
    status_counts: dict[str, int] = field(default_factory=lambda: {s: 0 for s in STATUS_ORDER})

    def add(self, v: VisitResult, attention: bool) -> None:
        self.visits += 1
        self.billed += v.total_billed
        self.insurer_paid += v.insurer_paid
        self.paid += v.paid - v.refunded
        self.still_owed += v.remaining
        self.at_issue += v.at_stake
        self.attention += attention
        self.status_counts[v.status] += 1

    def __add__(self, other: "PersonTotals") -> "PersonTotals":
        out = PersonTotals(self.member_id, self.name)
        for name in ("visits", "billed", "insurer_paid", "paid", "still_owed", "at_issue", "attention"):
            setattr(out, name, getattr(self, name) + getattr(other, name))
        out.status_counts = {s: self.status_counts[s] + other.status_counts[s] for s in STATUS_ORDER}
        return out


def member_of(v: VisitResult) -> str:
    return v.visit.get("member_id") or NOBODY


def household_totals(visits: list[VisitResult], members: list[dict],
                     attention: tuple[str, ...]) -> tuple[list[PersonTotals], PersonTotals]:
    """One row per household member (in the members' order, with no visits too), a "not assigned to anyone" row
    when some visits have no member or an unknown one, and the family total."""
    rows = {m["id"]: PersonTotals(m["id"], m["name"]) for m in members}
    for v in visits:
        key = member_of(v) if member_of(v) in rows else NOBODY
        if key not in rows:
            rows[key] = PersonTotals(NOBODY, "Not assigned to anyone")
        rows[key].add(v, v.status in attention)
    people = list(rows.values())
    family = sum(people, PersonTotals("family", "Family"))
    return people, family


def visits_for(visits: list[VisitResult], member_id: str | None) -> list[VisitResult]:
    """A member's visits, or everyone's for None (the family view)."""
    return visits if not member_id else [v for v in visits if member_of(v) == member_id]
