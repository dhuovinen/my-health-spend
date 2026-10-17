"""Write samples/household-ingest.json: the made-up example ingest as a three-person household (UX-06, ADR-041).

It adds Jordan, Alex and Sam Sample as household members, says who each example visit was for (the vitamins stay
unassigned, so the Household page shows that row too), and adds Sam's six-line well-child visit at Example
Pediatrics, where the statement skips the plan discount on one line: the line comparison shows a $15.00
difference (TC-UX-02-2, TC-UX-10-2). Every name and number is synthetic. Usage (the file is committed):

    uv run tools/make_household_sample.py [--out samples/household-ingest.json]
"""

import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "samples" / "example-ingest.json"

MEMBERS = [
    {"id": "mem-jordan", "name": "Jordan Sample", "relationship": "self"},
    {"id": "mem-alex", "name": "Alex Sample", "relationship": "spouse"},
    {"id": "mem-sam", "name": "Sam Sample", "relationship": "child"},
]
WHO = {"v-2026-02-10-pcp": "mem-jordan", "v-2026-04-02-pcp": "mem-jordan", "v-2026-04-02-lab": "mem-jordan",
       "v-2026-07-20-imaging": "mem-alex", "v-2026-09-28-derm": "mem-alex"}

# code, description, billed, allowed: Sam's well-child visit, all of it toward the deductible
LINES = [("99393", "Well child visit, 5-11 years", 220, 140), ("90460", "Immunization admin, first", 40, 25),
         ("90461", "Immunization admin, each more", 30, 18), ("90707", "MMR vaccine", 110, 85),
         ("90716", "Varicella vaccine", 160, 130), ("96110", "Developmental screening", 35, 20)]
SKIPPED = "96110"  # the statement charges this line in full: asks $15.00 more than the EOB


def household() -> dict:
    data = copy.deepcopy(json.loads(SOURCE.read_text()))
    data["source"]["notes"] = ("Made-up three-person household from example-ingest.json, written by "
                               "tools/make_household_sample.py. Every name, provider, amount and claim number is invented.")
    data["members"] = MEMBERS
    for plan in data["plans"]:
        plan["member_ids"] = [m["id"] for m in MEMBERS]
    for visit in data["visits"]:
        if visit["id"] in WHO:
            visit["member_id"] = WHO[visit["id"]]
    data["providers"].append({"id": "prov-peds", "name": "Example Pediatrics", "kind": "physician_practice",
                              "network_status": "in_network"})
    vid = "v-2026-08-11-peds"
    data["visits"].append({"id": vid, "date": "2026-08-11", "provider_id": "prov-peds", "plan_id": "plan-2026",
                           "member_id": "mem-sam", "category": "provider_visit", "description": "Well-child visit and vaccines",
                           "notes": "Expected: Discrepancy found. The statement skips the plan discount on 96110: $15.00."})
    billed, allowed = sum(l[2] for l in LINES), sum(l[3] for l in LINES)
    data["documents"].append({
        "id": "eob-2026-08-11-peds", "type": "eob", "date": "2026-08-25", "received_date": "2026-08-13",
        "plan_id": "plan-2026", "provider_id": "prov-peds", "visit_id": vid, "claim_number": "EX0000007",
        "claim_status": "processed", "network_status": "in_network", "billed": billed, "allowed": allowed,
        "adjustment": billed - allowed, "insurer_paid": 0, "deductible": allowed, "patient_responsibility": allowed,
        "lines": [{"service_date": "2026-08-11", "code": code, "description": desc, "billed": b, "allowed": a,
                   "insurer_paid": 0, "deductible": a, "patient_responsibility": a} for code, desc, b, a in LINES]})
    items = [{"service_date": "2026-08-11", "code": code, "description": desc, "charge": b,
              "adjustment": 0 if code == SKIPPED else b - a, "patient_amount": b if code == SKIPPED else a,
              "balance": b if code == SKIPPED else a} for code, desc, b, a in LINES]
    asks = sum(i["patient_amount"] for i in items)
    data["documents"].append({
        "id": "bill-peds-2026-09-05", "type": "provider_bill", "date": "2026-09-05", "due_date": "2026-10-05",
        "provider_id": "prov-peds", "network_status_shown": "in_network", "balance_due": asks,
        "lines": [{"visit_id": vid, "description": "Well-child visit", "billed_charge": billed, "insurance_paid": 0,
                   "adjustment": sum(i["adjustment"] for i in items), "patient_amount": asks, "patient_paid": 0,
                   "items": items}]})
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "samples" / "household-ingest.json")
    out = parser.parse_args().out
    out.write_text(json.dumps(household(), indent=2) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
