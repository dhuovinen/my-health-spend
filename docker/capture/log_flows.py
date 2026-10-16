"""mitmproxy addon for the `capture` service: append every request through the proxy to a JSON-lines file,
so privacy tests can search all captured traffic for identifiers and third-party hosts (TESTING.md).

It also stands in for the AI service: requests to CAPTURE_AI_HOST are answered from the recorded Messages API
responses in CAPTURE_AI_RECORDINGS (tests/fixtures/ai), so the test profile never reaches the real API."""

import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

from mitmproxy import http

PATH = os.environ.get("CAPTURE_LOG", "/home/mitmproxy/.mitmproxy/flows.jsonl")
AI_HOST = os.environ.get("CAPTURE_AI_HOST", "ai.capture.test")
RECORDINGS = Path(os.environ.get("CAPTURE_AI_RECORDINGS", "/recorded"))


def recording_for(body: str) -> str:
    return "eob.json" if "EXPLANATION OF BENEFITS" in body.upper() else "letter.json"


def in_request_calendar(recording: str, request_body: str) -> str:
    """Answer as the model would: in the calendar of the text it was sent (PRV-05 shifts the request's dates)."""
    try:
        sent = json.loads(request_body)["messages"][0]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        return recording
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b|\b(\d{4})-(\d{2})-(\d{2})\b", sent)
    recorded = sorted(set(re.findall(r"\d{4}-\d{2}-\d{2}", recording)))
    if not m or not recorded:
        return recording
    first = (date(int(m[3]), int(m[1]), int(m[2])) if m[3] else date(int(m[4]), int(m[5]), int(m[6])))
    days = (first - date.fromisoformat(recorded[0])).days
    return re.sub(r"\d{4}-\d{2}-\d{2}",
                  lambda d: (date.fromisoformat(d.group(0)) + timedelta(days=days)).isoformat(), recording)


class LogFlows:
    def request(self, flow):
        if flow.request.pretty_host == AI_HOST:
            sent = flow.request.get_text(strict=False) or ""
            body = in_request_calendar((RECORDINGS / recording_for(sent)).read_text(), sent)
            flow.response = http.Response.make(200, body.encode(), {"content-type": "application/json"})

    def response(self, flow):
        record = {
            "host": flow.request.pretty_host,
            "port": flow.request.port,
            "method": flow.request.method,
            "path": flow.request.path,
            "request_body": flow.request.get_text(strict=False) or "",
            "status": flow.response.status_code,
            "response_headers": dict(flow.response.headers),
            "response_body": flow.response.get_text(strict=False) or "",
        }
        with open(PATH, "a") as f:
            f.write(json.dumps(record) + "\n")


addons = [LogFlows()]
