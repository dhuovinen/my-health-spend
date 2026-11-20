"""OpenID Connect authorization code flow with PKCE, directly with the provider (PRV-12, ADR-048).

The ID token comes straight from the provider's token endpoint over TLS, so its claims are checked and its signature
isn't (OpenID Connect Core 3.1.3.7). Provider tokens are used here once and never stored or logged. Apple (ADR-057) asks
for no scope, skips PKCE and signs a fresh client secret for each token request.
"""

import base64
import hashlib
import json
import re
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from mhs.stack import SignInProvider

CLIENT_SECRET_SECONDS = 300  # Apple allows six months; one is made for each token request


class OidcError(Exception):
    """The sign-in couldn't be completed. Deliberately carries nothing from the provider's response."""


@dataclass(frozen=True)
class Flow:
    """What the browser holds between leaving for the provider and coming back."""

    provider: str
    state: str
    nonce: str
    verifier: str

    @staticmethod
    def new(provider: str) -> "Flow":
        return Flow(provider, secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(48))

    def to_cookie(self) -> str:
        return ".".join((self.provider, self.state, self.nonce, self.verifier))

    @staticmethod
    def from_cookie(value: str | None) -> "Flow | None":
        parts = (value or "").split(".")
        return Flow(*parts) if len(parts) == 4 and all(parts) else None


@dataclass(frozen=True)
class Identity:
    subject: str
    email: str


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def authorization_url(provider: SignInProvider, flow: Flow, redirect_uri: str) -> str:
    params = {"response_type": "code", "client_id": provider.client_id, "redirect_uri": redirect_uri,
              "state": flow.state, "nonce": flow.nonce}
    if provider.scopes:
        params["scope"] = provider.scopes
    if provider.response_mode:
        params["response_mode"] = provider.response_mode
    if provider.pkce:
        params["code_challenge"] = _b64(hashlib.sha256(flow.verifier.encode()).digest())
        params["code_challenge_method"] = "S256"
    return provider.authorize_url + "?" + urlencode(params)


def client_secret(provider: SignInProvider, now: float | None = None) -> str:
    """The fixed secret, or for Apple an ES256 token signed with the provider key, valid for a few minutes."""
    if provider.key is None:
        return provider.client_secret
    now = int(time.time() if now is None else now)
    header = {"alg": "ES256", "kid": provider.key.key_id}
    claims = {"iss": provider.key.team_id, "iat": now, "exp": now + CLIENT_SECRET_SECONDS,
              "aud": provider.key.audience, "sub": provider.client_id}
    signing_input = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(claims).encode())}"
    key = serialization.load_pem_private_key(provider.key.private_key_pem.encode(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):  # also checked when the provider was configured
        raise OidcError
    r, s = decode_dss_signature(key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256())))
    return f"{signing_input}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def _claims(id_token: str) -> dict:
    parts = id_token.split(".")
    if len(parts) != 3:
        raise OidcError
    try:
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except ValueError:
        raise OidcError from None
    if not isinstance(claims, dict):
        raise OidcError
    return claims


def check_claims(claims: dict, provider: SignInProvider, nonce: str, now: float | None = None) -> Identity:
    """The ID token checks that apply without a signature: who issued it, who it's for, whether it's current, and
    whether it belongs to this flow. Raises OidcError if any fails."""
    now = time.time() if now is None else now
    issuer, audience, expires, subject = (claims.get(k) for k in ("iss", "aud", "exp", "sub"))
    if not isinstance(issuer, str) or not re.fullmatch(provider.issuer, issuer):
        raise OidcError
    if audience != provider.client_id:  # one client: a list of audiences isn't expected from any provider
        raise OidcError
    if not isinstance(expires, (int, float)) or expires <= now:
        raise OidcError
    if not secrets.compare_digest(str(claims.get("nonce", "")).encode(), nonce.encode()):
        raise OidcError
    if not isinstance(subject, str) or not subject:
        raise OidcError
    email = claims.get("email")
    return Identity(subject, email if isinstance(email, str) else "")


def complete(provider: SignInProvider, flow: Flow, code: str, redirect_uri: str) -> Identity:
    """Swap the code for an ID token at the provider, and check it."""
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
            "client_id": provider.client_id, "client_secret": client_secret(provider)}
    if provider.pkce:
        data["code_verifier"] = flow.verifier
    try:
        response = httpx.post(provider.token_url, timeout=10, headers={"Accept": "application/json"}, data=data)
        id_token = response.json().get("id_token") if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError, AttributeError):
        raise OidcError from None
    if not isinstance(id_token, str):
        raise OidcError
    return check_claims(_claims(id_token), provider, flow.nonce)
