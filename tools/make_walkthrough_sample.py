"""Write the walkthrough sample in samples/walkthrough/ (docs/USER_TEST_GUIDE.md).

It sits on top of what `mhs-admin demo-setup` creates (Jordan Sample, the 2026 HDHP plan, the HSA) and adds Alex
Sample, Jordan's spouse, with an employer plan from Granite Mutual and a secondary plan, so each Release 2 feature
has a visit to look at without changing Jordan's demo story (docs/DEMO.md):

    walkthrough-ingest.json    import on the Import page after demo-setup
    granite-eob-1.pdf ... -3   upload one at a time to see learning from corrections (ING-06)

Every name, number and address is made up. Usage (rewrites the files; the sample is committed):

    uv run tools/make_walkthrough_sample.py [--out samples/walkthrough]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.pdfs import make_pdf  # noqa: E402

# What demo-setup creates (src/mhs/web/household/admin.py demo_settings); the file refers to these, so it imports
# only into the demo household.
JORDAN, JORDAN_PLAN, HSA = "mbr-jordan-sample", "plan-2026-example-hdhp-1700", "acct-hsa"
ALEX, ALEX_PLAN, SECONDARY, CARD = "mbr-alex-sample", "plan-2026-granite-ppo", "plan-2026-alex-secondary", "acct-card"

PROVIDERS = {
    "prov-wt-lakeside-fm": ("Lakeside Family Medicine", "in_network"),
    "prov-wt-bennett": ("Bennett Radiology", "in_network"),
    "prov-wt-northgate": ("Northgate Dermatology", "in_network"),
    "prov-wt-cedar": ("Cedar Valley Labs", "in_network"),
    "prov-wt-hillcrest": ("Hillcrest Imaging Center", "in_network"),
    "prov-wt-riverside": ("Riverside Physical Therapy", "in_network"),
    "prov-wt-summit": ("Summit Eye Associates", "in_network"),
    "prov-wt-maple": ("Maple Street Orthopedics", "in_network"),
    "prov-wt-harbor": ("Harbor Cardiology", "in_network"),
    "prov-wt-oakview": ("Oakview Imaging", "unknown"),
}


def visit(vid, day, provider, description, member=ALEX, plan=ALEX_PLAN, **extra):
    return {"id": vid, "date": day, "provider_id": provider, "member_id": member, "plan_id": plan,
            "category": "provider_visit", "description": description, **extra}


def eob(eid, vid, day, provider, claim, billed, allowed, paid, plan=ALEX_PLAN, deductible=0, copay=0, coinsurance=0,
        not_covered=0, **extra):
    """An EOB whose money adds up (REC-01): billed = discount + insurer paid + your share."""
    owed = deductible + copay + coinsurance + not_covered
    doc = {"id": eid, "type": "eob", "date": day, "plan_id": plan, "provider_id": provider, "visit_id": vid,
           "claim_number": claim, "claim_status": "processed", "network_status": "in_network",
           "billed": billed, "allowed": allowed, "adjustment": round(billed - allowed, 2), "insurer_paid": paid,
           "deductible": deductible, "copay": copay, "coinsurance": coinsurance, "not_covered": not_covered,
           "patient_responsibility": owed, **extra}
    assert abs(billed - (doc["adjustment"] + paid + owed + extra.get("secondary_paid", 0))) < 0.005, eid
    return doc


def pay(pid, day, provider, amount, account=HSA, kind="payment", **extra):
    return {"id": pid, "type": "payment", "date": day, "provider_id": provider, "account_id": account,
            "amount": amount, "kind": kind, **extra}


def ingest() -> dict:
    plans = [
        {"id": ALEX_PLAN, "plan_year": 2026, "insurer": "Granite Mutual", "plan_name": "Granite PPO 1000",
         "coverage_order": "primary", "coverage_start": "2026-01-01", "coverage_end": "2026-12-31",
         "hsa_eligible_plan": False, "coinsurance_rate": 0.2, "member_ids": [ALEX],
         "copays": {"primary_care": 25, "specialist": 60, "urgent_care": 75},
         "limits": [{"type": "deductible", "network": "in_network", "level": "individual", "amount": 1000},
                    {"type": "out_of_pocket_max", "network": "in_network", "level": "individual", "amount": 4000}]},
        {"id": SECONDARY, "plan_year": 2026, "insurer": "Example Health", "plan_name": "Spouse coverage (secondary)",
         "coverage_order": "secondary", "coverage_start": "2026-09-01", "coverage_end": "2026-12-31",
         "member_ids": [ALEX], "limits": []},
    ]
    members = [{"id": ALEX, "name": "Alex Sample", "relationship": "spouse", "aliases": ["Alex Sample", "Sample, Alex"]}]
    accounts = [{"id": CARD, "name": "Visa card", "type": "credit_card"}]
    providers = [{"id": pid, "name": name, "network_status": status} for pid, (name, status) in PROVIDERS.items()]

    v, d = [], []

    # 1. A copay visit that matches the plan: the baseline (REC-06 passes).
    v.append(visit("v-wt-01", "2026-02-10", "prov-wt-lakeside-fm", "Primary care visit", service_type="primary_care"))
    d += [eob("eob-wt-01", "v-wt-01", "2026-02-24", "prov-wt-lakeside-fm", "GM-10001", 210, 180, 155, copay=25),
          pay("pay-wt-01", "2026-03-02", "prov-wt-lakeside-fm", 25)]

    # 2. The MRI that meets Alex's deductible ($1,000) plus 20% of the rest.
    v.append(visit("v-wt-02", "2026-03-05", "prov-wt-bennett", "MRI of the lumbar spine"))
    d += [eob("eob-wt-02", "v-wt-02", "2026-03-20", "prov-wt-bennett", "GM-10002", 2400, 1600, 480,
              deductible=1000, coinsurance=120),
          pay("pay-wt-02", "2026-03-28", "prov-wt-bennett", 1120)]

    # 3. REC-06: a specialist charged a $75 copay; the plan says $60.
    v.append(visit("v-wt-03", "2026-04-14", "prov-wt-northgate", "Specialist visit, skin check",
                   service_type="specialist"))
    d += [eob("eob-wt-03", "v-wt-03", "2026-04-28", "prov-wt-northgate", "GM-10003", 260, 220, 145, copay=75)]

    # 4. REC-06: the deductible applied again after it was met in March.
    v.append(visit("v-wt-04", "2026-05-20", "prov-wt-cedar", "Blood tests"))
    d += [eob("eob-wt-04", "v-wt-04", "2026-06-03", "prov-wt-cedar", "GM-10004", 420, 300, 0, deductible=300)]

    # 5. REC-06: a preventive visit charged a copay.
    v.append(visit("v-wt-05", "2026-06-02", "prov-wt-lakeside-fm", "Annual physical", service_type="preventive"))
    d += [eob("eob-wt-05", "v-wt-05", "2026-06-16", "prov-wt-lakeside-fm", "GM-10005", 320, 250, 225, copay=25)]

    # 6. REC-09: a line denied as not medically necessary (PR-50), with the codes explained.
    v.append(visit("v-wt-06", "2026-06-18", "prov-wt-hillcrest", "Ultrasound and follow-up"))
    lines6 = [{"service_date": "2026-06-18", "code": "76700", "description": "Ultrasound, abdomen", "billed": 450,
               "allowed": 300, "insurer_paid": 300, "patient_responsibility": 0, "adjustment": 150,
               "remark_codes": ["CO-45"]},
              {"service_date": "2026-06-18", "code": "99214", "description": "Office visit", "billed": 250,
               "allowed": 250, "insurer_paid": 0, "patient_responsibility": 250, "not_covered": 250,
               "remark_codes": ["PR-50", "N130"]}]
    d += [eob("eob-wt-06", "v-wt-06", "2026-07-01", "prov-wt-hillcrest", "GM-10006", 700, 550, 300,
              not_covered=250, lines=lines6, remark_codes=["CO-45"])]

    # 7. MAT-08: Alex corrected the first EOB by hand; the insurer then sent a corrected one. Alex chooses.
    v.append(visit("v-wt-07", "2026-07-08", "prov-wt-riverside", "Physical therapy, 6 sessions"))
    # The corrected EOB lowers the allowed amount, so Alex's share drops from $120 to $90 after $120 was paid.
    first = eob("eob-wt-07", "v-wt-07", "2026-07-20", "prov-wt-riverside", "GM-10007", 900, 600, 480,
                coinsurance=120, member_edited=True)
    newer = eob("eob-wt-07-v2", "v-wt-07", "2026-08-15", "prov-wt-riverside", "GM-10007", 900, 450, 360,
                coinsurance=90, version_of="eob-wt-07", version_reason="corrected")
    d += [first, newer, pay("pay-wt-07", "2026-07-25", "prov-wt-riverside", 120)]

    # 8. ALC-08: paid $200 from the HSA on a $120 bill; the $80 refund came back by check, to the card account.
    v.append(visit("v-wt-08", "2026-08-12", "prov-wt-summit", "Eye exam and testing"))
    d += [eob("eob-wt-08", "v-wt-08", "2026-08-26", "prov-wt-summit", "GM-10008", 720, 600, 480, coinsurance=120),
          pay("pay-wt-08", "2026-08-20", "prov-wt-summit", 200),
          pay("ref-wt-08", "2026-09-30", "prov-wt-summit", 80, account=CARD, kind="refund", refund_of=["pay-wt-08"])]

    # 9. ALC-05: the first plan left $50; the second paid $40; Alex owes $10.
    v.append(visit("v-wt-09", "2026-09-15", "prov-wt-maple", "Knee follow-up"))
    d += [eob("eob-wt-09", "v-wt-09", "2026-09-29", "prov-wt-maple", "GM-10009", 400, 250, 200, coinsurance=50),
          {"id": "eob-wt-09-s", "type": "eob", "date": "2026-10-13", "plan_id": SECONDARY,
           "provider_id": "prov-wt-maple", "visit_id": "v-wt-09", "claim_number": "EH-55009",
           "claim_status": "processed", "network_status": "in_network", "billed": 400, "allowed": 50,
           "insurer_paid": 40, "patient_responsibility": 10},
          pay("pay-wt-09", "2026-10-20", "prov-wt-maple", 10)]

    # 10. ALC-05: the first plan's EOB is in; the second insurer's isn't yet.
    v.append(visit("v-wt-10", "2026-11-04", "prov-wt-harbor", "Cardiology consult"))
    d += [eob("eob-wt-10", "v-wt-10", "2026-11-10", "prov-wt-harbor", "GM-10010", 520, 350, 280, coinsurance=70)]

    # 11. PRE: an MRI Jordan plans for December, with a cash price.
    v.append(visit("plan-wt-11", "2026-12-16", "prov-wt-oakview", "MRI of the left knee", member=JORDAN,
                   plan=JORDAN_PLAN, planned=True, expected_allowed=1200, cash_price=650, service_type="other"))
    # 12. PRE: a planned eye exam whose date has passed with no documents.
    v.append(visit("plan-wt-12", "2026-11-03", "prov-wt-summit", "Annual eye exam", planned=True,
                   expected_allowed=180, service_type="specialist"))

    return {"schema_version": "0.1",
            "source": {"prepared_by": "tools/make_walkthrough_sample.py",
                       "notes": "Synthetic. Import after `mhs-admin demo-setup`; see docs/USER_TEST_GUIDE.md."},
            "members": members, "plans": plans, "accounts": accounts, "providers": providers,
            "visits": v, "documents": d}


# ING-06: an EOB layout the layout rules don't know, from Alex's insurer. Upload them one at a time.
GRANITE = """GRANITE MUTUAL
Explanation of Benefits - this is not a bill
Member: Alex Sample
Member ID: GMX-448-2201
Provider: {provider}
Date of service: {day}
Claim number: {claim}
Submitted by provider ${billed}
Contracted rate ${allowed}
Granite remitted ${paid}
Member portion ${owed}
Questions? Call Granite Mutual member services at (555) 010-4420.
"""
GRANITE_EOBS = [
    ("Westfield Allergy", "05/06/2026", "GM-20511", "412.00", "286.00", "228.80", "57.20"),
    ("Westfield Allergy", "05/27/2026", "GM-20587", "398.00", "271.00", "216.80", "54.20"),
    ("Brookside Podiatry", "06/09/2026", "GM-20640", "335.00", "240.00", "192.00", "48.00"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "samples" / "walkthrough")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "walkthrough-ingest.json").write_text(json.dumps(ingest(), indent=2) + "\n")
    for i, (provider, day, claim, billed, allowed, paid, owed) in enumerate(GRANITE_EOBS, 1):
        text = GRANITE.format(provider=provider, day=day, claim=claim, billed=billed, allowed=allowed, paid=paid,
                              owed=owed)
        (args.out / f"granite-eob-{i}.pdf").write_bytes(make_pdf(text))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
