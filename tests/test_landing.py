"""The public landing page (ADR-047): who sees it at "/", that it shows no data, and that its copy keeps the UI guide's rules."""

import re

import pytest
from fastapi.testclient import TestClient

from mhs.config import Config
from mhs.web.app import create_app


def is_landing(response) -> bool:
    return response.status_code == 200 and "Let’s make sense" in response.text


@pytest.fixture
def release0(tmp_path):
    return TestClient(create_app(Config(data_dir=tmp_path / "data")))


def test_release0_keeps_home_at_root_and_serves_the_page_at_welcome(release0):
    assert "No visits yet" in release0.get("/").text
    page = release0.get("/welcome")
    assert is_landing(page)
    assert 'href="/"' in page.text and "Open the app" in page.text


def test_copy_follows_the_ui_guide(release0):
    text = release0.get("/welcome").text
    assert not re.search(r"\$500B|\$25.{1,3}50B", text)  # unverified statistics stay off new material
    assert "potential discrepancy" in text and "worth a closer look" in text
    assert "Fictional documents" in text and "fictional example" in text
    assert "concept" not in text.lower()  # the product exists now
    assert "supabase" not in text.lower() and "lovable" not in text.lower()


@pytest.mark.parametrize("name", ["landing.css", "landing.js", "landing/billing-chaos.jpg", "landing/mark.png"])
def test_assets_are_served(release0, name):
    assert release0.get(f"/static/{name}").status_code == 200


@pytest.mark.postgres
def test_anonymous_visitor_gets_the_landing_page_at_root(household):
    c = household.client()
    r = c.get("/", follow_redirects=False)
    assert is_landing(r)
    assert 'href="/signin"' in r.text and "Sign in" in r.text
    assert r.headers["cache-control"] == "no-store"  # one URL, different answers per session
    assert is_landing(c.get("/welcome"))


@pytest.mark.postgres
def test_only_root_changed_other_pages_still_need_sign_in(household):
    c = household.client()
    for path in ("/visits", "/household", "/settings", "/uploads", "/data"):
        assert c.get(path, follow_redirects=False).headers["location"] == "/signin", path
    assert c.get("/api/visits").status_code == 401


@pytest.mark.postgres
def test_password_without_code_goes_to_mfa_not_the_landing_page(household):
    who = household.enrol()
    c = household.client()
    c.post("/signin", data={"email": who.email, "password": who.password}, follow_redirects=False)
    assert c.get("/", follow_redirects=False).headers["location"] == "/signin/mfa"


@pytest.mark.postgres
def test_member_gets_home_and_sign_in_sends_them_there(household):
    c = household.sign_in(household.enrol())
    home = c.get("/", follow_redirects=False)
    assert home.status_code == 200 and "No visits yet" in home.text and not is_landing(home)
    assert c.get("/signin", follow_redirects=False).headers["location"] == "/"
    assert is_landing(c.get("/welcome"))
    assert "Sign out" not in c.get("/welcome").text  # the public page shows nothing of the member's


@pytest.mark.postgres
def test_signing_out_returns_to_the_sign_in_form_and_root_is_public_again(household):
    c = household.sign_in(household.enrol())
    r = c.post("/signout", data={"csrf_token": household.csrf(c)}, follow_redirects=False)
    assert r.headers["location"] == "/signin"
    assert is_landing(c.get("/", follow_redirects=False))
