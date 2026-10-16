"""End to end on the running compose stack, through the `capture` proxy (TESTING.md "Release 1 test environment").

Runs only in the compose `tests` runner (docker compose --profile test run --rm tests), which sets MHS_STACK_URL.
A member is enrolled straight into the stack's database with the app's own key, then everything else goes
over HTTP the way a browser would.
"""

import json
import os
import re
import secrets
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pyotp
import pytest

pytestmark = pytest.mark.stack

STACK_URL = os.environ.get("MHS_STACK_URL")
MARKER = b"STACK-SYNTHETIC-" + secrets.token_hex(6).encode()


@pytest.fixture(scope="module")
def member():
    if not STACK_URL:
        pytest.skip("stack tests run in the compose tests runner (MHS_STACK_URL)")
    from mhs.web.household.admin import accounts_from_env

    db, accounts = accounts_from_env()
    hid = accounts.create_household(f"Stack test {uuid.uuid4().hex[:6]}")
    password = secrets.token_urlsafe(18)
    m, totp_secret = accounts.add_member(hid, f"stack-{uuid.uuid4().hex[:8]}@example.test", "Stack Tester", password)
    db.close()
    return m, password, totp_secret


@pytest.fixture(scope="module")
def browser(member):
    with httpx.Client(base_url=STACK_URL, proxy=os.environ.get("MHS_STACK_PROXY"), timeout=10,
                      follow_redirects=False) as c:
        yield c


def csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def test_full_session_over_the_stack(member, browser):
    m, password, totp_secret = member
    assert browser.get("/health").json() == {"ok": True}
    r = browser.post("/signin", data={"email": m.email, "password": password})
    assert r.status_code == 303 and r.headers["location"] == "/signin/mfa"
    assert browser.get("/api/uploads").status_code == 401  # TC-PRV-11-1 on the stack
    r = browser.post("/signin/mfa", data={"code": pyotp.TOTP(totp_secret).now(),
                                          "csrf_token": csrf(browser.get("/signin/mfa").text)})
    assert r.status_code == 303 and r.headers["location"] == "/"
    home = browser.get("/uploads")
    assert home.status_code == 200 and "Stack test" in home.text
    assert "script-src 'self'" in home.headers["content-security-policy"]

    r = browser.post("/uploads", files={"file": ("stack.pdf", b"%PDF-1.4 " + MARKER, "application/pdf")},
                     data={"csrf_token": csrf(home.text)})
    doc_id = r.headers["location"].split("uploaded=")[1]
    assert browser.get(f"/uploads/{doc_id}").content == b"%PDF-1.4 " + MARKER

    # Phase 1.2: the sample ingest file imports by upload and every Release 0 page renders for the household.
    sample = Path("/srv/mhs/samples/example-ingest.json")
    preview = browser.post("/import", data={"csrf_token": csrf(home.text)},
                           files={"file": ("example-ingest.json", sample.read_bytes(), "application/json")})
    assert preview.status_code == 200 and "What will change" in preview.text
    token = re.search(r'name="token" value="([^"]+)"', preview.text).group(1)
    r = browser.post("/import/confirm", data={"token": token, "csrf_token": csrf(preview.text)})
    assert r.status_code == 303 and r.headers["location"] == "/import?done=1"
    assert "$80.00" in browser.get("/").text  # at stake in the sample
    for url in ("/visits", "/visits/v-2026-04-02-pcp", "/providers", "/providers/prov-pcp?year=2026", "/import",
                "/settings", "/help", "/settings/export"):
        assert browser.get(url).status_code == 200, url

    # The worker picks up a job from the Postgres queue.
    token = browser.get("/api/session").json()["csrf_token"]
    job = browser.post("/api/jobs/ping", headers={"x-csrf-token": token}).json()["job_id"]
    deadline = time.monotonic() + 30
    while browser.get(f"/api/jobs/{job}").json()["status"] != "done":
        assert time.monotonic() < deadline, "worker didn't finish the ping job"
        time.sleep(0.5)

    r = browser.post("/signout", data={"csrf_token": csrf(browser.get("/").text)})
    assert r.status_code == 303
    assert browser.get("/api/uploads").status_code == 401


def test_originals_volume_holds_only_ciphertext(member):
    root = Path(os.environ["MHS_STACK_OBJECTS_DIR"])
    files = [p for p in root.rglob("*") if p.is_file()]
    assert files, "no originals on the volume"
    assert not any(MARKER in p.read_bytes() for p in files)  # TC-PRV-06-2 on the stack


def test_captured_traffic_stays_first_party(member):
    """TC-PRV-08-1 (partial): every request the session made went to the app, and no response pulled in
    a third-party resource."""
    log = Path(os.environ["MHS_STACK_CAPTURE_LOG"])
    flows = [json.loads(line) for line in log.read_text().splitlines()]
    assert flows, "capture saw no traffic"
    app_host = urlsplit(STACK_URL).hostname
    assert {f["host"] for f in flows} == {app_host}
    for f in flows:
        if f["response_headers"].get("content-type", "").startswith("text/html"):
            assert not re.search(r'(?:src|href)="(?:https?:)?//', f["response_body"]), f["path"]
