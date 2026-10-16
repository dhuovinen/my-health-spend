"""Claude extraction (ADR-028, ADR-034) against recorded API responses: no network, no key. The recordings in
tests/fixtures/ai are Messages API responses in the shape the API returns for the request the extractor makes."""

import json
import re
from pathlib import Path

import pytest

from mhs.ingest.ai import FALLBACK_BETA, MODEL, AiConfig, AiUnavailable, ClaudeExtractor, make_client, to_extraction
from tests.test_r1_scenarios import EOB

RECORDED = Path(__file__).parent / "fixtures" / "ai"
TOKEN = "tok_aaaaaaaaaaaaaaaaaaaaaaaaaa"
SCRUBBED_EOB = EOB.replace("Pat Example", TOKEN).replace("W123-456-789", "tok_bbbbbbbbbbbbbbbbbbbbbbbbbb")


def in_request_calendar(recording: str, body: dict) -> str:
    """Answer as the model would: in the calendar of the text it was sent. PRV-05 shifts the request's dates, so
    the recording's ISO dates move by the gap between its earliest date and the request's first printed date."""
    from datetime import date, timedelta

    from mhs.ingest.values import DATE_IN_TEXT, parse_date

    sent = body["messages"][0]["content"]
    first = next((d for d in (parse_date(m) for m in DATE_IN_TEXT.findall(sent)) if d), None)
    recorded = sorted(set(re.findall(r"\d{4}-\d{2}-\d{2}", recording)))
    if not first or not recorded:
        return recording
    days = (date.fromisoformat(first) - date.fromisoformat(recorded[0])).days
    return re.sub(r"\d{4}-\d{2}-\d{2}", lambda m: (date.fromisoformat(m.group(0)) + timedelta(days=days)).isoformat(),
                  recording)


class RecordedAi:
    """An Anthropic client whose transport answers from a recording and keeps every request it was sent."""

    def __init__(self, recording: str | None = None, status: int = 200, body: str | None = None):
        import httpx2

        self.requests: list[dict] = []

        def answer(request):
            sent = json.loads(request.content)
            self.requests.append({"url": str(request.url), "headers": dict(request.headers), "body": sent})
            text = body if body is not None else in_request_calendar((RECORDED / f"{recording}.json").read_text(), sent)
            return httpx2.Response(status, text=text, headers={"content-type": "application/json"})

        config = AiConfig(api_key="test-key-not-real", base_url="http://ai.test")
        client = make_client(config, transport=httpx2.MockTransport(answer)).with_options(max_retries=0)
        self.extractor = ClaudeExtractor(config, client)


def test_request_carries_scrubbed_text_schema_and_fallback():
    ai = RecordedAi("eob")
    ai.extractor.extract(SCRUBBED_EOB)
    (sent,) = ai.requests
    assert sent["url"].startswith("http://ai.test/v1/messages")
    assert FALLBACK_BETA in sent["headers"]["anthropic-beta"] and sent["headers"]["x-api-key"] == "test-key-not-real"
    body = sent["body"]
    assert body["model"] == MODEL and body["fallbacks"] == "default"
    assert body["output_config"]["format"]["type"] == "json_schema" and body["output_config"]["effort"] == "medium"
    assert SCRUBBED_EOB in body["messages"][0]["content"]
    for identifier in ("Pat Example", "W123-456-789"):  # TC-PLT-04-1 (unit): only pseudonymized text is sent
        assert identifier not in json.dumps(body)


def test_recorded_eob_becomes_an_extraction():
    x = RecordedAi("eob").extractor.extract(SCRUBBED_EOB)
    f = x.fields
    assert x.doc_type == "eob" and x.type_confidence == 0.98 and x.layout == "AI (claude-opus-5-5)"
    assert (f["billed"].value, f["allowed"].value, f["insurer_paid"].value) == (32000, 20000, 15500)
    assert f["patient"].value == TOKEN and f["service_start"].value == "2026-09-28"
    assert f["network_status"].value == "in_network" and f["claim_status"].value == "processed"
    assert x.lines == [{"service_date": "2026-09-28", "description": "Skin biopsy", "code": "11102", "billed": 32000,
                        "allowed": 20000, "insurer_paid": 15500, "patient_responsibility": 4500}]
    assert x.warnings == []


def test_a_value_the_document_does_not_show_is_marked_for_checking():
    """The recording claims a $25.00 deductible the EOB never prints: kept for the member to see, but marked."""
    f = RecordedAi("eob").extractor.extract(SCRUBBED_EOB).fields["deductible"]
    assert f.value == 2500 and f.confidence <= 0.5 and f.note == "not found in the document text"


def test_arithmetic_checks_apply_to_ai_output():
    data = json.loads(json.loads((RECORDED / "eob.json").read_text())["content"][1]["text"])
    data["fields"]["allowed"]["value"] = "210.00"
    x = to_extraction(data, SCRUBBED_EOB.replace("$200.00", "$210.00"))
    assert any("allowed amount" in w for w in x.warnings) and x.fields["allowed"].confidence <= 0.6


def test_other_documents_are_filed_and_forced_types_are_passed_on():
    ai = RecordedAi("letter")
    x = ai.extractor.extract("Dear tok_aaaaaaaaaaaaaaaaaaaaaaaaaa, thank you for your visit.")
    assert x.doc_type == "other" and x.fields == {} and "This is a letter, not a bill." in x.warnings
    ai.extractor.extract("Dear tok_x", forced_type="provider_statement")
    assert "this is a provider_statement" in ai.requests[-1]["body"]["messages"][0]["content"]


@pytest.mark.parametrize("ai,message", [
    (lambda: RecordedAi("refusal"), "declined"),
    (lambda: RecordedAi(status=529, body='{"type":"error","error":{"type":"overloaded_error","message":"x"}}'),
     "HTTP 529"),
    (lambda: RecordedAi(body=(RECORDED / "eob.json").read_text().replace('"text": "{', '"text": "not json {')),
     "wrong shape"),
])
def test_failures_are_reported_without_document_text(ai, message):
    with pytest.raises(AiUnavailable, match=message) as e:
        ai().extractor.extract(SCRUBBED_EOB)
    assert "Skin biopsy" not in str(e.value) and "tok_" not in str(e.value)
