"""Reconciliation engine: checks, visit status, provider ledgers, HSA gaps and plan-limit progress.

Pure functions over plain record dicts (money in integer cents). No database or web imports.
Rules are documented in docs/MVP_REQUIREMENTS.md section 5.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

WAITING_DAYS = 30
DUPLICATE_WINDOW_DAYS = 14
INSURED_CATEGORIES = {"provider_visit", "service"}

STATUS_ORDER = ["discrepancy", "balance_outstanding", "missing_documents", "waiting", "matched"]
STATUS_LABELS = {
    "discrepancy": "Discrepancy",
    "balance_outstanding": "Balance outstanding",
    "missing_documents": "Missing documents",
    "waiting": "Waiting",
    "matched": "Matched",
}
CHECK_NAMES = {
    "C1": "EOB adds up",
    "C2": "Bill matches EOB",
    "C3": "Network status agrees",
    "C4": "Paid matches what was billed",
    "C6": "Balance outstanding",
}


@dataclass
class Dataset:
    plans: list[dict] = field(default_factory=list)
    accounts: list[dict] = field(default_factory=list)
    members: list[dict] = field(default_factory=list)
    providers: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    visits: list[dict] = field(default_factory=list)
    documents: list[dict] = field(default_factory=list)


@dataclass
class Check:
    code: str
    result: str  # pass | fail | na
    detail: str = ""
    amount: int = 0

    @property
    def name(self) -> str:
        return CHECK_NAMES[self.code]


@dataclass
class Allocation:
    payment: dict
    amount: int
    surplus: bool = False  # paid beyond what any visit was billed


@dataclass
class VisitResult:
    visit: dict
    provider: dict
    member: dict | None
    group_id: str
    carry_in: bool  # earlier-year visit still on a statement in this year
    eob: dict | None
    bill_lines: list[tuple[dict, dict]]  # (bill, line), newest bill first
    receipts: list[dict]
    total_billed: int
    insurer_paid: int
    insurer_owed: int | None  # EOB patient responsibility
    billed_to_me: int  # latest statement amount, else EOB responsibility, else receipt total
    settled: bool = False  # dropped off a later statement from the same provider
    allocations: list[Allocation] = field(default_factory=list)
    remaining: int = 0
    unexplained: int = 0  # settled per provider but no matching payment in the data
    checks: list[Check] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    status: str = "matched"
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
    def paid(self) -> int:
        return sum(a.amount for a in self.allocations)

    @property
    def overpaid(self) -> int:
        return sum(a.amount for a in self.allocations if a.surplus)

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    @property
    def latest_line(self) -> tuple[dict, dict] | None:
        return self.bill_lines[0] if self.bill_lines else None


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
        return out


@dataclass
class LimitProgress:
    plan: dict
    limit: dict
    label: str
    used: int
    member_names: list[str]
    note: str = ""

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


def _days(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def available_years(ds: Dataset) -> list[int]:
    years = {int(v["date"][:4]) for v in ds.visits}
    years |= {int(d["date"][:4]) for d in ds.documents if d["type"] == "payment"}
    return sorted(years, reverse=True)


def build_report(ds: Dataset, year: int, today: date) -> Report:
    providers = {p["id"]: p for p in ds.providers}
    members = {m["id"]: m for m in ds.members}
    accounts = {a["id"]: a for a in ds.accounts}
    group_of = _group_providers(ds.providers, ds.relationships)

    docs_by_type = defaultdict(list)
    for d in ds.documents:
        docs_by_type[d["type"]].append(d)
    eob_by_visit = {}
    for e in sorted(docs_by_type["eob"], key=lambda d: d["date"]):
        eob_by_visit[e["visit_id"]] = e  # latest wins
    lines_by_visit = defaultdict(list)
    for bill in sorted(docs_by_type["provider_bill"], key=lambda d: d["date"], reverse=True):
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
        g.statements.sort(key=lambda b: b["date"])

    # Visits in scope: dated in the year, or earlier visits still on a statement dated in the year
    ys = str(year)
    in_scope = []
    for v in ds.visits:
        carry_in = v["date"][:4] < ys and any(b["date"][:4] == ys for b, _ in lines_by_visit.get(v["id"], []))
        if v["date"][:4] == ys or carry_in:
            in_scope.append((v, carry_in))

    results: list[VisitResult] = []
    for v, carry_in in sorted(in_scope, key=lambda x: x[0]["date"]):
        eob = eob_by_visit.get(v["id"])
        lines = lines_by_visit.get(v["id"], [])
        receipts = receipts_by_visit.get(v["id"], [])
        latest = lines[0][1] if lines else None
        receipt_total = sum(r["total"] for r in receipts)
        insurer_owed = eob["patient_responsibility"] if eob else None
        if latest is not None:
            billed_to_me = latest["patient_amount"]
        elif eob:
            billed_to_me = insurer_owed
        else:
            billed_to_me = receipt_total
        vr = VisitResult(
            visit=v, provider=providers[v["provider_id"]], member=members.get(v.get("member_id")),
            group_id=group_of[v["provider_id"]], carry_in=carry_in, eob=eob, bill_lines=lines, receipts=receipts,
            total_billed=eob["billed"] if eob else (latest.get("billed_charge", 0) if latest else receipt_total),
            insurer_paid=eob["insurer_paid"] if eob else (latest.get("insurance_paid", 0) if latest else 0),
            insurer_owed=insurer_owed, billed_to_me=billed_to_me,
        )
        if lines:
            last_listed = lines[0][0]["date"]
            later = [s for s in groups[vr.group_id].statements if s["date"] > last_listed]
            vr.settled = bool(later)
        results.append(vr)
        groups[vr.group_id].visits.append(vr)

    # Payments: allocate oldest-first to the group's visits on or before the payment date
    for p in docs_by_type["payment"]:
        if p["date"][:4] == ys and p["provider_id"] in group_of:
            groups[group_of[p["provider_id"]]].payments.append(p)
    for g in groups.values():
        g.payments.sort(key=lambda p: p["date"])
        owed_left = {vr.id: vr.billed_to_me for vr in g.visits}
        for p in g.payments:
            if p.get("kind") == "refund":
                continue
            left = p["amount"]
            for vr in g.visits:
                if left <= 0:
                    break
                if vr.visit["date"] <= p["date"] and owed_left[vr.id] > 0:
                    take = min(left, owed_left[vr.id])
                    owed_left[vr.id] -= take
                    left -= take
                    vr.allocations.append(Allocation(p, take))
            if left > 0 and g.visits:
                before = [vr for vr in g.visits if vr.visit["date"] <= p["date"]]
                target = before[-1] if before else g.visits[0]
                target.allocations.append(Allocation(p, left, surplus=True))
        for vr in g.visits:
            if vr.settled:
                vr.unexplained, vr.remaining = owed_left[vr.id], 0
            else:
                vr.remaining = owed_left[vr.id]

    for vr in results:
        _check_visit(vr, is_hsa, today)

    for g in groups.values():
        _summarize_group(g, is_hsa, ys)

    report_groups = sorted((g for g in groups.values() if g.visits or g.payments),
                           key=lambda g: (-(g.overpaid + g.gap + g.unpaid + g.no_claim_payments), g.name))
    return Report(
        year=year, today=today,
        visits=sorted((v for v in results if not v.carry_in), key=lambda v: v.visit["date"], reverse=True),
        groups=report_groups,
        limits=_limit_progress(ds, year, eob_by_visit, members),
        years=available_years(ds) or [year],
    )


def _check_visit(vr: VisitResult, is_hsa, today: date) -> None:
    eob, latest = vr.eob, vr.latest_line
    checks = []

    if eob:
        billed_parts = eob["insurer_paid"] + eob.get("adjustment", 0) + eob.get("additional_savings", 0) + eob["patient_responsibility"]
        resp_parts = sum(eob.get(k, 0) for k in ("deductible", "copay", "coinsurance", "not_covered"))
        d1, d2 = eob["billed"] - billed_parts, eob["patient_responsibility"] - resp_parts
        if d1 or d2:
            parts = []
            if d1:
                parts.append(f"billed differs from paid + discount + savings + your cost by {_fmt(d1)}")
            if d2:
                parts.append(f"your cost differs from deductible + copay + coinsurance + not covered by {_fmt(d2)}")
            checks.append(Check("C1", "fail", "; ".join(parts), max(abs(d1), abs(d2))))
        else:
            checks.append(Check("C1", "pass", "Billed = insurer paid + discount + savings + your cost"))
    else:
        checks.append(Check("C1", "na", "No EOB"))

    if eob and latest:
        bill, line = latest
        d_pt = line["patient_amount"] - eob["patient_responsibility"]
        d_billed = eob["billed"] - line.get("billed_charge", eob["billed"])
        if d_pt or d_billed:
            parts = []
            if d_pt:
                parts.append(f"statement of {bill['date']} asks {_fmt(line['patient_amount'])}, EOB says you owe {_fmt(eob['patient_responsibility'])}")
            if d_billed:
                parts.append(f"insurer was billed {_fmt(eob['billed'])}, statement shows {_fmt(line.get('billed_charge', 0))} in charges")
            checks.append(Check("C2", "fail", "; ".join(parts), max(abs(d_pt), abs(d_billed))))
        else:
            checks.append(Check("C2", "pass", f"Statement of {bill['date']} matches the EOB"))
    else:
        checks.append(Check("C2", "na", "Needs both an EOB and a provider statement"))

    known = {}
    if eob:
        known["EOB"] = eob.get("network_status")
    if latest:
        known["statement"] = latest[0].get("network_status_shown")
    known["provider record"] = vr.provider.get("network_status")
    known = {k: s for k, s in known.items() if s in ("in_network", "out_of_network")}
    if len(set(known.values())) > 1:
        checks.append(Check("C3", "fail", ", ".join(f"{k}: {s.replace('_', ' ')}" for k, s in known.items())))
    elif len(known) >= 2:
        checks.append(Check("C3", "pass", "All sources agree"))
    else:
        checks.append(Check("C3", "na", "Network status known from fewer than two sources"))

    if vr.overpaid:
        checks.append(Check("C4", "fail", f"Paid {_fmt(vr.overpaid)} more than was owed for this visit", vr.overpaid))
    elif vr.paid:
        checks.append(Check("C4", "pass", f"Payments of {_fmt(vr.paid)} applied"))
    else:
        checks.append(Check("C4", "na", "No payments applied"))

    if vr.remaining:
        _age_balance(vr, today)
        basis = f"per statement of {latest[0]['date']}" if latest else "per insurer"
        detail = f"{_fmt(vr.remaining)} unpaid {basis}"
        if vr.balance_age is not None:
            detail += f"; first billed {vr.balance_age} days ago"
        if vr.notices >= 2:
            detail += f"; second notice or later (on {vr.notices} statements)"
        if vr.notice_label:
            detail += f"; statement says \"{vr.notice_label}\""
        checks.append(Check("C6", "fail", detail, vr.remaining))
    elif vr.settled and vr.unexplained:
        checks.append(Check("C6", "pass", "Provider's later statement no longer lists this visit"))
    else:
        checks.append(Check("C6", "pass" if vr.billed_to_me else "na", "Nothing owed"))
    vr.checks = checks

    category = vr.visit["category"]
    if category in INSURED_CATEGORIES and not eob:
        vr.missing.append("EOB")
    if category in ("supplements", "equipment") and not vr.receipts:
        vr.missing.append("Receipt")
    if category == "rx" and not (vr.receipts or vr.bill_lines or eob):
        vr.missing.append("Receipt or bill")

    failed = {c.code for c in checks if c.result == "fail"}
    if failed & {"C1", "C2", "C3", "C4"}:
        vr.status = "discrepancy"
    elif vr.remaining:
        vr.status = "balance_outstanding"
    elif vr.missing:
        age = (today - date.fromisoformat(vr.visit["date"])).days
        vr.status = "waiting" if age < WAITING_DAYS else "missing_documents"
    else:
        vr.status = "matched"

    if vr.remaining:
        vr.hsa_flags.append(f"Unpaid {_fmt(vr.remaining)} — pay from HSA")
    vr.outside_hsa = sum(a.amount for a in vr.allocations if not is_hsa(a.payment))
    if vr.outside_hsa:
        vr.hsa_flags.append(f"{_fmt(vr.outside_hsa)} paid outside the HSA — submit an HSA reimbursement claim")
    if vr.unexplained:
        vr.hsa_flags.append(f"Provider shows {_fmt(vr.unexplained)} settled, but no matching payment found — paid outside the HSA?")

    stake = max((c.amount for c in checks if c.result == "fail" and c.code in ("C1", "C2")), default=0)
    vr.at_stake = stake + vr.overpaid


def _age_balance(vr: VisitResult, today: date) -> None:
    """Age an open balance from the first statement that asked for it, else from the EOB."""
    owed = [(bill, line) for bill, line in vr.bill_lines if line.get("balance", line["patient_amount"]) > 0]
    if owed:
        first = min(bill["date"] for bill, _ in owed)
        vr.notices = len({bill["id"] for bill, _ in owed})
        vr.notice_label = owed[0][0].get("notice", "")  # bill_lines are newest first
    elif vr.eob:
        first = vr.eob["date"]
    else:
        return
    vr.balance_age = max((today - date.fromisoformat(first)).days, 0)


def _summarize_group(g: ProviderGroup, is_hsa, ys: str) -> None:
    payments = [p for p in g.payments if p.get("kind") != "refund"]
    refunds = [p for p in g.payments if p.get("kind") == "refund"]
    g.paid = sum(p["amount"] for p in payments) - sum(p["amount"] for p in refunds)
    g.paid_outside_hsa = sum(p["amount"] for p in payments if not is_hsa(p))
    g.should_owe = sum(v.insurer_owed if v.insurer_owed is not None else v.billed_to_me for v in g.visits)
    g.billed_to_me = sum(v.billed_to_me for v in g.visits)
    g.unpaid = sum(v.remaining for v in g.visits)
    if not g.visits:
        g.no_claim_payments = g.paid
    else:
        g.overpaid = max(g.paid - g.should_owe, 0)
        g.gap = max(g.should_owe - g.paid - g.unpaid, 0)

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
        owed = v.insurer_owed if v.insurer_owed is not None else v.billed_to_me
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
            entries.append(LedgerEntry(s["date"], "statement", f"Statement: {_fmt(s['balance_due'])} due", ref=s["id"]))
    order = {"charge": 0, "statement": 1, "payment": 2, "refund": 2}
    entries.sort(key=lambda e: (e.date, order[e.kind]))
    running = 0
    for e in entries:
        running += e.charge - e.payment
        e.balance = running
    g.ledger = entries


def _limit_progress(ds: Dataset, year: int, eob_by_visit: dict, members: dict) -> list[LimitProgress]:
    out = []
    visits = {v["id"]: v for v in ds.visits}
    for plan in ds.plans:
        if plan.get("plan_year") != year:
            continue
        eobs = [e for e in eob_by_visit.values()
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
                out.append(LimitProgress(plan, limit, label, used, names, note))
    return out


def _fmt(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"
