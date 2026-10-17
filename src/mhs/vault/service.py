"""Identity vault service: a separate process reachable only from the application tier (ARCHITECTURE.md).

Every call needs the vault service token. Household ids come from the application tier's signed-in session,
never from a member's input, and every lookup is scoped to that household.
"""

import hmac
import logging
import os
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from mhs.data.db import Database
from mhs.data.keys import LocalKeyFile, db_keyring
from mhs.stack import VAULT_PORT, database_url, secret
from mhs.vault.store import KIND_PATTERN, VaultStore

log = logging.getLogger("mhs.vault")


class TokenizeIn(BaseModel):
    kind: str = Field(pattern=KIND_PATTERN.pattern)
    value: str = Field(min_length=1, max_length=500)


def household(household_id: str) -> str:
    try:
        return str(uuid.UUID(household_id))
    except ValueError:
        raise HTTPException(404, "Not found") from None


def create_app(store: VaultStore, service_token: str) -> FastAPI:
    if len(service_token) < 32:
        raise RuntimeError("the vault service token must be at least 32 characters")
    app = FastAPI(title="MHS identity vault", docs_url=None, redoc_url=None, openapi_url=None)
    expected = f"Bearer {service_token}".encode()

    def authorized(request: Request) -> None:
        given = request.headers.get("authorization", "").encode()
        if not hmac.compare_digest(given, expected):
            raise HTTPException(401, "Unauthorized")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/v1/households/{household_id}/tokens", dependencies=[Depends(authorized)])
    def tokenize(household_id: str, body: TokenizeIn):
        hid = household(household_id)
        token = store.tokenize(hid, body.kind, body.value)
        log.info("tokenize household=%s kind=%s", hid, body.kind)  # access log without the value
        return {"token": token}

    @app.get("/v1/households/{household_id}/tokens/{token}", dependencies=[Depends(authorized)])
    def detokenize(household_id: str, token: str):
        hid = household(household_id)
        found = store.detokenize(hid, token)
        log.info("detokenize household=%s found=%s", hid, found is not None)
        if found is None:
            raise HTTPException(404, "Not found")
        return {"kind": found[0], "value": found[1]}

    @app.get("/v1/households/{household_id}/entries", dependencies=[Depends(authorized)])
    def entries(household_id: str):
        hid = household(household_id)
        found = store.entries(hid)
        log.info("export household=%s entries=%s", hid, len(found))
        return {"entries": found}

    @app.delete("/v1/households/{household_id}", dependencies=[Depends(authorized)])
    def delete_household(household_id: str):
        hid = household(household_id)
        n = store.delete_household(hid)
        log.info("delete household=%s entries=%s", hid, n)
        return {"deleted": n}

    return app


def store_from_env() -> tuple[Database, VaultStore]:
    db = Database(database_url(), max_size=5)
    keys = LocalKeyFile(os.environ.get("MHS_KEY_FILE", "/run/secrets/mhs/kek"))
    return db, VaultStore(db, db_keyring(db, keys, "vault.household_keys"))


def serve() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    _, store = store_from_env()
    app = create_app(store, secret("VAULT_TOKEN") or "")
    uvicorn.run(app, host=os.environ.get("MHS_HOST", "127.0.0.1"), port=int(os.environ.get("MHS_VAULT_PORT", VAULT_PORT)))
