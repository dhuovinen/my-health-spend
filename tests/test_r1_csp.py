"""PRV-08: no third-party scripts, and a Content Security Policy that blocks them (TC-PRV-08-3)."""

import re
from pathlib import Path

import pytest

from mhs.web.household import security

pytestmark = pytest.mark.postgres

HOUSEHOLD = Path(__file__).resolve().parents[1] / "src" / "mhs" / "web" / "household"
STATIC = HOUSEHOLD.parent / "static"
# Plain links out (navigation, never a resource the page loads): the founder's profile on the landing page's About us
# (docs/gtm/ABOUT.md). Referrer-Policy is same-origin, so following one sends nothing about the visitor.
OUTBOUND_LINKS = {"https://www.linkedin.com/in/don-huovinen-288399/"}


def directives(csp: str) -> dict[str, list[str]]:
    return {d.split()[0]: d.split()[1:] for d in (p.strip() for p in csp.split(";")) if d}


def test_tc_prv_08_3_policy_allows_only_own_scripts():
    d = directives(security.CSP)
    assert d["default-src"] == ["'none'"]
    assert d["script-src"] == ["'self'"]
    assert d["style-src"] == ["'self'"]
    assert d["object-src"] == ["'none'"] and d["frame-ancestors"] == ["'none'"] and d["base-uri"] == ["'none'"]
    assert d["manifest-src"] == ["'self'"]  # the home-screen icons' manifest (ADR-060), nothing else
    for name, values in d.items():
        allowed_data = name == "img-src"  # the favicon-style inline SVGs only
        for v in values:
            assert v not in ("'unsafe-inline'", "'unsafe-eval'", "*", "http:", "https:"), name
            assert v != "data:" or allowed_data, name


def test_tc_prv_08_3_header_on_every_response(household):
    who = household.enrol()
    anon = household.client()
    member = household.sign_in(who)
    responses = [
        anon.get("/health"), anon.get("/signin"), anon.get("/static/style.css"), anon.get("/no-such-page"),
        anon.get("/api/visits"), anon.get("/", follow_redirects=False),
        member.get("/"), member.get("/api/visits"), member.get("/api/uploads/upl_missing"),
    ]
    for r in responses:
        assert r.headers["content-security-policy"] == security.CSP, r.url
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["referrer-policy"] == "same-origin"
    assert member.get("/").headers["cache-control"] == "no-store"
    assert "no-store" not in anon.get("/static/style.css").headers.get("cache-control", "")


def test_tc_prv_08_1_pages_reference_no_third_party_resources():
    """No external URLs, no inline scripts and no inline styles in the application tier's pages and assets."""
    files = (list((HOUSEHOLD / "templates").glob("*.html")) + list((HOUSEHOLD.parent / "templates").glob("*.html"))
             + [STATIC / "style.css", STATIC / "app.js", STATIC / "landing.css", STATIC / "landing.js"])
    for path in files:
        text = path.read_text()
        for url in OUTBOUND_LINKS:
            text = text.replace(f'<a class="linkedin" href="{url}" rel="noopener noreferrer">', "")
        assert not re.search(r"https?://", text), path
        assert not re.search(r"<script(?![^>]*\bsrc=\"/static/)", text), path  # only own script files, if any
        assert not re.search(r"\sstyle=", text), path
        assert not re.search(r"\son[a-z]+=", text), path  # no inline event handlers
        assert "@import" not in text and "eval(" not in text, path


def test_served_pages_load_only_same_origin_assets(household):
    who = household.enrol()
    member = household.sign_in(who)
    html = "".join(member.get(p).text for p in ("/", "/visits", "/providers", "/import", "/settings", "/help", "/accuracy", "/uploads"))
    html += household.client().get("/signin").text + household.client().get("/").text
    for url in re.findall(r'(?:src|href)="([^"]+)"', html):
        assert url.startswith(("/", "#", "?")) and not url.startswith("//") or url in OUTBOUND_LINKS, url
