"""Social sign-in (PRV-12, ADR-048): TC-PRV-12-1 to 4 and 6. TC-PRV-12-5 is in test_ux_layout.py, in a real browser."""

import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from mhs.stack import SignInProvider, sign_in_providers
from mhs.web.household import oidc
from tests.conftest import csrf_from
from tests.fake_oidc import CLIENT_ID, ISSUER, FakeProvider

PROVIDER = SignInProvider("google", "Google", CLIENT_ID, "x", "https://a", "https://t", r"https://issuer\.example\.test")
GOOD = {"iss": ISSUER, "aud": CLIENT_ID, "sub": "s", "nonce": "n", "exp": 2_000_000_000, "email": "e@example.test"}


# --- token checks and configuration, no database ---

def test_good_claims_give_the_identity():
    assert oidc.check_claims(GOOD, PROVIDER, "n", now=1_000) == oidc.Identity("s", "e@example.test")
    assert oidc.check_claims({**GOOD, "email": None}, PROVIDER, "n", now=1_000).email == ""


@pytest.mark.parametrize("change", [
    {"iss": "https://evil.example.test"}, {"iss": ISSUER + ".evil.test"}, {"iss": None}, {"aud": "another-client"},
    {"aud": [CLIENT_ID, "another"]}, {"exp": 500}, {"exp": None}, {"nonce": "other"}, {"nonce": None}, {"sub": ""},
    {"sub": None},
])
def test_tc_prv_12_3_bad_claims_are_refused(change):
    with pytest.raises(oidc.OidcError):
        oidc.check_claims({**GOOD, **change}, PROVIDER, "n", now=1_000)


def test_real_issuers_match_only_their_own_provider(monkeypatch):
    for name in ("GOOGLE", "MICROSOFT"):
        monkeypatch.setenv(f"MHS_{name}_CLIENT_ID", "id")
        monkeypatch.setenv(f"MHS_{name}_CLIENT_SECRET", "secret")
    google, microsoft = sign_in_providers()
    claims = {**GOOD, "aud": "id"}
    assert oidc.check_claims({**claims, "iss": "https://accounts.google.com"}, google, "n", now=1)
    assert oidc.check_claims({**claims, "iss": "accounts.google.com"}, google, "n", now=1)
    tenant = "https://login.microsoftonline.com/9188040d-6c67-4c5b-b112-36a304b66dad/v2.0"
    assert oidc.check_claims({**claims, "iss": tenant}, microsoft, "n", now=1)
    for provider, issuer in ((google, tenant), (microsoft, "https://accounts.google.com"),
                             (google, "https://accounts.google.com.evil.test")):
        with pytest.raises(oidc.OidcError):
            oidc.check_claims({**claims, "iss": issuer}, provider, "n", now=1)


def test_a_provider_without_a_client_stays_off(monkeypatch):
    for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "MICROSOFT_CLIENT_ID", "MICROSOFT_CLIENT_SECRET"):
        monkeypatch.delenv(f"MHS_{name}", raising=False)
    monkeypatch.setenv("MHS_GOOGLE_CLIENT_ID", "id-without-secret")
    assert sign_in_providers() == ()


# --- the flow ---

@pytest.fixture
def provider():
    fake = FakeProvider()
    yield fake
    fake.stop()


@pytest.fixture
def social(make_household, provider):
    return make_household(sign_in_providers=(provider.as_provider(),), public_url="http://testserver")


def back_from_provider(client, path="/signin/with/google"):
    """Follow the browser's round trip by hand: to the provider, and back to the callback."""
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303, r.text
    assert "openid email" == parse_qs(urlsplit(r.headers["location"]).query)["scope"][0]
    back = httpx.get(r.headers["location"]).headers["location"]
    return back, client.get(back, follow_redirects=False)


def next_code(household, who) -> str:
    """A code can't be used twice in its 30 seconds, so a test that signs in twice forgets the last one it used."""
    with household.accounts.db.tx() as c:
        c.execute("UPDATE app.members SET totp_last_step = 0 WHERE id = %s", (who.member_id,))
    return who.code()


def sign_in_again(household, who):
    next_code(household, who)
    return household.sign_in(who)


def link(client):
    return back_from_provider(client, "/account/link/google")[1]


@pytest.mark.postgres
def test_tc_prv_12_1_linked_account_still_needs_the_code(social):
    who = social.enrol()
    assert link(social.sign_in(who)).status_code == 200
    c = social.client()
    _, r = back_from_provider(c)
    assert r.status_code == 200 and "Verification code" in r.text
    assert c.get("/visits", follow_redirects=False).headers["location"] == "/signin/mfa"  # no data before the code
    assert c.get("/api/visits").status_code == 401
    wrong = c.post("/signin/mfa", data={"code": "000000", "csrf_token": csrf_from(r.text)}, follow_redirects=False)
    assert wrong.status_code == 401
    done = c.post("/signin/mfa", data={"code": next_code(social, who), "csrf_token": csrf_from(r.text)}, follow_redirects=False)
    assert done.headers["location"] == "/"
    assert c.get("/api/visits").status_code == 200


@pytest.mark.postgres
def test_tc_prv_12_2_unlinked_account_gets_nothing_even_with_a_members_email(social, provider, app_db):
    who = social.enrol()
    provider.email = who.email  # the same address as a member: must not match
    c = social.client()
    _, matching = back_from_provider(c)
    provider.email = "nobody@example.test"
    _, other = back_from_provider(social.client())
    assert matching.status_code == other.status_code == 401
    assert matching.text == other.text  # doesn't say whether the email is a member's
    assert "mhs_session" not in c.cookies
    assert c.get("/api/visits").status_code == 401
    with app_db.tx() as tx:
        assert tx.execute("SELECT count(*) AS n FROM app.members").fetchone()["n"] == 1
        assert tx.execute("SELECT count(*) AS n FROM app.member_identities").fetchone()["n"] == 0


@pytest.mark.postgres
def test_tc_prv_12_3_tampered_callbacks_start_no_session(social, provider):
    who = social.enrol()
    link(social.sign_in(who))

    def assert_refused(client, url):
        r = client.get(url, follow_redirects=False)
        assert r.status_code == 400 and "not completed" in r.text
        assert "mhs_session" not in client.cookies

    c = social.client()  # wrong state
    leaving = c.get("/signin/with/google", follow_redirects=False)
    back = httpx.get(leaving.headers["location"]).headers["location"]
    assert_refused(c, back.replace("state=", "state=x"))
    c = social.client()  # no flow cookie at all: someone else's callback link
    r = social.client().get("/signin/with/google", follow_redirects=False)
    assert_refused(c, httpx.get(r.headers["location"]).headers["location"])
    c = social.client()  # the flow is used up on the first try, for the same browser too
    back, first = back_from_provider(c)
    assert first.status_code == 200
    r = c.get(back, follow_redirects=False)
    assert r.status_code == 400 and "not completed" in r.text
    c = social.client()  # the member said no at the provider
    provider.deny = True
    _, r = back_from_provider(c)
    assert r.status_code == 400 and "mhs_session" not in c.cookies
    provider.deny = False
    for bad in ({"iss": "https://evil.example.test"}, {"aud": "other"}, {"nonce": "other"}, {"exp": time.time() - 5}):
        provider.overrides = bad
        c = social.client()
        _, r = back_from_provider(c)
        assert r.status_code == 400 and "mhs_session" not in c.cookies, bad
    provider.overrides = {}


@pytest.mark.postgres
def test_tc_prv_12_4_link_and_unlink_on_the_account_page(social, provider):
    who = social.enrol()
    member = social.sign_in(who)
    page = member.get("/account").text
    assert 'href="/account/link/google"' in page and "not linked" in page
    assert social.client().get("/account/link/google", follow_redirects=False).headers["location"] == "/signin"

    r = link(member)
    assert r.status_code == 200 and "is linked" in r.text and 'href="/account"' in r.text
    page = member.get("/account").text
    assert "person@example.test" in page and "/account/identities/google/unlink" in page

    provider.email = "changed@example.test"  # the provider's email changes: same person, same link
    _, r = back_from_provider(social.client())
    assert r.status_code == 200 and "Verification code" in r.text

    forged = member.post("/account/identities/google/unlink", data={"csrf_token": "wrong"})
    assert forged.status_code == 403
    r = member.post("/account/identities/google/unlink", data={"csrf_token": social.csrf(member)},
                    follow_redirects=False)
    assert r.headers["location"] == "/account"
    _, r = back_from_provider(social.client())
    assert r.status_code == 401  # no longer signs in; the password still does
    assert sign_in_again(social, who)


@pytest.mark.postgres
def test_an_account_links_to_one_member_and_a_member_to_one_per_provider(social, provider):
    first, second = social.enrol(), social.enrol()
    assert link(social.sign_in(first)).status_code == 200
    r = link(social.sign_in(second))  # same provider account as the first member
    assert r.status_code == 409 and "be linked" in r.text
    assert "not linked" in sign_in_again(social, second).get("/account").text
    provider.subject = "subject-2"  # the first member's second Google account
    assert link(sign_in_again(social, first)).status_code == 409


@pytest.mark.postgres
def test_a_link_flow_is_bound_to_the_member_who_started_it(social, provider):
    """Finishing a stale link doesn't sign anyone in, and using its state twice doesn't link twice."""
    who = social.enrol()
    member = social.sign_in(who)
    back, r = back_from_provider(member, "/account/link/google")
    assert r.status_code == 200
    assert member.get(back, follow_redirects=False).status_code == 400  # flow cookie gone


@pytest.mark.postgres
def test_a_locked_member_cant_use_the_linked_account(social):
    who = social.enrol()
    link(social.sign_in(who))
    c = social.client()
    for _ in range(5):
        c.post("/signin", data={"email": who.email, "password": "wrong-password-123"})
    _, r = back_from_provider(social.client())
    assert r.status_code == 401


@pytest.mark.postgres
def test_tc_prv_12_6_logs_and_deleting_the_member(social, app_db):
    who, other = social.enrol(), social.enrol("Other", None)
    member = social.sign_in(who)
    link(member)
    back_from_provider(social.client())
    member.post("/account/identities/google/unlink", data={"csrf_token": social.csrf(member)})
    link(member)
    back_from_provider(social.client())
    social.accounts.link_identity(other.member_id, "microsoft", "z", "")
    with app_db.tx() as c:
        events = [r["event"] for r in c.execute("SELECT event FROM app.security_log WHERE member_id = %s ORDER BY id",
                                                (who.member_id,)).fetchall()]
        assert events == ["identity_linked", "social_signin", "identity_unlinked", "identity_linked", "social_signin"]
        c.execute("DELETE FROM app.members WHERE id = %s", (who.member_id,))
        rows = c.execute("SELECT member_id FROM app.member_identities").fetchall()
    assert [str(r["member_id"]) for r in rows] == [other.member_id]


@pytest.mark.postgres
def test_nothing_shows_without_a_provider(household):
    who = household.enrol()
    assert "Continue with" not in household.client().get("/signin").text
    assert "Sign-in accounts" not in household.sign_in(who).get("/account").text
    assert household.client().get("/signin/with/google").status_code == 404


@pytest.mark.postgres
def test_sign_in_page_links_to_the_provider_and_says_what_it_learns(social):
    page = social.client().get("/signin").text
    assert 'href="/signin/with/google"' in page and "sees nothing of your records" in page
    assert "/signin/with/google" not in page.split("<form")[1].split("</form>")[0]  # a link, not a form post


@pytest.mark.postgres
def test_a_non_ascii_state_is_refused_not_a_crash(social):
    c = social.client()
    c.get("/signin/with/google", follow_redirects=False)
    assert c.get("/signin/with/google/callback?code=x&state=%C3%A9", follow_redirects=False).status_code == 400
