"""User scenarios for phase 1.3 uploads (ADR-033): a member signs in with MFA and uploads a provider statement,
an EOB and HSA and insurer exports; the worker reads the documents; the member reviews, corrects and confirms;
the confirmed data shows on their visits. Each test names the requirement and test cases it covers."""

import hashlib
import io
import json
import re
import shutil
from html.parser import HTMLParser

import pytest

from mhs.data.household_store import HouseholdStore
from mhs.data.queue import JobQueue
from mhs.ingest.worker import make_handlers, run_once
from tests.conftest import admin_sql
from tests.pdfs import make_image, make_pdf, make_scanned_pdf
from tests.test_web import CsrfClient

pytestmark = pytest.mark.postgres

STATEMENT = """Example Dermatology
1200 Main Street, Springfield
Statement date: 10/01/2026
Account number: 556677
Patient: Example, Pat A.
Phone: (555) 201-3344
Due date: 10/31/2026
09/28/2026 11102 Skin biopsy $320.00 $0.00 $320.00
Amount due: $320.00
"""
EOB = """Example Health
EXPLANATION OF BENEFITS          THIS IS NOT A BILL
Patient: Pat Example     Member ID: W123-456-789
Provider: Example Dermatology
Claim number: C-2026-0042
Date of service: 09/28/2026
Date processed: 10/05/2026
Amount billed: $320.00
Plan discount: $120.00
Allowed amount: $200.00
Plan paid: $155.00
Coinsurance: $45.00
Your responsibility: $45.00
In-network
09/28/2026 11102 Skin biopsy $320.00 $200.00 $155.00 $45.00
"""
IDENTIFIERS = ["Pat Example", "Example, Pat", "W123-456-789", "W123456789", "556677", "201-3344"]
HSA_CSV = """Date,Description,Amount,Balance
10/10/2026,"EXAMPLE DERMATOLOGY, SPRINGFIELD (Card Transaction ID: 9001)",-45.00,955.00
10/01/2026,Employee Contribution,500.00,1000.00
09/30/2026,Balance Forward,0.00,500.00
"""


class FormValues(HTMLParser):
    """The values a browser would post from the first form whose action ends with `action`."""

    def __init__(self, action: str):
        super().__init__()
        self.action, self.inside, self.values, self.select = action, False, {}, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.inside = (a.get("action") or "").endswith(self.action) and not self.values
        elif self.inside and tag == "input" and a.get("name"):
            self.values[a["name"]] = a.get("value") or ""
        elif self.inside and tag == "select":
            self.select = a.get("name")
        elif self.inside and tag == "option" and self.select:
            if "selected" in a or self.select not in self.values:
                self.values[self.select] = a.get("value", "")

    def handle_endtag(self, tag):
        if tag == "select":
            self.select = None
        elif tag == "form":
            self.inside = False


def form_values(html: str, action: str) -> dict:
    p = FormValues(action)
    p.feed(html)
    return p.values


class Member:
    """A signed-in member of a household with a member record and a 2026 plan, plus the worker."""

    def __init__(self, household, app_db, worker_db, name="Household"):
        self.who = household.enrol(name)
        raw = household.sign_in(self.who)
        self.client = CsrfClient(raw, household.csrf(raw))
        self.store = HouseholdStore(app_db, self.who.household_id)
        self.worker_db = worker_db
        self.objects_dir = household.objects_dir
        self.client.post("/settings/members", data={"name": "Pat Example", "relationship": "self"})
        self.client.post("/settings/plans", data={"plan_year": "2026", "insurer": "Example Health",
                                                  "plan_name": "Medical"})

    def upload(self, name: str, data: bytes, kind: str = "auto", ctype: str = "application/pdf"):
        return self.client.post("/uploads", files={"file": (name, data, ctype)}, data={"kind": kind},
                                follow_redirects=False)

    def upload_id(self, r) -> str:
        assert r.status_code == 303, r.text[:2000]
        return r.headers["location"].split("uploaded=")[1]

    def work(self) -> int:
        """Run the worker until the queue is empty; returns how many jobs ran."""
        n = 0
        while run_once(JobQueue(self.worker_db), self.worker_db) is not None:
            n += 1
        return n

    def review(self, upload_id: str):
        page = self.client.get(f"/uploads/{upload_id}/review")
        assert page.status_code == 200, page.text[:2000]
        return page.text, form_values(page.text, f"/uploads/{upload_id}/confirm")

    def confirm(self, upload_id: str, values: dict):
        return self.client.post(f"/uploads/{upload_id}/confirm", data=values, follow_redirects=False)

    def import_export(self, name: str, data: bytes, ctype="text/csv", kind="auto"):
        preview = self.client.post("/uploads", files={"file": (name, data, ctype)}, data={"kind": kind})
        assert preview.status_code == 200 and "What will change" in preview.text, preview.text[:3000]
        token = re.search(r'name="token" value="([^"]+)"', preview.text).group(1)
        done = self.client.post("/import/confirm", data={"token": token}, follow_redirects=False)
        assert done.headers["location"] == "/import?done=1"
        return preview


@pytest.fixture
def member(household, app_db, worker_db):
    return Member(household, app_db, worker_db)


def test_statement_upload_review_and_confirm(member):
    """ING-01 (TC-1), ING-02, ING-03, ING-05 (TC-1, TC-2), ING-10 (TC-1): a PDF statement becomes a confirmed bill."""
    pdf = make_pdf(STATEMENT)
    uid = member.upload_id(member.upload("derm-statement.pdf", pdf))
    assert member.client.get(f"/api/uploads/{uid}").json()["status"] == "reading"
    assert member.work() == 1
    upload = member.client.get(f"/api/uploads/{uid}").json()
    assert upload["status"] == "review" and upload["doc_type"] == "provider_statement"

    text, values = member.review(uid)
    assert "Example Dermatology" in text and "320.00" in text and "2026-10-01" in text
    assert "check" in text  # the provider came from the letterhead: below the threshold, highlighted
    assert values["member_id"] == "mbr-pat-example"  # the patient, re-identified, matches the member
    # TC-ING-05-2: nothing reaches reconciliation before confirmation.
    assert member.store.all("visit") == [] and "No visits yet" in member.client.get("/").text

    r = member.confirm(uid, values)
    assert r.status_code == 303 and r.headers["location"] == "/visits/v-2026-09-28-example-dermatology", r.text[:2000]
    bill = member.store.get("document", "bill-example-dermatology-2026-10-01")
    assert bill["balance_due"] == 32000 and bill["lines"][0]["visit_id"] == "v-2026-09-28-example-dermatology"
    assert member.store.get("visit", "v-2026-09-28-example-dermatology")["member_id"] == "mbr-pat-example"
    assert bill["file_sha256"] == hashlib.sha256(pdf).hexdigest()  # TC-ING-10-1: the original, unchanged
    assert member.client.get(f"/files/{bill['id']}").content == pdf
    assert "Example Dermatology" in member.client.get("/visits?year=2026").text
    assert member.client.get(f"/api/uploads/{uid}").json()["status"] == "confirmed"


def test_eob_upload_corrected_and_matched_to_the_visit(member):
    """ING-02 (TC-3), ING-03, ING-04, ING-05 (TC-3, TC-4), PLT-04 (TC-2): an EOB joins the statement's visit."""
    sid = member.upload_id(member.upload("statement.pdf", make_pdf(STATEMENT)))
    member.work()
    member.confirm(sid, member.review(sid)[1])

    eid = member.upload_id(member.upload("eob.pdf", make_pdf(EOB)))
    member.work()
    assert member.client.get(f"/api/uploads/{eid}").json()["doc_type"] == "eob"  # "THIS IS NOT A BILL"
    text, values = member.review(eid)
    assert values["visit_id"] == "v-2026-09-28-example-dermatology"  # same provider and date
    assert values["provider_id"] == "prov-example-dermatology" and values["plan_id"] == "plan-2026-medical"
    assert values["patient_responsibility"] == "45.00" and "11102" in text
    values["patient_responsibility"] = "54.00"  # TC-ING-05-3: the member corrects a value
    r = member.confirm(eid, values)
    assert r.headers["location"] == "/visits/v-2026-09-28-example-dermatology"
    eob = member.store.get("document", "eob-c-2026-0042")
    assert eob["patient_responsibility"] == 5400 and eob["allowed"] == 20000 and eob["lines"][0]["code"] == "11102"
    extraction = member.store.get("extraction", eid)
    assert len(extraction["corrections"]) == 1, extraction["corrections"]
    [fix] = extraction["corrections"]
    assert (fix["field"], fix["extracted"], fix["confirmed"]) == ("patient_responsibility", 4500, 5400) and fix["at"]
    assert extraction["fields"]["patient_responsibility"]["value"] == 4500  # what was read stays visible
    visit_page = member.client.get("/visits/v-2026-09-28-example-dermatology").text
    assert "$54.00" in visit_page and "$320.00" in visit_page

    # TC-ING-05-4: editing after confirmation updates the visit at once.
    _, values = member.review(eid)
    values["patient_responsibility"] = "45.00"
    member.confirm(eid, values)
    assert member.store.get("document", "eob-c-2026-0042")["patient_responsibility"] == 4500
    assert len(member.store.get("extraction", eid)["corrections"]) == 2


def test_identifiers_never_reach_the_worker(member, pgdb):
    """PRV-01 (TC-1, TC-2), PRV-03, PRV-04 (TC-2): the queue and the worker's records hold tokens, not identifiers."""
    for name, text in (("s.pdf", STATEMENT), ("e.pdf", EOB)):
        member.upload_id(member.upload(name, make_pdf(text)))
    member.work()
    payloads = " ".join(r[0] for r in admin_sql(pgdb, "SELECT payload::text FROM app.jobs WHERE household_id = %s",
                                                (member.who.household_id,)))
    extractions = " ".join(r[0] for r in admin_sql(pgdb, "SELECT data::text FROM app.records WHERE kind = 'extraction' "
                                                   "AND household_id = %s", (member.who.household_id,)))
    for value in IDENTIFIERS:
        assert value.lower() not in payloads.lower(), value
        assert value.lower() not in extractions.lower(), value
    assert "tok_" in payloads and "Example Dermatology" in payloads  # providers aren't identifiers
    # "Example, Pat A." on the statement and "Pat Example" on the EOB are one person: one name token (PRV-03).
    names = admin_sql(pgdb, "SELECT count(*) FROM vault.entries WHERE household_id = %s AND kind = 'name'",
                      (member.who.household_id,))[0][0]
    assert names == 1
    review_text = member.review(member.client.get("/api/uploads").json()[0]["id"])[0]
    assert "tok_" not in review_text  # the member sees their own values, re-identified


def test_hsa_export_upload(member):
    """ING-08 (TC-1, TC-2), ING-07 (TC-1, TC-5): an HSA CSV export imports; re-sends and overlaps add nothing."""
    preview = member.import_export("hsa-2026.csv", HSA_CSV.encode())
    assert "Documents" in preview.text
    payments = [d for d in member.store.all("document") if d["type"] == "payment"]
    assert [(p["amount"], p["provider_id"], p["account_id"]) for p in payments] == [(4500, "prov-example-dermatology", "acct-hsa")]
    kinds = sorted(d["kind"] for d in member.store.all("document") if d["type"] == "account_transaction")
    assert kinds == ["balance_forward", "contribution_employee"]
    assert member.store.get("account", "acct-hsa")["type"] == "hsa"

    again = member.upload("hsa-2026.csv", HSA_CSV.encode(), ctype="text/csv")
    assert again.status_code == 409 and "already uploaded" in again.text  # TC-ING-07-1

    overlap = HSA_CSV.replace("Date,Description,Amount,Balance\n",
                              "Date,Description,Amount,Balance\n10/20/2026,Interest,1.25,956.25\n")
    member.import_export("hsa-2026-later.csv", overlap.encode())
    docs = member.store.all("document")
    assert len([d for d in docs if d["type"] == "payment"]) == 1  # TC-ING-07-5: no duplicates
    assert sorted(d["kind"] for d in docs if d["type"] == "account_transaction") == [
        "balance_forward", "contribution_employee", "interest"]


def test_hsa_export_problems(member):
    """ING-08 (TC-3, TC-4): a missing column refuses the file; a balance gap is warned about by date."""
    r = member.upload("bad.csv", b"Date,Description,Balance\n10/01/2026,Contribution,100.00\n", ctype="text/csv")
    assert r.status_code == 400 and "Missing column(s): amount" in r.text
    assert member.store.all("original") == []  # nothing saved
    gap = HSA_CSV.replace("-45.00,955.00", "-45.00,900.00")
    preview = member.client.post("/uploads", files={"file": ("gap.csv", gap.encode(), "text/csv")})
    assert "The running balance breaks on 2026-10-10" in preview.text


def test_hsa_export_formats_agree(tmp_path):
    """ING-08 (TC-5): the administrator's HTML ".xls", CSV and XLSX of the same data give identical transactions."""
    from openpyxl import Workbook

    from mhs.ingest.hsa import parse_export

    rows = [["10/10/2026", "EXAMPLE DERMATOLOGY, SPRINGFIELD (Card Transaction ID: 9001)", "($45.00)", "$955.00"],
            ["10/01/2026", "Employee Contribution", "$500.00", "$1,000.00"]]
    html = "<table>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</table>"
    csv_text = "Date,Description,Amount,Balance\n" + "".join(
        f'{r[0]},"{r[1]}",{r[2].replace("($", "-").replace(")", "").replace("$", "").replace(",", "")},'
        f'{r[3].replace("$", "").replace(",", "")}\n' for r in rows)
    wb = Workbook()
    ws = wb.active
    ws.append(["Date", "Description", "Amount", "Balance"])
    for r in rows:
        ws.append([r[0], r[1], -45.0 if "45" in r[2] else 500.0, 955.0 if "955" in r[3] else 1000.0])
    buf = io.BytesIO()
    wb.save(buf)
    results = [parse_export("TransactionHistory.xls", html.encode()), parse_export("t.csv", csv_text.encode()),
               parse_export("t.xlsx", buf.getvalue())]
    assert [r.format for r in results] == ["html", "csv", "xlsx"]
    assert all(not r.errors for r in results)
    assert results[0].rows == results[1].rows == results[2].rows
    assert results[0].rows[0].date == "2026-10-01"  # oldest first


def test_claims_export_upload(member):
    """The insurer's claims CSV: each claim becomes an EOB on a visit, matched to the member and the 2026 plan."""
    csv_text = ("Patient,Provided By,Claim Type,Claim Number,Service Date,Processed Date,Claim Received,Status,Billed,"
                "Plan Discount,Allowed,Plan Paid,Additional Savings,Deductible,Coinsurance,Copay,Not Covered,Your Cost\n"
                "Pat Example,Example Family Medicine,Medical,C-77,2026-04-02,2026-04-20,2026-04-05,Approved,$250.00,"
                "$100.00,$150.00,$105.00,$0.00,$0.00,$0.00,$45.00,$0.00,$45.00\n")
    member.import_export("claims.csv", csv_text.encode())
    eob = member.store.get("document", "eob-c-77")
    assert eob["patient_responsibility"] == 4500 and eob["plan_id"] == "plan-2026-medical"
    assert member.store.get("visit", eob["visit_id"])["member_id"] == "mbr-pat-example"
    assert "Example Family Medicine" in member.client.get("/providers?year=2026").text


@pytest.mark.parametrize("name,data,ctype,reason", [
    ("letter.docx", b"PK\x03\x04docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
     "only PDFs, photos"),
    ("bundle.zip", b"PK\x03\x04zip", "application/zip", "only PDFs, photos"),
    ("empty.pdf", b"", "application/pdf", "is empty"),
    ("broken.pdf", b"%PDF-1.4 garbage", "application/pdf", "damaged"),
    ("notpdf.pdf", b"hello", "application/pdf", "a PDF, though"),
    ("photo.jpg", b"\xff\xd8\xff not really a photo", "image/jpeg", "damaged or in a format"),
])
def test_unreadable_uploads_are_refused(member, name, data, ctype, reason):
    """ING-01 (TC-5): each refused with a plain reason; nothing saved."""
    r = member.upload(name, data, ctype=ctype)
    assert r.status_code in (400, 415) and reason in r.text
    assert member.store.all("original") == []


def test_password_protected_and_oversized_pdfs_are_refused(member, monkeypatch):
    from pypdf import PdfReader, PdfWriter

    from mhs.web.household import intake

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf(EOB))))
    writer.encrypt("secret-password")
    buf = io.BytesIO()
    writer.write(buf)
    r = member.upload("locked.pdf", buf.getvalue())
    assert r.status_code == 400 and "password-protected" in r.text
    monkeypatch.setattr(intake, "MAX_UPLOAD", 100)
    r = member.upload("big.pdf", make_pdf(EOB))
    assert r.status_code == 413 and "larger than" in r.text
    assert member.store.all("original") == []


def test_photo_is_entered_by_hand(member):
    """ING-01 (TC-2, partial), ING-05: a photo is stored; with no OCR engine the member enters the EOB's fields."""
    png = make_image("a photo")
    uid = member.upload_id(member.upload("eob-photo.png", png, kind="eob", ctype="image/png"))
    member.work()
    text, values = member.review(uid)
    assert "No text could be read" in text and values["billed"] == ""
    values.update(provider="Example Labs", service_start="2026-05-03", billed="80.00", allowed="60.00",
                  insurer_paid="40.00", patient_responsibility="20.00", claim_number="L-9")
    r = member.confirm(uid, values)
    assert r.status_code == 303, r.text[:2000]
    eob = member.store.get("document", "eob-l-9")
    assert eob["billed"] == 8000 and member.store.get("provider", "prov-example-labs")
    assert member.client.get("/files/eob-l-9").content == png


@pytest.fixture
def engines_member(make_household, app_db, worker_db):
    """A member on an app configured like the compose stack: Tesseract OCR and the Presidio scrubber."""
    if not shutil.which("tesseract"):
        pytest.skip("tesseract isn't installed here; the compose tests runner has it")
    pytest.importorskip("presidio_analyzer")
    return Member(make_household(ocr_engine="tesseract", scrubber="presidio"), app_db, worker_db)


@pytest.mark.parametrize("name,make,ctype", [
    ("eob.png", lambda: make_image(EOB), "image/png"),
    ("eob.heic", lambda: make_image(EOB, "HEIC"), "image/heic"),
    ("eob-scan.pdf", lambda: make_scanned_pdf(EOB), "application/pdf"),
])
def test_photo_and_scan_are_read_by_ocr(engines_member, pgdb, name, make, ctype):
    """ING-01 (TC-2, TC-3), ING-03, PRV-04: a photo (PNG or iPhone HEIC) or a scanned PDF of an EOB is read by OCR
    in the application tier, scrubbed, and extracts like the PDF does; the worker sees tokens only."""
    m = engines_member
    uid = m.upload_id(m.upload(name, make(), ctype=ctype))
    m.work()
    text, values = m.review(uid)
    assert "OCR (tesseract)" in text
    assert values["billed"] == "320.00" and values["patient_responsibility"] == "45.00"
    assert values["service_start"] == "2026-09-28" and values["provider"] == "Example Dermatology"
    payload = admin_sql(pgdb, "SELECT payload::text FROM app.jobs WHERE household_id = %s",
                        (m.who.household_id,))[0][0]
    for value in IDENTIFIERS:
        assert value.lower() not in payload.lower(), value
    assert m.confirm(uid, values).status_code == 303


def test_presidio_scrubs_strangers_in_a_letter(engines_member, pgdb):
    """PRV-04 (TC-2) with Presidio: names the household doesn't know never reach the worker."""
    m = engines_member
    letter = ("Lakeside Family Medicine\nDear Pat Example,\nJordan Rivera called for you about the bill on 03/14/2026.\n"
              "Our billing manager Aisha Okafor can be reached at 555-310-4000.")
    m.upload_id(m.upload("letter.pdf", make_pdf(letter)))
    m.work()
    payload = admin_sql(pgdb, "SELECT payload::text FROM app.jobs WHERE household_id = %s", (m.who.household_id,))[0][0]
    for value in ("Pat Example", "Jordan Rivera", "Aisha Okafor", "555-310-4000"):
        assert value not in payload, value
    assert "03/14/2026" in payload and "Lakeside Family Medicine" in payload


def test_ai_extraction_for_a_household_that_turned_it_on(member, accounts, pgdb):
    """ADR-028, ADR-034, PLT-04 (TC-1 in process, TC-2): with AI extraction on, the document goes to an AI worker as
    scrubbed text only; the member sees which fields the AI found, a value the document doesn't show is marked,
    and the member's correction is what gets confirmed."""
    from tests.test_r1_ai import RecordedAi

    hid = member.who.household_id
    accounts.set_ai_extraction(hid, True)
    assert "with the help of AI" in member.client.get("/uploads").text
    uid = member.upload_id(member.upload("eob.pdf", make_pdf(EOB)))
    assert admin_sql(pgdb, "SELECT kind FROM app.jobs WHERE household_id = %s", (hid,)) == [("extract_ai",)]
    queue = JobQueue(member.worker_db)
    assert run_once(queue, member.worker_db, kinds=["ping", "extract"], stale_kinds=["extract_ai"]) is None
    ai = RecordedAi("eob")
    assert run_once(queue, member.worker_db, make_handlers(ai.extractor), kinds=["ping", "extract", "extract_ai"])
    text, values = member.review(uid)
    assert "fields found by AI (claude-opus-5-5)" in text
    assert values["billed"] == "320.00" and values["deductible"] == "25.00"
    assert "not found in the document text" in text
    sent = json.dumps([r["body"] for r in ai.requests])
    assert "tok_" in sent and all(v.lower() not in sent.lower() for v in IDENTIFIERS)  # TC-PLT-04-1, in process
    values["deductible"] = ""  # the member corrects what the AI concluded
    assert member.confirm(uid, values).status_code == 303
    ext = member.store.get("extraction", uid)
    assert ext["extractor"] == "ai" and ext["fields"]["deductible"]["value"] == 2500  # the AI's value stays visible


def test_ai_jobs_are_read_by_the_rules_when_ai_is_unavailable(member, accounts, pgdb):
    """No AI worker after a minute, or the AI declines: the layout rules read the document and the review says so."""
    from tests.test_r1_ai import RecordedAi

    hid = member.who.household_id
    accounts.set_ai_extraction(hid, True)
    first = member.upload_id(member.upload("eob.pdf", make_pdf(EOB)))
    admin_sql(pgdb, "UPDATE app.jobs SET created_at = now() - interval '2 minutes' WHERE household_id = %s", (hid,))
    queue = JobQueue(member.worker_db)
    assert run_once(queue, member.worker_db, kinds=["ping", "extract"], stale_kinds=["extract_ai"])
    text, values = member.review(first)
    assert "AI reading isn&#39;t running on this server" in text and values["billed"] == "320.00"
    second = member.upload_id(member.upload("statement.pdf", make_pdf(STATEMENT)))
    assert run_once(queue, member.worker_db, make_handlers(RecordedAi("refusal").extractor))
    text, values = member.review(second)
    assert "AI extraction declined this document, so the layout rules read this document" in text
    assert values["balance_due"] == "320.00" and member.store.get("extraction", second)["extractor"] == "rules"


def test_reclassify_reads_again(member):
    """ING-02 (TC-4): an unrecognised letter is 'other'; the member's type persists and extraction runs again."""
    letter = "Example Dermatology\nDear patient,\nThank you for choosing our practice. Please keep this letter.\n"
    uid = member.upload_id(member.upload("letter.pdf", make_pdf(letter)))
    member.work()
    assert member.client.get(f"/api/uploads/{uid}").json()["doc_type"] == "other"
    r = member.client.post(f"/uploads/{uid}/reclassify", data={"doc_type": "provider_statement"}, follow_redirects=False)
    assert r.status_code == 303 and member.client.get(f"/api/uploads/{uid}").json()["status"] == "reading"
    member.work()
    upload = member.client.get(f"/api/uploads/{uid}").json()
    assert upload["doc_type"] == "provider_statement" and upload["status"] == "review"


def test_multi_page_pdf_is_one_document(member):
    """ING-01 (TC-3, PDF part): a multi-page PDF is one upload, read in page order."""
    pages = [EOB.split("Amount billed")[0], "Amount billed" + EOB.split("Amount billed")[1]]
    uid = member.upload_id(member.upload("two-pages.pdf", make_pdf(*pages)))
    member.work()
    extraction = member.store.get("extraction", uid)
    assert extraction["pages"] == 2 and extraction["fields"]["billed"]["value"] == 32000
    assert len(member.client.get("/api/uploads").json()) == 1


def test_lines_that_dont_add_up_are_flagged(member):
    """ING-04 (TC-3): lines summing to less than the header total are flagged before confirmation."""
    eob = EOB.replace("09/28/2026 11102 Skin biopsy $320.00", "09/28/2026 11102 Skin biopsy $280.00")
    uid = member.upload_id(member.upload("eob.pdf", make_pdf(eob)))
    member.work()
    assert "Lines differ from the total by $40.00" in member.review(uid)[0]


def test_another_household_cannot_see_or_confirm_an_upload(household, app_db, worker_db, member):
    """PRV-11 on uploads: another household's upload, review and confirm are not found."""
    uid = member.upload_id(member.upload("eob.pdf", make_pdf(EOB)))
    member.work()
    other = Member(household, app_db, worker_db, "Other household")
    for path in (f"/uploads/{uid}", f"/uploads/{uid}/review", f"/api/uploads/{uid}"):
        assert other.client.get(path).status_code == 404, path
    assert other.client.post(f"/uploads/{uid}/confirm", data={}).status_code == 404
    assert other.client.post(f"/uploads/{uid}/reclassify", data={"doc_type": "eob"}).status_code == 404
    assert other.client.get("/api/uploads").json() == []


def test_upload_page_offers_every_kind(member):
    page = member.client.get("/uploads").text
    for label in ("Provider bill or statement", "EOB from the insurer", "HSA/FSA transaction export",
                  "Insurer claims export"):
        assert label in page
    assert 'capture="environment"' in page  # phone camera capture (UX-10)
    assert json.dumps(member.client.get("/api/uploads").json()) == "[]"
