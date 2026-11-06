"""Each household's private address for forwarding bills and EOBs by email (ING-01, ADR-039)."""

import base64
import os
import re
import secrets

from mhs.data.db import Database

TOKEN = re.compile(r"^[a-z2-7]{16}$")


def domain() -> str:
    return os.environ.get("MHS_INBOUND_DOMAIN", "inbound.mhs.local")


def address_for(db: Database, household_id: str) -> str:
    """The household's inbound address, made on first use."""
    with db.tx() as c:
        row = c.execute("SELECT token FROM app.inbound_addresses WHERE household_id = %s", (household_id,)).fetchone()
        if row is None:
            token = base64.b32encode(secrets.token_bytes(10)).decode().lower()
            c.execute("INSERT INTO app.inbound_addresses (token, household_id) VALUES (%s, %s) "
                      "ON CONFLICT (household_id) DO NOTHING", (token, household_id))
            row = c.execute("SELECT token FROM app.inbound_addresses WHERE household_id = %s",
                            (household_id,)).fetchone()
    return f"{row['token']}@{domain()}"


def household_for(db: Database, address: str) -> str | None:
    local, _, host = (address or "").strip().lower().strip("<>").partition("@")
    if host != domain().lower() or not TOKEN.match(local):
        return None
    with db.tx() as c:
        row = c.execute("SELECT household_id FROM app.inbound_addresses WHERE token = %s", (local,)).fetchone()
    return str(row["household_id"]) if row else None
