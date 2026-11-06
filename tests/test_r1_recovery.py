"""Self-service account recovery (TC-PRV-07-3, ADR-037): recovery codes in place of a lost password and phone."""

import re
import time

import pyotp
import pytest

from mhs.data.household_store import HouseholdStore
from mhs.web.household.auth import MAX_FAILED, RECOVERY_CODES
from tests.conftest import SAMPLE, admin_sql, csrf_from
from tests.test_web import CsrfClient

pytestmark = pytest.mark.postgres
NEW_PASSWORD = "a-new-long-password-42"


def codes_in(html: str) -> list[str]:
    return re.findall(r"<li><code>([A-Z2-7]{5}-[A-Z2-7]{5})</code></li>", html)


def key_in(html: str) -> str:
    return re.search(r'class="enrol-key">([^<]+)<', html).group(1).replace(" ", "")


def enrol(household, who) -> list[str]:
    """Open the member's enrolment link, as a new member does: the QR code and the recovery codes, once."""
    token = household.accounts.create_enrolment_link(who.email)
    page = household.client().post(f"/enrol/{token}")
    assert page.status_code == 200 and "qr-box" in page.text
    codes = codes_in(page.text)
    assert len(codes) == RECOVERY_CODES and len(set(codes)) == RECOVERY_CODES
    return codes


def recover(client, email: str, code: str, password: str = NEW_PASSWORD):
    step1 = client.post("/recover", data={"email": email, "code": code})
    if step1.status_code != 200:
        return step1
    token = re.search(r'action="/recover/([^"]+)"', step1.text).group(1)
    return client.post(f"/recover/{token}", data={"password": password, "password2": password})


def sign_in(household, email: str, password: str, key: str):
    c = household.client()
    r = c.post("/signin", data={"email": email, "password": password}, follow_redirects=False)
    if r.status_code != 303:
        return None
    r = c.post("/signin/mfa", data={"code": pyotp.TOTP(key).now(), "csrf_token": csrf_from(c.get("/signin/mfa").text)},
               follow_redirects=False)
    return c if r.status_code == 303 and r.headers["location"] == "/" else None


def test_tc_prv_07_3_lost_phone_and_password(household, app_db):
    """The member loses both, recovers with a code, and finds all their data and linkage intact."""
    who = household.enrol()
    codes = enrol(household, who)
    raw = household.sign_in(who)
    browser = CsrfClient(raw, household.csrf(raw))
    preview = browser.post("/import", files=[("file", ("i.json", SAMPLE.read_bytes(), "application/json"))])
    browser.post("/import/confirm", data={"token": re.search(r'name="token" value="([^"]+)"', preview.text).group(1)})
    assert len(HouseholdStore(app_db, who.household_id).all("visit")) == 6

    done = recover(household.client(), who.email, codes[3].lower().replace("-", " "))  # any spelling of the code
    assert done.status_code == 200 and "qr-box" in done.text
    new_codes, new_key = codes_in(done.text), key_in(done.text)
    assert len(new_codes) == RECOVERY_CODES and not set(new_codes) & set(codes)
    assert new_key != who.totp_secret

    stale = household.client()
    stale.cookies.set("mhs_session", raw.cookies["mhs_session"])
    assert stale.get("/api/visits").status_code == 401  # old sessions ended
    assert sign_in(household, who.email, who.password, new_key) is None  # the old password is gone
    member = sign_in(household, who.email, NEW_PASSWORD, new_key)
    assert member is not None and len(member.get("/api/visits").json()) == 6  # data and linkage intact


def test_codes_are_single_use_and_replaced(household):
    who = household.enrol()
    codes = enrol(household, who)
    assert recover(household.client(), who.email, codes[0]).status_code == 200
    again = recover(household.client(), who.email, codes[0])
    assert again.status_code == 401 and "already used" in again.text
    assert recover(household.client(), who.email, codes[1]).status_code == 401  # the whole old set was replaced


def test_wrong_codes_lock_the_account_and_unknown_emails_look_the_same(household):
    who = household.enrol()
    codes = enrol(household, who)
    c = household.client()
    wrong = c.post("/recover", data={"email": who.email, "code": "AAAAA-AAAAA"})
    unknown = c.post("/recover", data={"email": "nobody@example.test", "code": "AAAAA-AAAAA"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.text.replace(who.email, "X") == unknown.text.replace("nobody@example.test", "X")
    for _ in range(MAX_FAILED - 1):
        c.post("/recover", data={"email": who.email, "code": "AAAAA-AAAAA"})
    assert c.post("/recover", data={"email": who.email, "code": codes[0]}).status_code == 401  # locked


def test_recovery_and_enrolment_links_stay_apart(household):
    who = household.enrol()
    codes = enrol(household, who)
    step1 = household.client().post("/recover", data={"email": who.email, "code": codes[0]})
    recover_token = re.search(r'action="/recover/([^"]+)"', step1.text).group(1)
    assert household.client().post(f"/enrol/{recover_token}").status_code == 404  # can't show the QR code
    enrol_token = household.accounts.create_enrolment_link(who.email)
    r = household.client().post(f"/recover/{enrol_token}", data={"password": NEW_PASSWORD, "password2": NEW_PASSWORD})
    assert r.status_code == 404  # can't change the password
    assert sign_in(household, who.email, who.password, who.totp_secret) is not None


def test_password_rules_keep_the_recovery_open(household):
    who = household.enrol()
    codes = enrol(household, who)
    c = household.client()
    token = re.search(r'action="/recover/([^"]+)"', c.post("/recover", data={"email": who.email,
                                                                            "code": codes[0]}).text).group(1)
    assert c.post(f"/recover/{token}", data={"password": NEW_PASSWORD, "password2": "different-password-1"}).status_code == 400
    assert c.post(f"/recover/{token}", data={"password": "short", "password2": "short"}).status_code == 400
    done = c.post(f"/recover/{token}", data={"password": NEW_PASSWORD, "password2": NEW_PASSWORD})
    assert done.status_code == 200 and "qr-box" in done.text


def test_a_recovery_link_expires(household, pgdb):
    who = household.enrol()
    codes = enrol(household, who)
    c = household.client()
    token = re.search(r'action="/recover/([^"]+)"', c.post("/recover", data={"email": who.email,
                                                                            "code": codes[0]}).text).group(1)
    admin_sql(pgdb, "UPDATE app.enrolment_links SET expires_at = now() - interval '1 minute' WHERE purpose = 'recover'")
    r = c.post(f"/recover/{token}", data={"password": NEW_PASSWORD, "password2": NEW_PASSWORD})
    assert r.status_code == 404 and "expired" in r.text


def test_account_page_makes_new_codes_after_an_authenticator_code(household):
    who = household.enrol()
    old = enrol(household, who)
    raw = household.sign_in(who)
    member = CsrfClient(raw, household.csrf(raw))
    assert f"<strong>{RECOVERY_CODES}</strong> unused recovery codes" in member.get("/account").text
    assert member.post("/account/recovery-codes", data={"code": "000000"}).status_code == 401
    assert raw.post("/account/recovery-codes", data={"code": pyotp.TOTP(who.totp_secret).now()}).status_code == 403
    # The current step was used at sign-in and can't be replayed; the next one is within the allowed drift.
    page = member.post("/account/recovery-codes", data={"code": pyotp.TOTP(who.totp_secret).at(time.time() + 30)})
    new = codes_in(page.text)
    assert page.status_code == 200 and len(new) == RECOVERY_CODES and not set(new) & set(old)
    assert recover(household.client(), who.email, old[0]).status_code == 401
    assert 'href="/account"' in member.get("/").text


def test_codes_are_stored_only_as_hashes(household, pgdb):
    who = household.enrol()
    codes = enrol(household, who)
    stored = [bytes(r[0]) for r in admin_sql(pgdb, "SELECT code_hash FROM app.recovery_codes WHERE member_id = %s",
                                             (who.member_id,))]
    assert len(stored) == RECOVERY_CODES
    assert not any(c.encode() in s or c.replace("-", "").encode() in s for c in codes for s in stored)
