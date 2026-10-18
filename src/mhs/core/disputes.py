"""Dispute cases (DSP-01, DSP-03 to DSP-05, DSP-07; ADR-042): their state, follow-ups, deadlines, evidence and savings.

A case lives on its visit record (`visit.cases`); the member's changes to it are in edits.py. Pure functions over
record dicts and the engine's visit results; real dates (ADR-022); money in integer cents. No database or web imports.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

FOLLOW_UP_DAYS = 30  # A-13: providers and insurers, editable per case
APPEAL_DAYS = 180  # the ACA minimum for an internal appeal; a plan can say otherwise (plan.appeal_days)
NSA_DAYS = 120  # No Surprises Act patient-provider dispute: days from the first bill
NSA_THRESHOLD = 40000  # ...open when the bill is $400.00 or more above the good-faith estimate
SOON_DAYS = 14  # a deadline this close raises the visit in the attention queue

CASE_STATUSES = ("open", "contacted", "waiting", "resolved")
CASE_LABELS = {"open": "Opened", "contacted": "Contacted", "waiting": "Waiting on them", "resolved": "Resolved"}
CASE_HELP = {
    "open": "You opened the case and haven't contacted anyone yet.",
    "contacted": "You contacted them and are waiting for an answer.",
    "waiting": "They answered and you are waiting for them to act (a corrected bill, a refund, a new EOB).",
    "resolved": "The case is closed with its outcome.",
}
OUTCOMES = {"corrected": "Corrected", "refunded": "Refunded", "written_off": "Written off", "denied": "Denied"}
PARTIES = ("provider", "insurer")

LETTERS = {
    "itemized_bill": "Itemized bill request",
    "billing_correction": "Billing correction",
    "refund": "Refund request",
    "claim_resubmission": "Claim resubmission",
    "appeal": "Appeal to the insurer",
}
LETTER_PARTY = {"itemized_bill": "provider", "billing_correction": "provider", "refund": "provider",
                "claim_resubmission": "provider", "appeal": "insurer"}
# The letter that fits a finding: by its kind, else by its check's code.
LETTER_FOR = {"missed_adjustment": "billing_correction", "balance_billing": "billing_correction",
              "billed_mismatch": "billing_correction", "duplicate_charge": "billing_correction",
              "over_estimate": "billing_correction", "overpayment": "refund", "not_filed": "claim_resubmission",
              "unexplained": "itemized_bill", "self_pay": "billing_correction", "C1": "appeal", "C3": "appeal"}


def letter_for(finding: dict) -> str:
    return LETTER_FOR.get(finding.get("kind") or "", LETTER_FOR.get(finding.get("code") or "", "itemized_bill"))


def party_for(findings: list[dict]) -> str:
    """Who a case is with by default: the insurer for an EOB that doesn't add up or a network mismatch."""
    kinds = [letter_for(f) for f in findings if f.get("code") != "C6"]  # a balance owed is nobody's to dispute
    return "insurer" if kinds and all(LETTER_PARTY[k] == "insurer" for k in kinds) else "provider"


def cases_of(visit: dict) -> list[dict]:
    """The visit's cases. A minimal dispute from Release 1 (ADR-035) reads as one case."""
    cases = [dict(c) for c in visit.get("cases") or []]
    old = visit.get("dispute")
    if old and not cases:
        resolved = old.get("status") == "closed"
        case = {"id": "dispute", "opened": old["opened"], "status": "resolved" if resolved else "open",
                "party": "provider", "history": [{"date": old["opened"], "status": "open"}]}
        if old.get("note"):
            case["note"] = old["note"]
        if resolved:
            case["history"].append({"date": old.get("closed") or old["opened"], "status": "resolved",
                                    **({"note": old["outcome"]} if old.get("outcome") else {})})
        cases.append(case)
    return cases


def is_open(case: dict) -> bool:
    return case.get("status") != "resolved"


@dataclass
class Deadline:
    kind: str  # appeal | nsa | follow_up
    label: str
    due: str  # ISO date
    days_left: int

    @property
    def soon(self) -> bool:
        return 0 <= self.days_left <= SOON_DAYS

    @property
    def passed(self) -> bool:
        return self.days_left < 0


def _deadline(kind: str, label: str, start: str, days: int, today: date) -> Deadline:
    due = date.fromisoformat(start) + timedelta(days=days)
    return Deadline(kind, label, due.isoformat(), (due - today).days)


def appeal_days(plan: dict | None) -> int:
    return int((plan or {}).get("appeal_days") or APPEAL_DAYS)


def visit_deadlines(vr, plan: dict | None, today: date) -> list[Deadline]:
    """DSP-05: the insurer appeal deadline per claim (the EOB's date plus the plan's window), and the No Surprises
    Act dispute deadline for a self-pay bill $400 or more above its good-faith estimate (120 days from the first
    bill that lists the visit)."""
    out = []
    several = len(vr.claims) > 1
    for c in vr.claims:
        number = c.get("claim_number")
        label = f"Appeal claim {number} to the insurer" if several and number else "Appeal to the insurer"
        out.append(_deadline("appeal", label, c["date"], appeal_days(plan), today))
    estimate = next((c for c in vr.checks if c.code == "estimate" and c.result in ("fail", "closed")), None)
    if estimate and estimate.amount >= NSA_THRESHOLD and vr.bill_lines:
        first_bill = min(b["date"] for b, _ in vr.bill_lines)
        out.append(_deadline("nsa", "Start a No Surprises Act dispute", first_bill, NSA_DAYS, today))
    return sorted(out, key=lambda d: d.due)


@dataclass
class Evidence:
    """DSP-01: the documents behind a case, and what is missing from them."""
    documents: list[tuple[str, dict]] = field(default_factory=list)  # (kind, record): bill, eob, receipt, payment, refund
    missing: list[str] = field(default_factory=list)


PAYMENT_FINDINGS = {"overpayment", "unexplained"}


def evidence(vr, findings: list[dict]) -> Evidence:
    ev = Evidence()
    ev.documents += [("bill", b) for b, _ in reversed(vr.bill_lines)]
    ev.documents += [("eob", c) for c in vr.claims]
    ev.documents += [("receipt", r) for r in vr.receipts]
    seen = set()
    for a in vr.allocations:
        if a.payment["id"] not in seen:
            seen.add(a.payment["id"])
            ev.documents.append(("refund" if a.refund else "payment", a.payment))
    if not vr.bill_lines and not vr.receipts:
        ev.missing.append("Provider bill")
    if vr.insured and not vr.claims:
        ev.missing.append("Insurance decision (EOB)")
    about_payments = any(f.get("kind") in PAYMENT_FINDINGS for f in findings)
    if (vr.responsibility > 0 or about_payments) and not vr.paid:
        ev.missing.append("Payment proof")
    return ev


@dataclass
class CaseView:
    case: dict
    visit_id: str
    party_name: str
    contacts: list[dict]  # the case's notes, newest first
    deadlines: list[Deadline]  # the visit's, while the case is open
    follow_up: Deadline | None  # when a reminder is due: the last contact plus the follow-up days, until a reply
    evidence: Evidence
    follow_up_days: int = FOLLOW_UP_DAYS

    @property
    def id(self) -> str:
        return self.case["id"]

    @property
    def status(self) -> str:
        return self.case["status"]

    @property
    def label(self) -> str:
        return CASE_LABELS[self.status]

    @property
    def open(self) -> bool:
        return is_open(self.case)

    @property
    def party(self) -> str:
        return self.case.get("party") or "provider"

    @property
    def findings(self) -> list[dict]:
        return self.case.get("findings") or []

    @property
    def amount(self) -> int:
        """The dollars at issue: the largest finding, since one excess can show up as several (ADR-035)."""
        return max((f["amount"] for f in self.findings), default=0)

    @property
    def outcome(self) -> dict | None:
        return self.case.get("outcome") if self.status == "resolved" else None

    @property
    def recovered(self) -> int:
        return (self.outcome or {}).get("recovered", 0)

    @property
    def letter(self) -> str:
        """The recommended letter for the case's first finding."""
        if self.party == "insurer":
            return "appeal"
        kinds = [letter_for(f) for f in self.findings if LETTER_PARTY[letter_for(f)] == "provider"]
        return kinds[0] if kinds else "itemized_bill"

    @property
    def reminder(self) -> bool:
        return self.open and self.follow_up is not None and self.follow_up.days_left <= 0

    @property
    def last_contact(self) -> dict | None:
        sent = [n for n in self.contacts if sent_by_member(n)]
        return sent[0] if sent else None


def sent_by_member(note: dict) -> bool:
    """A contact the member made: something they sent, or a call they logged without saying who called whom."""
    return note.get("direction") == "sent" or (note.get("channel") == "phone" and not note.get("direction"))


def follow_up(contacts: list[dict], days: int, today: date) -> Deadline | None:
    """DSP-04: due `days` after the member's last contact, unless a reply was logged on or after it."""
    sent = [n["date"] for n in contacts if sent_by_member(n)]
    if not sent:
        return None
    last = max(sent)
    if any(n.get("direction") == "received" and n["date"] >= last for n in contacts):
        return None
    return _deadline("follow_up", "Follow up", last, days, today)


def case_views(vr, notes: list[dict], plan: dict | None, deadlines: list[Deadline], today: date) -> list[CaseView]:
    insurer = (plan or {}).get("insurer") or "the insurer"
    out = []
    for case in cases_of(vr.visit):
        contacts = sorted((n for n in notes if n.get("case_id") == case["id"]), key=lambda n: (n["date"], n["id"]),
                          reverse=True)
        days = int(case.get("follow_up_days") or FOLLOW_UP_DAYS)
        party = case.get("party") or "provider"
        out.append(CaseView(
            case=case, visit_id=vr.id, party_name=insurer if party == "insurer" else vr.provider["name"],
            contacts=contacts, deadlines=deadlines if is_open(case) else [],
            follow_up=follow_up(contacts, days, today) if is_open(case) else None,
            evidence=evidence(vr, case.get("findings") or []), follow_up_days=days))
    return sorted(out, key=lambda c: (not c.open, c.case["opened"], c.id))


@dataclass
class Due:
    """Something with a date that needs the member: a follow-up that is due, or a deadline 14 days away or nearer."""
    kind: str  # follow_up | appeal | nsa
    label: str
    due: str
    days_left: int
    who: str = ""  # follow-ups: who to follow up with
    since: str = ""  # follow-ups: the last contact


def due_items(cases: list[CaseView], deadlines: list[Deadline]) -> list[Due]:
    """What raises a visit in the attention queue (TC-DSP-04-2, TC-DSP-05-3), soonest first."""
    out = [Due("follow_up", f"Follow up with {c.party_name}", c.follow_up.due, c.follow_up.days_left,
               who=c.party_name, since=c.last_contact["date"] if c.last_contact else "")
           for c in cases if c.reminder]
    out += [Due(d.kind, d.label, d.due, d.days_left) for d in deadlines if d.soon]
    return sorted(out, key=lambda d: (d.due, d.kind))


def recovered(visits: list[dict]) -> int:
    """DSP-07: the dollars recovered by every resolved case on these visits, each case once (TC-DSP-07-3)."""
    return sum((c.get("outcome") or {}).get("recovered", 0)
               for v in visits for c in cases_of(v) if c.get("status") == "resolved")
