"""The member's reconciliation decisions as record changes (MAT-07, ALC-04, REC-11; ADR-011, ADR-035).

Each function takes records and returns changed copies; the caller saves them as member edits, so imports keep
them. Pure functions; no database or web imports. Money in integer cents.
"""

import copy

from mhs.core import disputes
from mhs.core.accuracy import NOT_CLOSABLE

# Statement line fields and the item field each one sums (moving items moves these amounts with them).
LINE_FROM_ITEM = {"billed_charge": "charge", "adjustment": "adjustment", "insurance_paid": "insurance_paid",
                  "patient_amount": "patient_amount", "patient_paid": "patient_paid", "balance": "balance",
                  "write_off": "write_off"}
DOCUMENT_KINDS = ("bill", "itemized_bill", "eob", "receipt", "payment")
EXPECTATIONS = ("expected", "not_applicable")
VERDICTS = ("real", "wrong")  # the member's word on a finding they close (PLT-02, ADR-044)
REASON_LENGTH = 200


class EditError(ValueError):
    pass


# ---------- payment splits (ALC-04) ----------

def set_split(payment: dict, splits: dict[str, int]) -> dict:
    """The member's split of a payment across visits; it must account for the whole payment."""
    splits = {v: a for v, a in splits.items() if a}
    if any(a < 0 for a in splits.values()):
        raise EditError("Amounts can't be negative.")
    if sum(splits.values()) != payment["amount"]:
        raise EditError(f"The amounts add up to ${sum(splits.values()) / 100:,.2f}; the payment was "
                        f"${payment['amount'] / 100:,.2f}.")
    out = copy.deepcopy(payment)
    out["allocations"] = [{"visit_id": v, "amount": a} for v, a in splits.items()]
    out["allocation_source"] = "member"
    return out


def clear_split(payment: dict) -> dict:
    out = copy.deepcopy(payment)
    out.pop("allocations", None)
    out.pop("allocation_source", None)
    return out


# ---------- matches (MAT-05, MAT-07) ----------

def confirm_match(doc: dict, visit_id: str) -> dict:
    """The member confirms that a proposed document (or statement line) belongs to the visit."""
    out = copy.deepcopy(doc)
    for target in _match_targets(out, visit_id):
        if "match" in target:
            target["match"]["status"] = "confirmed"
    return out


def _match_targets(doc: dict, visit_id: str) -> list[dict]:
    if doc["type"] == "provider_bill":
        return [line for line in doc["lines"] if line["visit_id"] == visit_id]
    return [doc] if doc.get("visit_id") == visit_id else []


def move_document(doc: dict, from_visit: str, to_visit: str, reject: bool = False,
                  items: list[int] | None = None) -> dict:
    """Move a document, or a statement's line for one visit (or some of its items), to another visit.
    reject=True remembers that the document isn't for from_visit, so matching never proposes it again."""
    if from_visit == to_visit:
        raise EditError("Choose a different visit.")
    out = copy.deepcopy(doc)
    if out["type"] == "provider_bill":
        _move_bill_line(out, from_visit, to_visit, items)
        targets = [line for line in out["lines"] if line["visit_id"] == to_visit]
    else:
        if out.get("visit_id") != from_visit:
            raise EditError("That document isn't on this visit.")
        out["visit_id"] = to_visit
        targets = [out]
    for t in targets:
        match = t.setdefault("match", {})
        match["status"] = "confirmed"
        if reject:
            match["rejected"] = sorted(set(match.get("rejected", [])) | {from_visit})
    return out


def _move_bill_line(bill: dict, from_visit: str, to_visit: str, items: list[int] | None) -> None:
    line = next((l for l in bill["lines"] if l["visit_id"] == from_visit), None)
    if line is None:
        raise EditError("That statement has no line for this visit.")
    all_items = line.get("items") or []
    if items is None or set(items) >= set(range(len(all_items))) and all_items:
        moved = line
        bill["lines"].remove(line)
    else:
        if not all_items or any(i < 0 or i >= len(all_items) for i in items) or not items:
            raise EditError("Choose the statement lines to move.")
        chosen = [all_items[i] for i in sorted(set(items))]
        moved = {"visit_id": to_visit, "description": "; ".join(i.get("description", "") for i in chosen).strip("; ")
                 or "Moved from another visit", "items": chosen}
        for key, item_key in LINE_FROM_ITEM.items():
            if any(item_key in i for i in chosen):
                amount = sum(i.get(item_key) or 0 for i in chosen)
                moved[key] = amount
                if key in line:
                    line[key] -= amount
        if "patient_amount" not in moved:
            moved["patient_amount"] = moved.get("balance", 0)
            line["patient_amount"] -= moved["patient_amount"]
        line["items"] = [i for n, i in enumerate(all_items) if n not in set(items)]
    moved = {**moved, "visit_id": to_visit}
    existing = next((l for l in bill["lines"] if l["visit_id"] == to_visit), None)
    if existing:
        _combine_lines(existing, moved)
    else:
        bill["lines"].append(moved)


def _combine_lines(into: dict, other: dict) -> None:
    for key in LINE_FROM_ITEM:
        if key in into or key in other:
            into[key] = into.get(key, 0) + other.get(key, 0)
    if other.get("items"):
        into["items"] = (into.get("items") or []) + other["items"]
    into["description"] = "; ".join(d for d in (into.get("description"), other.get("description")) if d)


def merge_visits(keep: str, drop: str, documents: list[dict], notes: list[dict] = ()) \
        -> list[tuple[str, dict]]:
    """Move everything on visit `drop` to visit `keep`: documents, statement lines, payment splits and notes (its
    cases move with merge_cases). Returns the changed (kind, record) pairs; the caller then deletes `drop`. Totals
    don't change."""
    if keep == drop:
        raise EditError("Choose a different visit.")
    changed = []
    for doc in documents:
        out = copy.deepcopy(doc)
        if doc["type"] == "provider_bill":
            if not any(l["visit_id"] == drop for l in doc["lines"]):
                continue
            _move_bill_line(out, drop, keep, None)
        elif doc["type"] == "payment":
            if drop not in doc.get("visit_ids", []) and not any(a["visit_id"] == drop for a in doc.get("allocations", [])):
                continue
            if "visit_ids" in out:
                out["visit_ids"] = list(dict.fromkeys(keep if v == drop else v for v in out["visit_ids"]))
            if "allocations" in out:
                combined: dict[str, int] = {}
                for a in out["allocations"]:
                    vid = keep if a["visit_id"] == drop else a["visit_id"]
                    combined[vid] = combined.get(vid, 0) + a["amount"]
                out["allocations"] = [{"visit_id": v, "amount": a} for v, a in combined.items()]
        elif doc.get("visit_id") == drop:
            out["visit_id"] = keep
        else:
            continue
        changed.append(("document", out))
    for note in notes:
        if note.get("visit_id") == drop:
            changed.append(("provider_note", {**note, "visit_id": keep}))
    return changed


def references(visit_id: str, documents: list[dict], notes: list[dict] = ()) -> list[str]:
    """Ids of the records that point at a visit (a visit with any can't be deleted without orphans)."""
    out = []
    for d in documents:
        if d.get("visit_id") == visit_id or visit_id in d.get("visit_ids", []) \
                or any(l.get("visit_id") == visit_id for l in d.get("lines", [])) \
                or any(a.get("visit_id") == visit_id for a in d.get("allocations", [])):
            out.append(d["id"])
    out += [n["id"] for n in notes if n.get("visit_id") == visit_id]
    return out


# ---------- dispute cases (DSP-01, DSP-04, DSP-07; ADR-042) ----------

def _with_cases(visit: dict) -> tuple[dict, list[dict]]:
    """A copy of the visit whose cases are its own list (an old minimal dispute becomes a case)."""
    out = copy.deepcopy(visit)
    cases = copy.deepcopy(disputes.cases_of(visit))
    out.pop("dispute", None)
    out["cases"] = cases
    return out, cases


def _case(cases: list[dict], case_id: str) -> dict:
    case = next((c for c in cases if c["id"] == case_id), None)
    if case is None:
        raise EditError("There is no such case on this visit.")
    return case


def open_case(visit: dict, today: str, findings: list[dict], lines: list[dict] = (), party: str | None = None,
              note: str = "") -> tuple[dict, str]:
    """Open a case about some of the visit's findings (or all of them, for a case about the visit), keeping a copy
    of the findings and the lines that disagree as they are now (DSP-01). Returns the visit and the case id."""
    out, cases = _with_cases(visit)
    for f in findings:
        if any(disputes.is_open(c) and any((g["code"], g["amount"]) == (f["code"], f["amount"])
                                           for g in c.get("findings") or []) for c in cases):
            raise EditError("That finding already has an open case.")
    party = party or disputes.party_for(findings)
    if party not in disputes.PARTIES:
        raise EditError("Choose the provider or the insurer.")
    n = len(cases) + 1
    while any(c["id"] == f"case-{n}" for c in cases):
        n += 1
    case = {"id": f"case-{n}", "opened": today, "status": "open", "party": party,
            "findings": [{k: f[k] for k in ("code", "kind", "amount", "detail") if f.get(k) not in (None, "")}
                         for f in findings],
            "history": [{"date": today, "status": "open"}]}
    if lines:
        case["lines"] = list(lines)
    if note:
        case["note"] = note
    cases.append(case)
    return out, case["id"]


def set_case_status(visit: dict, case_id: str, status: str, today: str, note: str = "") -> dict:
    """Move a case to open, contacted or waiting; each change is dated in its history (TC-DSP-04-1)."""
    if status not in disputes.CASE_STATUSES or status == "resolved":
        raise EditError("Choose open, contacted or waiting; resolve a case with its outcome.")
    out, cases = _with_cases(visit)
    case = _case(cases, case_id)
    if case["status"] == "resolved":
        raise EditError("This case is resolved. Reopen it first.")
    if case["status"] != status:
        case["status"] = status
        case.setdefault("history", []).append({"date": today, "status": status, **({"note": note} if note else {})})
    return out


def set_case_party(visit: dict, case_id: str, party: str) -> dict:
    if party not in disputes.PARTIES:
        raise EditError("Choose the provider or the insurer.")
    out, cases = _with_cases(visit)
    _case(cases, case_id)["party"] = party
    return out


def set_follow_up(visit: dict, case_id: str, days: int | None) -> dict:
    """DSP-04: days after the last contact before a reminder; None goes back to the default (30)."""
    out, cases = _with_cases(visit)
    case = _case(cases, case_id)
    if days is None or days == disputes.FOLLOW_UP_DAYS:
        case.pop("follow_up_days", None)
    elif not 1 <= days <= 365:
        raise EditError("The follow-up is a number of days from 1 to 365.")
    else:
        case["follow_up_days"] = days
    return out


def resolve_case(visit: dict, case_id: str, today: str, result: str, recovered: int, note: str = "",
                 release: str = "") -> dict:
    """DSP-07: close the case with its outcome and the dollars recovered (none when denied or the findings were wrong);
    the findings it is about are closed with it, with the verdict the outcome implies (ADR-044)."""
    if result not in disputes.OUTCOMES:
        raise EditError("Choose the outcome: corrected, refunded, written off, denied or the findings were wrong.")
    if recovered < 0:
        raise EditError("The amount recovered can't be negative.")
    out, cases = _with_cases(visit)
    case = _case(cases, case_id)
    if case["status"] == "resolved":
        raise EditError("This case is already resolved.")
    recovered = 0 if result in disputes.NO_RECOVERY else recovered
    case["status"] = "resolved"
    case["outcome"] = {"result": result, "recovered": recovered, "date": today, **({"note": note} if note else {})}
    case.setdefault("history", []).append({"date": today, "status": "resolved",
                                           "note": f"{disputes.OUTCOMES[result]}, ${recovered / 100:,.2f} recovered"})
    how = f"case resolved: {disputes.OUTCOMES[result].lower()}"
    for f in case.get("findings") or []:
        verdict = None if f["code"] in NOT_CLOSABLE else disputes.OUTCOME_VERDICT.get(result)
        out = close_finding(out, f["code"], f["amount"], today, how, verdict, kind=f.get("kind", ""),
                            release=release if verdict else "")
    return out


def reopen_case(visit: dict, case_id: str, today: str) -> dict:
    """Reopen a resolved case: its outcome no longer counts (TC-DSP-07-3) and the findings it closed reopen."""
    out, cases = _with_cases(visit)
    case = _case(cases, case_id)
    if case["status"] != "resolved":
        raise EditError("This case is still open.")
    was = case.pop("outcome", None)
    case["status"] = "open"
    note = "Reopened" + (f" (was {disputes.OUTCOMES[was['result']].lower()})" if was else "")
    case.setdefault("history", []).append({"date": today, "status": "open", "note": note})
    for f in case.get("findings") or []:
        closed = next((c for c in out.get("closed_findings") or []
                       if (c["code"], c["amount"]) == (f["code"], f["amount"])), None)
        if closed and closed.get("how", "").startswith("case resolved"):
            out = reopen_finding(out, f["code"], f["amount"])
    return out


def merge_cases(keep: dict, drop: dict) -> tuple[dict, dict[str, str]]:
    """Merging visits: the dropped visit's cases move to the kept one, renamed where their ids clash. Returns the
    kept visit and the renames, for the notes that belong to those cases."""
    out, cases = _with_cases(keep)
    renames = {}
    for case in copy.deepcopy(disputes.cases_of(drop)):
        n, new_id = len(cases) + 1, case["id"]
        while any(c["id"] == new_id for c in cases):
            new_id, n = f"case-{n}", n + 1
        if new_id != case["id"]:
            renames[case["id"]] = new_id
            case["id"] = new_id
        cases.append(case)
    if not cases:
        del out["cases"]
    return out, renames


# ---------- findings and the document checklist (REC-11, MAT-10) ----------

def close_finding(visit: dict, code: str, amount: int, today: str, how: str = "marked dealt with",
                  verdict: str | None = None, reason: str = "", kind: str = "", release: str = "") -> dict:
    """Close a finding. The verdict is the member's word on it: a real problem, or wrong (a false positive); kind and
    release are kept with it so it still counts if the finding later disappears (ADR-044)."""
    if verdict is not None and verdict not in VERDICTS:
        raise EditError("Say whether the finding was a real problem or wrong.")
    out = copy.deepcopy(visit)
    closed = [f for f in out.get("closed_findings", []) if (f["code"], f["amount"]) != (code, amount)]
    entry = {"code": code, "amount": amount, "closed": today, "how": how}
    reason = " ".join(reason.split())[:REASON_LENGTH]
    entry.update({k: v for k, v in (("verdict", verdict), ("reason", reason), ("kind", kind), ("release", release))
                  if v})
    closed.append(entry)
    out["closed_findings"] = closed
    return out


def reopen_finding(visit: dict, code: str, amount: int) -> dict:
    out = copy.deepcopy(visit)
    out["closed_findings"] = [f for f in out.get("closed_findings", []) if (f["code"], f["amount"]) != (code, amount)]
    if not out["closed_findings"]:
        del out["closed_findings"]
    return out


def set_expectation(visit: dict, kind: str, state: str | None, today: str) -> dict:
    """Mark a document kind expected or not applicable for this visit (MAT-10); None goes back to the default."""
    if kind not in DOCUMENT_KINDS or (state is not None and state not in EXPECTATIONS):
        raise EditError("Unknown document or choice.")
    out = copy.deepcopy(visit)
    docs = out.setdefault("documents", {})
    if state is None:
        docs.pop(kind, None)
    else:
        docs[kind] = {"state": state, "since": today}
    if not docs:
        del out["documents"]
    return out
