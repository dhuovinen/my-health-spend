"""Match a document to the visit it belongs to, with a score and the reasons (MAT-05, ADR-035).

A score of 0.9 or more links automatically (the member can undo it), 0.6 to 0.9 is proposed for the member to
confirm, below 0.6 stays unmatched. Pure functions over plain record dicts; no database or web imports.
"""

from dataclasses import dataclass, field
from datetime import date

AUTO_LINK = 0.9
PROPOSE = 0.6
AMBIGUOUS = 0.05  # two candidates this close are only proposed

W_PROVIDER = 0.35
W_DATE = {0: 0.35, 3: 0.2, 14: 0.1}  # days apart (at most) -> weight
W_MEMBER, W_MEMBER_UNKNOWN = 0.2, 0.1
W_CLAIM = 0.3
W_AMOUNT = 0.2


@dataclass
class Facts:
    """What a document says about its visit."""
    provider_id: str
    service_date: str
    member_id: str | None = None
    claim_number: str | None = None
    billed: int | None = None
    rejected: set[str] = field(default_factory=set)  # visits the member said this document isn't for


@dataclass
class Candidate:
    visit_id: str
    score: float
    reasons: list[str]

    @property
    def decision(self) -> str:
        return decision(self.score)


def decision(score: float) -> str:
    """link (automatic, reversible), propose (member confirms) or none."""
    if score >= AUTO_LINK:
        return "link"
    return "propose" if score >= PROPOSE else "none"


def _days(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def score(facts: Facts, visit: dict, same_group: set[str] = frozenset(), claim_numbers: set[str] = frozenset(),
          amounts: set[int] = frozenset()) -> Candidate | None:
    """Score one visit. same_group: provider ids reconciled together with the document's provider;
    claim_numbers and amounts: what the visit's documents already show. None when it can never match."""
    if visit["id"] in facts.rejected:
        return None
    if visit["provider_id"] != facts.provider_id and visit["provider_id"] not in same_group:
        return None  # TC-MAT-05-4: another provider never matches
    member = visit.get("member_id")
    if member and facts.member_id and member != facts.member_id:
        return None  # TC-MAT-05-3: another household member's visit
    reasons, total = [], W_PROVIDER
    reasons.append("same provider" if visit["provider_id"] == facts.provider_id else "related provider")
    days = _days(visit["date"], facts.service_date)
    weight = next((w for limit, w in W_DATE.items() if days <= limit), 0.0)
    total += weight
    if days == 0:
        reasons.append("same date of service")
    elif weight:
        reasons.append(f"dates of service {days} day{'s' if days != 1 else ''} apart")
    if member and facts.member_id:
        total += W_MEMBER
        reasons.append("same person")
    else:
        total += W_MEMBER_UNKNOWN
        reasons.append("person not known on both")
    if facts.claim_number and facts.claim_number in claim_numbers:
        total += W_CLAIM
        reasons.append(f"same claim number {facts.claim_number}")
    if facts.billed is not None and facts.billed in amounts:
        total += W_AMOUNT
        reasons.append(f"same billed amount ${facts.billed / 100:,.2f}")
    return Candidate(visit["id"], round(min(total, 1.0), 2), reasons)


def candidates(facts: Facts, visits: list[dict], documents: list[dict] = (), same_group: set[str] = frozenset()) \
        -> list[Candidate]:
    """Every visit that could match, best first. documents: the household's documents, for the claim numbers
    and billed amounts each visit already has."""
    claims: dict[str, set[str]] = {}
    amounts: dict[str, set[int]] = {}
    for d in documents:
        if d.get("type") == "eob":
            if d.get("claim_number"):
                claims.setdefault(d["visit_id"], set()).add(d["claim_number"])
            if d.get("billed") is not None:
                amounts.setdefault(d["visit_id"], set()).add(d["billed"])
        elif d.get("type") == "provider_bill":
            for line in d.get("lines", []):
                if line.get("billed_charge") is not None:
                    amounts.setdefault(line["visit_id"], set()).add(line["billed_charge"])
    out = []
    for v in visits:
        c = score(facts, v, same_group, claims.get(v["id"], set()), amounts.get(v["id"], set()))
        if c and c.score > 0:
            out.append(c)
    return sorted(out, key=lambda c: (-c.score, c.visit_id))


def best(facts: Facts, visits: list[dict], documents: list[dict] = (), same_group: set[str] = frozenset()) \
        -> tuple[Candidate | None, str]:
    """The best candidate and what to do with it: link, propose or none. A near tie is only proposed."""
    found = candidates(facts, visits, documents, same_group)
    if not found or found[0].decision == "none":
        return None, "none"
    top = found[0]
    if top.decision == "link" and len(found) > 1 and top.score - found[1].score < AMBIGUOUS:
        return top, "propose"
    return top, top.decision
