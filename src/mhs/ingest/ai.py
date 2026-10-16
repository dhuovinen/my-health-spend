"""Claude extraction (ADR-028, ADR-034): the worker sends scrubbed document text to the Claude API and gets back the
same Extraction the layout rules produce, with a confidence per field.

Only pseudonymized text is sent (PLT-04): identifiers are vault tokens before the job is queued, and the worker
never sees anything else. Every value the model returns is checked against the text it was given; a value the
text doesn't contain is kept but marked for checking, and the arithmetic checks run as for the rules. The member
reviews and confirms every field, and the review page says the document was read by AI.

Off unless the worker runs with MHS_EXTRACTOR=claude and the household has AI extraction turned on
(`mhs-admin ai-extraction`). Settings: MHS_ANTHROPIC_API_KEY(_FILE), MHS_AI_MODEL, MHS_AI_BASE_URL, MHS_AI_PROXY
(the worker has no route out of the compose network; the test profile sends it through the capture proxy).
"""

import json
import os
import re
from dataclasses import dataclass

from mhs.ingest.extract import DATE, EOB_LABELS, EXTRACTED, STATEMENT_LABELS, TYPES, Extraction, Field, check
from mhs.ingest.values import parse_amount, parse_date

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"  # on a refusal, the API reruns the request on its chosen fallback
EOB_FIELDS = ("patient", "provider", "claim_number", "service_start", "service_end", "processed_date",
              *EOB_LABELS, "claim_status", "network_status")
STATEMENT_FIELDS = ("patient", "provider", "account_number", "statement_date", "due_date", *STATEMENT_LABELS,
                    "notice")
FIELDS = tuple(dict.fromkeys(EOB_FIELDS + STATEMENT_FIELDS))
MONEY = set(EOB_LABELS) | set(STATEMENT_LABELS)
DATES = {"service_start", "service_end", "processed_date", "statement_date", "due_date"}
EOB_LINE = ("billed", "allowed", "insurer_paid", "patient_responsibility")
STATEMENT_LINE = ("charge", "adjustment", "insurance_paid", "patient_paid", "balance")
LINE_KEYS = ("service_date", "code", "description", *EOB_LINE, *STATEMENT_LINE)
TOKEN = re.compile(r"tok_[a-z2-7]{26}")

SYSTEM = f"""You read US medical billing documents for a household that reconciles its bills, insurer EOBs and \
HSA payments. You get the document's text, read from a PDF or by OCR. Names, member IDs, account numbers, \
addresses, phone numbers and similar identifiers have been replaced with tokens like tok_abcdefghijklmnopqrstuvwxyz \
before you see it: copy a token exactly where a field's value is a token, and never guess what it stands for.

Classify the document as one of: {", ".join(f"{k} ({v})" for k, v in TYPES.items())}. An EOB says it is not a bill. \
An itemized bill lists charges with codes; a provider statement asks for payment.

Then fill every field. Use an empty string for a field the document doesn't show; never infer or compute a value \
the document doesn't print. Amounts are plain numbers in dollars with two decimals ("1234.56", negative for \
credits). Dates are YYYY-MM-DD. claim_status is "processed", "denied" or "pending"; network_status is \
"in_network" or "out_of_network". For an EOB, billed is what the provider charged, adjustment the plan or \
network discount, allowed the allowed amount, insurer_paid what the plan paid, patient_responsibility what the \
patient owes. For a statement, balance_due is the amount due now.

List each service line the document prints, with the amounts it shows for that line (empty strings for the \
rest). Give each field a confidence from 0 to 1 for how sure you are that it is what the document says. Add a \
short warning for anything a person should check, such as numbers that don't add up."""

FIELD_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["value", "confidence"],
                "properties": {"value": {"type": "string"}, "confidence": {"type": "number"}}}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["doc_type", "type_confidence", "fields", "lines", "warnings"],
    "properties": {
        "doc_type": {"type": "string", "enum": list(TYPES)},
        "type_confidence": {"type": "number"},
        "fields": {"type": "object", "additionalProperties": False, "required": list(FIELDS),
                   "properties": {name: FIELD_SCHEMA for name in FIELDS}},
        "lines": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": list(LINE_KEYS),
            "properties": {k: {"type": "string"} for k in LINE_KEYS}}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
}


class AiUnavailable(RuntimeError):
    """The AI couldn't read this document (refused, failed or answered in the wrong shape); the rules take over.
    Messages never include document text."""


@dataclass(frozen=True)
class AiConfig:
    api_key: str | None = None  # None: the SDK's own resolution (ANTHROPIC_API_KEY, profiles)
    model: str = MODEL
    base_url: str | None = None
    proxy: str | None = None
    timeout: float = 120.0


def config_from_env() -> AiConfig:
    from mhs.stack import secret

    return AiConfig(api_key=secret("ANTHROPIC_API_KEY"), model=os.environ.get("MHS_AI_MODEL", MODEL),
                    base_url=os.environ.get("MHS_AI_BASE_URL") or None, proxy=os.environ.get("MHS_AI_PROXY") or None,
                    timeout=float(os.environ.get("MHS_AI_TIMEOUT_SECONDS", "120")))


def make_client(config: AiConfig, transport=None):
    """An Anthropic client; `transport` lets tests answer with recorded responses."""
    import anthropic

    http = {"proxy": config.proxy} if config.proxy else {}
    if transport is not None:
        http["transport"] = transport
    return anthropic.Anthropic(api_key=config.api_key, base_url=config.base_url, timeout=config.timeout,
                               max_retries=2, http_client=anthropic.DefaultHttpxClient(**http))


class ClaudeExtractor:
    name = "claude"

    def __init__(self, config: AiConfig | None = None, client=None):
        self.config = config or AiConfig()
        self.client = client or make_client(self.config)

    def extract(self, text: str, forced_type: str | None = None) -> Extraction:
        import anthropic

        prompt = "Document text:\n<document>\n" + text + "\n</document>"
        if forced_type:
            prompt += f"\n\nThe household says this is a {forced_type}; use that doc_type."
        try:
            response = self.client.beta.messages.create(
                model=self.config.model, max_tokens=16000, system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
                betas=[FALLBACK_BETA], fallbacks="default",
            )
        except anthropic.APIStatusError as e:
            raise AiUnavailable(f"AI extraction failed: HTTP {e.status_code}") from None
        except anthropic.APIError as e:
            raise AiUnavailable(f"AI extraction failed: {type(e).__name__}") from None
        if response.stop_reason == "refusal":
            raise AiUnavailable("AI extraction declined this document")
        if response.stop_reason == "max_tokens":
            raise AiUnavailable("AI extraction ran out of room")
        body = next((b.text for b in response.content if b.type == "text"), "")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            raise AiUnavailable("AI extraction answered in the wrong shape") from None
        x = to_extraction(data, text, forced_type)
        x.layout = f"AI ({response.model})"
        return x


def _confidence(value) -> float:
    try:
        return round(min(0.99, max(0.0, float(value))), 2)
    except (TypeError, ValueError):
        return 0.0


def _dates_in(text: str) -> set[str]:
    return {d for d in (parse_date(m) for m in re.findall(DATE, text)) if d}


def _value(name: str, raw: str):
    """The model's string as the type the rules produce: cents for money, ISO dates, text otherwise."""
    raw = (raw or "").strip()
    if not raw:
        return None
    if name in MONEY:
        return parse_amount(raw)
    if name in DATES:
        return parse_date(raw)
    return raw


def _grounded(name: str, value, text: str, dates: set[str]) -> bool:
    """Whether the document text shows this value: the guard against a value the model made up."""
    if name in MONEY:
        return f"{abs(value) / 100:,.2f}" in text or f"{abs(value) / 100:.2f}" in text
    if name in DATES:
        return value in dates
    if name in ("claim_status", "network_status"):
        return True  # a reading of the document, not a copied value
    if TOKEN.fullmatch(value) or len(value) > 3:
        return re.sub(r"\s+", " ", value).lower() in re.sub(r"\s+", " ", text).lower()
    return True


def to_extraction(data: dict, text: str, forced_type: str | None = None) -> Extraction:
    doc_type = forced_type or data.get("doc_type")
    if doc_type not in TYPES:
        raise AiUnavailable("AI extraction answered in the wrong shape")
    x = Extraction(doc_type, 1.0 if forced_type else _confidence(data.get("type_confidence")), "AI")
    x.warnings = [w for w in data.get("warnings", []) if isinstance(w, str) and w.strip()][:10]
    if doc_type not in EXTRACTED:
        x.warnings.append(f"{TYPES[doc_type]} documents are kept with your uploads; their fields aren't read yet.")
        return x
    dates = _dates_in(text)
    raw_fields = data.get("fields") or {}
    for name in EOB_FIELDS if doc_type == "eob" else STATEMENT_FIELDS:
        f = raw_fields.get(name) or {}
        value = _value(name, f.get("value", ""))
        if value is None:
            x.fields[name] = Field(None, 0.0, "not on document")
        elif not _grounded(name, value, text, dates):
            x.fields[name] = Field(value, min(0.5, _confidence(f.get("confidence"))), "not found in the document text")
        else:
            x.fields[name] = Field(value, _confidence(f.get("confidence")))
    keys = EOB_LINE if doc_type == "eob" else STATEMENT_LINE
    for raw in data.get("lines") or []:
        line = {"service_date": parse_date(raw.get("service_date", "")), "description": raw.get("description", "")}
        if code := (raw.get("code") or "").strip():
            line["code"] = code
        line.update({k: v for k in keys if (v := _value("billed", raw.get(k, ""))) is not None})
        x.lines.append({k: v for k, v in line.items() if v not in (None, "")})
    if doc_type != "eob" and x.lines and x.fields["billed"].value is None and all("charge" in l for l in x.lines):
        x.fields["billed"] = Field(sum(l["charge"] for l in x.lines), 0.7, "sum of the lines")
    check(x)
    return x
