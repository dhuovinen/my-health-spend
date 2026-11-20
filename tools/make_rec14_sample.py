"""Write samples/rec14/: made-up data for REC-14 (ADR-045) and the result each visit should show.

Each case has its own provider, so its series can't touch another case's. Every visit has line detail on an EOB and is
paid in full unless the case says otherwise, so a flag is the only thing that could make it look wrong. Usage (the
files are committed):

    uv run tools/make_rec14_sample.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "samples" / "rec14"
RILEY, SAM = "mbr-riley-test", "mbr-sam-test"
PLAN, PLAN_B, PLAN_2025, PLAN_LOW = "plan-2026", "plan-2026-b", "plan-2025", "plan-2026-low"
COMPLETE = "Complete"


class Data:
    def __init__(self):
        self.visits, self.documents, self.providers, self.expected = [], [], [], {}

    def provider(self, name: str) -> str:
        pid = "prov-" + name.lower().replace(" ", "-")
        if pid not in [p["id"] for p in self.providers]:
            self.providers.append({"id": pid, "name": name, "kind": "physician_practice", "network_status": "in_network"})
        return pid

    def visit(self, case, vid, when, lines, provider, member=RILEY, plan=PLAN, status="processed", flags=(), notes=(),
              expected_status=COMPLETE, paid=True):
        """lines: dicts from line(), or None for a claim with totals only."""
        pid = self.provider(provider)
        self.visits.append({"id": vid, "date": when, "provider_id": pid, "member_id": member, "plan_id": plan,
                            "category": "provider_visit"})
        parts = lines if lines else [line("X", 500, 400, 400)]
        head = {k: sum(l.get(k, 0) for l in parts) for k in ("billed", "allowed", "adjustment", "insurer_paid", "deductible",
                                                             "copay", "coinsurance", "not_covered", "patient_responsibility")}
        doc = {"id": f"eob-{vid}", "type": "eob", "date": when, "plan_id": plan, "provider_id": pid, "visit_id": vid,
               "claim_number": f"CLM-{vid}", "claim_status": status, "network_status": "in_network", **head}
        if lines:
            doc["lines"] = [{"service_date": when, **l} for l in lines]
        self.documents.append(doc)
        owed = head["patient_responsibility"]
        if paid and owed and status != "denied":
            self.documents.append({"id": f"pay-{vid}", "type": "payment", "date": when, "kind": "payment", "provider_id": pid,
                                   "account_id": "acct-hsa", "amount": owed,
                                   "allocations": [{"visit_id": vid, "amount": owed}]})
        self.expected[vid] = {"case": case, "flags": list(flags), "notes": list(notes), "status": expected_status,
                              "at_issue": 0, "provider": provider, "date": when}


def line(code, billed, allowed, share, deductible=None, units=None, coinsurance=0, description="Treatment"):
    deductible = share - coinsurance if deductible is None else deductible
    out = {"code": code, "description": description, "billed": billed, "allowed": allowed, "adjustment": billed - allowed,
           "insurer_paid": allowed - share, "deductible": deductible, "copay": 0, "coinsurance": coinsurance,
           "not_covered": 0, "patient_responsibility": share}
    return {**out, "units": units} if units else out


def flag(name, *words):
    return {"name": name, "contains": list(words)}


ALLOWED, BILLED, SHARE, CODES = ("Allowed amount changed", "Billed amount changed", "Your share changed",
                                 "Codes changed in a series")
LOOK = ("Worth a closer look", "a new contract", "an added service", "a different dose")


def build() -> tuple[dict, dict]:
    d = Data()
    # Control: the same treatment at the same price makes no flags.
    for i, when in enumerate(("2026-01-05", "2026-02-05", "2026-03-05")):
        d.visit("Control", f"v-control-{i + 1}", when, [line("96413", 500, 400, 400)], "Control Clinic")

    d.visit("TC-REC-14-1", "v-tc1-a", "2026-02-02", [line("96413", 500, 400, 400)], "Case One Infusion")
    d.visit("TC-REC-14-1", "v-tc1-b", "2026-03-02", [line("96413", 500, 250, 250)], "Case One Infusion",
            flags=[flag(ALLOWED, "96413", "$400.00", "Feb 2, 2026", "$250.00", "Mar 2, 2026", "$150.00", *LOOK)])

    d.visit("TC-REC-14-2", "v-tc2-a", "2026-02-03", [line("99214", 150, 90, 90)], "Case Two Practice")
    d.visit("TC-REC-14-2", "v-tc2-b", "2026-03-03", [line("99214", 150.10, 90, 90)], "Case Two Practice",
            flags=[flag(BILLED, "99214", "$150.00", "$150.10", "$0.10")])

    d.visit("TC-REC-14-3", "v-tc3-a", "2026-02-04", [line("96413", 500, 400, 400)], "Case Three Infusion")
    d.visit("TC-REC-14-3", "v-tc3-b", "2026-03-04", [line("96413", 500, 400, 80, deductible=0, coinsurance=80)],
            "Case Three Infusion", notes=[flag(SHARE, "deductible", "explains", "$400.00", "$80.00")])

    d.visit("TC-REC-14-4", "v-tc4-a", "2026-02-05", [line("96413", 500, 400, 400)], "Case Four Infusion")
    d.visit("TC-REC-14-4", "v-tc4-b", "2026-03-05", [line("96413", 500, 400, 250)], "Case Four Infusion",
            flags=[flag(SHARE, "96413", "$400.00", "$250.00", "$150.00")])

    low = [line("96413", 500, 250, 250)]
    d.visit("TC-REC-14-5 person", "v-tc5a-a", "2026-02-06", [line("96413", 500, 400, 400)], "Case Five Person")
    d.visit("TC-REC-14-5 person", "v-tc5a-b", "2026-03-06", low, "Case Five Person", member=SAM)
    d.visit("TC-REC-14-5 group", "v-tc5b-a", "2026-02-07", [line("96413", 500, 400, 400)], "Case Five Group One")
    d.visit("TC-REC-14-5 group", "v-tc5b-b", "2026-03-07", low, "Case Five Group Two")
    d.visit("TC-REC-14-5 plan", "v-tc5c-a", "2026-02-08", [line("96413", 500, 400, 400)], "Case Five Plan")
    d.visit("TC-REC-14-5 plan", "v-tc5c-b", "2026-03-08", low, "Case Five Plan", plan=PLAN_B)
    d.visit("TC-REC-14-5 year", "v-tc5d-a", "2025-12-09", [line("96413", 500, 400, 400)], "Case Five Year", plan=PLAN_2025)
    d.visit("TC-REC-14-5 year", "v-tc5d-b", "2026-01-09", low, "Case Five Year")

    d.visit("TC-REC-14-6 units", "v-tc6a-a", "2026-02-10", [line("97110", 200, 200, 200, units=2)], "Case Six Units")
    d.visit("TC-REC-14-6 units", "v-tc6a-b", "2026-03-10", [line("97110", 100, 100, 100, units=1)], "Case Six Units")
    d.visit("TC-REC-14-6 modifier", "v-tc6b-a", "2026-02-11", [line("99214", 500, 400, 400)], "Case Six Modifier")
    d.visit("TC-REC-14-6 modifier", "v-tc6b-b", "2026-03-11", [line("99214-25", 500, 250, 250)], "Case Six Modifier")

    ab = [line("A1001", 100, 100, 100), line("B1002", 100, 100, 100)]
    for i, when in enumerate(("2026-01-12", "2026-02-12", "2026-03-12", "2026-04-12")):
        d.visit("TC-REC-14-7 series", f"v-tc7a-{i + 1}", when, ab, "Case Seven Series")
    d.visit("TC-REC-14-7 series", "v-tc7a-5", "2026-05-12", ab + [line("C1003", 100, 100, 100)], "Case Seven Series",
            flags=[flag(CODES, "added C1003", *LOOK)])
    for i, when in enumerate(("2026-01-13", "2026-02-13")):
        d.visit("TC-REC-14-7 short", f"v-tc7b-{i + 1}", when, ab, "Case Seven Short")
    d.visit("TC-REC-14-7 short", "v-tc7b-3", "2026-03-13", ab + [line("C1003", 100, 100, 100)], "Case Seven Short")

    d.visit("TC-REC-14-8 no lines", "v-tc8a-a", "2026-02-14", None, "Case Eight Totals")
    d.visit("TC-REC-14-8 no lines", "v-tc8a-b", "2026-03-14", None, "Case Eight Totals")
    d.visit("TC-REC-14-8 unconfirmed", "v-tc8b-a", "2026-02-15", [line("96413", 500, 400, 400)], "Case Eight Unconfirmed")

    d.visit("TC-REC-14-9", "v-tc9-1", "2026-01-16", [line("96413", 500, 400, 400)], "Case Nine Infusion")
    d.visit("TC-REC-14-9", "v-tc9-2", "2026-02-16", [line("96413", 500, 400, 400)], "Case Nine Infusion")
    d.visit("TC-REC-14-9", "v-tc9-3", "2026-03-16", low, "Case Nine Infusion", flags=[flag(ALLOWED, "$150.00")])
    d.visit("TC-REC-14-9", "v-tc9-4", "2026-04-16", low, "Case Nine Infusion")
    d.visit("TC-REC-14-9", "v-tc9-5", "2026-05-16", low, "Case Nine Infusion")

    # Beyond the test cases: rules ADR-045 states that TC-1 to TC-10 don't reach.
    d.visit("Tolerance", "v-tol-a", "2026-02-17", [line("96413", 500, 400, 400)], "Extra Tolerance")
    d.visit("Tolerance", "v-tol-b", "2026-03-17", [line("96413", 500, 400, 399.50)], "Extra Tolerance")
    d.visit("Both change", "v-both-a", "2026-02-18", [line("96413", 500, 400, 400)], "Extra Both")
    d.visit("Both change", "v-both-b", "2026-03-18", [line("96413", 600, 250, 250)], "Extra Both",
            flags=[flag(ALLOWED, "$150.00"), flag(BILLED, "$100.00")])
    d.visit("Back again", "v-back-a", "2026-02-19", [line("96413", 500, 400, 400)], "Extra Back")
    d.visit("Back again", "v-back-b", "2026-03-19", [line("96413", 500, 250, 250)], "Extra Back", flags=[flag(ALLOWED, "$150.00")])
    d.visit("Back again", "v-back-c", "2026-04-19", [line("96413", 500, 400, 400)], "Extra Back", flags=[flag(ALLOWED, "$150.00")])
    d.visit("Denied claim", "v-den-a", "2026-02-20", [line("96413", 500, 400, 400)], "Extra Denied")
    d.visit("Denied claim", "v-den-b", "2026-03-20", [line("96413", 500, 0, 0)], "Extra Denied", status="denied", expected_status=None)
    d.visit("Deductible reached", "v-ded-a", "2026-02-21", [line("96413", 500, 400, 400)], "Extra Deductible", plan=PLAN_LOW)
    d.visit("Deductible reached", "v-ded-b", "2026-03-21", [line("96413", 500, 400, 150, deductible=100, coinsurance=50)],
            "Extra Deductible", plan=PLAN_LOW, notes=[flag(SHARE, "deductible", "explains")])

    # Billed amounts from statement lines, with no EOB (expected status depends on the waiting period, so not checked).
    pid = d.provider("Extra Statements")
    for vid, when, charge in (("v-stmt-a", "2026-02-22", 400), ("v-stmt-b", "2026-03-22", 250)):
        d.visits.append({"id": vid, "date": when, "provider_id": pid, "member_id": RILEY, "plan_id": PLAN,
                         "category": "provider_visit"})
        d.documents.append({"id": f"bill-{vid}", "type": "provider_bill", "date": when, "provider_id": pid, "balance_due": charge,
                            "lines": [{"visit_id": vid, "billed_charge": charge, "patient_amount": charge, "items": [
                                {"code": "96413", "description": "Treatment", "service_date": when, "charge": charge,
                                 "patient_amount": charge}]}]})
        d.expected[vid] = {"case": "Statement lines", "flags": [], "notes": [], "status": None, "at_issue": None,
                           "provider": "Extra Statements", "date": when}
    d.expected["v-stmt-b"]["flags"] = [flag(BILLED, "$400.00", "$250.00", "$150.00")]

    limits = lambda amount: [{"type": "deductible", "network": "in_network", "level": "individual", "amount": amount}]  # noqa: E731
    plan = lambda pid, year, name, amount=10000: {  # noqa: E731
        "id": pid, "plan_year": year, "insurer": "Test Insurer", "plan_name": name, "coverage_order": "primary",
        "coverage_start": f"{year}-01-01", "coverage_end": f"{year}-12-31", "hsa_eligible_plan": True,
        "coinsurance_rate": 0.2, "member_ids": [RILEY, SAM], "limits": limits(amount)}
    data = {"schema_version": "0.1",
            "source": {"prepared_by": "tools/make_rec14_sample.py", "prepared_on": "2026-11-06",
                       "notes": "Made-up data for REC-14. Every name, provider, amount and claim number is invented."},
            "members": [{"id": RILEY, "name": "Riley Test", "relationship": "self"},
                        {"id": SAM, "name": "Sam Test", "relationship": "child"}],
            "accounts": [{"id": "acct-hsa", "name": "HSA", "type": "hsa"}],
            "plans": [plan(PLAN, 2026, "Test HDHP"), plan(PLAN_B, 2026, "Test Second Plan"), plan(PLAN_2025, 2025, "Test HDHP 2025"),
                      plan(PLAN_LOW, 2026, "Test Low Deductible", 500)],
            "providers": d.providers, "visits": d.visits, "documents": d.documents}
    return data, d.expected


if __name__ == "__main__":
    data, expected = build()
    OUT.mkdir(exist_ok=True)
    (OUT / "rec14-ingest.json").write_text(json.dumps(data, indent=2) + "\n")
    (OUT / "rec14-expected.json").write_text(json.dumps(expected, indent=2) + "\n")
    print(f"{len(data['visits'])} visits and {len(data['documents'])} documents in {OUT}")
