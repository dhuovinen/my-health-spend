"""ING-09 insurer connection (ADR-054): mapping CARIN Blue Button EOBs, retries, and claims already on file."""

import httpx
import pytest

from mhs.core.lines import identity_1
from mhs.data.money import to_cents
from mhs.ingest import fhir
from tests.fhir_fixtures import bundle, eob

PAYER = fhir.Payer("examplehealth", "Example Health", "https://fhir.example.test/r4", "https://auth.example.test/a",
                   "https://auth.example.test/t", "client-1")
PLANS = [{"id": "plan-2026", "plan_year": 2026, "insurer": "Example Health", "member_ids": ["mem-1"]}]


def test_tc_ing_09_2_categories_land_in_the_right_fields():
    m = fhir.map_eob(eob())
    assert (m.claim_number, m.provider, m.service_date, m.network) == ("CLM-1001", "Lakeside Family Medicine",
                                                                        "2026-03-04", "in_network")
    assert m.amounts == {"billed": 20000, "allowed": 12000, "insurer_paid": 9600, "patient_responsibility": 2400,
                         "coinsurance": 2400, "deductible": 0, "adjustment": 8000}
    assert identity_1(m.amounts) == 0  # REC-01 holds
    assert m.lines[0]["code"] == "99213"


def test_reason_codes_become_remark_codes():
    m = fhir.map_eob(eob(reason="50"))
    assert m.lines[0]["remark_codes"] == ["50"]


def test_ingest_file_is_valid_and_keeps_no_patient_identifiers():
    from mhs.data.importer import schema_errors

    res = fhir.to_ingest([eob()], PAYER, "mem-1", [], [], [], PLANS)
    assert res.read == 1 and not res.skipped
    assert schema_errors({**res.ingest, "plans": PLANS, "members": [{"id": "mem-1", "name": "M"}]}) == []
    text = str(res.ingest)
    assert "p-777" not in text and "Patient" not in text
    doc = res.ingest["documents"][0]
    assert doc["extensions"]["feed"] == "fhir" and doc["patient_responsibility"] == 24.0


def test_tc_ing_09_3_same_claim_already_uploaded_is_not_added_twice():
    on_file = to_cents({"id": "eob-clm-1001", "type": "eob", "date": "2026-03-20", "visit_id": "v1",
                        "claim_number": "clm 1001", "billed": 200, "insurer_paid": 96, "patient_responsibility": 24})
    res = fhir.to_ingest([eob()], PAYER, "mem-1", [], [{"id": "v1", "date": "2026-03-04", "provider_id": "p"}],
                         [on_file], PLANS)
    assert (res.already, "documents" in res.ingest) == (1, False)
    changed = fhir.to_ingest([eob(paid=110.0, coins=10.0)], PAYER, "mem-1", [],
                             [{"id": "v1", "date": "2026-03-04", "provider_id": "p"}], [on_file], PLANS)
    doc = changed.ingest["documents"][0]
    assert changed.versions == 1 and doc["version_of"] == "eob-clm-1001" and doc["visit_id"] == "v1"


def test_claim_without_a_plan_is_left_out_with_a_reason():
    res = fhir.to_ingest([eob(when="2025-05-01")], PAYER, "mem-1", [], [], [], PLANS)
    assert res.read == 1 and "add your 2025 plan" in res.skipped[0]


def transport(responses):
    calls = []

    def handler(request):
        calls.append(request)
        status, body, headers = responses.pop(0)
        return httpx.Response(status, json=body, headers=headers or {})
    return httpx.MockTransport(handler), calls


def test_tc_ing_09_5_retries_then_pages():
    page2 = f"{PAYER.fhir_base}/ExplanationOfBenefit?page=2"
    t, calls = transport([(429, {}, {"Retry-After": "1"}), (503, {}, None), (200, bundle([eob()], page2), None),
                          (200, bundle([eob(claim="CLM-2")]), None)])
    waits = []
    got = fhir.pull(PAYER, fhir.Grant("tok", "p-777"), httpx.Client(transport=t), sleep=waits.append)
    assert [e["id"] for e in got] == ["x-CLM-1001", "x-CLM-2"] and waits == [1, 2]
    assert calls[0].headers["authorization"] == "Bearer tok"


def test_tc_ing_09_5_gives_up_after_retries():
    t, _ = transport([(500, {}, None)] * (fhir.RETRIES + 1))
    with pytest.raises(fhir.FhirError, match="Nothing was imported"):
        fhir.pull(PAYER, fhir.Grant("tok", "p"), httpx.Client(transport=t), sleep=lambda s: None)


def test_tc_ing_09_4_withdrawn_consent_stops_the_pull():
    t, _ = transport([(401, {}, None)])
    with pytest.raises(fhir.FhirError, match="withdrawn"):
        fhir.pull(PAYER, fhir.Grant("tok", "p"), httpx.Client(transport=t), sleep=lambda s: None)


def test_next_links_only_on_the_payers_host():
    t, calls = transport([(200, bundle([eob()], "https://elsewhere.test/steal"), None)])
    fhir.pull(PAYER, fhir.Grant("tok", "p"), httpx.Client(transport=t), sleep=lambda s: None)
    assert len(calls) == 1


def test_token_exchange_needs_a_patient():
    t, _ = transport([(200, {"access_token": "a"}, None)])
    flow = fhir.Flow.new("examplehealth", "mem-1")
    with pytest.raises(fhir.FhirError):
        fhir.exchange(PAYER, flow, "code", "https://app/cb", httpx.Client(transport=t))
    t, _ = transport([(200, {"access_token": "a", "patient": "p-777"}, None)])
    assert fhir.exchange(PAYER, flow, "code", "https://app/cb", httpx.Client(transport=t)).patient == "p-777"


def test_authorization_url_has_pkce_and_audience():
    url = fhir.authorization_url(PAYER, fhir.Flow.new("examplehealth", "mem-1"), "https://app/cb")
    assert "code_challenge_method=S256" in url and "aud=https%3A%2F%2Ffhir.example.test%2Fr4" in url


def test_payers_inline_or_from_a_file(tmp_path):
    entry = [{"name": "Example Health", "label": "Example Health", "fhir_base": "https://f/r4/",
              "authorize_url": "https://a", "token_url": "https://t", "client_id": "c", "client_secret": "s"}]
    import json

    inline = fhir.payers_from(json.dumps(entry))
    assert inline[0].name == "examplehealth" and inline[0].fhir_base == "https://f/r4" and inline[0].client_secret == "s"
    f = tmp_path / "payers.json"
    f.write_text(json.dumps(entry))
    assert fhir.payers_from(str(f), lambda n: "from-env")[0].client_secret == "from-env"
    assert fhir.payers_from(None) == () and fhir.payers_from(str(tmp_path / "missing.json")) == ()
