"""Letters and call scripts for a dispute case (DSP-02, DSP-03; ADR-042).

Drafted in the application tier when the member asks, filled with what the records hold and the member's real
identifiers (ADR-022), and returned to the page: never stored, queued or sent. What the app doesn't know stays a
bracketed blank for the member to fill in.
"""

from dataclasses import dataclass, field
from datetime import datetime

from mhs.core.disputes import LETTERS, CaseView
from mhs.core.reconcile import FINDING_KINDS, VisitResult

# Identifiers a letter can carry; the member can type any of them on the draft form (used once, not kept).
IDENTIFIERS = {
    "name": "Your name",
    "address": "Your mailing address",
    "account_number": "Account number with the provider",
    "member_number": "Member ID on your insurance card",
    "phone": "Your phone number",
}
DISCLAIMER = ("This draft is information to help you write your own letter, not legal or financial advice. Check every "
              "name, number and amount against your documents before you send it.")


def money(cents: int | None) -> str:
    return "—" if cents is None else f"${cents / 100:,.2f}"


def day(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        return iso


@dataclass
class Letter:
    kind: str
    to: str
    subject: str
    body: str
    blanks: list[str] = field(default_factory=list)  # identifiers left for the member to fill in

    @property
    def title(self) -> str:
        return LETTERS[self.kind]

    @property
    def text(self) -> str:
        return f"To: {self.to}\nRe: {self.subject}\n\n{self.body}\n"


class Facts:
    """What a letter or call script says, from the visit, the case and the member's identifiers."""

    def __init__(self, vr: VisitResult, case: CaseView, plan: dict | None, ids: dict[str, str]):
        self.vr, self.case, self.plan = vr, case, plan or {}
        self.blanks: list[str] = []
        self.ids = {k: (v or "").strip() for k, v in ids.items()}
        if not self.ids.get("name") and vr.member:
            self.ids["name"] = vr.member["name"]

    def id(self, key: str, blank: str) -> str:
        if self.ids.get(key):
            return self.ids[key]
        if key not in self.blanks:
            self.blanks.append(key)
        return f"[{blank}]"

    @property
    def name(self) -> str:
        return self.id("name", "your name")

    @property
    def patient(self) -> str:
        return self.vr.member["name"] if self.vr.member else self.name

    @property
    def provider(self) -> str:
        return self.vr.provider["name"]

    @property
    def insurer(self) -> str:
        return self.plan.get("insurer") or "[your insurer]"

    @property
    def dos(self) -> str:
        return day(self.vr.visit["date"])

    @property
    def claims(self) -> str:
        numbers = [c.get("claim_number") for c in self.vr.claims if c.get("claim_number")]
        return ", ".join(numbers) if numbers else ""

    @property
    def eob(self) -> dict | None:
        return self.vr.eob

    @property
    def statement(self) -> tuple[dict, dict] | None:
        return self.vr.latest_line

    def findings(self, *kinds: str) -> list[dict]:
        return [f for f in self.case.findings if not kinds or f.get("kind") in kinds]

    def account_line(self) -> str:
        return f"Account number: {self.id('account_number', 'your account number with ' + self.provider)}"

    def member_line(self) -> str:
        return f"Member ID: {self.id('member_number', 'your member ID')}"

    def signature(self) -> str:
        lines = ["Thank you,", "", self.name, self.id("address", "your mailing address")]
        if self.ids.get("phone"):
            lines.append(self.ids["phone"])
        return "\n".join(lines)

    def enclosed(self) -> str:
        names = {"bill": "the statement of {}", "eob": "the Explanation of Benefits of {}", "receipt": "the receipt of {}",
                 "payment": "proof of my payment of {}", "refund": "the refund of {}"}
        out = []
        for kind, doc in self.case.evidence.documents:
            if kind in ("payment", "refund"):
                out.append(names[kind].format(f"{money(doc.get('amount'))} on {day(doc['date'])}"))
            else:
                out.append(names[kind].format(day(doc["date"])))
        return ("Enclosed are copies of " + _join(out) + ".") if out else ""

    def lines(self) -> str:
        out = []
        for line in self.case.case.get("lines") or []:
            what = " ".join(x for x in (line.get("code"), line.get("description")) if x) or "a line"
            parts = []
            if line.get("charge") is not None:
                parts.append(f"charged {money(line['charge'])}")
            if line.get("billed") is not None:
                parts.append(f"the insurer was billed {money(line['billed'])}")
            if line.get("patient_amount") is not None:
                parts.append(f"you ask me for {money(line['patient_amount'])}")
            if line.get("patient_responsibility") is not None:
                parts.append(f"the EOB says I owe {money(line['patient_responsibility'])}")
            if line.get("note"):
                parts.append(line["note"].lower())
            out.append(f"- {what}: " + ", ".join(parts))
        return ("The lines that don't agree:\n" + "\n".join(out)) if out else ""


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


def _paragraphs(*parts: str) -> str:
    return "\n\n".join(p for p in parts if p)


def _reference(f: Facts, insurer: bool = False) -> str:
    rows = [f"Patient: {f.patient}", f"Date of service: {f.dos}"]
    if insurer:
        rows += [f.member_line(), f"Provider: {f.provider}"]
    else:
        rows.append(f.account_line())
    if f.claims:
        rows.append(f"Claim number: {f.claims}")
    return "\n".join(rows)


def itemized_bill(f: Facts) -> Letter:
    body = _paragraphs(
        f"Dear {f.provider} billing office,",
        _reference(f),
        f"Please send me an itemized bill for my services on {f.dos}: each service with its date, procedure code "
        f"(CPT or HCPCS), units and charge, and every insurance payment, adjustment, payment and write-off applied to "
        f"this account." + (f" My insurer, {f.insurer}, processed claim {f.claims} for this visit." if f.claims else ""),
        "Please hold the account from collections while I review it.",
        f.signature())
    return Letter("itemized_bill", f"{f.provider}, billing office", f"Itemized bill request, services on {f.dos}", body)


def billing_correction(f: Facts) -> Letter:
    paras = []
    stmt, eob = f.statement, f.eob
    asks_owes = f.findings("missed_adjustment", "balance_billing")
    if asks_owes and stmt and eob:
        bill, line = stmt
        text = (f"Your statement of {day(bill['date'])} asks me to pay {money(line['patient_amount'])}. The "
                f"Explanation of Benefits from {f.insurer} for claim {f.claims or 'for this visit'}, processed "
                f"{day(eob['date'])}, says my responsibility is {money(eob['patient_responsibility'])}, "
                f"{money(asks_owes[0]['amount'])} less.")
        if asks_owes[0].get("kind") == "balance_billing":
            text += (f" As a provider in my plan's network, you agreed to accept the plan's allowed amount "
                     f"({money(eob.get('allowed'))}) and not to bill me for the difference.")
        else:
            text += f" The statement doesn't apply the plan's discount of {money(eob.get('adjustment'))}."
        paras.append(text)
    for d in f.findings("duplicate_charge"):
        paras.append(f"The same service is charged twice: {d.get('detail', '').rstrip('.')}.")
    for d in f.findings("billed_mismatch"):
        paras.append(f"The charges on your statement don't match what you billed {f.insurer}: "
                     f"{d.get('detail', '').rstrip('.')}.")
    for d in f.findings("over_estimate"):
        gfe = f.vr.visit.get("good_faith_estimate")
        text = f"Your good-faith estimate for this care was {money(gfe)}; the bill is {money(d['amount'])} more."
        if d["amount"] >= 40000:
            text += (" Because the bill is $400.00 or more above the estimate, I have the right under the No Surprises "
                     "Act to dispute it through the federal patient-provider dispute resolution process.")
        paras.append(text)
    other = [d for d in f.findings() if d.get("kind") not in
             ("missed_adjustment", "balance_billing", "duplicate_charge", "billed_mismatch", "over_estimate")]
    for d in other:
        paras.append(f"{FINDING_KINDS.get(d.get('kind'), 'A problem')}: {d.get('detail', '').rstrip('.')}.")
    if not paras:
        paras.append("The bill for this visit doesn't agree with my records.")
    target = money(eob["patient_responsibility"]) if eob and asks_owes else ""
    request = ("Please correct the bill" + (f" to {target}" if target else "") + ", send me a corrected statement, "
               "and hold the account from collections until it is corrected.")
    body = _paragraphs(f"Dear {f.provider} billing office,", _reference(f), *paras, f.lines(), request, f.enclosed(),
                       f.signature())
    return Letter("billing_correction", f"{f.provider}, billing office", f"Billing correction, services on {f.dos}", body)


def refund(f: Facts) -> Letter:
    vr = f.vr
    over = next((d["amount"] for d in f.findings("overpayment")), vr.overpaid)
    basis = (f"the Explanation of Benefits from {f.insurer} for claim {f.claims} says I owe "
             f"{money(vr.responsibility)}" if vr.claims else f"I owe {money(vr.responsibility)}")
    body = _paragraphs(
        f"Dear {f.provider} billing office,",
        _reference(f),
        f"I have paid {money(vr.paid)} for my services on {f.dos}, but {basis}. That is an overpayment of "
        f"{money(over)}.",
        f"Please refund {money(over)} to me by the way I paid, within 30 days, and send me a statement that shows the "
        f"refund. If you have applied it to another balance, please tell me which one.",
        f.enclosed(), f.signature())
    return Letter("refund", f"{f.provider}, billing office", f"Refund request, {money(over)}, services on {f.dos}", body)


def claim_resubmission(f: Facts) -> Letter:
    stmt, eob = f.statement, f.eob
    asks = (f"Your statement of {day(stmt[0]['date'])} asks me to pay {money(stmt[1]['patient_amount'])} for my "
            f"services on {f.dos}." if stmt else f"I received a bill for my services on {f.dos}.")
    if eob:
        situation = (f"{f.insurer} processed claim {f.claims or 'for this visit'} on {day(eob['date'])}, but the claim "
                     f"doesn't match the services on your bill, so it needs to be corrected and sent again.")
        request = (f"Please correct the claim and resubmit it to {f.insurer} (patient {f.patient}, member ID "
                   f"{f.id('member_number', 'your member ID')}), and hold the balance until the insurer has processed "
                   f"it.")
    else:
        situation = (f"I have no Explanation of Benefits from my insurer, {f.insurer}, for this visit, so the claim seems "
                     f"not to have been filed or not received.")
        request = (f"Please file the claim with {f.insurer} (patient {f.patient}, member ID "
                   f"{f.id('member_number', 'your member ID')}) and hold the balance until the insurer has processed "
                   f"it. If it was filed, please send me the claim number and the date it was sent.")
    body = _paragraphs(f"Dear {f.provider} billing office,", _reference(f), f"{asks} {situation}", request,
                       f.enclosed(), f.signature())
    return Letter("claim_resubmission", f"{f.provider}, billing office",
                  f"Please {'resubmit' if eob else 'file'} my claim, services on {f.dos}", body)


def appeal(f: Facts) -> Letter:
    eob = f.eob
    reasons = []
    for d in f.findings():
        if d.get("code") == "C3":
            reasons.append(f"The claim's network status doesn't agree with my records ({d.get('detail', '')}). "
                           f"{f.provider} is in my plan's network, so the claim should be paid at the in-network level.")
        elif d.get("code") == "C1":
            reasons.append(f"The amounts on the Explanation of Benefits don't add up: {d.get('detail', '').rstrip('.')}.")
        else:
            reasons.append(f"{FINDING_KINDS.get(d.get('kind'), 'A problem')}: {d.get('detail', '').rstrip('.')}.")
    if not reasons:
        reasons.append("I believe the claim was processed incorrectly.")
    deadline = next((d for d in f.case.deadlines if d.kind == "appeal"), None)
    opening = (f"I am asking for an internal appeal of claim {f.claims or '[claim number]'}"
               + (f", processed on {day(eob['date'])}" if eob else "") + f", for my services from {f.provider} on {f.dos}.")
    body = _paragraphs(
        f"Dear {f.insurer} appeals department,",
        _reference(f, insurer=True),
        opening, *reasons, f.lines(),
        "Please review the claim, reprocess it, and send me a corrected Explanation of Benefits. Please also send me "
        "copies of the documents and the plan provisions the decision relied on.",
        (f"I am filing within the appeal window, which ends on {day(deadline.due)}." if deadline else ""),
        f.enclosed(), f.signature())
    return Letter("appeal", f"{f.insurer}, appeals", f"Appeal of claim {f.claims or 'for services on ' + f.dos}", body)


DRAFTS = {"itemized_bill": itemized_bill, "billing_correction": billing_correction, "refund": refund,
          "claim_resubmission": claim_resubmission, "appeal": appeal}


def draft(kind: str, vr: VisitResult, case: CaseView, plan: dict | None, ids: dict[str, str]) -> Letter:
    """TC-DSP-02-1: a letter with the real claim number, dates, amounts and request, filled in here."""
    facts = Facts(vr, case, plan, ids)
    letter = DRAFTS[kind](facts)
    letter.blanks = facts.blanks
    return letter


@dataclass
class CallScript:
    """DSP-03: who to call, what to have ready, what to ask for, and what to write down."""
    who: str
    ready: list[tuple[str, str]]
    say: str
    ask: list[str]
    record: list[str]


def call_script(vr: VisitResult, case: CaseView, plan: dict | None, ids: dict[str, str]) -> CallScript:
    f = Facts(vr, case, plan, ids)
    insurer = case.party == "insurer"
    ready = [("Patient", f.patient), ("Date of service", f.dos)]
    if insurer:
        ready.append(("Member ID", f.ids.get("member_number") or "on your insurance card"))
    else:
        ready.append(("Account number", f.ids.get("account_number") or "on the statement"))
    if f.claims:
        ready.append(("Claim number", f.claims))
    if f.statement:
        ready.append(("Latest statement", f"{day(f.statement[0]['date'])}, asks {money(f.statement[1]['patient_amount'])}"))
    if f.eob:
        ready.append(("EOB", f"{day(f.eob['date'])}, you owe {money(f.eob['patient_responsibility'])}"))
    if vr.paid:
        ready.append(("You paid", money(vr.paid)))
    kind = case.letter
    issue = "; ".join(FINDING_KINDS.get(d.get("kind"), d.get("code", "")) + f" ({money(d['amount'])})"
                      for d in case.findings) or "a question about this visit"
    say = (f"I'm calling about {'claim ' + f.claims if f.claims else 'my bill'} for {f.patient}'s visit on {f.dos}. "
           f"My records show {issue}.")
    ask = {
        "refund": [f"Refund the overpayment of {money(case.amount or vr.overpaid)} to how you paid.",
                   "When will the refund be sent, and how?"],
        "billing_correction": ["Correct the bill" + (f" to {money(f.eob['patient_responsibility'])}, as the EOB says"
                                                      if f.eob else "") + " and send a corrected statement.",
                               "Hold the account from collections until it is corrected."],
        "claim_resubmission": [f"File or resubmit the claim to {f.insurer}.",
                               "If it was filed: the claim number and the date it was sent."],
        "itemized_bill": ["Send an itemized bill with codes, units, charges and every payment and adjustment."],
        "appeal": ["Reprocess the claim, or how to file an appeal and where to send it.",
                   "Send a corrected Explanation of Benefits."],
    }[kind]
    record = ["The date and time of the call", "The name of the person you spoke with",
              "The call reference number (ask for one)", "What they agreed to do, and by when"]
    return CallScript(who=f"{case.party_name} ({'member services, the number on your insurance card' if insurer else 'billing office, the number on the statement'})",
                      ready=ready, say=say, ask=ask, record=record)
