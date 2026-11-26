"""The public landing page (ADR-047, CareBack's design from REBRAND_PLAN.md §5): who sees it at "/", that it shows no
data, and that its copy keeps the UI guide's rules."""

import re

import pytest
from fastapi.testclient import TestClient

from mhs.config import Config
from mhs.web.app import create_app


def is_landing(response) -> bool:
    return response.status_code == 200 and "Now somebody does." in response.text


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


def test_page_is_careback_and_never_names_the_old_brand(release0):
    """ADR-060 and the owner's call of 2026-11-25: the page doesn't mention My Health Spend at all, and "Back" never
    promises money back."""
    text = release0.get("/welcome").text
    assert not re.search(r"Health\s+(?:\$|[Ss])pend|MyHealthSpend|MH\$", text)
    assert "<title>CareBack" in text and 'aria-label="CareBack home"' in text
    assert "It can’t promise that" in text
    assert not re.search(r"(get|win) (your|you) money back|guarantee|save you", text, re.I)


def test_about_us_is_signed_by_the_founder(release0):
    """docs/gtm/ABOUT.md: the mission, how we work and Don's signature, with his photo served by the app (the policy
    allows only the site's own images) and a link to his LinkedIn profile. Community service, not "a nonprofit"."""
    text = release0.get("/welcome").text
    assert 'href="#about">About us</a>' in text and 'id="about"' in text
    assert "Check every bill. Fix what’s wrong. Pay only what you owe." in text
    assert '<img src="/static/landing/don-huovinen.jpg" alt="Don Huovinen"' in text
    assert 'href="https://www.linkedin.com/in/don-huovinen-288399/"' in text
    assert "partner with a leading nonprofit" in text
    assert not re.search(r"CareBack is a (non-?profit|charity)|tax[- ](efficient|deductible|advice)", text, re.I)
    assert "Who is behind CareBack?" in text


def test_page_reads_complete_without_its_script(release0):
    """The red pen and the documents lining up are only added by landing.js: the HTML itself has the loops drawn and
    no animation classes, and the pause button stays hidden until the script can work it."""
    text = release0.get("/welcome").text
    assert text.count('<use href="#loop"/>') == 2 and 'id="loop"' in text
    assert "drawing" not in text and 'class="motion' not in text
    assert '<button class="pen-toggle" type="button" hidden>' in text


def test_start_button_follows_sign_up(release0):
    """Release 0 has no sign-up, so the closing button opens the app; the Release 1 cases are in test_r1_signup.py."""
    text = release0.get("/welcome").text
    assert '<a class="btn brand" href="/">Open the app</a>' in text and "Get started" not in text
    assert "accounts are set up by invitation" in text


@pytest.mark.parametrize("name", ["landing.css", "landing.js", "landing/billing-chaos.jpg", "landing/mark.svg",
                                  "landing/don-huovinen.jpg", "favicon.svg", "apple-touch-icon.png", "icon-192.png", "icon-512.png",
                                  "icon-maskable-512.png", "og-image.png", "site.webmanifest", "brand/mark.svg"])
def test_assets_are_served(release0, name):
    assert release0.get(f"/static/{name}").status_code == 200


def test_brand_icons_are_linked_and_the_manifest_points_at_real_files(release0):
    """ADR-060 and REBRAND_PLAN.md §2.3: every page head carries the icons, the manifest names CareBack, and the
    bare /favicon.ico browsers ask for is a real icon."""
    for path in ("/welcome", "/"):
        text = release0.get(path).text
        for link in ('href="/favicon.ico"', 'href="/static/favicon.svg"', 'rel="apple-touch-icon"', 'rel="manifest"'):
            assert link in text, (path, link)
    ico = release0.get("/favicon.ico")
    assert ico.status_code == 200 and ico.headers["content-type"] == "image/x-icon"
    assert ico.content[:4] == b"\x00\x00\x01\x00"  # an ICO file, not the SVG under another name
    manifest = release0.get("/static/site.webmanifest").json()
    assert manifest["name"] == "CareBack"
    for entry in manifest["icons"]:
        assert release0.get(entry["src"]).status_code == 200, entry["src"]


def test_landing_page_has_a_link_preview_image(release0):
    text = release0.get("/welcome").text
    match = re.search(r'<meta property="og:image" content="([^"]+)">', text)
    assert match and match.group(1).startswith("http") and match.group(1).endswith("/static/og-image.png")


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


@pytest.mark.postgres
def test_release1_serves_the_icon_and_preview_image_without_sign_in(household):
    c = household.client()
    ico = c.get("/favicon.ico", follow_redirects=False)
    assert ico.status_code == 200 and ico.headers["content-type"] == "image/x-icon"
    text = c.get("/welcome").text
    assert 'rel="manifest"' in text and "/static/og-image.png" in text
