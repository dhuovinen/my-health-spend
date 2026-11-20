"""One main address (ADR-058): with MHS_REDIRECT_OTHER_HOSTS, the app forwards every other host to MHS_PUBLIC_URL, and
the old site's /auth goes to the sign-in page."""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.postgres

MAIN = "https://myhealthspend.com"


@pytest.fixture
def forwarding(make_household):
    return make_household(public_url=MAIN, redirect_other_hosts=True, cookie_secure=True)


def at(household, base: str) -> TestClient:
    return TestClient(household.app, base_url=base)


@pytest.mark.parametrize("other", ["https://app.myhealthspend.com", "https://www.myhealthspend.com",
                                   "https://mhs-app-123.us-east4.run.app"])
def test_other_hosts_go_to_the_same_path_on_the_main_address(forwarding, other):
    c = at(forwarding, other)
    r = c.get("/visits?year=2026", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == f"{MAIN}/visits?year=2026"
    assert r.headers["x-content-type-options"] == "nosniff"  # the security headers come with it
    r = c.post("/signin", data={"email": "a@example.test", "password": "x"}, follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == f"{MAIN}/signin"  # a post stays a post
    assert c.get("/signin/with/google/callback?code=c&state=s", follow_redirects=False).headers["location"] \
        == f"{MAIN}/signin/with/google/callback?code=c&state=s"


def test_the_main_address_and_health_answer_directly(forwarding):
    assert at(forwarding, MAIN).get("/signin").status_code == 200
    assert at(forwarding, MAIN).get("/").status_code == 200  # the landing page for signed-out visitors
    assert at(forwarding, "https://mhs-app-123.us-east4.run.app").get("/health").json() == {"ok": True}


def test_forwarding_is_off_unless_turned_on(make_household):
    plain = make_household(public_url=MAIN)
    assert at(plain, "https://app.myhealthspend.com").get("/signin").status_code == 200


def test_the_old_sites_sign_in_link_reaches_sign_in(household):
    r = household.client().get("/auth", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/signin"
