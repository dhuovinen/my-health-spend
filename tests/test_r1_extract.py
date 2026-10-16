"""Pure rules behind uploads: amounts and dates (ING-03), identifier scrubbing and normalization (PRV-01 to 04),
classification and extraction (ING-02 to 04). No database."""

import pytest

from mhs.ingest.extract import classify, extract
from mhs.ingest.scrub import Scrubber, normalize
from mhs.ingest.values import parse_amount, parse_date_range
from mhs.vault.store import new_token


@pytest.mark.parametrize("text,cents", [("$1,234.56", 123456), ("1234.56", 123456), ("(45.00)", -4500),
                                        ("-45.00", -4500), ("45.00 CR", -4500), ("$0.00", 0), ("n/a", None)])
def test_tc_ing_03_4_amounts(text, cents):
    assert parse_amount(text) == cents


def test_tc_ing_03_2_date_of_service_range():
    assert parse_date_range("Dates of service: 03/01/2026 - 03/04/2026") == ("2026-03-01", "2026-03-04")
    x = extract("EXPLANATION OF BENEFITS\nDates of service: 03/01/2026 through 03/04/2026\nAmount billed: $10.00")
    assert (x.fields["service_start"].value, x.fields["service_end"].value) == ("2026-03-01", "2026-03-04")


def test_tc_ing_03_3_missing_fields_are_not_guessed():
    x = extract("Example Clinic\nStatement date: 10/01/2026\nAmount due: $20.00\n")
    assert x.fields["account_number"].value is None and x.fields["account_number"].note == "not on document"
    assert x.fields["account_number"].confidence == 0


def test_tc_ing_04_2_no_invented_lines():
    x = extract("Example Clinic\nStatement date: 10/01/2026\nAmount due: $20.00\n")
    assert x.lines == []


def test_tc_ing_02_2_statement_and_itemized_bill():
    assert classify("Example Hospital\nStatement date: 10/01/2026\nAmount due: $20.00\nPlease pay")[0] == "provider_statement"
    itemized = ("Example Hospital ITEMIZED STATEMENT\nRev code CPT Units\n0450 99284 1 $900.00\n"
                "HCPCS J1885 2 $40.00\nAmount due: $940.00")
    assert classify(itemized)[0] == "itemized_bill"


def test_tc_ing_02_3_not_a_bill_is_an_eob():
    text = "Example Health\nTHIS IS NOT A BILL\nStatement date: 10/01/2026\nAmount due: $45.00\nPlease pay"
    assert classify(text)[0] == "eob"


def test_other_types_are_recognised():
    assert classify("Example Health Savings Account\nBeginning balance $1.00\nContribution\nEnding balance")[0] == "hsa_statement"
    assert classify("Example Pharmacy\nRx # 12345 Refill 2 Qty 30")[0] == "pharmacy_receipt"
    assert classify("GOOD FAITH ESTIMATE\nExpected charges $1,200.00\nNo Surprises Act")[0] == "good_faith_estimate"
    assert classify("Hello there")[0] == "other"


@pytest.fixture
def scrubber():
    tokens: dict = {}
    return Scrubber(lambda kind, value: tokens.setdefault((kind, value), new_token()), ["Pat Example"]), tokens


def test_tc_prv_03_1_one_token_per_person_and_member_id(scrubber):
    s, tokens = scrubber
    for text in ("Patient: PAT A. EXAMPLE", "Patient: Example, Pat", "Patient: pat  example",
                 "Member ID: W123-456-789", "Member ID: W123456789"):
        s.scrub(text)
    assert sorted(k for k, _ in tokens) == ["member_id", "name"]


def test_tc_prv_03_3_and_02_2_different_people_stay_apart():
    assert normalize("name", "John Smith") != normalize("name", "Joan Smith")
    assert normalize("name", "John Smith Sr.") != normalize("name", "John Smith Jr")


def test_tc_prv_04_2_free_text_identifiers_are_replaced(scrubber):
    s, _ = scrubber
    text = ("Dear Pat Example, we called 555-201-3344 and wrote to pat@example.com about account 556677.\n"
            "Account #: 556677\nDOB: 01/02/1970\nSSN: 123-45-6789\nMail: 12 Elm Street, Apt 4")
    out = s.scrub(text).text
    for value in ("Pat Example", "555-201-3344", "pat@example.com", "556677", "01/02/1970",
                  "123-45-6789", "12 Elm Street"):
        assert value not in out, value
    assert out.count("tok_") >= 7


def test_tc_prv_01_3_tokens_are_random_and_unique():
    tokens = {new_token() for _ in range(1000)}
    assert len(tokens) == 1000 and all(t.startswith("tok_") and len(t) == 30 for t in tokens)


def test_scrubbing_leaves_amounts_dates_and_providers():
    s = Scrubber(lambda kind, value: new_token(), [])
    text = "Provider: Example Dermatology\nDate of service: 09/28/2026\nAmount billed: $320.00\nClaim number: C-1"
    assert s.scrub(text).text == text


def test_practice_ledger_statement_layout():
    """The statement layout Release 0's converter reads, ported to the worker (synthetic text in that layout)."""
    text = "\n".join([
        "Example Retina Specialists (PAR) Statement Date",
        "10/01/2026 12345 $40.00",
        "tok_aaaaaaaaaaaaaaaaaaaaaaaaaa Last Appt Date: 09/15/2026",
        "09/15/2026 Jane Doe, MD Office visit $200.00 $40.00",
        "Example Health states a coinsurance of $40.00",
        "(Insurance Adjustment) Example Health",
        "contractual $60.0009/20/2026",
        "Example Health $100.0009/22/2026",
        "09/16/2026 Imaging $50.00 $0.00",
        "Visa $50.0009/30/2026",
        "Due From Patient: $40.00",
    ])
    x = extract(text, forced_type="provider_statement")
    assert x.layout == "statement: practice ledger layout"
    f = x.fields
    assert (f["provider"].value, f["statement_date"].value, f["balance_due"].value) == (
        "Example Retina Specialists (PAR)", "2026-10-01", 4000)
    assert f["patient"].value.startswith("tok_") and f["network_status"].value == "in_network"
    first, second = x.lines
    assert (first["rendering_provider"], first["charge"], first["adjustment"], first["insurance_paid"],
            first["patient_amount"], first["balance"]) == ("Jane Doe, MD", 20000, 6000, 10000, 4000, 4000)
    assert (second["patient_paid"], second["balance"]) == (5000, 0)
    assert x.warnings == []
