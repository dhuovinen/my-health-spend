"""From a confirmed card review to a plan record (ING-11, ADR-061). Pure functions over record dicts, money in cents.

`find_plan` says whether a card is for a plan the household has (same insurer and group number and kind), `merge`
lays the card's values over it, and `changes` says in words what a card would change, for the review page.
A card never sets `terms_confirmed`; if it changes the terms, the member's earlier confirmation is cleared.
"""

import re

TERM_KEYS = ("coinsurance_rate", "copays", "limits")


def norm(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def kind_of(plan: dict) -> str:
    return plan.get("coverage_kind") or "medical"


def find_plan(plans: list[dict], insurer: str, group_token: str | None, kind: str,
              year: int) -> tuple[dict | None, dict | None]:
    """(the plan for this year, the latest plan of an earlier or later year) for the same insurer, group number
    and kind. Both can be None (a new plan). A group number counts only when both sides have one."""
    same = [p for p in plans if kind_of(p) == kind and norm(p.get("insurer")) == norm(insurer)
            and (not group_token or not p.get("group_number") or p["group_number"] == group_token)]
    this_year = next((p for p in same if p.get("plan_year") == year), None)
    other = sorted((p for p in same if p.get("plan_year") != year), key=lambda p: -p["plan_year"])
    return this_year, (other[0] if other else None)


def _limit_key(limit: dict) -> tuple:
    return limit.get("type"), limit.get("network"), limit.get("level"), limit.get("member_id")


def merge(existing: dict | None, incoming: dict) -> dict:
    """The plan with the card's values on it. Empty values don't erase anything; copays and limits are added by
    key; members are added, never removed; contacts replace the ones with the same label."""
    plan = {**(existing or {})}
    for key, value in incoming.items():
        if value in (None, "", [], {}):
            continue
        if key == "copays":
            plan["copays"] = {**plan.get("copays", {}), **value}
        elif key == "limits":
            kept = {_limit_key(l): l for l in plan.get("limits", [])}
            kept.update({_limit_key(l): l for l in value})
            plan["limits"] = list(kept.values())
        elif key == "member_ids":
            plan["member_ids"] = sorted({*plan.get("member_ids", []), *value})
        elif key == "member_numbers":
            plan["member_numbers"] = {**plan.get("member_numbers", {}),
                                      **{m: {**plan.get("member_numbers", {}).get(m, {}), **v} for m, v in value.items()}}
        elif key == "contacts":
            labels = {c["label"] for c in value}
            plan["contacts"] = [c for c in plan.get("contacts", []) if c["label"] not in labels] + list(value)
        elif key == "rx":
            plan["rx"] = {**plan.get("rx", {}), **value}
        elif key == "card_documents":
            plan["card_documents"] = sorted({*plan.get("card_documents", []), *value})
        else:
            plan[key] = value
    if existing and existing.get("terms_confirmed") and any(plan.get(k) != existing.get(k) for k in TERM_KEYS):
        plan["terms_confirmed"] = False  # the member confirmed the old terms; a card that changes them needs a new look
    return plan


def _dollars(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def changes(old: dict | None, new: dict, member_names: dict[str, str], service_names: dict[str, str]) -> list[str]:
    """What the card changes on an existing plan, in words. Empty when there is nothing new (already on file)."""
    if old is None:
        return []
    out = []
    for key, label in (("insurer", "Insurer"), ("plan_name", "Plan name"), ("plan_type", "Plan type"),
                       ("coverage_start", "Coverage start"), ("coverage_end", "Coverage end"),
                       ("coverage_order", "Coverage order"), ("payer_id", "Payer ID"), ("hsa_eligible_plan", "HSA-eligible")):
        if new.get(key) != old.get(key) and new.get(key) not in (None, ""):
            out.append(f"{label}: {old.get(key) or 'not set'} to {new[key]}")
    if new.get("group_number") != old.get("group_number") and new.get("group_number"):
        out.append("Group number changed" if old.get("group_number") else "Group number added")
    if new.get("coinsurance_rate") != old.get("coinsurance_rate") and new.get("coinsurance_rate") is not None:
        was = old.get("coinsurance_rate")
        out.append(f"Coinsurance: {'not set' if was is None else f'{was * 100:g}%'} to {new['coinsurance_rate'] * 100:g}%")
    for k, v in (new.get("copays") or {}).items():
        was = (old.get("copays") or {}).get(k)
        if was != v:
            out.append(f"{service_names.get(k, k)} copay: {'not set' if was is None else _dollars(was)} to {_dollars(v)}")
    old_limits = {_limit_key(l): l for l in old.get("limits", [])}
    for l in new.get("limits") or []:
        was = old_limits.get(_limit_key(l))
        if was is None or was["amount"] != l["amount"]:
            what = f"{l['level'].capitalize()} {l['type'].replace('_', ' ')}"
            out.append(f"{what}: {'not set' if was is None else _dollars(was['amount'])} to {_dollars(l['amount'])}")
    for m in sorted(set(new.get("member_ids") or []) - set(old.get("member_ids") or [])):
        out.append(f"Member added: {member_names.get(m, m)}")
    for m, v in (new.get("member_numbers") or {}).items():
        if v != (old.get("member_numbers") or {}).get(m):
            out.append(f"Member ID for {member_names.get(m, m)}")
    old_contacts = {c["label"]: c for c in old.get("contacts", [])}
    for c in new.get("contacts") or []:
        if old_contacts.get(c["label"]) != c:
            out.append(f"{c['label']}: {'updated' if c['label'] in old_contacts else 'added'}")
    if new.get("rx") and new["rx"] != old.get("rx"):
        out.append("Pharmacy numbers (RxBIN, PCN, group)")
    return out
