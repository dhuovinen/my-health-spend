"""The insurer's claims export (CSV): one row per claim, each an EOB with its visit.

The layout is the one Release 0's converter reads (the owner's insurer portal export); column names are matched
loosely so close variants work. Patients are matched to household members, providers by name or alias, and each
claim to the plan for its service year.
"""

import csv
import io
import re

from mhs.ingest.resolve import Members, Providers, plan_for, slug
from mhs.ingest.values import dollars, parse_amount, parse_date

COLUMNS = {
    "provider": ("provided by", "provider", "provider name", "rendering provider"),
    "claim_type": ("claim type", "coverage", "type"),
    "claim_number": ("claim number", "claim #", "claim no", "claim id"),
    "patient": ("patient", "patient name", "member"),
    "service_date": ("service date", "date of service", "dos", "service start"),
    "processed_date": ("processed date", "processed", "date processed"),
    "received_date": ("claim received", "received date", "date received"),
    "status": ("status", "claim status"),
    "billed": ("billed", "amount billed", "charges", "billed amount"),
    "adjustment": ("plan discount", "discount", "network discount"),
    "allowed": ("allowed", "allowed amount"),
    "insurer_paid": ("plan paid", "paid by plan", "insurer paid", "plan payment"),
    "additional_savings": ("additional savings",),
    "deductible": ("deductible",),
    "coinsurance": ("coinsurance",),
    "copay": ("copay", "copayment"),
    "not_covered": ("not covered", "noncovered"),
    "patient_responsibility": ("your cost", "you owe", "patient responsibility", "member responsibility"),
}
REQUIRED = ("provider", "claim_number", "service_date", "billed", "allowed", "insurer_paid", "patient_responsibility")
STATUS = {"approved": "processed", "processed": "processed", "paid": "processed", "denied": "denied",
          "pending": "pending", "adjusted": "adjusted"}
MONEY_FIELDS = ("billed", "adjustment", "allowed", "insurer_paid", "additional_savings", "deductible", "coinsurance",
                "copay", "not_covered", "patient_responsibility")


def _header(row: list[str]) -> dict[str, int]:
    cols = {}
    for i, cell in enumerate(row):
        c = re.sub(r"\s+", " ", cell.strip().lower())
        for key, names in COLUMNS.items():
            if c in names and key not in cols:
                cols[key] = i
    return cols


def is_claims_export(name: str, data: bytes) -> bool:
    if not name.lower().endswith(".csv"):
        return False
    first = data.decode("utf-8-sig", errors="replace").splitlines()[:1]
    return bool(first) and len(set(_header(next(csv.reader(first)))) & set(REQUIRED)) >= 4


def to_ingest(name: str, data: bytes, store_records: dict[str, list[dict]]) -> tuple[dict | None, list[str], list[str]]:
    """(ingest data, errors, notes). store_records holds the household's providers, members, plans and visits."""
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig", errors="replace"))))
    if not rows:
        return None, ["The file is empty."], []
    cols = _header(rows[0])
    missing = [k for k in REQUIRED if k not in cols]
    if missing:
        names = ", ".join(COLUMNS[k][0].title() for k in missing)
        return None, [f"Missing column(s): {names}. Nothing was imported."], []
    providers = Providers(store_records["provider"])
    members = Members(store_records["member"])
    existing_visits = {(v["provider_id"], v["date"]): v["id"] for v in store_records["visit"]}
    visits, eobs, errors, notes, seen = [], [], [], [], set()
    for n, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue
        get = lambda k: row[cols[k]].strip() if k in cols and cols[k] < len(row) else ""  # noqa: E731
        claim = get("claim_number")
        when = parse_date(get("service_date"))
        if not claim or not when:
            errors.append(f"Row {n}: claim number or service date missing.")
            continue
        pid = providers.resolve(get("provider"))
        kind = get("claim_type") or "medical"
        plan_id = plan_for(store_records["plan"], int(when[:4]), kind)
        if not plan_id:
            errors.append(f"Row {n} (claim {claim}): no {kind.lower()} plan for {when[:4]}. Add the plan in Settings first.")
            continue
        visit_id = existing_visits.get((pid, when))
        if visit_id is None:
            visit_id = f"v-{when}-{pid.removeprefix('prov-')}"
            if visit_id in seen:
                visit_id += f"-{slug(claim)}"
            seen.add(visit_id)
            existing_visits[(pid, when)] = visit_id
            member_id = members.find(get("patient"))
            if get("patient") and not member_id:
                notes.append(f"Claim {claim}: patient isn't a household member in Settings; visit saved without a member.")
            visits.append({"id": visit_id, "date": when, "provider_id": pid, "plan_id": plan_id,
                           "category": "provider_visit", "description": f"{kind} claim {claim}",
                           **({"member_id": member_id} if member_id else {})})
        amounts = {k: parse_amount(get(k)) for k in MONEY_FIELDS if get(k)}
        eob = {
            "id": f"eob-{slug(claim)}", "type": "eob",
            "date": parse_date(get("processed_date")) or when,
            "plan_id": plan_id, "provider_id": pid, "visit_id": visit_id, "claim_number": claim,
            "claim_status": STATUS.get(get("status").lower(), "pending"),
            "network_status": "unknown",
            **{k: dollars(v) for k, v in amounts.items() if v is not None},
            "notes": f"Insurer status: {get('status') or 'not given'}. Source: {name}",
        }
        if received := parse_date(get("received_date")):
            eob["received_date"] = received
        for k in REQUIRED[3:]:
            eob.setdefault(k, 0.0)
        eobs.append(eob)
    for p in providers.new.values():
        notes.append(f"New provider {p['name']!r}. If it's one you already have, add the name as an alias in Settings.")
    if errors:
        return None, errors, notes
    data = {"schema_version": "0.1", "visits": visits, "documents": eobs}
    if providers.new:
        data["providers"] = list(providers.new.values())
    return data, [], notes
