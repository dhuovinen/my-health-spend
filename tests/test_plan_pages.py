"""Plan ahead pages (PRE-01 to PRE-07, ADR-053), visit-page additions (REC-06, REC-09, MAT-08), on both apps."""

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
