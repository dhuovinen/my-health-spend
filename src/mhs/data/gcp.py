"""Google Cloud access for the REST adapters (ADR-036): an httpx client and an access token.

On Cloud Run the token comes from the service account through the metadata server (`google.auth.default`). Against
an emulator or in tests a fixed token is enough. Document text and keys never go in log lines or error messages.
"""

import time
from typing import Protocol

import httpx

SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class GoogleError(RuntimeError):
    """A Google Cloud call failed; the message names the operation and HTTP status only."""


class TokenSource(Protocol):
    def token(self) -> str: ...


class StaticToken:
    """A fixed bearer token: emulators accept any, and tests don't need a real one."""

    def __init__(self, value: str = "local-test-token"):
        self.value = value

    def token(self) -> str:
        return self.value


class _HttpxRequest:
    """google-auth's transport interface over httpx, so no `requests` dependency is needed."""

    def __init__(self, http: httpx.Client):
        self.http = http

    def __call__(self, url, method="GET", body=None, headers=None, timeout=None, **kwargs):
        from google.auth import exceptions

        try:
            r = self.http.request(method, url, content=body, headers=headers, timeout=timeout or 30)
        except httpx.HTTPError as e:
            raise exceptions.TransportError(str(e)) from e

        class Response:
            status = r.status_code
            headers = dict(r.headers)
            data = r.content

        return Response()


class GoogleToken:
    """Application default credentials (the Cloud Run service account), refreshed before they expire."""

    def __init__(self, http: httpx.Client | None = None):
        import google.auth

        self.credentials, _ = google.auth.default(scopes=[SCOPE])
        self.request = _HttpxRequest(http or httpx.Client(timeout=30))
        self.expires = 0.0

    def token(self) -> str:
        if not self.credentials.valid or time.time() > self.expires - 300:
            self.credentials.refresh(self.request)
            expiry = getattr(self.credentials, "expiry", None)
            self.expires = expiry.timestamp() if expiry else time.time() + 300
        return self.credentials.token


def default_token(emulated: bool) -> TokenSource:
    return StaticToken() if emulated else GoogleToken()


def check(r: httpx.Response, operation: str) -> httpx.Response:
    if r.status_code >= 400:
        raise GoogleError(f"{operation} failed: HTTP {r.status_code}")
    return r
