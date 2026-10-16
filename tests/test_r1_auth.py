"""PRV-11 sign-in with MFA and sessions: TC-PRV-11-1 and TC-PRV-11-3, plus lockout, replay and CSRF."""

import io
import time

import pyotp
import pytest

from mhs.web.household.auth import MAX_FAILED, AccountError
from tests.conftest import admin_sql, csrf_from

pytestmark = pytest.mark.postgres

DATA_ROUTES = [
    "/", "/visits", "/visits/v1", "/providers", "/providers/p1", "/import", "/settings", "/settings/export", "/help",
    "/files/d1", "/uploads", "/uploads/upl_x", "/api/uploads", "/api/visits", "/api/session", "/api/visits/v1",
]
# Every post route of the Release 0 pages, as (path, form data).
PAGE_POSTS = [
    ("/notes", {"provider_id": "prov-pcp", "text": "x"}), ("/notes/n1", {"text": "x"}), ("/notes/n1/delete", {}),
    ("/import", {}), ("/import/confirm", {"token": "t"}), ("/settings/plans", {"plan_name": "X"}),
    ("/settings/plans/p1", {}), ("/settings/plans/p1/limits", {}), ("/settings/plans/p1/limits/0/delete", {}),
    ("/settings/members", {"name": "X"}), ("/settings/accounts", {"name": "X"}), ("/settings/providers/p1", {}),
    ("/settings/relationships/r1", {}),
]


def test_tc_prv_11_1_password_alone_reaches_no_data(household):
    """TC-PRV-11-1: after the password, every data route still needs the second factor."""
    who = household.enrol()
    c = household.client()
    r = c.post("/signin", data={"email": who.email, "password": who.password}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/signin/mfa"
    for path in DATA_ROUTES:
        r = c.get(path, follow_redirects=False)
        if path.startswith("/api/"):
            assert r.status_code == 401, path
        else:
            assert r.status_code == 303 and r.headers["location"] == "/signin/mfa", path
    assert c.post("/api/jobs/ping").status_code == 401
    for path, data in PAGE_POSTS:
        r = c.post(path, data=data, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/signin/mfa", path
    # Wrong code: still nothing.
    r = c.post("/signin/mfa", data={"code": "000000", "csrf_token": csrf_from(c.get("/signin/mfa").text)})
    assert r.status_code == 401
    assert c.get("/api/visits").status_code == 401
    # Right code: in.
    r = c.post("/signin/mfa", data={"code": who.code(), "csrf_token": csrf_from(c.get("/signin/mfa").text)},
               follow_redirects=False)
    assert r.status_code == 303
    assert c.get("/api/visits").json() == []
    assert "No visits yet" in c.get("/").text
    assert "Household" in c.get("/uploads").text


def test_no_session_redirects_to_sign_in(household):
    c = household.client()
    assert c.get("/", follow_redirects=False).headers["location"] == "/signin"
    assert c.get("/api/visits").status_code == 401
    assert c.get("/signin/mfa", follow_redirects=False).headers["location"] == "/signin"


def test_wrong_password_and_unknown_email_look_the_same(household):
    who = household.enrol()
    c = household.client()
    wrong = c.post("/signin", data={"email": who.email, "password": "not-the-password"})
    unknown = c.post("/signin", data={"email": "nobody@example.test", "password": "not-the-password"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.text.replace(who.email, "X") == unknown.text.replace("nobody@example.test", "X")
    assert "mhs_session" not in c.cookies


def test_lockout_after_repeated_failures(household, pgdb):
    who = household.enrol()
    c = household.client()
    for _ in range(MAX_FAILED):
        c.post("/signin", data={"email": who.email, "password": "wrong-password-123"})
    r = c.post("/signin", data={"email": who.email, "password": who.password}, follow_redirects=False)
    assert r.status_code == 401  # right password, but locked
    admin_sql(pgdb, "UPDATE app.members SET locked_until = now() - interval '1 second' WHERE id = %s",
              (who.member_id,))
    r = c.post("/signin", data={"email": who.email, "password": who.password}, follow_redirects=False)
    assert r.status_code == 303  # the lock lifts after LOCK_MINUTES


def test_totp_code_cannot_be_replayed(household):
    who = household.enrol()
    household.sign_in(who)
    c = household.client()
    c.post("/signin", data={"email": who.email, "password": who.password})
    # The code that was just used is refused, and so is the code from the step before it.
    totp = pyotp.TOTP(who.totp_secret)
    for code in (totp.now(), totp.at(int(time.time()) - 30)):
        r = c.post("/signin/mfa", data={"code": code, "csrf_token": csrf_from(c.get("/signin/mfa").text)})
        assert r.status_code == 401


def test_pre_mfa_token_dies_when_mfa_passes(household):
    who = household.enrol()
    c = household.client()
    c.post("/signin", data={"email": who.email, "password": who.password})
    old = c.cookies["mhs_session"]
    c.post("/signin/mfa", data={"code": who.code(), "csrf_token": csrf_from(c.get("/signin/mfa").text)})
    assert c.cookies["mhs_session"] != old
    stale = household.client()
    stale.cookies.set("mhs_session", old)
    assert stale.get("/api/visits").status_code == 401


def test_tc_prv_11_3_sign_out_invalidates_the_session(household):
    who = household.enrol()
    c = household.sign_in(who)
    token = c.cookies["mhs_session"]
    r = c.post("/signout", data={"csrf_token": household.csrf(c)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/signin"
    replay = household.client()
    replay.cookies.set("mhs_session", token)
    assert replay.get("/api/visits").status_code == 401
    assert replay.get("/", follow_redirects=False).headers["location"] == "/signin"


def test_tc_prv_11_3_idle_session_expires(household, pgdb):
    who = household.enrol()
    c = household.sign_in(who)
    assert c.get("/api/visits").status_code == 200
    admin_sql(pgdb, "UPDATE app.sessions SET last_seen_at = now() - interval '16 minutes' WHERE member_id = %s",
              (who.member_id,))
    assert c.get("/api/visits").status_code == 401
    assert admin_sql(pgdb, "SELECT count(*) FROM app.sessions WHERE member_id = %s", (who.member_id,))[0][0] == 0


def test_absolute_session_lifetime(household, pgdb):
    who = household.enrol()
    c = household.sign_in(who)
    admin_sql(pgdb, "UPDATE app.sessions SET created_at = now() - interval '13 hours' WHERE member_id = %s",
              (who.member_id,))
    assert c.get("/api/visits").status_code == 401


def test_session_cookie_flags(household):
    who = household.enrol()
    c = household.client()
    r = c.post("/signin", data={"email": who.email, "password": who.password}, follow_redirects=False)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie


def test_csrf_token_required_on_every_page_post(household):
    who = household.enrol()
    c = household.sign_in(who)
    for path, data in PAGE_POSTS:
        assert c.post(path, data=data).status_code == 403, path
        assert c.post(path, data={**data, "csrf_token": "wrong"}).status_code == 403, path


def test_csrf_token_required_on_posts(household):
    who = household.enrol()
    c = household.sign_in(who)
    files = {"file": ("a.pdf", b"%PDF-1.4 test", "application/pdf")}
    assert c.post("/uploads", files=files, data={"csrf_token": "wrong"}).status_code == 403
    assert c.post("/api/jobs/ping").status_code == 403
    assert c.post("/api/jobs/ping", headers={"x-csrf-token": household.csrf(c)}).status_code == 200
    assert c.post("/signout", data={"csrf_token": "wrong"}).status_code == 403


def test_cross_origin_posts_refused(household):
    who = household.enrol()
    c = household.client()
    r = c.post("/signin", data={"email": who.email, "password": who.password},
               headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    r = c.post("/signin", data={"email": who.email, "password": who.password}, headers={"origin": "null"})
    assert r.status_code == 403  # opaque origin
    r = c.post("/signin", data={"email": who.email, "password": who.password},
               headers={"origin": "http://testserver"}, follow_redirects=False)
    assert r.status_code == 303


def test_member_rules(accounts):
    hid = accounts.create_household("H")
    with pytest.raises(AccountError):
        accounts.add_member(hid, "a@example.test", "A", "short")
    with pytest.raises(AccountError):
        accounts.add_member(hid, "not-an-email", "A", "long-enough-password")
    with pytest.raises(AccountError):
        accounts.add_member("00000000-0000-0000-0000-000000000000", "a@example.test", "A", "long-enough-password")
    accounts.add_member(hid, "A@Example.test", "A", "long-enough-password")
    with pytest.raises(AccountError):
        accounts.add_member(hid, "a@example.TEST", "A", "long-enough-password")  # emails are case-insensitive


def test_reset_mfa_issues_new_secret_and_ends_sessions(household, accounts, pgdb):
    who = household.enrol()
    c = household.sign_in(who)
    new_secret = accounts.reset_mfa(who.email)
    assert new_secret != who.totp_secret
    assert c.get("/api/visits").status_code == 401
    assert accounts.provisioning_uri(who.email, new_secret).startswith("otpauth://totp/")
    with pytest.raises(AccountError):
        accounts.reset_mfa("nobody@example.test")


def test_admin_commands(app_db, app_keys, pgdb, tmp_path, monkeypatch, capsys):
    """mhs-admin as run in the app container: create a household, add a member, reset MFA."""
    from mhs.web.household import admin

    monkeypatch.setenv("MHS_DATABASE_URL", pgdb.url("app"))
    monkeypatch.setenv("MHS_KEY_FILE", str(tmp_path / "keys" / "app.kek"))  # the app_keys fixture's file
    admin.main(["create-household", "Admin test"])
    hid = capsys.readouterr().out.strip()
    monkeypatch.setattr("sys.stdin", io.StringIO("admin-test-password-1\n"))
    admin.main(["add-member", "--household", hid, "--email", "admin@example.test", "--name", "Admin",
                "--password-stdin"])
    out = capsys.readouterr().out
    assert f"added to household {hid}" in out and "otpauth://totp/" in out
    admin.main(["reset-mfa", "--email", "admin@example.test"])
    assert "otpauth://totp/" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="No such member"):
        admin.main(["reset-mfa", "--email", "nobody@example.test"])

