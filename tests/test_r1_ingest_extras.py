"""Phase 1.3 local leftovers: reading in the background, previews, copies and versions (ING-07), and blanking
identifiers on images (PRV-04)."""

import io
import re
import shutil

import pytest
from PIL import Image

from mhs.ingest.ocr import TesseractOcr, Word
from mhs.ingest.redact import blank_pages, identifier_words
from tests.pdfs import make_image, make_pdf
from tests.test_r1_scenarios import EOB, STATEMENT, Member

pytestmark = pytest.mark.postgres


@pytest.fixture
def member(household, app_db, worker_db):
    return Member(household, app_db, worker_db)


def confirmed(member, name: str, data: bytes, ctype: str = "application/pdf", **changes) -> str:
    uid = member.upload_id(member.upload(name, data, ctype=ctype))
    member.work()
    text, values = member.review(uid)
    values.update(changes)
    assert member.confirm(uid, values).status_code == 303
    return uid


# --- reading in the background --------------------------------------------------------------------------

def test_a_failed_read_is_reported_and_can_be_retried(member, vault_client, monkeypatch):
    real = vault_client.tokenize

    def broken(*args):
        raise RuntimeError("vault down")

    monkeypatch.setattr(vault_client, "tokenize", broken)
    uid = member.upload_id(member.upload("statement.pdf", make_pdf(STATEMENT)))
    upload = member.client.get(f"/api/uploads/{uid}").json()
    assert upload["status"] == "failed"
    assert "read: try again" in member.client.get("/uploads").text
    assert "couldn&#39;t be read" in member.review(uid)[0]
    monkeypatch.setattr(vault_client, "tokenize", real)
    member.client.post(f"/uploads/{uid}/reclassify", data={"doc_type": "provider_statement"})
    member.work()
    assert member.client.get(f"/api/uploads/{uid}").json()["status"] == "review"


# --- previews --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,data,ctype", [
    ("photo.png", lambda: make_image("Amount billed: $320.00"), "image/png"),
    ("photo.heic", lambda: make_image("Amount billed: $320.00", "HEIC"), "image/heic"),
    ("eob.pdf", lambda: make_pdf(EOB), "application/pdf"),
])
def test_preview_of_photos_and_pdfs(member, name, data, ctype):
    """TC-ING-01-2: iPhone HEIC shows in the browser as JPEG; PDFs show their first page; originals unchanged."""
    raw = data()
    uid = member.upload_id(member.upload(name, raw, ctype=ctype))
    member.work()
    r = member.client.get(f"/uploads/{uid}/preview")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(r.content)).size[0] > 100
    assert member.client.get(f"/uploads/{uid}").content == raw
    assert f'src="/uploads/{uid}/preview"' in member.review(uid)[0]


def test_previews_stay_in_their_household(household, app_db, worker_db, member):
    uid = member.upload_id(member.upload("photo.png", make_image("x"), ctype="image/png"))
    other = Member(household, app_db, worker_db, "Other")
    assert other.client.get(f"/uploads/{uid}/preview").status_code == 404


# --- copies and versions (ING-07) ------------------------------------------------------------------------

def test_tc_ing_07_2_a_second_copy_of_an_eob_is_flagged(member):
    confirmed(member, "eob.pdf", make_pdf(EOB))
    copy = member.upload_id(member.upload("eob-again.pdf", make_pdf(EOB + "Page 1 of 1")))  # a second scan: other bytes, same document
    member.work()
    text, _ = member.review(copy)
    assert "looks like a copy of an EOB you already have" in text and "It's a copy" in text
    before = len(member.store.all("document"))
    r = member.client.post(f"/uploads/{copy}/file", data={}, follow_redirects=False)
    assert r.status_code == 303
    assert len(member.store.all("document")) == before
    ext = member.store.get("extraction", copy)
    assert ext["status"] == "filed" and ext["copy_of"] == "eob-c-2026-0042"


def test_a_corrected_eob_is_a_new_version(member):
    confirmed(member, "eob.pdf", make_pdf(EOB))
    corrected = EOB.replace("Your responsibility: $45.00", "Your responsibility: $25.00").replace(
        "Plan paid: $155.00", "Plan paid: $175.00")
    uid = member.upload_id(member.upload("eob-corrected.pdf", make_pdf(corrected)))
    member.work()
    text, values = member.review(uid)
    assert "A corrected EOB for claim C-2026-0042" in text and "$45.00 → $25.00" in text
    member.confirm(uid, values)
    assert member.store.get("document", "eob-c-2026-0042")["patient_responsibility"] == 2500


def visit_figures(member, visit_id: str) -> dict:
    from datetime import date

    from mhs.core.reconcile import build_report
    from mhs.data.repository import load_dataset

    v = build_report(load_dataset(member.store), 2026, date(2026, 12, 1)).visit(visit_id)
    return {"total_billed": v.total_billed, "billed_to_me": v.billed_to_me, "remaining": v.remaining,
            "at_stake": v.at_stake, "status": v.status, "duplicates": [c for c in v.checks if "uplicate" in str(c)]}


def test_tc_ing_07_3_a_resent_statement_is_not_counted_twice(member):
    confirmed(member, "statement.pdf", make_pdf(STATEMENT))
    before = visit_figures(member, "v-2026-09-28-example-dermatology")
    resent = STATEMENT.replace("Statement date: 10/01/2026", "Statement date: 11/01/2026")
    uid = member.upload_id(member.upload("statement-november.pdf", make_pdf(resent)))
    member.work()
    text, values = member.review(uid)
    assert "A re-sent copy of the statement of 2026-10-01" in text and "aren&#39;t counted twice" in text
    member.confirm(uid, values)
    after = visit_figures(member, "v-2026-09-28-example-dermatology")
    assert after == before and after["billed_to_me"] == 32000  # the same $320.00, not $640.00; no duplicate finding


def test_tc_ing_07_4_a_changed_balance_is_a_newer_statement(member):
    confirmed(member, "statement.pdf", make_pdf(STATEMENT))
    newer = STATEMENT.replace("Statement date: 10/01/2026", "Statement date: 11/01/2026").replace(
        "Amount due: $320.00", "Amount due: $120.00").replace("$320.00 $0.00 $320.00", "$320.00 $200.00 $120.00")
    uid = member.upload_id(member.upload("statement-newer.pdf", make_pdf(newer)))
    member.work()
    text, _ = member.review(uid)
    assert "A newer statement" in text and "$320.00 to $120.00" in text and "It's a copy" not in text


# --- blanking identifiers on images (PRV-04) -------------------------------------------------------------

def test_blanking_paints_over_identifier_words():
    page = Image.new("RGB", (400, 100), "white")
    words = [Word("Pat", 1, (0.1, 0.1, 0.2, 0.3), 0.9), Word("Example,", 1, (0.25, 0.1, 0.45, 0.3), 0.9),
             Word("EOB", 1, (0.6, 0.1, 0.7, 0.3), 0.9)]
    targets = identifier_words([("name", "Pat Example"), ("member_id", "W123-456-789")])
    assert targets == {"pat", "example", "w123-456-789"}
    [out], n = blank_pages([page], words, targets)
    assert n == 2
    assert out.getpixel((60, 20)) == (0, 0, 0) and out.getpixel((140, 20)) == (0, 0, 0)  # blanked
    assert out.getpixel((260, 20)) == (255, 255, 255)  # "EOB" kept
    assert page.getpixel((60, 20)) == (255, 255, 255)  # the original page untouched


@pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract isn't installed here; the compose tests runner has it")
def test_tc_prv_04_1_scrubbed_photo_shows_no_identifiers(make_household, app_db, worker_db, app_keyring):
    """A photo of an EOB with seeded identifiers: the blanked copy, read again by OCR, shows none of them."""
    household = make_household(ocr_engine="tesseract", scrubber="presidio")
    m = Member(household, app_db, worker_db)
    photo = make_image(EOB.replace("Example Health", "Bluewater Health"))
    uid = m.upload_id(m.upload("eob-photo.png", photo, kind="eob", ctype="image/png"))
    rec = m.store.get("original", uid)
    assert rec.get("scrubbed_keys"), "no blanked copy was stored"
    sealed = (household.objects_dir / rec["scrubbed_keys"][0]).read_bytes()
    image = app_keyring.decrypt(m.who.household_id, sealed, f"scrubbed:{uid}:1")
    again = TesseractOcr().read(image, "image/png").text
    assert "EXPLANATION" in again.upper() and "320.00" in again  # the rest of the page is still readable
    for seed in (r"\bPat\b", r"W123", r"456-789"):  # "Patient:" is a label and stays
        assert not re.search(seed, again), seed
