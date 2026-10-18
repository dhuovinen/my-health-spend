"""The HSA and tax page and the visit page's tax section (ADR-043), on both apps, with the synthetic household in
samples/tax-ingest.json (tools/make_tax_sample.py). The engine's cases are in tests/test_tax.py.

Web tests run on the real date, so they ask for year 2026 explicitly and don't assert advice that depends on how
many days are left in the year.
"""

import json
import re

import pytest

from mhs.core.tax import DISCLAIMER
from tests.test_r1_pages import member, upload_import
from tests.test_tax import SAMPLE
from tests.test_web import web  # noqa: F401  (the fixture: both apps)
from tests.pdfs import make_pdf

VITAMINS = "v-2026-04-11-vitamins"
MASSAGE = "v-2026-05-02-massage"
EYE = "v-2026-08-20-eye"
DISCLAIMER_HTML = DISCLAIMER.replace("'", "&#39;")


def import_tax_sample(web, path=SAMPLE):
    preview = web.import_preview(path)
    assert preview.status_code == 200 and "What will change" in preview.text, preview.text[:2000]
    token = preview.text.split('name="token" value="')[1].split('"')[0]
    assert web.client.post("/import/confirm", data={"token": token}, follow_redirects=False).status_code == 303


def section(html: str, section_id: str) -> str:
    m = re.search(rf'<section[^>]*id="{section_id}"[^>]*>(.*?)</section>', html, re.S)
    assert m, section_id
    return m.group(1)


def test_tax_page_shows_the_year(web):
    """TAX-04, TAX-06, TAX-07, TAX-09, TAX-10 on one page, each suggesting block with the disclaimer (TC-CMP-04-1)."""
    import_tax_sample(web)
    html = web.client.get("/tax?year=2026").text
    summary = section(html, "summary")
    assert "Year-end summary for 2026" in summary and "$474.00" in summary  # HSA distributions
    assert "Jamie Example" in summary and "Not matched to a visit" in summary and "Vitamins and supplements" in summary
    assert "7.5% of your adjusted gross income" in summary and "isn't advice to itemize" in summary
    vault = section(html, "vault")
    assert 'id="vault-total">$330.00<' in vault and "reimbursement opportunities" in vault
    assert "Reimbursed Jan 15, 2026" in vault
    contributions = section(html, "contributions")
    assert "Excess contribution" in contributions and "$300.00" in contributions and "$7,575.00" in contributions
    assert "Account fees in 2026: <strong>$2.00</strong> (Paper statement fee, Paper statement fee)" in contributions
    flags = section(html, "flags")
    assert "likely not a qualified expense" in flags and "Jamie Example isn&#39;t your tax dependent in 2026" in flags
    for block in ("summary", "vault", "flags", "pay"):
        assert DISCLAIMER_HTML in section(html, block), block
    assert DISCLAIMER_HTML in html.split('id="disclaimer"')[1][:1000]
    assert 'href="/tax"' in web.client.get("/").text  # in the nav, and linked from Home's HSA card


def test_tc_tax_07_3_guidance_only_after_the_member_marks_a_mistake_with_the_disclaimer(web):
    import_tax_sample(web)
    page = web.client.get(f"/visits/{VITAMINS}").text
    assert 'id="tax"' in page and "Likely not qualified" in page and "Nutritional Supplements" in page
    assert "mistaken distribution" not in page
    r = web.client.post(f"/visits/{VITAMINS}/tax", data={"mistake": "on"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/visits/{VITAMINS}#tax"
    page = web.client.get(f"/visits/{VITAMINS}").text
    tax_section = page.split('id="tax"')[1].split('id="lines"')[0]
    assert "mistaken distribution" in tax_section and DISCLAIMER_HTML in tax_section
    assert "mistaken distribution" in section(web.client.get("/tax?year=2026").text, "flags")


def test_member_category_and_letter_on_a_visit_are_kept_on_reimport(web):
    """TAX-01: the member's category and "letter on file" are member edits (ADR-011)."""
    import_tax_sample(web)
    assert "Needs documentation" in web.client.get(f"/visits/{MASSAGE}").text
    web.client.post(f"/visits/{MASSAGE}/tax", data={"documentation": "on"})
    page = web.client.get(f"/visits/{MASSAGE}").text
    assert "Needs documentation (letter on file)" in page
    web.client.post(f"/visits/{VITAMINS}/tax", data={"category": "medicines"})
    assert "(your choice)" in web.client.get(f"/visits/{VITAMINS}").text
    import_tax_sample(web)  # without "Replace my edits"
    assert web.store.get("visit", VITAMINS)["tax"] == {"category": "medicines", "version": "pub502-2025"}
    assert web.store.get("visit", MASSAGE)["tax"] == {"documentation": True}
    # the letter makes the massage a qualified expense: its card payment joins the vault
    assert 'id="vault-total">$420.00<' in web.client.get("/tax?year=2026").text
    assert web.client.post(f"/visits/{VITAMINS}/tax", data={"category": "nonsense"}).status_code == 400


def test_tc_tax_04_3_reimbursed_once_from_the_vault(web):
    import_tax_sample(web)
    r = web.client.post(f"/tax/reimburse/pay-2026-08-20-eye", data={"date": "2026-10-01", "year": "2026"},
                        follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/tax?year=2026&saved=vault#vault"
    html = web.client.get("/tax?year=2026").text
    assert 'id="vault-total">$120.00<' in html and "Reimbursed Oct 1, 2026" in html
    again = web.client.post(f"/tax/reimburse/pay-2026-08-20-eye", data={"year": "2026"})
    assert again.status_code == 400 and "can&#39;t be reimbursed twice" in again.text
    [reimb] = [d for d in web.store.all("document") if d["id"] == "reimb-pay-2026-08-20-eye"]
    assert (reimb["from_account_id"], reimb["amount"], reimb["payment_ids"]) == ("acct-hsa", 21000, ["pay-2026-08-20-eye"])
    # the reconciliation's own HSA flag agrees: the payment now counts as reimbursed from the HSA
    assert "outside the HSA" not in web.client.get(f"/visits/{EYE}").text.split('id="tax"')[0]
    assert web.client.post("/tax/reimburse/pay-2026-02-05-pcp", data={}).status_code == 404  # not in the vault


def test_tc_tax_03_2_strategy_setting_changes_the_vault_and_the_advice(web):
    import_tax_sample(web)
    assert web.client.post("/tax/strategy", data={"hsa_strategy": "save_for_later"}, follow_redirects=False).status_code == 303
    html = web.client.get("/tax?year=2026").text
    assert "savings banked for later" in section(html, "vault")
    assert "keep the receipt" in section(html, "pay")
    assert web.client.post("/tax/strategy", data={"hsa_strategy": "spend_it"}).status_code == 400


def test_account_rules_people_and_the_contribution_rule(web):
    """TAX-02, TAX-06, TAX-09 forms; account and member fields are Settings data (written to settings.json)."""
    import_tax_sample(web)
    bad = web.client.post("/tax/accounts/acct-lpfsa", data={"type": "lpfsa", "plan_year": "2026", "grace_period": "on",
                                                           "carryover": "100", "year": "2026", "rules": "1"})
    assert bad.status_code == 400 and "grace period or a carryover, not both" in bad.text
    ok = web.client.post("/tax/accounts/acct-lpfsa", data={
        "type": "lpfsa", "plan_year": "2026", "grace_period": "on", "carryover": "", "run_out_end": "2027-03-31",
        "balance": "250", "balance_as_of": "2026-10-10", "member_ids": ["mem-robin", "mem-casey"], "rules": "1"},
        follow_redirects=False)
    assert ok.status_code == 303
    lpfsa = next(a for a in web.settings_json()["accounts"] if a["id"] == "acct-lpfsa")
    assert lpfsa["grace_period"] is True and lpfsa["balance"] == 250 and "carryover" not in lpfsa
    assert "through Mar 15, 2027" in section(web.client.get("/tax?year=2026").text, "accounts")
    web.client.post("/tax/accounts/acct-hsa", data={"type": "hsa", "opened": "2025-03-01", "member_ids": "mem-robin",
                                                    "coverage": "2026-01-01 to 2026-12-31: family", "rules": "1"})
    hsa = web.store.get("account", "acct-hsa")
    assert hsa["coverage"] == [{"type": "family", "start": "2026-01-01", "end": "2026-12-31"}]
    assert hsa["opened"] == "2025-03-01" and hsa["member_ids"] == ["mem-robin"]
    bad = web.client.post("/tax/accounts/acct-hsa", data={"type": "hsa", "coverage": "all year family please", "rules": "1"})
    assert bad.status_code == 400 and "Coverage line" in bad.text
    # Jamie becomes a 2026 dependent: the HSA may pay for the urgent care visit after all (TC-TAX-09-3)
    web.client.post("/tax/members/mem-jamie", data={"birth_year": "2002", "dep-2025": "yes", "dep-2026": "yes"})
    assert web.store.get("member", "mem-jamie")["tax_dependent"] == {"2025": True, "2026": True}
    assert "Jamie Example isn&#39;t your tax dependent" not in web.client.get("/tax?year=2026").text
    assert web.client.post("/tax/members/mem-jamie", data={"birth_year": "twenty"}).status_code == 400
    # the last-month rule for 2026: the full family limit plus catch-up, with the testing-period warning
    web.client.post("/tax/contribution-rule/acct-hsa", data={"year": "2026", "rule": "last_month"})
    contributions = section(web.client.get("/tax?year=2026").text, "contributions")
    assert "last-month rule" in contributions and "$9,750.00" in contributions and "testing period" in contributions
    assert "Excess contribution" not in contributions
    assert web.store.get("account", "acct-hsa")["last_month_rule_years"] == [2026]


def test_tc_tax_04_4_vault_receipt_is_the_unchanged_original(web, tmp_path):
    """ING-10: the receipt behind a vault entry opens byte for byte as it was imported."""
    data = json.loads(SAMPLE.read_text())
    receipt = make_pdf("Example Eye Care", "Eye exam and eyeglasses  $210.00")
    next(d for d in data["documents"] if d["id"] == "rcpt-2026-08-20-eye")["file"] = "files/eye-receipt.pdf"
    (tmp_path / "files").mkdir()
    (tmp_path / "files" / "eye-receipt.pdf").write_bytes(receipt)
    path = tmp_path / "tax-ingest.json"
    path.write_text(json.dumps(data))
    import_tax_sample(web, path)
    vault = section(web.client.get("/tax?year=2026").text, "vault")
    assert 'href="/files/rcpt-2026-08-20-eye"' in vault
    assert web.client.get("/files/rcpt-2026-08-20-eye").content == receipt


def test_tax_pages_with_no_hsa_and_no_data(web):
    html = web.client.get("/tax").text
    assert "No HSA yet" in html and "Nothing in the vault" in html
    assert web.client.post("/tax/accounts/nope", data={"type": "hsa"}).status_code == 404
    assert web.client.post("/tax/members/nope", data={}).status_code == 404
    assert web.client.post("/visits/nope/tax", data={}).status_code == 404


@pytest.mark.postgres
def test_tax_page_and_forms_belong_to_their_household(household, app_db):
    a, ca = member(household, "Household A")
    b, cb = member(household, "Household B")
    upload_import(ca, json.loads(SAMPLE.read_text()))
    assert "Robin Example" in ca.get("/tax?year=2026").text
    html = cb.get("/tax?year=2026").text
    assert "Robin Example" not in html and "acct-hsa" not in html
    assert cb.post("/tax/accounts/acct-hsa", data={"type": "hsa"}).status_code == 404
    assert cb.post("/tax/members/mem-robin", data={"birth_year": "1900"}).status_code == 404
    assert cb.post("/tax/reimburse/pay-2026-08-20-eye", data={}).status_code == 404
    assert cb.post(f"/visits/{VITAMINS}/tax", data={"mistake": "on"}).status_code == 404


def test_making_a_card_an_fsa_changes_only_its_type(web):
    """The "make another account an FSA or HRA" form sends the type only; fields set elsewhere are kept."""
    import_tax_sample(web)
    card = web.store.get("account", "acct-card")
    web.store.upsert("account", {**card, "plan_year": 2026, "notes": "kept"})
    web.client.post("/tax/accounts/acct-card", data={"type": "hra"})
    card = web.store.get("account", "acct-card")
    assert (card["type"], card["plan_year"], card["notes"]) == ("hra", 2026, "kept")


def test_a_payment_reimbursed_in_part_stays_open_for_the_rest(web):
    import_tax_sample(web)
    eye = "pay-2026-08-20-eye"
    web.store.upsert("document", {"id": "reimb-part", "type": "account_reimbursement", "date": "2026-09-01",
                                  "from_account_id": "acct-hsa", "amount": 10000, "payment_ids": [eye]})
    html = web.client.get("/tax?year=2026").text
    assert 'id="vault-total">$230.00<' in html and "$110.00 left" in html
    assert web.client.post(f"/tax/reimburse/{eye}", data={"date": "2026-10-01"}, follow_redirects=False).status_code == 303
    second = web.store.get("document", f"reimb-{eye}")
    assert second["amount"] == 11000
    assert 'id="vault-total">$120.00<' in web.client.get("/tax?year=2026").text
