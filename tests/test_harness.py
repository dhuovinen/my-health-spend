"""The test harness's conversions and comparison and its generated PDFs (tools/), without a stack."""

import csv
import importlib.util
import io
import re
from pathlib import Path

from mhs.ingest.text import read_pdf
from tests.pdfs import make_pdf

ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


harness = load("run_harness")
generator = load("make_harness_pdfs")


def row(**over) -> dict:
    base = {"Member_Name": "Pat Example", "Member_Relationship": "Spouse", "Date_of_Service": "2026-03-01",
            "Provider_Name": "Dr. A, MD", "Billed_Charge": "100", "Negotiated_Allowed_Amount": "80",
            "Insurance_Paid_Amount": "60", "Member_Deductible": "20", "Member_Copay": "0", "Member_Coinsurance": "0",
            "Total_Member_Responsibility": "20", "EOB_Claim_Number": "C1", "EOB_Adjudication_Date": "2026-03-10",
            "HSA_Transaction_ID": "H1", "HSA_Payment_Date": "2026-03-20", "HSA_Amount_Paid": "20",
            "Reconciliation_Match_Status": "Fully Reconciled"}
    return base | over


def rows_of(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def test_service_codes_add_up_to_one_claim_and_a_second_provider_keeps_its_own():
    rows = [row(), row(Billed_Charge="50", Total_Member_Responsibility="5", HSA_Amount_Paid="5"),
            row(Provider_Name="Lab B")]
    claims = rows_of(harness.claims_csv(rows))
    assert [(c["Claim Number"], c["Provider"], c["Billed"], c["You Owe"]) for c in claims] == [
        ("C1", "Dr. A, MD", "150.00", "25.00"), ("C1-2", "Lab B", "100.00", "20.00")]


def test_hsa_payments_are_added_up_per_transaction_in_the_export_layout():
    rows = [row(), row(HSA_Amount_Paid="5"), row(HSA_Transaction_ID="", HSA_Payment_Date="", HSA_Amount_Paid="0")]
    assert rows_of(harness.hsa_csv(rows)) == [{"Date": "2026-03-20", "Description": "Payment to Dr. A MD",
                                               "Amount": "-25.00"}]


def test_a_second_tranche_is_a_payment_not_a_charge():
    tranche = row(Billed_Charge="0", Negotiated_Allowed_Amount="0", Insurance_Paid_Amount="0", HSA_Transaction_ID="H2",
                  HSA_Amount_Paid="10", Total_Member_Responsibility="10")
    [visit] = harness.expected_visits([row(Reconciliation_Match_Status="Partially Reconciled / Multi-Tranche"), tranche])
    assert (visit["owed"], visit["paid"]) == (2000, 3000)
    assert len(rows_of(harness.claims_csv([row(), tranche]))) == 1


def test_the_worst_status_of_a_visits_rows_is_what_it_should_show():
    rows = [row(), row(Reconciliation_Match_Status="Unreconciled / Out-of-Pocket Direct")]
    [visit] = harness.expected_visits(rows)
    assert visit["expected"].startswith("Unreconciled") and "balance_outstanding" in visit["accept"]


def test_compare_reports_each_difference_and_what_nobody_expected():
    expected = [{"date": "2026-03-01", "provider": "Dr. A", "member": "Pat", "owed": 2000, "paid": 2000,
                 "expected": "Fully Reconciled", "accept": ["complete"]},
                {"date": "2026-03-02", "provider": "Dr. A", "member": "Pat", "owed": 0}]
    actual = [{"date": "2026-03-01", "provider": "DR. A, MD", "member": "Pat", "owed": 2500, "paid": 2000,
               "status": "discrepancy", "label": "Discrepancy found"},
              {"date": "2026-03-09", "provider": "Other", "member": "Pat", "owed": 0, "paid": 0, "status": "complete",
               "label": "Complete"}]
    rows, extra = harness.compare(expected, actual)
    assert rows[0]["problems"] == ["owed $25.00, expected $20.00", "status Discrepancy found, expected Fully Reconciled"]
    assert rows[1]["problems"] == ["no such visit in the app"]
    assert [v["provider"] for v in extra] == ["Other"]


def test_the_same_day_and_provider_for_another_person_is_not_a_match():
    expected = [{"date": "2026-03-01", "provider": "Dr. A", "member": "Sam", "owed": 0}]
    actual = [{"date": "2026-03-01", "provider": "Dr. A", "member": "Pat", "owed": 0, "paid": 0, "status": "complete",
               "label": "Complete"}]
    assert harness.compare(expected, actual)[0][0]["ok"] is False


def test_the_committed_data_set_is_read_as_documented():
    folder = ROOT / "samples" / "harness"
    rows = harness.read_master(next(folder.glob("*.csv")).read_text(encoding="utf-8-sig"))
    assert len(rows) == 52 and len(rows[0]) == 28
    assert harness.is_tranche(next(r for r in rows if r["HSA_Transaction_ID"] == "HSA-HEN-8003B"))
    assert {m["relationship"] for m in harness.members_of(rows)} == {"self", "spouse", "child"}


def test_an_invoice_can_match_under_its_practitioner_or_its_facility():
    expected = [{"date": "2026-03-01", "provider": "Dr. A", "match": ["Dr. A", "Children's Clinic"], "member": "Pat",
                 "owed": 500, "paid": None, "accept": None}]
    actual = [{"date": "2026-03-01", "provider": "Children\u2019s Clinic", "member": None, "owed": 500, "paid": 0,
               "status": "discrepancy", "label": "Discrepancy found"}]
    assert harness.compare(expected, actual)[0][0]["ok"] is True


def test_the_pdf_households_expect_one_visit_per_invoice_at_its_amount_due():
    rows = generator.read_master()
    visits = harness.expected_from_invoices([r for r in rows if r["Family"] == "The Trumans"], generator.documents(rows))
    [ankle] = [v for v in visits if v["provider"] == "Tri-County Orthopedics"]
    assert ankle["owed"] == 27500  # $340.00 less the $65.00 paid by personal card
    assert len(visits) == 15


# ---------- the generated PDFs say what the CSV says ----------

PDFS = ROOT / "samples" / "harness" / "pdfs"


def text_of(name: str) -> str:
    return "\n".join(read_pdf((PDFS / name).read_bytes())).replace("\u2019", "'")


def amount(text: str, label: str) -> int:
    return round(float(re.search(rf"{label}: (-?)\$([\d,.]+)", text).group(2).replace(",", "")) * 100)


def test_the_pdfs_are_exactly_what_the_generator_writes():
    docs = generator.documents(generator.read_master())
    assert {p.name for p in PDFS.glob("*.pdf")} == set(docs)
    assert len(docs) == 47
    for name, pages in docs.items():
        assert (PDFS / name).read_bytes() == make_pdf(*pages), name
        assert all(len(line) <= 118 for page in pages for line in page.splitlines()), f"{name}: a line runs off the page"


def test_every_invoice_has_the_csvs_charges_and_adds_up():
    rows = generator.read_master()
    groups = {}
    for r in rows:
        groups.setdefault(r["Provider_Invoice_Asset_PDF"], []).append(r)
    for name, group in groups.items():
        text, charges = text_of(name), [r for r in group if not generator.is_tranche(r)]
        assert charges[0]["Member_Name"].split()[0] in text and charges[0]["Provider_Name"].replace("\u2019", "'") in text
        assert generator.us_date(charges[0]["Date_of_Service"]) in text
        for r in charges:
            assert r["CPT_HCPCS_Code"] in text and r["EOB_Claim_Number"] in text
        assert amount(text, "Total charges") == generator.total(charges, "Billed_Charge"), name
        assert amount(text, "Allowed amount") == generator.total(charges, "Negotiated_Allowed_Amount"), name
        assert amount(text, "Insurance payments") == generator.total(charges, "Insurance_Paid_Amount"), name
        owed = generator.total(charges, "Total_Member_Responsibility")
        assert amount(text, "Patient responsibility") == owed, name
        received = sum(round(float(m.replace(",", "")) * 100) for m in re.findall(r"Payment received.*: -\$([\d,.]+)", text))
        assert amount(text, "Amount due") == owed - received, name


def test_each_eob_lists_every_claim_row_and_its_totals_add_up():
    rows = generator.read_master()
    for family in ("The Trumans", "The Hendersons"):
        part = [r for r in rows if r["Family"] == family]
        charges = [r for r in part if not generator.is_tranche(r)]
        text = text_of(part[0]["Insurance_EOB_Asset_PDF"])
        for r in charges:
            assert f"{generator.us_date(r['Date_of_Service'])} {r['EOB_Claim_Number']} {r['Member_Name']}" in text
        owed = [round(float(m.replace(",", "")) * 100) for m in re.findall(r"You owe \$([\d,.]+)", text)]
        assert len(owed) == len(charges) and sum(owed) == generator.total(charges, "Total_Member_Responsibility")
        assert amount(text, "Total you owe") == sum(owed)
        assert amount(text, "Total billed") == generator.total(charges, "Billed_Charge")


def test_each_hsa_statement_has_every_payment():
    rows = generator.read_master()
    expected = {"The Trumans": 80900}
    for family in ("The Trumans", "The Hendersons"):
        part = [r for r in rows if r["Family"] == family]
        text = text_of(part[0]["HSA_Statement_Asset_PDF"])
        paid = generator.total(part, "HSA_Amount_Paid")
        assert amount(text, "Total disbursements") == expected.get(family, paid)
        for r in part:
            if r["HSA_Transaction_ID"]:
                assert f"{generator.us_date(r['HSA_Payment_Date'])} {r['HSA_Transaction_ID']}" in text
