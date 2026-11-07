"""A stand-in OpenID Connect provider for tests (PRV-12): real HTTP on loopback, with PKCE and single-use codes checked."""

import base64
import hashlib
import json
import secrets
import socket
import threading
import time
from urllib.parse import urlencode

import uvicorn
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse

from mhs.stack import SignInProvider

ISSUER = "https://issuer.example.test"
CLIENT_ID = "test-client"
CLIENT_SECRET = "test-secret"


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


class FakeProvider:
    """Signs in whoever `subject` and `email` say. `overrides` changes ID token claims, to test the checks."""

    def __init__(self, host: str = "127.0.0.1"):
        self.subject, self.email = "subject-1", "person@example.test"
        self.overrides: dict = {}
        self.scopes: list[str] = []
        self.deny = False
        self.codes: dict[str, dict] = {}
        api = FastAPI()

        @api.get("/authorize")
        def authorize(client_id: str, redirect_uri: str, state: str, nonce: str, scope: str, response_type: str,
                      code_challenge: str, code_challenge_method: str):
            assert client_id == CLIENT_ID and response_type == "code" and code_challenge_method == "S256"
            self.scopes.append(scope)
            if self.deny:
                return RedirectResponse(redirect_uri + "?" + urlencode({"error": "access_denied", "state": state}))
            code = secrets.token_urlsafe(16)
            self.codes[code] = {"nonce": nonce, "challenge": code_challenge, "redirect_uri": redirect_uri}
            return RedirectResponse(redirect_uri + "?" + urlencode({"code": code, "state": state}))

        @api.post("/token")
        def token(code: str = Form(""), code_verifier: str = Form(""), redirect_uri: str = Form(""),
                  client_id: str = Form(""), client_secret: str = Form(""), grant_type: str = Form("")):
            issued = self.codes.pop(code, None)  # single use
            if issued is None or grant_type != "authorization_code" or redirect_uri != issued["redirect_uri"] \
                    or (client_id, client_secret) != (CLIENT_ID, CLIENT_SECRET):
                raise HTTPException(400)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()
            if challenge != issued["challenge"]:
                raise HTTPException(400)
            claims = {"iss": ISSUER, "aud": CLIENT_ID, "sub": self.subject, "email": self.email,
                      "nonce": issued["nonce"], "exp": time.time() + 300, **self.overrides}
            return JSONResponse({"id_token": f"{_b64({'alg': 'none'})}.{_b64(claims)}.signature"})

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.url = f"http://{host}:{self.port}"
        self.server = uvicorn.Server(uvicorn.Config(api, host="127.0.0.1", port=self.port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.time() + 10
        while not self.server.started:
            assert time.time() < deadline, "fake provider didn't start"
            time.sleep(0.02)

    def as_provider(self, name: str = "google", label: str = "Google") -> SignInProvider:
        return SignInProvider(name, label, CLIENT_ID, CLIENT_SECRET, f"{self.url}/authorize", f"{self.url}/token",
                              r"https://issuer\.example\.test")

    def stop(self):
        self.server.should_exit = True
        self.thread.join(5)
