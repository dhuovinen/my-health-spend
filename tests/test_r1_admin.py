"""The owner's admin screen and the optional authenticator code (PLT-09, ADR-049): TC-PLT-09-1 to 3."""

import pyotp
import pytest

from mhs.web.household.admin import main as admin_main
from mhs.web.household.auth import AccountError
from mhs.web.household.features import Features
from tests.conftest import csrf_from
from tests.test_r1_social import back_from_provider, link, next_code, sign_in_again


def make_owner(household, who):
    household.accounts.set_owner(who.email, True)


def events(app_db, member_id=None, prefix=""):
    with app_db.tx() as c:
        rows = c.execute("SELECT event, member_id FROM app.security_log WHERE event LIKE %s ORDER BY id",
                         (prefix + "%",)).fetchall()
    return [r["event"] for r in rows if member_id is None or str(r["member_id"]) == member_id]


def sign_in_with_password(household, who):
    c = household.client()
    r = c.post("/signin", data={"email": who.email, "password": who.password}, follow_redirects=False)
    return c, r


def turn_code_off(household, owner_client, owner):
    page = owner_client.get("/admin").text
    return owner_client.post("/admin/require-code", data={"state": "off", "code": next_code(household, owner),
                                                          "csrf_token": csrf_from(page)}, follow_redirects=False)


def turn_code_on(owner_client):
    return owner_client.post("/admin/require-code", data={"state": "on", "csrf_token": csrf_from(
        owner_client.get("/admin").text)}, follow_redirects=False)


@pytest.mark.postgres
def test_tc_plt_09_1_only_an_owner_reaches_the_admin_screen(household):
    member, owner = household.enrol(), household.enrol()
    make_owner(household, owner)
    assert household.client().get("/admin", follow_redirects=False).headers["location"] == "/signin"
    m = household.sign_in(member)
    assert m.get("/admin").status_code == 404
    assert m.post("/admin/require-code", data={"state": "off", "csrf_token": household.csrf(m)}).status_code == 404
    assert 'href="/admin"' not in m.get("/account").text
    o = household.sign_in(owner)
    assert o.get("/admin").status_code == 200
    assert 'href="/admin"' in o.get("/account").text


@pytest.mark.postgres
def test_an_owner_always_enters_the_code_and_the_role_ends_their_sessions(household, app_db):
    owner = household.enrol()
    o = household.sign_in(owner)
    make_owner(household, owner)
    assert o.get("/api/visits").status_code == 401  # the role change signed them out
    o = sign_in_again(household, owner)
    assert turn_code_off(household, o, owner).status_code == 303
    c, r = sign_in_with_password(household, owner)
    assert r.headers["location"] == "/signin/mfa"  # the code is off for members, not owners
    assert c.get("/api/visits").status_code == 401
    with pytest.raises(AccountError):
        household.accounts.start_session(household.accounts.check_password(owner.email, owner.password),
                                         without_code=True)


@pytest.mark.postgres
def test_tc_plt_09_2_turning_the_code_off_and_on(household, app_db):
    member, owner = household.enrol(), household.enrol()
    make_owner(household, owner)
    m_before = household.sign_in(member)
    o = household.sign_in(owner)

    # off: needs the owner's current code
    page = o.get("/admin").text
    assert "Required" in page and "stolen password" in page
    wrong = o.post("/admin/require-code", data={"state": "off", "code": "000000", "csrf_token": csrf_from(page)})
    assert wrong.status_code == 401 and Features(app_db).require_code()
    assert turn_code_off(household, o, owner).headers["location"] == "/admin"
    assert not Features(app_db).require_code()

    # a member signs in without a code; a sign-in already waiting for one goes through too
    c, r = sign_in_with_password(household, member)
    assert r.headers["location"] == "/"
    assert c.get("/api/visits").status_code == 200
    assert m_before.get("/api/visits").status_code == 200  # sessions that did enter a code stay

    # on: sessions without a code end; those with one stay
    assert turn_code_on(o).headers["location"] == "/admin"
    assert c.get("/api/visits").status_code == 401
    assert m_before.get("/api/visits").status_code == 200
    assert o.get("/admin").status_code == 200
    c, r = sign_in_with_password(household, member)
    assert r.headers["location"] == "/signin/mfa"
    page = c.get("/signin/mfa").text
    assert "Verification code" in page and "<svg" not in page  # confirmed before, so no setup: just the code

    # logged, with who
    assert events(app_db, owner.member_id, "setting_") == ["setting_require_code_off", "setting_require_code_on"]
    changes = o.get("/admin").text
    assert "require code off" in changes and "Test Member" in changes


@pytest.mark.postgres
def test_a_waiting_sign_in_goes_through_when_the_code_is_turned_off(household, app_db):
    member = household.enrol()
    c, r = sign_in_with_password(household, member)
    assert r.headers["location"] == "/signin/mfa"
    Features(app_db).set("require_code", False)
    r = c.get("/signin/mfa", follow_redirects=False)
    assert r.headers["location"] == "/"
    assert c.get("/api/visits").status_code == 200


@pytest.mark.postgres
def test_a_member_who_never_set_up_an_authenticator_is_taken_through_it(household, app_db):
    member, fresh = household.enrol(), household.enrol()
    features = Features(app_db)
    features.set("require_code", False)
    c, _ = sign_in_with_password(household, member)  # never entered a code
    assert c.get("/api/visits").status_code == 200
    features.set("require_code", True)

    c, r = sign_in_with_password(household, member)
    page = c.get("/signin/mfa").text
    assert "<svg" in page and "Add this account" in page  # shown the authenticator to set up
    assert c.get("/api/visits").status_code == 401  # and nothing else until a code from it
    key = page.split('class="enrol-key">')[1].split("<")[0].replace(" ", "")
    assert key == member.totp_secret
    r = c.post("/signin/mfa", data={"code": pyotp.TOTP(key).now(), "csrf_token": csrf_from(page)},
               follow_redirects=False)
    assert r.headers["location"] == "/" and c.get("/api/visits").status_code == 200
    # once confirmed, the next sign-in only asks for the code
    c, _ = sign_in_with_password(household, member)
    assert "<svg" not in c.get("/signin/mfa").text

    # a member added but never signed in isn't shown it after a password: they have the enrolment link
    c, _ = sign_in_with_password(household, fresh)
    assert "<svg" not in c.get("/signin/mfa").text


@pytest.mark.postgres
def test_tc_plt_09_3_the_admin_screen_shows_no_household_data(household):
    from tests.test_web import CsrfClient, ReleaseOne
    from tests.test_ux import import_household

    owner = household.enrol("The Sample family")
    make_owner(household, owner)
    o = household.sign_in(owner)
    r1 = ReleaseOne.__new__(ReleaseOne)
    r1.client = CsrfClient(o, household.csrf(o))
    import_household(r1)
    page = o.get("/admin").text
    visits = o.get("/api/visits").json()
    assert visits
    for visit in visits:
        for value in (visit.get("id"), visit.get("provider_id"), visit.get("date_of_service")):
            assert not value or str(value) not in page
    assert "The Sample family" not in page and owner.email not in page
    assert "Households" in page and "Members" in page


@pytest.mark.postgres
def test_members_can_still_make_recovery_codes_and_delete_without_a_code(household, app_db):
    member, other = household.enrol(), household.enrol()
    Features(app_db).set("require_code", False)
    c, _ = sign_in_with_password(household, member)
    page = c.get("/account").text
    assert 'name="password"' in page and 'name="code"' not in page
    r = c.post("/account/recovery-codes", data={"password": member.password, "csrf_token": csrf_from(page)})
    assert r.status_code == 200 and "new recovery codes" in r.text
    data = c.get("/data").text
    assert 'name="code"' not in data.split('action="/data/delete"')[1].split("</form>")[0]
    r = c.post("/data/delete", data={"password": member.password, "confirm": "DELETE",
                                     "csrf_token": csrf_from(data)})
    assert r.status_code == 200
    # with the code on, deleting still needs it
    Features(app_db).set("require_code", True)
    o = household.sign_in(other)
    r = o.post("/data/delete", data={"password": other.password, "confirm": "DELETE", "code": "000000",
                                     "csrf_token": household.csrf(o)})
    assert r.status_code == 401


@pytest.mark.postgres
def test_social_sign_in_follows_the_toggles(make_household, app_db):
    from tests.fake_oidc import FakeProvider

    fake = FakeProvider()
    try:
        social = make_household(sign_in_providers=(fake.as_provider(),), public_url="http://testserver")
        member, owner = social.enrol(), social.enrol()
        make_owner(social, owner)
        link(social.sign_in(member))
        o = social.sign_in(owner)

        # provider off: no button, no sign-in, no linking; back on, the link still works
        page = o.get("/admin").text
        assert "Google: on" in page and "Microsoft: not set up" in page
        o.post("/admin/providers/google", data={"state": "off", "csrf_token": csrf_from(page)})
        assert "Continue with Google" not in social.client().get("/signin").text
        assert social.client().get("/signin/with/google").status_code == 404
        assert "Sign-in accounts" not in o.get("/account").text
        assert o.post("/admin/providers/microsoft", data={"state": "off", "csrf_token": csrf_from(page)},
                      ).status_code == 404  # not configured
        o.post("/admin/providers/google", data={"state": "on", "csrf_token": csrf_from(page)})
        assert events(app_db, owner.member_id, "setting_") == ["setting_signin_google_off", "setting_signin_google_on"]

        # code off: the provider alone signs a member in, through a link to Home (the cookie is Strict)
        turn_code_off(social, o, owner)
        c = social.client()
        _, r = back_from_provider(c)
        assert r.status_code == 200 and 'href="/"' in r.text and "Verification code" not in r.text
        assert c.get("/api/visits").status_code == 200
        assert "You'll still enter your authenticator code" not in social.client().get("/signin").text
    finally:
        fake.stop()


@pytest.mark.postgres
def test_mhs_admin_owner_and_require_code(household, app_db, monkeypatch, capsys):
    import mhs.web.household.admin as admin

    who = household.enrol()
    monkeypatch.setattr(admin, "accounts_from_env", lambda: (_NoClose(app_db), household.accounts))
    admin_main(["owner", "--email", who.email, "on"])
    assert "is an owner" in capsys.readouterr().out and household.accounts.is_owner(who.email)
    admin_main(["require-code", "off"])
    assert "OFF" in capsys.readouterr().out and not Features(app_db).require_code()
    admin_main(["require-code", "on"])
    assert "required" in capsys.readouterr().out
    assert events(app_db, prefix="setting_")[-2:] == ["setting_require_code_off", "setting_require_code_on"]
    with pytest.raises(SystemExit):
        admin_main(["owner", "--email", "nobody@example.test", "status"])


class _NoClose:
    """The test database, kept open when mhs-admin closes its connection."""

    def __init__(self, db):
        self.db = db

    def __getattr__(self, name):
        return getattr(self.db, name)

    def close(self):
        pass
