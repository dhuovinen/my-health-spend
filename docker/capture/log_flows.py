"""mitmproxy addon for the `capture` service: append every request through the proxy to a JSON-lines file,
so privacy tests can search all captured traffic for identifiers and third-party hosts (TESTING.md)."""

import json
import os

PATH = os.environ.get("CAPTURE_LOG", "/home/mitmproxy/.mitmproxy/flows.jsonl")


class LogFlows:
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
