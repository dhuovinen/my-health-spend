"""Reconciliation engine: checks, visit status, provider ledgers, HSA gaps and plan-limit progress.

Pure functions over plain record dicts (money in integer cents). No database or web imports.
Release 0 rules are in docs/MVP_REQUIREMENTS.md section 5; Release 1 (phase 1.4) adds claims per visit, line
pairing, the three money identities with the $1.00 tolerance, settlement and the nine statuses (ADR-009,
ADR-014 to ADR-017, ADR-035).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from mhs.core.lines import (BUCKETS, TOLERANCE_CAP, LineMatch, add_buckets, adjustment_of, buckets,
                            claim_differences, duplicate_items, fmt, judge, pair_lines, self_pay_buckets,
                            self_pay_difference)

WAITING_DAYS = 30
DUPLICATE_WINDOW_DAYS = 14
INSURED_CATEGORIES = {"provider_visit", "service"}

# REC-11: one status per visit, the first that applies (ADR-009).
STATUS_ORDER = ["in_dispute", "discrepancy", "needs_review", "balance_outstanding", "awaiting_eob",
                "awaiting_documents", "missing_documents", "resolved", "complete"]
STATUS_LABELS = {
    "in_dispute": "In dispute",
    "discrepancy": "Discrepancy found",
    "needs_review": "Needs review",
    "balance_outstanding": "Balance outstanding",
    "awaiting_eob": "Awaiting EOB",
    "awaiting_documents": "Awaiting documents",
    "missing_documents": "Missing documents",
    "resolved": "Resolved",
    "complete": "Complete",
}
STATUS_HELP = {
    "in_dispute": "You opened a dispute with the provider or insurer. Close it here when it's settled.",
    "discrepancy": "The documents don't agree, or you paid more than you owe. The findings below say by how much.",
    "needs_review": "A document was matched to this visit with less certainty. Confirm it belongs here, or move it.",
    "balance_outstanding": "You still owe the provider money for this visit.",
    "awaiting_eob": "The insurer hasn't sent its decision (EOB) yet. Wait for it before paying a bill.",
    "awaiting_documents": "A document you expect hasn't arrived yet.",
    "missing_documents": "A document this visit needs is overdue. Ask for it.",
    "resolved": "There was a problem with this visit and it has been dealt with.",
    "complete": "Every document agrees and nothing is owed.",
}
ATTENTION = ("in_dispute", "discrepancy", "needs_review", "balance_outstanding")
CHECK_NAMES = {
    "C1": "EOB adds up",
    "self_pay": "Bill adds up (self-pay)",
    "C2": "Bill matches EOB",
    "lines": "Bill lines match EOB lines",
    "duplicate": "No duplicate charges",
    "C3": "Network status agrees",
    "C4": "Paid matches what you owe",
    "settlement": "Every dollar accounted for",
    "claim_filed": "Claim filed with insurance",
    "C6": "Balance outstanding",
}
FINDING_KINDS = {
    "missed_adjustment": "Missed adjustment",
    "balance_billing": "Balance billing",
    "billed_mismatch": "Charges differ from the claim",
    "overpayment": "Overpayment",
    "duplicate_charge": "Duplicate charge",
    "unexplained": "Unexplained remainder",
    "not_filed": "Claim may not be filed",
}
# A failing check in this set makes the visit "Discrepancy found"; claim_filed and C6 have their own statuses.
DISCREPANCY_CODES = {"C1", "self_pay", "C2", "duplicate", "C3", "C4", "settlement"}
STAKE_CODES = {"C1", "self_pay", "C2", "duplicate"}
DOCUMENT_LABELS = {"eob": "Insurance decision (EOB)", "bill": "Provider bill", "itemized_bill": "Itemized bill",
                   "receipt": "Receipt", "payment": "Payment proof"}


@dataclass
class Dataset:
    plans: list[dict] = field(default_factory=list)
    accounts: list[dict] = field(default_factory=list)
    members: list[dict] = field(default_factory=list)
    providers: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    visits: list[dict] = field(default_factory=list)
    documents: list[dict] = field(default_factory=list)
    waiting_days: int = WAITING_DAYS  # REC-11 threshold, a household preference


@dataclass
class Check:
    code: str
    result: str  # pass | fail | na | cleared (under the tolerance) | info | closed (by the member)
    detail: str = ""
    amount: int = 0
    kind: str = ""  # finding type, e.g. missed_adjustment (FINDING_KINDS)
    closed: dict | None = None  # the member's closing entry

    @property
    def name(self) -> str:
        return CHECK_NAMES[self.code]

    @property
    def kind_label(self) -> str:
        return FINDING_KINDS.get(self.kind, "")


@dataclass
class Allocation:
    payment: dict
    amount: int
    surplus: bool = False  # paid beyond what the visit owes
    source: str = "oldest"  # member | statement | oldest
    refund: bool = False


@dataclass
class DocumentState:
    kind: str
    state: str  # present | expected | not_applicable
    note: str = ""
    blocking: bool = True  # counts toward Awaiting / Missing documents when expected
    since: str = ""  # expected since (member's request), else the visit date

    @property
    def label(self) -> str:
        return DOCUMENT_LABELS[self.kind]


@dataclass
class Settlement:
    """Identity 3 (ADR-014): responsibility = paid − refunds + write-offs + still owed."""
    responsibility: int = 0
    paid: int = 0
    refunds: int = 0
    write_offs: int = 0
    still_owed: int = 0  # negative: a credit due from the provider
    unexplained: int = 0  # the part of still owed the provider no longer asks for
    paid_hsa: int = 0
    paid_other: int = 0

    def __add__(self, other: "Settlement") -> "Settlement":
        return Settlement(**{k: getattr(self, k) + getattr(other, k) for k in self.__dataclass_fields__})

    @property
    def balanced(self) -> bool:
        return self.responsibility == self.paid - self.refunds + self.write_offs + self.still_owed


@dataclass
class VisitResult:
    visit: dict
    provider: dict
    member: dict | None
    group_id: str
    carry_in: bool  # earlier-year visit still on a statement in this year
    claims: list[dict]  # EOBs, the latest version of each claim number, oldest first
    bill_lines: list[tuple[dict, dict]]  # (bill, line), newest bill first
    receipts: list[dict]
    total_billed: int
    insurer_paid: int
    insurer_owed: int | None  # EOB patient responsibility, summed over claims
    billed_to_me: int  # latest statement amount, else EOB responsibility, else receipt total
    insured: bool = True
    age: int = 0
    waiting_days: int = WAITING_DAYS
    settled: bool = False  # dropped off a later statement from the same provider
    allocations: list[Allocation] = field(default_factory=list)
    remaining: int = 0
    unexplained: int = 0  # settled per provider but no matching payment in the data
    write_off: int = 0
    checks: list[Check] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    documents: list[DocumentState] = field(default_factory=list)
    review: list[dict] = field(default_factory=list)  # proposed matches: {doc, line, match}
    line_match: LineMatch | None = None
    buckets: dict[str, int] = field(default_factory=dict)  # ALC-01 for the visit
    line_buckets: list[tuple[str, dict[str, int]]] = field(default_factory=list)
    settlement: Settlement = field(default_factory=Settlement)
    status: str = "complete"
    hsa_flags: list[str] = field(default_factory=list)
    outside_hsa: int = 0  # paid from accounts other than the HSA, not reimbursed
    at_stake: int = 0
    balance_age: int | None = None  # days since the member was first asked to pay an open balance
    notices: int = 0  # statements that list this visit with a balance owed
    notice_label: str = ""  # notice wording printed on the latest such statement, e.g. "Past due"

    @property
    def id(self) -> str:
        return self.visit["id"]

    @property
    def eob(self) -> dict | None:
        """The visit's claim, or its claims added up when there are several."""
        if len(self.claims) <= 1:
            return self.claims[0] if self.claims else None
        out = dict(self.claims[-1])
        out["claim_number"] = ", ".join(c.get("claim_number", "") for c in self.claims)
        for key in ("billed", "allowed", "adjustment", "insurer_paid", "secondary_paid", "additional_savings",
                    "deductible", "copay", "coinsurance", "not_covered", "patient_responsibility"):
            if any(key in c for c in self.claims):
                out[key] = sum(c.get(key) or 0 for c in self.claims)
        out["network_status"] = next((c["network_status"] for c in self.claims
                                      if c.get("network_status") in ("in_network", "out_of_network")),
                                     out.get("network_status"))
        out.pop("lines", None)
        return out

    @property
    def responsibility(self) -> int:
        """What the member owes for the visit before write-offs: the EOB's, else what the provider asks."""
        return self.insurer_owed if self.insurer_owed is not None else self.billed_to_me

    @property
    def paid(self) -> int:
        return sum(a.amount for a in self.allocations if not a.refund)

    @property
    def refunded(self) -> int:
        return sum(a.amount for a in self.allocations if a.refund)

    @property
    def surplus(self) -> int:
        return sum(a.amount for a in self.allocations if a.surplus and not a.refund)

    @property
    def overpaid(self) -> int:
        return max(self.surplus - self.refunded, 0)

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    @property
    def status_help(self) -> str:
        return STATUS_HELP[self.status]

    @property
    def latest_line(self) -> tuple[dict, dict] | None:
        return self.bill_lines[0] if self.bill_lines else None

    @property
    def findings(self) -> list[Check]:
        return [c for c in self.checks if c.result == "fail"]

    @property
    def cleared(self) -> list[Check]:
        return [c for c in self.checks if c.result == "cleared"]

    @property
    def dispute(self) -> dict | None:
        return self.visit.get("dispute")

    @property
    def awaiting_eob(self) -> bool:
        """Insured, no EOB yet, within the waiting threshold: a bill isn't treated as owed yet (REC-02)."""
        return self.insured and not self.claims and self.age < self.waiting_days


@dataclass
class LedgerEntry:
    date: str
    kind: str  # charge | payment | refund | statement
    description: str
    charge: int = 0
    payment: int = 0
    balance: int = 0
    ref: str = ""


@dataclass
class ProviderGroup:
    id: str
    providers: list[dict]
    unconfirmed: list[dict]  # suspected relationships joining this group
    visits: list[VisitResult] = field(default_factory=list)
    payments: list[dict] = field(default_factory=list)
    statements: list[dict] = field(default_factory=list)
    should_owe: int = 0
    billed_to_me: int = 0
    paid: int = 0
    paid_outside_hsa: int = 0
    overpaid: int = 0
    unpaid: int = 0
    gap: int = 0  # insurer says owed, but neither billed-and-unpaid nor paid
    no_claim_payments: int = 0
    provider_says_owed: int | None = None
    latest_statement: dict | None = None
    duplicates: list[tuple[dict, dict]] = field(default_factory=list)
    ledger: list[LedgerEntry] = field(default_factory=list)
    settlement: Settlement = field(default_factory=Settlement)
    cleared_total: int = 0  # differences cleared within tolerance this plan year (ADR-015)

    @property
    def name(self) -> str:
        return " / ".join(p["name"] for p in self.providers)

    @property
    def flags(self) -> list[str]:
        out = []
        if self.overpaid:
            out.append("overpaid")
        if self.unpaid:
            out.append("unpaid")
        if self.gap:
            out.append("gap")
        if self.no_claim_payments:
            out.append("no_claim")
        if self.paid_outside_hsa:
            out.append("outside_hsa")
        if self.duplicates:
            out.append("duplicate")
        if self.unconfirmed:
            out.append("unconfirmed")
        if self.cleared_total > TOLERANCE_CAP:
            out.append("tolerance")
        return out


@dataclass
class LimitProgress:
    plan: dict
    limit: dict
    label: str
    used: int
    member_names: list[str]
    note: str = ""
    member_id: str | None = None  # an individual limit's member (UX-06), None for the family or anyone covered

    @property
    def pct(self) -> int:
        amount = self.limit["amount"]
        return min(100, round(100 * self.used / amount)) if amount else 0


@dataclass
class Report:
    year: int
    today: date
    visits: list[VisitResult]  # visits dated in the year (carry-ins excluded)
    groups: list[ProviderGroup]
    limits: list[LimitProgress]
    years: list[int]
    waiting_days: int = WAITING_DAYS

    def visit(self, visit_id: str) -> VisitResult | None:
        return next((v for g in self.groups for v in g.visits if v.id == visit_id), None)

    def group(self, group_id: str) -> ProviderGroup | None:
        return next((g for g in self.groups if g.id == group_id), None)

    @property
    def status_counts(self) -> dict[str, int]:
        counts = {s: 0 for s in STATUS_ORDER}
        for v in self.visits:
            counts[v.status] += 1
        return counts

    @property
    def buckets(self) -> dict[str, int]:
        """ALC-01 for the year: where every billed dollar of this year's visits went."""
        return add_buckets(*(v.buckets for v in self.visits))

    @property
    def totals(self) -> dict[str, int]:
        return {
            "billed": sum(v.total_billed for v in self.visits),
            "insurer_paid": sum(v.insurer_paid for v in self.visits),
            "you_paid": sum(g.paid for g in self.groups),
            "at_stake": sum(v.at_stake for v in self.visits),
            "unpaid": sum(g.unpaid for g in self.groups),
            "gap": sum(g.gap for g in self.groups),
            "outside_hsa": sum(g.paid_outside_hsa for g in self.groups),
            "unexplained": sum(v.unexplained for g in self.groups for v in g.visits),
            "no_claim": sum(g.no_claim_payments for g in self.groups),
        }

    @property
    def ledger_visits(self) -> list[VisitResult]:
        """Every visit on a provider ledger this year, carry-ins included, newest first.

        The HSA totals come from the ledgers, so their counts and filtered lists use these visits too."""
        return sorted((v for g in self.groups for v in g.visits), key=lambda v: v.visit["date"], reverse=True)

    @property
    def hsa_counts(self) -> dict[str, int]:
        """How many visits (or provider groups, or payments) sit behind each HSA total."""
        visits = self.ledger_visits
        return {
            "unpaid": sum(1 for v in visits if v.remaining),
            "gap": sum(1 for g in self.groups if g.gap),
            "outside_hsa": sum(1 for v in visits if v.outside_hsa),
            "unexplained": sum(1 for v in visits if v.unexplained),
            "no_claim": sum(1 for g in self.groups if g.no_claim_payments
                            for p in g.payments if p.get("kind") != "refund"),
        }

    @property
    def unconfirmed_relationships(self) -> list[dict]:
        seen, out = set(), []
        for g in self.groups:
            for r in g.unconfirmed:
                if r["id"] not in seen:
                    seen.add(r["id"])
                    out.append(r)
        return out


def _group_providers(providers: list[dict], relationships: list[dict]) -> dict[str, str]:
    parent = {p["id"]: p["id"] for p in providers}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for r in relationships:
        if r["status"] == "rejected" or r["provider_id"] not in parent or r["related_provider_id"] not in parent:
            continue
        a, b = find(r["provider_id"]), find(r["related_provider_id"])
        if a != b:
            parent[max(a, b)] = min(a, b)
    return {pid: find(pid) for pid in parent}


def provider_groups(ds: Dataset) -> dict[str, str]:
    """Provider id -> the id of the group it is reconciled with (suspected and confirmed relationships)."""
    return _group_providers(ds.providers, ds.relationships)


def _days(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def available_years(ds: Dataset) -> list[int]:
    years = {int(v["date"][:4]) for v in ds.visits}
    years |= {int(d["date"][:4]) for d in ds.documents if d["type"] == "payment"}
    return sorted(years, reverse=True)


def current_claims(eobs: list[dict]) -> dict[str, list[dict]]:
    """Visit id -> its claims: the latest EOB per claim number (EOBs without one are versions of each other)."""
    latest: dict[tuple[str, str], dict] = {}
    for e in sorted(eobs, key=lambda d: (d["date"], d["id"])):
        latest[(e["visit_id"], e.get("claim_number") or "")] = e
    out = defaultdict(list)
    for (vid, _), e in sorted(latest.items(), key=lambda kv: (kv[1]["date"], kv[1]["id"])):
        out[vid].append(e)
    return out


def _line_amount(line: dict, key: str) -> int:
    """A statement line's amount, or the sum of its items' when only the items carry it."""
    if line.get(key) is not None:
        return line[key]
    item_key = "charge" if key == "billed_charge" else key
    return sum(i.get(item_key) or 0 for i in line.get("items") or [])


def build_report(ds: Dataset, year: int, today: date) -> Report:
    providers = {p["id"]: p for p in ds.providers}
    members = {m["id"]: m for m in ds.members}
    accounts = {a["id"]: a for a in ds.accounts}
    group_of = _group_providers(ds.providers, ds.relationships)

    docs_by_type = defaultdict(list)
    for d in ds.documents:
        docs_by_type[d["type"]].append(d)
    claims_by_visit = current_claims(docs_by_type["eob"])
    lines_by_visit = defaultdict(list)
    for bill in sorted(docs_by_type["provider_bill"], key=lambda d: (d["date"], d["id"]), reverse=True):
        for line in bill["lines"]:
            lines_by_visit[line["visit_id"]].append((bill, line))
    receipts_by_visit = defaultdict(list)
    for r in docs_by_type["receipt"]:
        receipts_by_visit[r["visit_id"]].append(r)
    reimbursed = {pid for r in docs_by_type["account_reimbursement"] for pid in r["payment_ids"]}

    def is_hsa(payment):
        acct = accounts.get(payment["account_id"], {})
        return acct.get("type") == "hsa" or payment["id"] in reimbursed

    # Groups
    groups: dict[str, ProviderGroup] = {}
    for pid, gid in group_of.items():
        g = groups.setdefault(gid, ProviderGroup(id=gid, providers=[], unconfirmed=[]))
        g.providers.append(providers[pid])
    for r in ds.relationships:
        if r["status"] == "suspected" and r["provider_id"] in group_of:
            groups[group_of[r["provider_id"]]].unconfirmed.append(r)
    for bill in docs_by_type["provider_bill"]:
        if bill["provider_id"] in group_of:
            groups[group_of[bill["provider_id"]]].statements.append(bill)
    for g in groups.values():
        g.providers.sort(key=lambda p: p["name"])
        g.statements.sort(key=lambda b: (b["date"], b["id"]))

    # Visits in scope: dated in the year, or earlier visits still on a statement dated in the year
    ys = str(year)
    in_scope = []
    for v in ds.visits:
        carry_in = v["date"][:4] < ys and any(b["date"][:4] == ys for b, _ in lines_by_visit.get(v["id"], []))
        if v["date"][:4] == ys or carry_in:
            in_scope.append((v, carry_in))

    results: list[VisitResult] = []
    for v, carry_in in sorted(in_scope, key=lambda x: (x[0]["date"], x[0]["id"])):
        claims = claims_by_visit.get(v["id"], [])
        lines = lines_by_visit.get(v["id"], [])
        receipts = receipts_by_visit.get(v["id"], [])
        latest = lines[0][1] if lines else None
        receipt_total = sum(r["total"] for r in receipts)
        insurer_owed = sum(c["patient_responsibility"] for c in claims) if claims else None
        if latest is not None:
            billed_to_me = latest["patient_amount"]
        elif claims:
            billed_to_me = insurer_owed
        else:
            billed_to_me = receipt_total
        path = v.get("payment_path")
        insured = path == "insurance" or (path is None and v["category"] in INSURED_CATEGORIES)
        vr = VisitResult(
            visit=v, provider=providers[v["provider_id"]], member=members.get(v.get("member_id")),
            group_id=group_of[v["provider_id"]], carry_in=carry_in, claims=claims, bill_lines=lines,
            receipts=receipts,
            total_billed=(sum(c["billed"] for c in claims) if claims
                          else (_line_amount(latest, "billed_charge") or latest["patient_amount"] if latest
                                else receipt_total)),
            insurer_paid=(sum(c["insurer_paid"] for c in claims) if claims
                          else (latest.get("insurance_paid", 0) if latest else 0)),
            insurer_owed=insurer_owed, billed_to_me=billed_to_me, insured=insured,
            age=max((today - date.fromisoformat(v["date"])).days, 0), waiting_days=ds.waiting_days,
        )
        if latest is not None:
            # Provider write-offs after adjudication; asking less than the EOB counts as one (REC-02 TC-4).
            vr.write_off = _line_amount(latest, "write_off")
            if insurer_owed is not None and lines[0][0]["date"] >= max(c["date"] for c in claims):
                # A statement sent after the EOB that asks for less has written the difference off.
                vr.write_off += max(insurer_owed - vr.write_off - latest["patient_amount"], 0)
        if lines:
            last_listed = lines[0][0]["date"]
            later = [s for s in groups[vr.group_id].statements if s["date"] > last_listed]
            vr.settled = bool(later)
        results.append(vr)
        groups[vr.group_id].visits.append(vr)

    for p in docs_by_type["payment"]:
        if p["date"][:4] == ys and p["provider_id"] in group_of:
            groups[group_of[p["provider_id"]]].payments.append(p)
    for g in groups.values():
        g.payments.sort(key=lambda p: (p["date"], p["id"]))
        _allocate(g)
        for vr in g.visits:
            _settle(vr, is_hsa)

    for vr in results:
        _check_visit(vr, groups[vr.group_id], is_hsa, today)

    for g in groups.values():
        _summarize_group(g, is_hsa, ys)

    report_groups = sorted((g for g in groups.values() if g.visits or g.payments),
                           key=lambda g: (-(g.overpaid + g.gap + g.unpaid + g.no_claim_payments), g.name))
    return Report(
        year=year, today=today,
        visits=sorted((v for v in results if not v.carry_in), key=lambda v: (v.visit["date"], v.id), reverse=True),
        groups=report_groups,
        limits=_limit_progress(ds, year, [c for cs in claims_by_visit.values() for c in cs], members),
        years=available_years(ds) or [year],
        waiting_days=ds.waiting_days,
    )


# ---------- allocation (ALC-04, ADR-016, ADR-035) ----------

def _allocate(g: ProviderGroup) -> None:
    """Payments belong to the provider. A split the member set comes first, then the provider statement's split,
    then oldest visit first; what is left is an overpayment on the latest visit before the payment."""
    visits = g.visits
    by_id = {vr.id: vr for vr in visits}
    owed_left = {vr.id: max(vr.responsibility - vr.write_off, 0) for vr in visits}
    payments = [p for p in g.payments if p.get("kind") != "refund"]
    left = {p["id"]: p["amount"] for p in payments}

    def give(vr, p, amount, source):
        take = min(amount, max(owed_left[vr.id], 0))
        if take:
            vr.allocations.append(Allocation(p, take, source=source))
            owed_left[vr.id] -= take
        if amount - take:
            vr.allocations.append(Allocation(p, amount - take, surplus=True, source=source))
        left[p["id"]] -= amount

    for p in payments:  # 1. the member's split (MAT-07)
        for a in p.get("allocations") or []:
            if a["visit_id"] in by_id and left[p["id"]] >= a["amount"] > 0:
                give(by_id[a["visit_id"]], p, a["amount"], "member")

    for vr in visits:  # 2. the provider statement's split: what it credits to each visit (TC-ALC-04-1)
        if not vr.bill_lines:
            continue
        bill, line = vr.bill_lines[0]
        need = min(_line_amount(line, "patient_paid") - sum(a.amount for a in vr.allocations), owed_left[vr.id])
        for p in payments:
            if need <= 0:
                break
            if left[p["id"]] > 0 and p["date"] <= bill["date"] and not p.get("allocations"):
                take = min(need, left[p["id"]])
                give(vr, p, take, "statement")
                need -= take

    for p in payments:  # 3. oldest visit first, then the surplus
        if left[p["id"]] <= 0:
            continue
        for vr in visits:
            if left[p["id"]] <= 0:
                break
            if vr.visit["date"] <= p["date"] and owed_left[vr.id] > 0:
                give(vr, p, min(left[p["id"]], owed_left[vr.id]), "oldest")
        if left[p["id"]] > 0 and visits:
            before = [vr for vr in visits if vr.visit["date"] <= p["date"]]
            target = before[-1] if before else visits[0]
            target.allocations.append(Allocation(p, left[p["id"]], surplus=True))
            left[p["id"]] = 0

    for r in (p for p in g.payments if p.get("kind") == "refund"):  # refunds offset overpayments, latest first
        amount = r["amount"]
        for vr in sorted(visits, key=lambda v: v.visit["date"], reverse=True):
            take = min(amount, vr.overpaid)
            if take:
                vr.allocations.append(Allocation(r, take, refund=True))
                amount -= take
        if amount and visits:
            target = max((v for v in visits if v.paid), key=lambda v: v.visit["date"], default=visits[-1])
            target.allocations.append(Allocation(r, amount, refund=True))


def _settle(vr: VisitResult, is_hsa) -> None:
    """Identity 3 per visit (REC-13), and what is still owed and unexplained."""
    s = Settlement(responsibility=vr.responsibility, paid=vr.paid, refunds=vr.refunded, write_offs=vr.write_off)
    s.still_owed = s.responsibility - s.write_offs - s.paid + s.refunds
    s.paid_hsa = sum(a.amount for a in vr.allocations if not a.refund and is_hsa(a.payment))
    s.paid_other = s.paid - s.paid_hsa
    provider_owed = None
    if vr.settled:
        provider_owed = 0
    elif vr.bill_lines and "balance" in vr.bill_lines[0][1]:
        bill, line = vr.bill_lines[0]
        later = sum(a.amount for a in vr.allocations if not a.refund and a.payment["date"] > bill["date"])
        provider_owed = max(line["balance"] - later, 0)
    if provider_owed is not None:
        s.unexplained = max(s.still_owed - provider_owed, 0)
    vr.settlement = s
    vr.unexplained = s.unexplained
    vr.remaining = max(s.still_owed - s.unexplained, 0)


# ---------- checks and status ----------

def _check_visit(vr: VisitResult, g: ProviderGroup, is_hsa, today: date) -> None:
    eob, latest = vr.eob, vr.latest_line
    checks: list[Check] = []

    # REC-01 identities 1 and 2, per claim and per line (ALC-01 buckets alongside)
    if vr.claims:
        for claim in vr.claims:
            checks.append(_claim_check(claim, len(vr.claims) > 1))
            lines = claim.get("lines") or []
            for i, line in enumerate(lines):
                vr.line_buckets.append((f"{line.get('code') or line.get('description') or f'Line {i + 1}'}",
                                        buckets(line)))
        vr.buckets = add_buckets(*(_claim_buckets(c) for c in vr.claims))
    elif not vr.insured and latest:
        d = self_pay_difference(latest[1])
        if d is not None:
            result = judge(d)
            detail = ("Billed = self-pay discount + your cost; no EOB expected" if result == "pass" else
                      f"billed {fmt(latest[1]['billed_charge'])} differs from self-pay discount + your cost by "
                      f"{fmt(d)}")
            checks.append(Check("self_pay", result, detail, abs(d)))
        else:
            checks.append(Check("C1", "na", "No insurance claim for this visit"))
        vr.buckets = self_pay_buckets(latest[1])
    elif not vr.insured:
        checks.append(Check("C1", "na", "No insurance claim for this visit"))
        if vr.receipts:
            vr.buckets = {"member_responsibility": sum(r["total"] for r in vr.receipts)}
    else:
        checks.append(Check("C1", "na", "No EOB" if vr.insured else "No insurance claim for this visit"))

    checks.append(_bill_vs_eob(vr))
    checks.append(_line_check(vr))
    checks.extend(_duplicate_checks(vr, g))
    checks.append(_network_check(vr))

    if vr.overpaid:
        result = judge(vr.overpaid)
        detail = (f"You paid {fmt(vr.overpaid)} more than you owe for this visit (all payment methods combined). "
                  f"Ask {vr.provider['name']} for a refund or a credit." if result == "fail"
                  else f"Paid {fmt(vr.overpaid)} more than you owe")
        checks.append(Check("C4", result, detail, vr.overpaid, "overpayment"))
    elif vr.surplus and vr.refunded:
        checks.append(Check("C4", "pass", f"A refund of {fmt(vr.refunded)} cleared the overpayment"))
    elif vr.paid:
        checks.append(Check("C4", "pass", f"Payments of {fmt(vr.paid)} applied"))
    else:
        checks.append(Check("C4", "na", "No payments applied"))

    checks.append(_settlement_check(vr, g))

    if vr.insured and not vr.claims and latest and not vr.awaiting_eob:
        bill = latest[0]
        checks.append(Check(
            "claim_filed", "fail",
            f"{vr.provider['name']} billed you {fmt(latest[1]['patient_amount'])} (statement of {bill['date']}), but "
            f"no insurance decision has arrived {vr.age} days after the visit. The provider may not have filed with "
            f"your insurance: ask them to file the claim, since what you owe may drop once the insurer processes it.",
            latest[1]["patient_amount"], "not_filed"))

    if vr.remaining:
        _age_balance(vr, today)
        basis = f"per statement of {latest[0]['date']}" if latest else "per insurer"
        detail = f"{fmt(vr.remaining)} unpaid {basis}"
        if vr.balance_age is not None:
            detail += f"; first billed {vr.balance_age} days ago"
        if vr.notices >= 2:
            detail += f"; second notice or later (on {vr.notices} statements)"
        if vr.notice_label:
            detail += f"; statement says \"{vr.notice_label}\""
        if vr.awaiting_eob:
            checks.append(Check("C6", "info", detail + ". Wait for the insurer's decision (EOB) before paying: "
                                "it says what you really owe", vr.remaining))
        else:
            checks.append(Check("C6", "fail", detail, vr.remaining))
    elif vr.settled and vr.unexplained:
        checks.append(Check("C6", "pass", "Provider's later statement no longer lists this visit"))
    else:
        checks.append(Check("C6", "pass" if vr.billed_to_me else "na", "Nothing owed"))

    closed = {(f["code"], f["amount"]): f for f in vr.visit.get("closed_findings") or []}
    for c in checks:
        if c.result == "fail" and (c.code, c.amount) in closed:
            c.result, c.closed = "closed", closed[(c.code, c.amount)]
    vr.checks = checks

    vr.review = _proposed(vr)
    vr.documents = _documents(vr)
    vr.missing = ["Receipt or bill" if d.note.startswith("or a") else "EOB" if d.kind == "eob" else d.label
                  for d in vr.documents if d.state == "expected" and d.blocking]
    vr.status = _status(vr, today)

    if vr.remaining:
        if vr.awaiting_eob:
            vr.hsa_flags.append(f"Statement asks {fmt(vr.remaining)}; wait for the EOB before paying from the HSA")
        else:
            vr.hsa_flags.append(f"Unpaid {fmt(vr.remaining)} — pay from HSA")
    vr.outside_hsa = sum(a.amount for a in vr.allocations if not a.refund and not is_hsa(a.payment))
    if vr.outside_hsa:
        vr.hsa_flags.append(f"{fmt(vr.outside_hsa)} paid outside the HSA — submit an HSA reimbursement claim")
    if vr.unexplained:
        vr.hsa_flags.append(f"Provider shows {fmt(vr.unexplained)} settled, but no matching payment found — paid outside the HSA?")

    stake = max((c.amount for c in checks if c.result == "fail" and c.code in STAKE_CODES), default=0)
    overpaid = vr.overpaid if any(c.code == "C4" and c.result == "fail" for c in checks) else 0
    vr.at_stake = max(stake, overpaid)  # paying an inflated bill is the same dollars as the bill's excess


def _claim_check(claim: dict, several: bool) -> Check:
    diffs = claim_differences(claim)
    failing = [d for d in diffs if d.result == "fail"]
    shown = failing or [d for d in diffs if d.result == "cleared"]
    prefix = f"Claim {claim['claim_number']}: " if several and claim.get("claim_number") else ""
    if not shown:
        lines = len(claim.get("lines") or [])
        detail = "Billed = insurer paid + discount + savings + your cost"
        if lines:
            detail += f", on the claim and each of its {lines} line{'s' if lines != 1 else ''}"
        return Check("C1", "pass", prefix + detail)
    detail = "; ".join(f"{d.where}: {d.what}" if d.where.startswith("line") else d.what for d in shown)
    return Check("C1", "fail" if failing else "cleared", prefix + detail, max(d.amount for d in shown))


def _claim_buckets(claim: dict) -> dict[str, int]:
    lines = claim.get("lines") or []
    if lines and all(l.get("billed") is not None for l in lines) and sum(l["billed"] for l in lines) == claim["billed"] \
            and all(l.get("patient_responsibility") is not None and l.get("insurer_paid") is not None for l in lines):
        return add_buckets(*(buckets(l) for l in lines))
    return buckets(claim)


def _bill_vs_eob(vr: VisitResult) -> Check:
    """REC-02: the provider asks more than the EOB says (a missed adjustment or balance billing), or its
    charges differ from the claim's."""
    eob, latest = vr.eob, vr.latest_line
    if not (eob and latest):
        if latest and not eob and vr.insured:
            return Check("C2", "na", "Waiting for the insurer's decision (EOB) before comparing it with the bill")
        return Check("C2", "na", "Needs both an EOB and a provider statement")
    bill, line = latest
    asks, owes = line["patient_amount"], eob["patient_responsibility"]
    d_pt = asks - owes
    billed_charge = _line_amount(line, "billed_charge") if (line.get("billed_charge") is not None or line.get("items")) \
        else eob["billed"]
    d_billed = eob["billed"] - billed_charge
    parts, results, amounts, kind = [], [], [], ""
    if d_pt > 0:
        text = f"statement of {bill['date']} asks {fmt(asks)}, EOB says you owe {fmt(owes)}"
        eob_adj = sum(adjustment_of(c) or 0 for c in vr.claims)
        missed = eob_adj - _line_amount(line, "adjustment")
        if missed > 0:
            kind = "missed_adjustment"
            text += (f". The statement doesn't apply the plan's {fmt(eob_adj)} discount (a missed adjustment): ask "
                     f"{vr.provider['name']} to apply the EOB and send a corrected bill")
        else:
            kind = "balance_billing"
            text += (". The provider is billing you for more than the plan allows (balance billing); an in-network "
                     "provider has agreed to accept the plan's allowed amount")
        parts.append(text)
        results.append(judge(d_pt))
        amounts.append(d_pt)
    if d_billed:
        parts.append(f"insurer was billed {fmt(eob['billed'])}, statement shows {fmt(billed_charge)} in charges "
                     f"(charges sent to the insurer that the statement doesn't show you, or the reverse)")
        results.append(judge(d_billed))
        amounts.append(abs(d_billed))
        kind = kind or "billed_mismatch"
    if "fail" in results or "cleared" in results:
        result = "fail" if "fail" in results else "cleared"
        if d_pt < 0:
            parts.append(f"it asks {fmt(-d_pt)} less than the EOB says you owe")
        return Check("C2", result, "; ".join(parts), max(amounts), kind)
    if d_pt < 0:
        return Check("C2", "info", f"Statement of {bill['date']} asks {fmt(asks)}, {fmt(-d_pt)} less than the EOB "
                                   f"says you owe ({fmt(owes)}); no overcharge")
    return Check("C2", "pass", f"Statement of {bill['date']} matches the EOB")


def _line_check(vr: VisitResult) -> Check:
    """MAT-06: pair the bill's lines with the EOB's. Leftover lines are listed, not findings (ADR-035)."""
    items = (vr.latest_line[1].get("items") or []) if vr.latest_line else []
    eob_lines = [l for c in vr.claims for l in c.get("lines") or []]
    if not (items and eob_lines):
        return Check("lines", "na", "Needs line detail on both the statement and the EOB")
    when = vr.visit["date"]
    vr.line_match = m = pair_lines([{"service_date": when, **i} for i in items],
                                   [{"service_date": when, **l} for l in eob_lines])
    paired = sum(len(p.bill) for p in m.pairs)
    detail = f"{paired} of {len(items)} bill line{'s' if len(items) != 1 else ''} paired with the EOB"
    notes = [n for p in m.pairs for n in p.notes]
    if m.bill_only:
        detail += "; on the bill only: " + ", ".join(
            f"{i.get('code') or i.get('description') or 'a line'} {fmt(i.get('charge') or 0)}" for i in m.bill_only)
    if m.eob_only:
        detail += "; on the EOB only: " + ", ".join(
            f"{l.get('code') or l.get('description') or 'a line'} {fmt(l.get('billed') or 0)}" for l in m.eob_only)
    if notes:
        detail += ". " + "; ".join(notes)
    return Check("lines", "pass" if m.complete and not notes else "info", detail)


def _duplicate_checks(vr: VisitResult, g: ProviderGroup) -> list[Check]:
    """REC-04: the same code, date and provider twice on the visit's latest statement."""
    if not vr.latest_line:
        return []
    bill = vr.latest_line[0]
    dates = {v.id: v.visit["date"] for v in g.visits}
    items = []
    for line in bill["lines"]:  # an item without its own date is on its visit's date
        for i in line.get("items") or []:
            items.append({"service_date": dates.get(line["visit_id"], line["visit_id"]), **i,
                          "_visit": line["visit_id"]})
    out = []
    for a, b in duplicate_items(items):
        if b["_visit"] != vr.id:
            continue
        amount = b.get("charge") or 0
        out.append(Check("duplicate", "fail",
                         f"{b['code']} appears twice on the statement of {bill['date']} ({fmt(amount)} the second time). "
                         f"Ask {vr.provider['name']} to remove the duplicate charge.", amount, "duplicate_charge"))
    return out or [Check("duplicate", "pass" if items else "na",
                         "No charge appears twice" if items else "No line detail on the statement")]


def _network_check(vr: VisitResult) -> Check:
    known = {}
    if vr.eob:
        known["EOB"] = vr.eob.get("network_status")
    if vr.latest_line:
        known["statement"] = vr.latest_line[0].get("network_status_shown")
    known["provider record"] = vr.provider.get("network_status")
    known = {k: s for k, s in known.items() if s in ("in_network", "out_of_network")}
    if len(set(known.values())) > 1:
        return Check("C3", "fail", ", ".join(f"{k}: {s.replace('_', ' ')}" for k, s in known.items()))
    if len(known) >= 2:
        return Check("C3", "pass", "All sources agree")
    return Check("C3", "na", "Network status known from fewer than two sources")


def _settlement_check(vr: VisitResult, g: ProviderGroup) -> Check:
    s = vr.settlement
    if not s.responsibility and not s.paid:
        return Check("settlement", "na", "Nothing owed")
    if s.unexplained:
        result = judge(s.unexplained)
        if vr.settled:
            later = next(st for st in g.statements if st["date"] > vr.bill_lines[0][0]["date"])
            why = (f"the provider's statement of {later['date']} no longer lists this visit, and no payment, refund "
                   f"or write-off covers it. If you paid another way (a card, a check), add the payment; otherwise "
                   f"ask the provider why it was dropped")
        else:
            bill, line = vr.bill_lines[0]
            why = (f"the provider's statement of {bill['date']} shows {fmt(line['balance'])} still owed, less than "
                   f"your payments, refunds and write-offs leave ({fmt(s.still_owed)})")
        return Check("settlement", result, f"Of the {fmt(s.responsibility)} you owe, {fmt(s.unexplained)} isn't "
                                           f"explained: {why}", s.unexplained, "unexplained")
    parts = [f"you owe {fmt(s.responsibility)}", f"paid {fmt(s.paid)}"]
    if s.refunds:
        parts.append(f"refunded {fmt(s.refunds)}")
    if s.write_offs:
        parts.append(f"written off {fmt(s.write_offs)}")
    owed = (f"still owed {fmt(s.still_owed)}" if s.still_owed >= 0 else f"credit due to you {fmt(-s.still_owed)}")
    return Check("settlement", "pass", ", ".join(parts) + f", {owed}")


def _proposed(vr: VisitResult) -> list[dict]:
    """Documents linked to the visit by a proposed match the member hasn't confirmed (MAT-05)."""
    out = []
    for c in vr.claims:
        if (c.get("match") or {}).get("status") == "proposed":
            out.append({"doc": c, "line": None, "match": c["match"]})
    for bill, line in vr.bill_lines:
        if (line.get("match") or {}).get("status") == "proposed":
            out.append({"doc": bill, "line": line, "match": line["match"]})
    for r in vr.receipts:
        if (r.get("match") or {}).get("status") == "proposed":
            out.append({"doc": r, "line": None, "match": r["match"]})
    return out


def _documents(vr: VisitResult) -> list[DocumentState]:
    """MAT-10: which documents are present, expected or not applicable, by payment path and category."""
    category = vr.visit["category"]
    bill_or_receipt = not vr.insured and category not in ("supplements", "equipment")  # rx, self-pay visits
    has_items = any(line.get("items") for _, line in vr.bill_lines)
    owed = vr.responsibility > 0
    out = [
        DocumentState("eob", "present" if vr.claims else "expected" if vr.insured else "not_applicable"),
        DocumentState("bill", "present" if vr.bill_lines else
                      "expected" if bill_or_receipt and not vr.receipts and not vr.claims else
                      "expected" if vr.insured and vr.claims and vr.remaining else "not_applicable",
                      "or a receipt" if bill_or_receipt else "",
                      blocking=bill_or_receipt),
        DocumentState("itemized_bill", "present" if has_items else "not_applicable"),
        DocumentState("receipt", "present" if vr.receipts else
                      "expected" if category in ("supplements", "equipment") and not vr.insured else
                      "expected" if bill_or_receipt and not vr.bill_lines and not vr.claims else "not_applicable",
                      "or a bill" if bill_or_receipt else ""),
        DocumentState("payment", "present" if vr.paid else "expected" if owed else "not_applicable", blocking=False),
    ]
    if bill_or_receipt:  # one of the two is enough: show the bill as the expected one only once
        for d in out:
            if d.kind == "receipt" and d.state == "expected":
                d.blocking = False
    choices = vr.visit.get("documents") or {}
    for d in out:
        d.since = vr.visit["date"]
        choice = choices.get(d.kind)
        if not choice or d.state == "present":
            continue
        d.state = choice["state"]
        d.since = choice.get("since", d.since)
        d.note = "marked by you" if choice["state"] == "not_applicable" else "you asked for it"
        d.blocking = d.kind != "payment"
    return out


def _status(vr: VisitResult, today: date) -> str:
    """REC-11: the first status that applies (ADR-009)."""
    if (vr.dispute or {}).get("status") == "open":
        return "in_dispute"
    if any(c.result == "fail" and c.code in DISCREPANCY_CODES for c in vr.checks):
        return "discrepancy"
    if vr.review:
        return "needs_review"
    if vr.remaining and not vr.awaiting_eob:
        return "balance_outstanding"
    expected = [d for d in vr.documents if d.state == "expected" and d.blocking]

    def waiting(d: DocumentState) -> bool:
        return (today - date.fromisoformat(d.since)).days < vr.waiting_days

    if any(d.kind == "eob" and waiting(d) for d in expected):
        return "awaiting_eob"
    if any(d.kind != "eob" and waiting(d) for d in expected):
        return "awaiting_documents"
    if expected:
        return "missing_documents"
    if any(c.result == "closed" for c in vr.checks) or (vr.dispute or {}).get("status") == "closed" \
            or (vr.surplus and vr.refunded and not vr.overpaid):
        return "resolved"
    return "complete"


def _age_balance(vr: VisitResult, today: date) -> None:
    """Age an open balance from the first statement that asked for it, else from the EOB."""
    owed = [(bill, line) for bill, line in vr.bill_lines if line.get("balance", line["patient_amount"]) > 0]
    if owed:
        first = min(bill["date"] for bill, _ in owed)
        vr.notices = len({bill["id"] for bill, _ in owed})
        vr.notice_label = owed[0][0].get("notice", "")  # bill_lines are newest first
    elif vr.claims:
        first = vr.claims[0]["date"]
    else:
        return
    vr.balance_age = max((today - date.fromisoformat(first)).days, 0)


def _summarize_group(g: ProviderGroup, is_hsa, ys: str) -> None:
    payments = [p for p in g.payments if p.get("kind") != "refund"]
    refunds = [p for p in g.payments if p.get("kind") == "refund"]
    g.paid = sum(p["amount"] for p in payments) - sum(p["amount"] for p in refunds)
    g.paid_outside_hsa = sum(p["amount"] for p in payments if not is_hsa(p))
    g.should_owe = sum(v.responsibility - v.write_off for v in g.visits)
    g.billed_to_me = sum(v.billed_to_me for v in g.visits)
    g.unpaid = sum(v.remaining for v in g.visits)
    g.settlement = sum((v.settlement for v in g.visits), Settlement())
    g.cleared_total = sum(c.amount for v in g.visits if v.visit["date"][:4] == ys for c in v.cleared)
    if not g.visits:
        g.no_claim_payments = g.paid
    else:
        g.overpaid = max(g.paid - g.should_owe, 0)
        g.gap = max(g.should_owe - g.paid - g.unpaid - sum(v.unexplained for v in g.visits), 0)

    in_year = [s for s in g.statements if s["date"][:4] == ys]
    if in_year:
        g.latest_statement = in_year[-1]
        after = sum(p["amount"] for p in payments if p["date"] > g.latest_statement["date"])
        g.provider_says_owed = max(g.latest_statement["balance_due"] - after, 0)

    for i, a in enumerate(payments):
        for b in payments[i + 1:]:
            if a["amount"] == b["amount"] and _days(a["date"], b["date"]) <= DUPLICATE_WINDOW_DAYS:
                g.duplicates.append((a, b))

    entries = []
    for v in g.visits:
        owed = v.responsibility - v.write_off
        basis = "EOB" if v.insurer_owed is not None else ("statement" if v.bill_lines else "receipt")
        desc = f"{v.provider['name']}: {v.visit.get('description', 'visit')} (you owe per {basis})"
        entries.append(LedgerEntry(v.visit["date"], "charge", desc, charge=owed, ref=v.id))
    for p in g.payments:
        kind = "refund" if p.get("kind") == "refund" else "payment"
        amount = -p["amount"] if kind == "refund" else p["amount"]
        source = "HSA" if is_hsa(p) else "outside HSA"
        entries.append(LedgerEntry(p["date"], kind, f"{kind.title()} ({source}) {p.get('reference', '')}".strip(),
                                   payment=amount, ref=p["id"]))
    for s in g.statements:
        if s["date"][:4] == ys:
            entries.append(LedgerEntry(s["date"], "statement", f"Statement: {fmt(s['balance_due'])} due", ref=s["id"]))
    order = {"charge": 0, "statement": 1, "payment": 2, "refund": 2}
    entries.sort(key=lambda e: (e.date, order[e.kind]))
    running = 0
    for e in entries:
        running += e.charge - e.payment
        e.balance = running
    g.ledger = entries


def _limit_progress(ds: Dataset, year: int, claims: list[dict], members: dict) -> list[LimitProgress]:
    out = []
    visits = {v["id"]: v for v in ds.visits}
    for plan in ds.plans:
        if plan.get("plan_year") != year:
            continue
        eobs = [e for e in claims
                if visits.get(e["visit_id"], {}).get("plan_id") == plan["id"] and e.get("claim_status") != "denied"]
        claim_members = {visits[e["visit_id"]].get("member_id") for e in eobs}
        covered = plan.get("member_ids") or sorted(m for m in claim_members if m)
        for limit in plan.get("limits", []):
            network = limit["network"]

            def in_network_scope(e):
                status = e.get("network_status", "unknown")
                if network == "combined":
                    return True
                if network == "in_network":
                    return status != "out_of_network"
                return status == "out_of_network"

            if limit["level"] == "individual":
                member_ids = [limit["member_id"]] if limit.get("member_id") else covered
            else:
                member_ids = None
            for mid in (member_ids or [None]):
                scoped = [e for e in eobs if in_network_scope(e)
                          and (mid is None or visits[e["visit_id"]].get("member_id") == mid)]
                if limit["type"] == "deductible":
                    used = sum(e.get("deductible", 0) for e in scoped)
                elif limit["type"] == "out_of_pocket_max":
                    used = sum(e.get("deductible", 0) + e.get("copay", 0) + e.get("coinsurance", 0) for e in scoped)
                else:  # annual_maximum: what the plan paid
                    used = sum(e["insurer_paid"] for e in scoped)
                if mid:
                    who = members.get(mid, {}).get("name", mid)
                else:
                    who = "Family" if limit["level"] == "family" else "Individual"
                kind = {"deductible": "deductible", "out_of_pocket_max": "out-of-pocket max",
                        "annual_maximum": "annual maximum"}[limit["type"]]
                label = f"{who} {network.replace('_', '-')} {kind}"
                names = sorted(members.get(m, {}).get("name", m) for m in claim_members if m)
                note = ""
                if mid is None and names:
                    note = "Includes claims imported for: " + ", ".join(names)
                if network == "in_network" and any(e.get("network_status", "unknown") == "unknown" for e in scoped):
                    note = (note + ". " if note else "") + "Claims with unknown network status are counted as in-network"
                out.append(LimitProgress(plan, limit, label, used, names, note, mid))
    return out


_fmt = fmt  # Release 0 name
