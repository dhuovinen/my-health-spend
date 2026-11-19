"""Plan ahead pages (PRE-01 to PRE-07, ADR-053), visit-page additions (REC-06, REC-09, MAT-08), on both apps."""

import json

from tests.conftest import SAMPLE
from tests.test_web import web  # noqa: F401  (fixture)


def loaded(web):  # noqa: F811
    r = web.import_preview(SAMPLE)
    token = r.text.split('name="token" value="')[1].split('"')[0]
    web.client.post("/import/confirm", data={"token": token})
    return web


def test_plan_a_visit_and_see_the_estimate(web):  # noqa: F811
    loaded(web)
    r = web.client.get("/plan")
    assert r.status_code == 200 and "Plan a visit" in r.text
    r = web.client.post("/plan", data={"date": "2026-11-20", "provider_id": "new", "provider": "Lakeside Imaging",
                                       "plan_id": "plan-2026", "member_id": "", "service_type": "specialist",
                                       "description": "MRI", "expected_allowed": "800.00", "cash_price": "450"},
                        follow_redirects=False)
    assert r.status_code == 303, r.text
    page = web.client.get(r.headers["location"]).text
    assert "What you'll likely owe" in page and "Ask before the visit" in page and "Cash or insurance" in page
    assert "Information, not legal, tax or medical advice" in page
    assert "Lakeside Imaging" in web.client.get("/plan").text


def test_bad_amount_shows_an_error(web):  # noqa: F811
    loaded(web)
    r = web.client.post("/plan", data={"date": "2026-11-20", "provider_id": "new", "provider": "X",
                                       "expected_allowed": "lots"})
    assert r.status_code == 400 and "isn&#39;t an amount" in r.text


def test_service_type_on_the_visit_page(web):  # noqa: F811
    loaded(web)
    r = web.client.post("/visits/v-2026-02-10-pcp/service-type", data={"service_type": "preventive"},
                        follow_redirects=False)
    assert r.status_code == 303
    page = web.client.get("/visits/v-2026-02-10-pcp").text
    assert "Your share matches your plan" in page


def test_coverage_page_shows_and_edits_the_plans(web):  # noqa: F811
    """Coverage: each plan's card, terms, progress and claims; editing comes back here (the Settings plan routes)."""
    loaded(web)
    page = web.client.get("/coverage?year=2026").text
    for text in ("Coverage", "Example Health", "What you pay", "2026 so far", "Claims under this plan",
                 "Edit this plan", "Confirm these terms"):
        assert text in page, text
    r = web.client.post("/settings/plans/plan-2026", data={"insurer": "Example Health", "plan_name": "HDHP",
                                                           "plan_year": "2026", "coinsurance_pct": "20",
                                                           "copays": "specialist: 60", "terms_confirmed": "on"},
                        follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/coverage?year=2026")
    page = web.client.get(r.headers["location"]).text
    assert "You confirmed these terms" in page and "$60.00" in page and "Specialist copay" in page
    bad = web.client.post("/settings/plans/plan-2026", data={"plan_year": "2026", "copays": "nonsense"})
    assert bad.status_code == 400 and "should look like" in bad.text and "Coverage" in bad.text
    assert 'href="/coverage' in web.client.get("/").text  # Home's plan limits link here


def eob_year(tmp_path, coinsurance_rate=0.2):
    """A made-up plan year: the deductible met, then four EOBs charging 30% coinsurance (REC-15)."""
    import json
    plan = {"id": "plan-2026", "plan_year": 2026, "insurer": "Example Health", "coverage_order": "primary",
            "plan_name": "PPO", "limits": [{"type": "deductible", "network": "in_network", "level": "individual",
                                             "amount": 100}]}
    if coinsurance_rate is not None:
        plan["coinsurance_rate"] = coinsurance_rate
    visits, docs = [], []
    for i in range(5):
        vid = f"v-2026-0{i + 2}-01"
        visits.append({"id": vid, "date": f"2026-0{i + 2}-01", "provider_id": "prov-a", "plan_id": "plan-2026",
                       "category": "provider_visit", "description": f"Visit {i}"})
        ded, coins = (100.0, 0.0) if i == 0 else (0.0, 150.0)
        allowed = 100.0 if i == 0 else 500.0
        docs.append({"id": f"eob-{i}", "type": "eob", "date": f"2026-0{i + 2}-15", "plan_id": "plan-2026",
                     "provider_id": "prov-a", "visit_id": vid, "claim_number": f"C{i}", "claim_status": "processed",
                     "network_status": "in_network", "billed": allowed + 50, "allowed": allowed, "adjustment": 50.0,
                     "insurer_paid": allowed - ded - coins, "deductible": ded, "copay": 0.0, "coinsurance": coins,
                     "not_covered": 0.0, "patient_responsibility": ded + coins})
    data = {"schema_version": "0.1", "source": {"prepared_by": "test", "prepared_on": "2026-11-19"},
            "plans": [plan], "accounts": [], "providers": [{"id": "prov-a", "name": "Example Clinic",
                                                            "kind": "physician_practice", "network_status": "in_network"}],
            "visits": visits, "documents": docs}
    path = tmp_path / "eob-year.json"
    path.write_text(json.dumps(data))
    return path


def import_file(web, path):  # noqa: F811
    r = web.import_preview(path)
    token = r.text.split('name="token" value="')[1].split('"')[0]
    web.client.post("/import/confirm", data={"token": token})


def test_tc_rec_15_6_and_8_coverage_shows_what_the_eobs_show(web, tmp_path):  # noqa: F811
    import_file(web, eob_year(tmp_path))
    page = web.client.get("/coverage?year=2026").text
    assert "What your EOBs show" in page and "30%" in page and "4 of 4 EOBs agree" in page
    assert "use=coinsurance" not in page  # the member entered 20%: nothing to fill
    visit = web.client.get("/visits/v-2026-05-01").text  # the third EOB at 30% made it known
    assert "Coinsurance matches your EOBs" in visit and "Plan terms differ from your EOBs" in visit
    assert "Compare on Coverage" in visit and "says 20%" in visit
    r = web.client.post("/visits/v-2026-05-01/findings", data={"code": "terms-coinsurance", "amount": "0",
                                                                "verdict": "wrong"}, follow_redirects=False)
    assert r.status_code == 303
    assert "Closed by you" in web.client.get("/visits/v-2026-05-01").text


def test_tc_rec_15_8_use_this_fills_the_form_but_saves_nothing(web, tmp_path):  # noqa: F811
    import_file(web, eob_year(tmp_path, coinsurance_rate=None))
    page = web.client.get("/coverage?year=2026").text
    assert "use=coinsurance" in page and "Use this" in page
    filled = web.client.get("/coverage?year=2026&edit=plan-2026&use=coinsurance").text
    assert "Filled in from your EOBs, not saved yet" in filled and 'value="30"' in filled
    after = web.client.get("/coverage?year=2026").text
    assert "Filled in from your EOBs" not in after and "Confirm these terms" in after
    terms = after.split("What you pay")[1].split("What your EOBs show")[0]
    assert "Not set" in terms  # coinsurance still empty: nothing was written to the plan
    nothing = web.client.get("/coverage?year=2026&edit=plan-2026&use=deductible").text  # not known: no prefill
    assert "Filled in from your EOBs" not in nothing


def test_tc_rec_15_9_each_household_reads_only_its_own_eobs(tmp_path, request):
    """Two households with the same plan: only the one with the EOBs sees terms read from them."""
    import pytest
    from tests.test_web import CsrfClient, ReleaseOne
    try:
        household = request.getfixturevalue("household")
    except pytest.FixtureLookupError:
        pytest.skip("needs the Release 1 fixtures")

    class Member(ReleaseOne):  # a signed-in member of a new household; import_preview comes from ReleaseOne
        def __init__(self, name):
            c = household.sign_in(household.enrol(name))
            self.client = CsrfClient(c, household.csrf(c))

    with_eobs, without = Member("With EOBs"), Member("Without")
    path = eob_year(tmp_path, coinsurance_rate=None)
    import_file(with_eobs, path)
    data = json.loads(path.read_text())
    data["documents"] = []
    path.write_text(json.dumps(data))
    import_file(without, path)
    assert "What your EOBs show" in with_eobs.client.get("/coverage?year=2026").text
    page = without.client.get("/coverage?year=2026").text
    assert "PPO" in page and "What your EOBs show" not in page
