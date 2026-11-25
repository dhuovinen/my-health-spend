"""Sign-up with Google or Microsoft (PRV-13, ADR-059): TC-PRV-13-1 to 9. TC-PRV-13-10 is in test_ux_layout.py, in a
real browser."""

import html
import re

import pyotp
import pytest

from mhs.data.records import HouseholdRecords
from mhs.stack import SignInProvider
from mhs.web.household import oidc
from mhs.web.household.consent import NOTICE_VERSION
from mhs.web.household.features import ALLOW_SIGNUP, REQUIRE_CODE, REQUIRE_CONSENT, Features
from mhs.web.household.signup import SIGNUP_COOKIE, TERMS_VERSION
from tests.conftest import admin_sql, csrf_from
from tests.fake_oidc import CLIENT_ID, ISSUER, FakeProvider
from tests.test_r1_social import back_from_provider

MICROSOFT = SignInProvider("microsoft", "Microsoft", CLIENT_ID, "x", "https://a", "https://t", r".*")
GOOGLE = SignInProvider("google", "Google", CLIENT_ID, "x", "https://a", "https://t", r".*")
CLAIMS = {"iss": ISSUER, "aud": CLIENT_ID, "sub": "s", "nonce": "n", "exp": 2_000_000_000, "email": "e@example.test"}
REFUSED = "can't sign in here"  # the PRV-12 answer while sign-up is closed


# --- verified email, no database ---

@pytest.mark.parametrize("provider, extra, verified", [
    (GOOGLE, {"email_verified": True}, True),
    (GOOGLE, {"email_verified": "true"}, True),
    (GOOGLE, {"email_verified": False}, False),
    (GOOGLE, {}, False),
    (MICROSOFT, {"tid": oidc.MICROSOFT_CONSUMERS}, True),
    (MICROSOFT, {"tid": "11111111-2222-3333-4444-555555555555"}, False),  # a work tenant: email not verified
    (MICROSOFT, {"tid": "11111111-2222-3333-4444-555555555555", "xms_edov": True}, True),
    (MICROSOFT, {"email_verified": True}, False),  # Microsoft doesn't send it; it mustn't count if it appears
    (GOOGLE, {"email_verified": True, "email": ""}, False),
])
def test_tc_prv_13_4_only_a_verified_email_counts(provider, extra, verified):
    assert oidc.check_claims({**CLAIMS, **extra}, provider, "n", now=1).email_verified is verified


# --- the flow ---

@pytest.fixture
def provider():
    fake = FakeProvider()
    yield fake
    fake.stop()


def two_providers(provider):
    return provider.as_provider(), provider.as_provider("microsoft", "Microsoft")


@pytest.fixture
def closed(make_household, provider):
    """Google and Microsoft set up; sign-up as it starts, closed."""
    return make_household(sign_in_providers=two_providers(provider), public_url="http://testserver")


@pytest.fixture
def site(closed, app_db):
    """Sign-up opened the way the owner would: consent required first."""
    features = Features(app_db)
    features.set(REQUIRE_CONSENT, True)
    features.set(ALLOW_SIGNUP, True)
    return closed


def text(response) -> str:
    return html.unescape(response.text)


def come_back(client, name="google"):
    return back_from_provider(client, f"/signin/with/{name}")[1]


def form_token(html: str) -> str:
    return re.search(r'name="form_token" value="([^"]+)"', html).group(1)


def create(client, html: str, name="Pat Doe", agree=True, token=None):
    data = {"name": name, "form_token": token or form_token(html)}
    if agree:
        data["agree"] = "on"
    return client.post("/signup", data=data, follow_redirects=False)


def count(app_db, table: str) -> int:
    with app_db.tx() as c:
        return c.execute(f"SELECT count(*) AS n FROM app.{table}").fetchone()["n"]


def member_row(app_db, email="person@example.test") -> dict:
    with app_db.tx() as c:
        return c.execute("SELECT m.*, h.name AS household FROM app.members m JOIN app.households h "
                         "ON h.id = m.household_id WHERE m.email = %s", (email,)).fetchone()


def enrolment_key(html: str) -> str:
    return html.split('class="enrol-key">')[1].split("<")[0].replace(" ", "")


def fresh_code(app_db, key: str, email="person@example.test") -> str:
    """A code can't be used twice in its 30 seconds; forget the last one used."""
    with app_db.tx() as c:
        c.execute("UPDATE app.members SET totp_last_step = 0 WHERE email = %s", (email,))
    return pyotp.TOTP(key).now()


def sign_up(site, app_db, name="Pat Doe"):
    """Sign up through the fake provider and enter the first code. Returns the client and the authenticator key."""
    c = site.client()
    r = create(c, come_back(c).text, name)
    assert r.headers["location"] == "/signin/mfa", r.text
    page = c.get("/signin/mfa").text
    key = enrolment_key(page)
    r = c.post("/signin/mfa", data={"code": fresh_code(app_db, key, member_row_email(app_db, name)),
                                    "csrf_token": csrf_from(page)}, follow_redirects=False)
    assert r.status_code == 200 and "Recovery codes" in text(r), r.text
    return c, key


def member_row_email(app_db, name: str) -> str:
    with app_db.tx() as c:
        return c.execute("SELECT email FROM app.members WHERE display_name = %s", (name,)).fetchone()["email"]


@pytest.mark.postgres
def test_tc_prv_13_1_a_new_google_account_signs_up(site, app_db):
    c = site.client()
    r = come_back(c)
    assert r.status_code == 200 and "Create your account" in text(r) and "person@example.test" in text(r)
    assert 'href="/terms"' in text(r) and 'href="/privacy-notice"' in text(r)
    assert count(app_db, "members") == 0 and count(app_db, "households") == 0  # nothing until "Create account"
    assert SIGNUP_COOKIE in c.cookies and "mhs_session" not in c.cookies

    r = create(c, r.text, "  Pat   Doe ")
    assert r.status_code == 303 and r.headers["location"] == "/signin/mfa"
    row = member_row(app_db)
    assert row["display_name"] == "Pat Doe" and row["household"] == "Pat Doe's household"
    assert row["password_hash"] is None and row["signed_up_with"] == "google" and not row["is_owner"]
    assert (row["terms_version"], row["privacy_version"]) == (TERMS_VERSION, NOTICE_VERSION)
    assert row["terms_accepted_at"] is not None
    with app_db.tx() as tx:
        linked = tx.execute("SELECT provider, subject, member_id FROM app.member_identities").fetchall()
    assert [(i["provider"], i["subject"], i["member_id"]) for i in linked] == [("google", "subject-1", row["id"])]

    assert c.get("/api/visits").status_code == 401  # no data before the code
    page = c.get("/signin/mfa").text
    assert "Add this account" in page  # the authenticator to set up, right after sign-up
    wrong = c.post("/signin/mfa", data={"code": "000000", "csrf_token": csrf_from(page)}, follow_redirects=False)
    assert wrong.status_code == 401
    key = enrolment_key(page)
    r = c.post("/signin/mfa", data={"code": fresh_code(app_db, key), "csrf_token": csrf_from(page)},
               follow_redirects=False)
    assert r.status_code == 200 and "You're all set" in text(r)
    assert len(re.findall(r"<li><code>", r.text)) == 10  # recovery codes, once
    assert site.accounts.recovery_codes_left(str(row["id"])) == 10
    assert c.get("/api/visits").status_code == 200
    assert "Pat Doe" in c.get("/").text

    again = site.client()  # next time: the code only, nothing to set up
    _, r = back_from_provider(again)
    assert r.status_code == 200 and "Verification code" in text(r) and "Add this account" not in text(r)
    with app_db.tx() as tx:
        events = [e["event"] for e in tx.execute("SELECT event FROM app.security_log WHERE member_id = %s ORDER BY id",
                                                 (row["id"],)).fetchall()]
    assert events == ["signup", "social_signin"]


@pytest.mark.postgres
def test_tc_prv_13_2_closed_sign_up_answers_as_before(closed, provider, app_db):
    c = closed.client()
    r = come_back(c)
    assert r.status_code == 401 and REFUSED in text(r) and "Create your account" not in text(r)
    assert count(app_db, "members") == 0 and count(app_db, "pending_signups") == 0
    assert SIGNUP_COOKIE not in c.cookies
    assert closed.client().get("/signup").status_code == 404
    assert closed.client().post("/signup", data={"name": "x", "agree": "on", "form_token": "x"}).status_code == 400


@pytest.mark.postgres
def test_tc_prv_13_3_an_email_that_is_already_a_member(site, provider, app_db):
    who = site.enrol()
    provider.email = who.email
    r = come_back(site.client())
    assert r.status_code == 409 and f"There's already an account for {who.email}" in text(r)
    assert count(app_db, "members") == 1 and count(app_db, "member_identities") == 0
    assert count(app_db, "pending_signups") == 0
    # case doesn't help either
    provider.email = who.email.upper()
    assert come_back(site.client()).status_code == 409


@pytest.mark.postgres
def test_a_linked_account_signs_in_and_is_never_offered_sign_up(site, provider, app_db):
    who = site.enrol()
    member = site.sign_in(who)
    back_from_provider(member, "/account/link/google")
    _, r = back_from_provider(site.client())
    assert "Verification code" in text(r) and "Create your account" not in text(r)
    for _ in range(5):  # locked: still not a new person
        site.client().post("/signin", data={"email": who.email, "password": "wrong-password-123"})
    r = come_back(site.client())
    assert r.status_code == 401 and "Create your account" not in text(r)
    assert count(app_db, "members") == 1


@pytest.mark.postgres
def test_tc_prv_13_4_unverified_emails_and_apple_cant_sign_up(site, provider, app_db, make_household):
    provider.overrides = {"email_verified": False}
    r = come_back(site.client())
    assert r.status_code == 401 and "didn't confirm an email address" in text(r)
    provider.overrides = {}
    r = come_back(site.client(), "microsoft")  # a work account: Microsoft doesn't vouch for its email
    assert r.status_code == 401 and "Microsoft didn't confirm" in text(r)
    provider.overrides = {"tid": oidc.MICROSOFT_CONSUMERS}
    assert "Create your account" in come_back(site.client(), "microsoft").text
    provider.overrides = {"xms_edov": True}
    assert "Create your account" in come_back(site.client(), "microsoft").text
    provider.overrides = {}

    other = FakeProvider()
    try:
        with_apple = make_household(sign_in_providers=(provider.as_provider(), other.as_apple()),
                                    public_url="http://testserver")
        _, r = back_from_provider(with_apple.client(), "/signin/with/apple", scope="")
        assert r.status_code == 401 and "Signing up with Apple isn't available yet" in text(r)
    finally:
        other.stop()
    assert count(app_db, "members") == 0


@pytest.mark.postgres
def test_tc_prv_13_5_create_account_refusals(site, provider, app_db):
    c = site.client()
    page = come_back(c).text
    r = create(c, page, agree=False)
    assert r.status_code == 400 and "Tick the box" in text(r) and 'value="Pat Doe"' in text(r)
    r = create(c, page, name="   ")
    assert r.status_code == 400 and "Enter your name (up to 80 characters)" in text(r)
    r = create(c, page, name="x" * 81)
    assert r.status_code == 400 and "up to 80 characters" in text(r)
    assert count(app_db, "members") == 0 and count(app_db, "households") == 0
    assert create(c, page).status_code == 303  # the same pending sign-up still works after those
    assert count(app_db, "members") == 1

    assert "Verification code" in come_back(site.client()).text  # the same account again: linked, so it signs in

    provider.subject, provider.email = "subject-2", "second@example.test"
    c = site.client()
    page = come_back(c).text
    stranger = site.client()  # the form token without the cookie: someone else's sign-up
    r = create(stranger, page)
    assert r.status_code == 400 and "expired" in text(r)
    assert create(c, page, token="wrong-token").status_code == 400  # the cookie without the form token
    assert count(app_db, "members") == 1


@pytest.mark.postgres
def test_a_pending_sign_up_is_used_once(site, app_db):
    c = site.client()
    page = come_back(c).text
    token = c.cookies[SIGNUP_COOKIE]
    assert create(c, page).status_code == 303
    assert SIGNUP_COOKIE not in c.cookies
    replay = site.client()
    replay.cookies.set(SIGNUP_COOKIE, token, path="/signup")
    assert create(replay, page).status_code == 400
    assert count(app_db, "members") == 1 and count(app_db, "households") == 1


@pytest.mark.postgres
def test_an_expired_or_closed_sign_up_creates_nothing(site, provider, app_db, pgdb):
    c = site.client()
    page = come_back(c).text
    admin_sql(pgdb, "UPDATE app.pending_signups SET expires_at = now() - interval '1 second'")
    r = create(c, page)
    assert r.status_code == 400 and "expired" in text(r)
    assert c.get("/signup").status_code == 404

    provider.subject = "subject-2"
    c = site.client()
    page = come_back(c).text
    Features(app_db).set(ALLOW_SIGNUP, False)  # the owner closes sign-up meanwhile
    assert create(c, page).status_code == 400
    Features(app_db).set(ALLOW_SIGNUP, True)
    Features(app_db).set("signin_google", False)  # or turns the provider off
    assert c.get("/signup").status_code == 404
    assert count(app_db, "members") == 0 and count(app_db, "pending_signups") == 0


@pytest.mark.postgres
def test_two_racing_sign_ups_for_one_email_make_one_account(site, provider, app_db):
    first = site.client()
    first_page = come_back(first).text
    provider.subject = "another-google-account-same-email"
    second = site.client()
    second_page = come_back(second).text
    assert create(first, first_page).status_code == 303
    r = create(second, second_page)
    assert r.status_code == 409 and "already an account" in text(r)
    assert count(app_db, "members") == 1 and count(app_db, "households") == 1
    assert count(app_db, "member_identities") == 1


@pytest.mark.postgres
def test_tc_prv_13_6_a_member_without_a_password(site, app_db):
    c, key = sign_up(site, app_db)
    row = member_row(app_db)
    r = site.client().post("/signin", data={"email": "person@example.test", "password": "a-guess-at-a-password"})
    wrong = site.client().post("/signin", data={"email": "nobody@example.test", "password": "a-guess-at-a-password"})
    assert r.status_code == wrong.status_code == 401 and r.text == wrong.text.replace("nobody@", "person@")
    for _ in range(6):
        site.client().post("/signin", data={"email": "person@example.test", "password": "another-guess-123"})
    assert member_row(app_db)["failed_attempts"] == 0  # nothing to guess, so nobody can lock them out

    account = c.get("/account").text
    assert "Your only way in" in account and "/account/identities/google/unlink" not in account
    assert c.post("/account/identities/google/unlink", data={"csrf_token": site.csrf(c)}).status_code == 409
    assert site.accounts.identities_of(str(row["id"])) == {"google": "person@example.test"}

    data = c.get("/data").text
    assert 'name="password"' not in data and 'name="code"' in data
    assert c.post("/data/export", data={"code": "000000", "csrf_token": site.csrf(c)}).status_code == 401
    r = c.post("/data/export", data={"code": fresh_code(app_db, key), "csrf_token": site.csrf(c)})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    r = c.post("/account/recovery-codes", data={"code": fresh_code(app_db, key), "csrf_token": site.csrf(c)})
    assert r.status_code == 200 and "Your new recovery codes" in text(r)
    r = c.post("/data/delete", data={"code": fresh_code(app_db, key), "confirm": "DELETE",
                                     "csrf_token": site.csrf(c)})
    assert r.status_code == 200 and count(app_db, "members") == 0 and count(app_db, "households") == 0


@pytest.mark.postgres
def test_without_the_code_a_recent_sign_in_confirms(site, app_db):
    Features(app_db).set(REQUIRE_CODE, False)
    c = site.client()
    r = create(c, come_back(c).text)
    assert r.headers["location"] == "/" and c.get("/api/visits").status_code == 200
    data = c.get("/data").text
    assert 'name="password"' not in data and 'name="code"' not in data and "within 10 minutes" in data
    assert c.post("/data/export", data={"csrf_token": site.csrf(c)}).status_code == 200
    with app_db.tx() as tx:
        tx.execute("UPDATE app.sessions SET created_at = now() - interval '11 minutes'")
    r = c.post("/data/export", data={"csrf_token": site.csrf(c)})
    assert r.status_code == 401 and "sign out and sign in again" in text(r)


@pytest.mark.postgres
def test_recovery_gives_a_signed_up_member_a_password(site, app_db):
    sign_up(site, app_db)
    codes = site.accounts.new_recovery_codes("person@example.test")
    r = site.client().post("/recover", data={"email": "person@example.test", "code": codes[0]})
    token = re.search(r'action="/recover/([^"]+)"', r.text).group(1)
    password = "a-new-long-password-123"
    r = site.client().post(f"/recover/{token}", data={"password": password, "password2": password})
    assert r.status_code == 200 and "enrol-key" in text(r)
    assert member_row(app_db)["password_hash"] is not None
    assert site.accounts.check_password("person@example.test", password) is not None


# --- the owner's switch (TC-PRV-13-7) ---

@pytest.mark.postgres
def test_tc_prv_13_7_the_owner_opens_sign_up_only_with_consent_required(closed, app_db):
    owner = closed.enrol()
    closed.accounts.set_owner(owner.email, True)
    o = closed.sign_in(owner)
    page = o.get("/admin").text
    assert "Sign-up" in page and "Closed" in page and "Signed up themselves" in page

    def post(path, state):
        return o.post(path, data={"state": state, "csrf_token": csrf_from(o.get("/admin").text)},
                      follow_redirects=False)

    r = post("/admin/allow-signup", "on")
    assert r.status_code == 409 and "Require consent before collection first" in text(r)
    assert not Features(app_db).allow_signup()
    assert post("/admin/require-consent", "on").status_code == 303
    assert post("/admin/allow-signup", "on").status_code == 303 and Features(app_db).allow_signup()
    assert "Open" in o.get("/admin").text
    r = post("/admin/require-consent", "off")
    assert r.status_code == 409 and "Close sign-up first" in text(r) and Features(app_db).require_consent()
    assert post("/admin/allow-signup", "off").status_code == 303 and not Features(app_db).allow_signup()
    with app_db.tx() as c:
        events = [e["event"] for e in c.execute("SELECT event FROM app.security_log WHERE event LIKE 'setting%%' "
                                                "AND member_id = %s ORDER BY id", (owner.member_id,)).fetchall()]
    assert events == ["setting_require_consent_on", "setting_allow_signup_on", "setting_allow_signup_off"]


@pytest.mark.postgres
def test_sign_up_needs_a_provider_that_allows_it(household, app_db):
    owner = household.enrol()
    household.accounts.set_owner(owner.email, True)
    o = household.sign_in(owner)
    Features(app_db).set(REQUIRE_CONSENT, True)
    r = o.post("/admin/allow-signup", data={"state": "on", "csrf_token": csrf_from(o.get("/admin").text)})
    assert r.status_code == 409 and "Google or Microsoft sign-in first" in text(r)
    Features(app_db).set(ALLOW_SIGNUP, True)  # even if set some other way, nothing offers it without a provider
    assert "Log in or sign up" not in household.client().get("/signin").text


@pytest.mark.postgres
def test_a_member_cant_open_sign_up(site, app_db):
    who = site.enrol()
    m = site.sign_in(who)
    assert m.post("/admin/allow-signup", data={"state": "off", "csrf_token": site.csrf(m)}).status_code == 404


# --- isolation (TC-PRV-13-8) ---

@pytest.mark.postgres
def test_tc_prv_13_8_signed_up_households_are_kept_apart(site, provider, app_db):
    a, _ = sign_up(site, app_db, "Alex A")
    provider.subject, provider.email = "subject-b", "b@example.test"
    b, _ = sign_up(site, app_db, "Blair B")
    hid_b = str(member_row(app_db, "b@example.test")["household_id"])
    HouseholdRecords(app_db, hid_b).put("visit", {"id": "v-b-1", "date": "2026-11-01"})
    assert [v["id"] for v in b.get("/api/visits").json()] == ["v-b-1"]
    assert a.get("/api/visits").json() == []
    assert a.get("/api/visits/v-b-1").status_code == 404
    assert member_row(app_db)["household_id"] != member_row(app_db, "b@example.test")["household_id"]


# --- the pages (TC-PRV-13-9) ---

@pytest.mark.postgres
def test_tc_prv_13_9_the_sign_in_page_open_and_closed(closed, app_db):
    page = closed.client().get("/signin").text
    assert "<h1>Sign in</h1>" in page and "Log in or sign up" not in page
    assert 'href="/terms"' in page and 'href="/privacy-notice"' in page
    assert "accounts are set up by invitation" in closed.client().get("/").text
    assert ">Sign in</a>" in closed.client().get("/").text

    Features(app_db).set(REQUIRE_CONSENT, True)
    Features(app_db).set(ALLOW_SIGNUP, True)
    page = closed.client().get("/signin").text
    assert "<h1>Log in or sign up</h1>" in page
    assert page.index("Continue with Google") < page.index("Continue with Microsoft") < page.index('action="/signin"')
    assert "By continuing, you agree to the" in page
    assert re.search(r'<a href="/terms">Terms of Service</a>.*<a href="/privacy-notice">Privacy Policy</a>', page)
    assert "/signin/with/google" not in page.split("<form")[1].split("</form>")[0]  # links, not form posts
    landing = closed.client().get("/").text
    assert "Sign in or sign up" in landing and "sign up with your Google or Microsoft account" in landing

    r = closed.client().get("/terms")
    assert r.status_code == 200 and "Terms of Service" in text(r) and TERMS_VERSION in text(r)


@pytest.mark.postgres
def test_a_failed_password_keeps_the_password_form_open(site):
    r = site.client().post("/signin", data={"email": "x@example.test", "password": "wrong-password-123"})
    assert '<details class="password-signin" open>' in text(r)
