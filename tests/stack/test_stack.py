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

from tests.pdfs import make_pdf
from tests.test_r1_scenarios import EOB, form_values

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

    pdf = make_pdf(MARKER.decode())
    r = browser.post("/uploads", files={"file": ("stack.pdf", pdf, "application/pdf")},
                     data={"csrf_token": csrf(home.text)})
    doc_id = r.headers["location"].split("uploaded=")[1]
    assert browser.get(f"/uploads/{doc_id}").content == pdf

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

    # Phase 1.3: an EOB PDF is read by the worker container, reviewed and confirmed onto a visit.
    upload = browser.post("/uploads", data={"csrf_token": csrf(home.text), "kind": "auto"},
                          files={"file": ("eob.pdf", make_pdf(EOB), "application/pdf")})
    assert upload.status_code == 303, upload.text[:1000]
    upload_id = upload.headers["location"].split("uploaded=")[1]
    deadline = time.monotonic() + 30
    while browser.get(f"/api/uploads/{upload_id}").json()["status"] != "review":
        assert time.monotonic() < deadline, "worker didn't read the upload"
        time.sleep(0.5)
    review = browser.get(f"/uploads/{upload_id}/review")
    assert "tok_" not in review.text  # re-identified for the member
    values = form_values(review.text, f"/uploads/{upload_id}/confirm")
    r = browser.post(f"/uploads/{upload_id}/confirm", data=values)
    assert r.status_code == 303 and r.headers["location"].startswith("/visits/"), r.text[:1000]
    assert "$45.00" in browser.get(r.headers["location"]).text

    r = browser.post("/signout", data={"csrf_token": csrf(browser.get("/").text)})
    assert r.status_code == 303
    assert browser.get("/api/uploads").status_code == 401


AI_HOST = "ai.capture.test"  # the capture proxy answers it with recorded responses (compose `worker-ai`)
SEEDS = ["Pat Example", "W123-456-789", "W123456789", "Jordan Rivera", "555-310-4000", "5553104000"]


@pytest.fixture(scope="module")
def ai_browser(member):
    """A second household, with AI extraction turned on, signed in over the stack."""
    from mhs.web.household.admin import accounts_from_env

    db, accounts = accounts_from_env()
    hid = accounts.create_household(f"Stack AI test {uuid.uuid4().hex[:6]}")
    accounts.set_ai_extraction(hid, True)
    password = secrets.token_urlsafe(18)
    m, totp_secret = accounts.add_member(hid, f"stack-ai-{uuid.uuid4().hex[:8]}@example.test", "AI Tester", password)
    db.close()
    with httpx.Client(base_url=STACK_URL, proxy=os.environ.get("MHS_STACK_PROXY"), timeout=10,
                      follow_redirects=False) as c:
        c.post("/signin", data={"email": m.email, "password": password})
        r = c.post("/signin/mfa", data={"code": pyotp.TOTP(totp_secret).now(),
                                        "csrf_token": csrf(c.get("/signin/mfa").text)})
        assert r.status_code == 303 and r.headers["location"] == "/"
        yield c


def test_photo_read_by_ocr_scrubbed_and_extracted_by_ai(ai_browser):
    """Phase 1.3 engines on the stack: a photo of an EOB is read by Tesseract in the app, scrubbed with Presidio
    and sent by the AI worker through `capture`; TC-PLT-04-1: the captured AI requests carry tokens, never the
    seeded identifiers; PRV-05: nor the real service dates."""
    from tests.pdfs import make_image

    browser = ai_browser
    log = Path(os.environ["MHS_STACK_CAPTURE_LOG"])
    seen = len(log.read_text().splitlines()) if log.exists() else 0
    photo = make_image(EOB + "Questions? Jordan Rivera in billing can help at 555-310-4000.\n" + MARKER.decode())
    home = browser.get("/uploads")
    assert "with the help of AI" in home.text
    upload = browser.post("/uploads", data={"csrf_token": csrf(home.text), "kind": "auto"},
                          files={"file": ("eob-photo.png", photo, "image/png")})
    assert upload.status_code == 303, upload.text[:1000]
    upload_id = upload.headers["location"].split("uploaded=")[1]
    deadline = time.monotonic() + 60
    while browser.get(f"/api/uploads/{upload_id}").json()["status"] != "review":
        assert time.monotonic() < deadline, "the AI worker didn't read the upload"
        time.sleep(0.5)
    review = browser.get(f"/uploads/{upload_id}/review").text
    assert "photo, OCR (tesseract)" in review and "fields found by AI (claude-opus-5-5)" in review
    values = form_values(review, f"/uploads/{upload_id}/confirm")
    assert values["billed"] == "320.00"
    assert values["service_start"] == "2026-09-28"  # PRV-05: shifted for the AI, shifted back for the household

    flows = [json.loads(line) for line in log.read_text().splitlines()[seen:]]
    sent = [f["request_body"] for f in flows if f["host"] == AI_HOST]
    assert sent, "capture saw no AI request for the photo"
    for body in sent:
        assert "tok_" in body
        for seed in SEEDS:
            assert seed.lower() not in body.lower(), seed
        assert "09/28/2026" not in body and "10/05/2026" not in body  # TC-PRV-05-2: real dates never sent


def test_originals_volume_holds_only_ciphertext(member):
    root = Path(os.environ["MHS_STACK_OBJECTS_DIR"])
    files = [p for p in root.rglob("*") if p.is_file()]
    assert files, "no originals on the volume"
    assert not any(MARKER in p.read_bytes() for p in files)  # TC-PRV-06-2 on the stack


def test_captured_traffic_stays_first_party(member):
    """TC-PRV-08-1 (partial): every request the session made went to the app, the AI worker's went only to the
    (stand-in) AI service, and no response pulled in a third-party resource."""
    log = Path(os.environ["MHS_STACK_CAPTURE_LOG"])
    flows = [json.loads(line) for line in log.read_text().splitlines()]
    assert flows, "capture saw no traffic"
    app_host = urlsplit(STACK_URL).hostname
    assert {f["host"] for f in flows} <= {app_host, AI_HOST}
    for f in flows:
        if f["response_headers"].get("content-type", "").startswith("text/html"):
            assert not re.search(r'(?:src|href)="(?:https?:)?//', f["response_body"]), f["path"]


def test_forwarded_email_arrives_and_is_read(member):
    """TC-ING-01-4 on the stack: mail to the household's address through the `mail` service becomes an upload the
    worker reads; strangers and unknown addresses are refused at SMTP."""
    import smtplib
    from email.message import EmailMessage

    from mhs.data.db import Database
    from mhs.data.household_store import HouseholdStore
    from mhs.stack import database_url
    from mhs.web.household.inbound import address_for

    m, _, _ = member
    db = Database(database_url(), max_size=1)
    to = address_for(db, m.household_id)
    host, port = os.environ["MHS_STACK_MAIL"].split(":")

    def mail(sender: str, rcpt: str):
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = sender, rcpt, "Fwd: EOB"
        msg.set_content("Forwarding my EOB.")
        msg.add_attachment(make_pdf(EOB + "Forwarded copy\n"), maintype="application", subtype="pdf",
                           filename="forwarded-eob.pdf")
        with smtplib.SMTP(host, int(port), timeout=30) as smtp:
            smtp.send_message(msg)

    with pytest.raises(smtplib.SMTPRecipientsRefused):
        mail(m.email, "nobody@inbound.mhs.local")
    with pytest.raises(smtplib.SMTPDataError):
        mail("stranger@example.test", to)
    mail(m.email, to)
    store = HouseholdStore(db, m.household_id)
    deadline = time.monotonic() + 60
    while True:
        emailed = [r for r in store.all("original") if r.get("via") == "email"]
        if emailed and (ext := store.get("extraction", emailed[0]["id"])) and ext["status"] == "review":
            break
        assert time.monotonic() < deadline, "the forwarded EOB wasn't read"
        time.sleep(0.5)
    assert ext["doc_type"] == "eob" and len(emailed) == 1
    db.close()


def test_typical_uploads_reach_a_visit_within_a_minute(member):
    """PLT-05 (TC-PLT-05-1, small): a few typical uploads, timed from upload to a confirmed visit without the member's
    own review time; tools/perf_run.py runs the full 50."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("perf_run", Path("/srv/mhs/tools/perf_run.py"))
    perf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(perf)
    results = perf.run(5, STACK_URL)
    s = perf.summary(results)
    assert s["confirmed"] == 5, results
    assert s["p95_seconds"] < perf.TARGET_SECONDS, s
