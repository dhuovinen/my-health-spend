"""Made-up CARIN Blue Button ExplanationOfBenefit resources for ING-09 tests. Every name and number is invented."""


def money(value):
    return {"value": value, "currency": "USD"}


def adj(code, value, reason=None):
    a = {"category": {"coding": [{"system": "http://hl7.org/fhir/us/carin-bb/CodeSystem/C4BBAdjudication",
                                  "code": code}]}, "amount": money(value)}
    if reason:
        a["reason"] = {"coding": [{"system": "https://x12.org/codes/claim-adjustment-reason-codes", "code": reason}]}
    return a


def eob(claim="CLM-1001", when="2026-03-04", billed=200.0, allowed=120.0, paid=96.0, deductible=0.0, coins=24.0,
        provider="Lakeside Family Medicine", network="innetwork", reason=None):
    return {
        "resourceType": "ExplanationOfBenefit", "id": f"x-{claim}", "status": "active", "outcome": "complete",
        "identifier": [{"type": {"coding": [{"code": "uc"}]}, "value": claim}],
        "patient": {"reference": "Patient/p-777"},
        "billablePeriod": {"start": when, "end": when}, "created": "2026-03-20",
        "provider": {"reference": "#org1"},
        "contained": [{"resourceType": "Organization", "id": "org1", "name": provider}],
        "supportingInfo": [{"category": {"coding": [{"code": "benefitpaymentstatus"}]},
                            "code": {"coding": [{"code": network}]}}],
        "item": [{"sequence": 1, "servicedDate": when,
                  "productOrService": {"coding": [{"system": "http://www.ama-assn.org/go/cpt", "code": "99213"}]},
                  "adjudication": [adj("submitted", billed), adj("eligible", allowed), adj("benefit", paid),
                                   adj("deductible", deductible), adj("coinsurance", coins),
                                   adj("memberliability", deductible + coins, reason)]}],
        "total": [adj("submitted", billed), adj("eligible", allowed), adj("benefit", paid),
                  adj("memberliability", deductible + coins)],
    }


def bundle(resources, next_url=None):
    b = {"resourceType": "Bundle", "type": "searchset", "entry": [{"resource": r} for r in resources]}
    if next_url:
        b["link"] = [{"relation": "next", "url": next_url}]
    return b
