"""Forwarded email (ING-01, TC-ING-01-4, ADR-039)."""

from email.message import EmailMessage

import pytest

from mhs.data.objects import LocalObjectStore
from mhs.data.queue import JobQueue
from mhs.web.household.inbound import address_for, household_for
from mhs.web.household.intake import Intake
from mhs.web.household.mail import handle_message
from tests.pdfs import make_image, make_pdf
from tests.test_r1_scenarios import EOB, Member

pytestmark = pytest.mark.postgres

STATEMENT_HTML = """<html><body><p>Example Dermatology</p>
<table><tr><td>Statement date:</td><td>10/01/2026</td></tr><tr><td>Patient:</td><td>Pat Example</td></tr>
<tr><td>Amount due:</td><td>$320.00</td></tr></table><p>Please pay this amount by 10/31/2026.</p></body></html>"""


@pytest.fixture
def member(household, app_db, worker_db):
    return Member(household, app_db, worker_db)


@pytest.fixture
def intake(household, app_db, app_keyring, vault_client) -> Intake:
    return Intake(app_db, app_keyring, LocalObjectStore(household.objects_dir), vault_client, JobQueue(app_db))


def message(sender: str, to: str, subject: str = "Fwd: bill", body: str = "See attached.",
            html: str | None = None, attachments=()) -> bytes:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = sender, to, subject
    m.set_content(body)
    if html:
        m.add_alternative(html, subtype="html")
    for name, data, maintype, subtype in attachments:
        m.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return m.as_bytes()


def uploads(member) -> list[dict]:
    return member.client.get("/api/uploads").json()


def test_tc_ing_01_4_one_document_per_attachment(member, intake, app_db):
    to = address_for(app_db, member.who.household_id)
    raw = message(member.who.email, to, attachments=[
        ("eob.pdf", make_pdf(EOB), "application", "pdf"),
        ("photo.png", make_image("Amount billed: $80.00"), "image", "png"),
        ("letter.docx", b"PK\x03\x04", "application", "octet-stream")])
    assert handle_message(raw, to, intake) == (250, "2 document(s) received")
    member.work()
    got = {u["filename"]: u for u in uploads(member)}
    assert set(got) == {"eob.pdf", "photo.png"}  # the .docx isn't a document the app reads
    assert got["eob.pdf"]["status"] == "review" and got["eob.pdf"]["doc_type"] == "eob"
    assert member.store.get("original", got["eob.pdf"]["id"])["via"] == "email"
    assert member.client.get(f"/uploads/{got['eob.pdf']['id']}").content == make_pdf(EOB)  # the original, unchanged


def test_tc_ing_01_4_a_statement_in_the_body_is_captured(member, intake, app_db):
    to = address_for(app_db, member.who.household_id)
    assert handle_message(message(member.who.email, to, html=STATEMENT_HTML), to, intake)[0] == 250
    member.work()
    [upload] = uploads(member)
    assert upload["filename"] == "email-body.html" and upload["doc_type"] == "provider_statement"
    text, values = member.review(upload["id"])
    assert values["balance_due"] == "320.00" and values["statement_date"] == "2026-10-01"
    assert "tok_" not in text


def test_a_forwarded_message_with_the_pdf_inside(member, intake, app_db):
    to = address_for(app_db, member.who.household_id)
    inner = EmailMessage()
    inner["From"], inner["Subject"] = "billing@example-dermatology.test", "Your statement"
    inner.set_content("Your statement is attached.")
    inner.add_attachment(make_pdf(EOB), maintype="application", subtype="pdf", filename="statement.pdf")
    outer = EmailMessage()
    outer["From"], outer["To"], outer["Subject"] = member.who.email, to, "Fwd: Your statement"
    outer.set_content("Forwarding.")
    outer.add_attachment(inner)
    assert handle_message(outer.as_bytes(), to, intake) == (250, "1 document(s) received")


def test_tc_ing_01_4_unknown_senders_are_rejected(household, app_db, worker_db, member, intake):
    to = address_for(app_db, member.who.household_id)
    pdf = [("eob.pdf", make_pdf(EOB), "application", "pdf")]
    assert handle_message(message("stranger@example.test", to, attachments=pdf), to, intake)[0] == 550
    other = Member(household, app_db, worker_db, "Other household")
    assert handle_message(message(other.who.email, to, attachments=pdf), to, intake)[0] == 550  # not this household
    assert handle_message(message(member.who.email, "nobody@inbound.mhs.local", attachments=pdf),
                          "nobody@inbound.mhs.local", intake) == (550, "No such mailbox")
    assert uploads(member) == [] and uploads(other) == []


def test_messages_without_documents_are_refused(member, intake, app_db):
    to = address_for(app_db, member.who.household_id)
    newsletter = "<html><body><p>Our office will be closed on Monday. Have a nice weekend!</p></body></html>"
    assert handle_message(message(member.who.email, to, html=newsletter), to, intake)[0] == 550
    pdf = [("eob.pdf", make_pdf(EOB), "application", "pdf")]
    assert handle_message(message(member.who.email, to, attachments=pdf), to, intake)[0] == 250
    again = handle_message(message(member.who.email, to, attachments=pdf), to, intake)
    assert again[0] == 550  # the same file again is a duplicate (TC-ING-07-1)
    assert len(uploads(member)) == 1


def test_each_household_has_its_own_address(household, app_db, worker_db, member):
    other = Member(household, app_db, worker_db, "Other household")
    a, b = address_for(app_db, member.who.household_id), address_for(app_db, other.who.household_id)
    assert a != b and a == address_for(app_db, member.who.household_id)  # stable
    assert household_for(app_db, a.upper()) == member.who.household_id and household_for(app_db, "x@elsewhere") is None
    assert a in member.client.get("/uploads").text
