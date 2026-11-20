"""A stand-in OpenID Connect provider for tests (PRV-12): real HTTP on loopback, with PKCE and single-use codes checked.

`as_apple()` switches it to Apple's shape (ADR-057): no scope, no PKCE, `response_mode=query`, and a client secret that
has to be an ES256 token signed with the key it hands out."""

import base64
import hashlib
import json
import secrets
import socket
import threading
import time
from urllib.parse import urlencode

import uvicorn
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse

from mhs.stack import ClientKey, SignInProvider

ISSUER = "https://issuer.example.test"
CLIENT_ID = "test-client"
CLIENT_SECRET = "test-secret"
TEAM_ID, KEY_ID = "TEAM123456", "KEY1234567"


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def _b64_bytes(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def signed_secret_is_valid(token: str, public_key: ec.EllipticCurvePublicKey, now: float | None = None) -> bool:
    """What Apple checks of a client secret: an ES256 signature by the registered key, and the right claims."""
    try:
        head, body, signature = token.split(".")
        raw = _unb64(signature)
        public_key.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
                          f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256()))
        header, claims = json.loads(_unb64(head)), json.loads(_unb64(body))
    except (ValueError, InvalidSignature):
        return False
    now = time.time() if now is None else now
    return header == {"alg": "ES256", "kid": KEY_ID} and claims["iss"] == TEAM_ID and claims["sub"] == CLIENT_ID \
        and claims["aud"] == ISSUER and claims["iat"] <= now < claims["exp"] <= now + 600


class FakeProvider:
    """Signs in whoever `subject` and `email` say. `overrides` changes ID token claims, to test the checks."""

    def __init__(self, host: str = "127.0.0.1"):
        self.subject, self.email = "subject-1", "person@example.test"
        self.overrides: dict = {}
        self.scopes: list[str] = []
        self.deny = False
        self.apple = False
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.codes: dict[str, dict] = {}
        api = FastAPI()

        @api.get("/authorize")
        def authorize(client_id: str, redirect_uri: str, state: str, nonce: str, response_type: str, scope: str = "",
                      code_challenge: str = "", code_challenge_method: str = "", response_mode: str = ""):
            assert client_id == CLIENT_ID and response_type == "code"
            if self.apple:  # no scope, so a plain redirect back; Apple doesn't take PKCE
                assert (scope, code_challenge, response_mode) == ("", "", "query")
            else:
                assert code_challenge and code_challenge_method == "S256" and not response_mode
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
                    or client_id != CLIENT_ID:
                raise HTTPException(400)
            if self.apple:
                if code_verifier or not signed_secret_is_valid(client_secret, self.key.public_key()):
                    raise HTTPException(400)
            else:
                challenge = _b64_bytes(hashlib.sha256(code_verifier.encode()).digest())
                if client_secret != CLIENT_SECRET or challenge != issued["challenge"]:
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

    def as_apple(self) -> SignInProvider:
        """Apple's shape (ADR-057). Apple sends no email when no scope was asked for."""
        self.apple, self.email = True, ""
        pem = self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()).decode()
        return SignInProvider("apple", "Apple", CLIENT_ID, "", f"{self.url}/authorize", f"{self.url}/token",
                              r"https://issuer\.example\.test", scopes="", pkce=False, response_mode="query",
                              key=ClientKey(TEAM_ID, KEY_ID, pem, audience=ISSUER))

    def stop(self):
        self.server.should_exit = True
        self.thread.join(5)
