"""PRV-05 date shifting for content sent to the AI service (ADR-022, ADR-034 condition): TC-PRV-05-1 and TC-PRV-05-2."""

import json
import re
from datetime import date

import pytest

from mhs.ingest.dates import MAX_DAYS, MIN_DAYS, new_offset, person_key, shift_text, unshift_extraction
from mhs.ingest.values import DATE_IN_TEXT, parse_date
from tests.pdfs import make_pdf
from tests.test_r1_scenarios import EOB, IDENTIFIERS, member  # noqa: F401 - the member fixture

TOKEN_A = "tok_aaaaaaaaaaaaaaaaaaaaaaaaaa"
TOKEN_B = "tok_bbbbbbbbbbbbbbbbbbbbbbbbbb"


def dates_in(text: str) -> list[str]:
    return [d for d in (parse_date(m) for m in DATE_IN_TEXT.findall(text)) if d]


@pytest.mark.parametrize("days", [MIN_DAYS, -MIN_DAYS, 200, -MAX_DAYS])
def test_shifting_keeps_formats_and_intervals_and_reverses(days):
    text = ("Date of service: 09/28/2026   Follow-up 9/5/2026   Processed 2026-10-12\n"
            "Statement dated Sep 28, 2026 and September 3, 2026; due 12/30/26; amount $45.00; ref 13/45/2026")
    shifted = shift_text(text, days)
    assert shift_text(shifted, -days) == text
    real, moved = dates_in(text), dates_in(shifted)
    assert len(real) == len(moved) and all(
        (date.fromisoformat(b) - date.fromisoformat(a)).days == days for a, b in zip(real, moved))
    assert "$45.00" in shifted and "13/45/2026" in shifted  # amounts and impossible dates untouched


def test_tc_prv_05_1_interval_between_visits_is_kept():
    days = new_offset()
    first, second = shift_text("09/01/2026", days), shift_text("09/15/2026", days)
    gap = (date.fromisoformat(parse_date(second)) - date.fromisoformat(parse_date(first))).days
    assert gap == 14


def test_offsets_are_random_and_never_small():
    offsets = {new_offset() for _ in range(200)}
    assert len(offsets) > 50 and all(MIN_DAYS <= abs(d) <= MAX_DAYS for d in offsets)
    assert any(d < 0 for d in offsets) and any(d > 0 for d in offsets)


def test_person_key_prefers_the_patient():
    assert person_key(f"Provider: X\nGuarantor: {TOKEN_B}\nPatient: {TOKEN_A}") in (TOKEN_A, TOKEN_B)
    assert person_key(f"Patient: {TOKEN_A}\nMember ID: {TOKEN_B}") == TOKEN_A
    assert person_key(f"Dear {TOKEN_B}, about your visit") == TOKEN_B
    assert person_key("no tokens here") == "household"


def test_unshifting_an_answer():
    record = {"fields": {"service_start": {"value": "2027-01-29"}, "billed": {"value": 100}},
              "lines": [{"service_date": "2027-01-29"}], "warnings": ["Visit on 01/29/2027 looks odd"]}
    unshift_extraction(record, 30, ("service_start",))
    assert record["fields"]["service_start"]["value"] == "2026-12-30" and record["fields"]["billed"]["value"] == 100
    assert record["lines"][0]["service_date"] == "2026-12-30" and record["warnings"] == ["Visit on 12/30/2026 looks odd"]


def ai_extract(member, accounts, text: str, name: str):
    from mhs.data.queue import JobQueue
    from mhs.ingest.worker import make_handlers, run_once
    from tests.test_r1_ai import RecordedAi

    accounts.set_ai_extraction(member.who.household_id, True)
    uid = member.upload_id(member.upload(name, make_pdf(text)))
    ai = RecordedAi("eob")
    assert run_once(JobQueue(member.worker_db), member.worker_db, make_handlers(ai.extractor),
                    kinds=["ping", "extract", "extract_ai"])
    (request,) = ai.requests
    return uid, request["body"]["messages"][0]["content"]


@pytest.mark.postgres
def test_tc_prv_05_2_year_end_visit_keeps_its_real_date(member, accounts):  # noqa: F811
    """A visit on 2026-12-30: the AI request carries the person's shifted date; the records keep 2026-12-30."""
    eob = EOB.replace("09/28/2026", "12/30/2026").replace("10/05/2026", "01/06/2027")
    uid, sent = ai_extract(member, accounts, eob, "year-end.pdf")
    assert "12/30/2026" not in sent and "01/06/2027" not in sent
    shifted = dates_in(sent)[0]
    [offset] = member.store.all("date_offset")
    assert (date.fromisoformat(shifted) - date(2026, 12, 30)).days == offset["days"]
    assert all(v.lower() not in sent.lower() for v in IDENTIFIERS)
    ext = member.store.get("extraction", uid)
    assert ext["dates_shifted"] is True and ext["extractor"] == "ai"
    assert ext["fields"]["service_start"]["value"] == "2026-12-30"
    assert ext["fields"]["processed_date"]["value"] == "2027-01-06"
    assert ext["lines"][0]["service_date"] == "2026-12-30"
    assert "not found in the document text" not in json.dumps(ext["fields"]["service_start"])
    text, values = member.review(uid)
    values["visit_id"] = "new"
    r = member.confirm(uid, values)
    assert r.headers["location"] == "/visits/v-2026-12-30-example-dermatology"  # plan year 2026, not shifted


@pytest.mark.postgres
def test_tc_prv_05_1_one_offset_per_person_across_documents(member, accounts):  # noqa: F811
    """Two EOBs for the same patient, 14 days apart: one offset, so the AI sees them 14 days apart too."""
    later = EOB.replace("09/28/2026", "10/12/2026").replace("C-2026-0042", "C-2026-0043")
    _, first = ai_extract(member, accounts, EOB, "first.pdf")
    _, second = ai_extract(member, accounts, later, "second.pdf")
    gap = (date.fromisoformat(dates_in(second)[0]) - date.fromisoformat(dates_in(first)[0])).days
    assert gap == 14
    assert len(member.store.all("date_offset")) == 1
    assert re.search(r"tok_[a-z2-7]{26}", member.store.all("date_offset")[0]["id"])
