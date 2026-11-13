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
