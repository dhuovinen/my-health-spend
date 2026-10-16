"""mitmproxy addon for the `capture` service: append every request through the proxy to a JSON-lines file,
so privacy tests can search all captured traffic for identifiers and third-party hosts (TESTING.md).

It also stands in for the AI service: requests to CAPTURE_AI_HOST are answered from the recorded Messages API
responses in CAPTURE_AI_RECORDINGS (tests/fixtures/ai), so the test profile never reaches the real API."""

import json
import os
from pathlib import Path

from mitmproxy import http

PATH = os.environ.get("CAPTURE_LOG", "/home/mitmproxy/.mitmproxy/flows.jsonl")
AI_HOST = os.environ.get("CAPTURE_AI_HOST", "ai.capture.test")
RECORDINGS = Path(os.environ.get("CAPTURE_AI_RECORDINGS", "/recorded"))


def recording_for(body: str) -> str:
    return "eob.json" if "EXPLANATION OF BENEFITS" in body.upper() else "letter.json"


class LogFlows:
    def request(self, flow):
        if flow.request.pretty_host == AI_HOST:
            body = (RECORDINGS / recording_for(flow.request.get_text(strict=False) or "")).read_bytes()
            flow.response = http.Response.make(200, body, {"content-type": "application/json"})

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
