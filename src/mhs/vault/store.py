"""Identity vault storage: the only map from tokens to identifiers (ARCHITECTURE.md, PRV-01, PRV-06).

Values are sealed with the vault's own per-household data key; the same value of the same kind always gets
the same token within a household (found through a keyed hash, so the database never holds the value).
"""

import base64
import hashlib
import hmac
import re
import secrets

from mhs.data.db import Database
from mhs.data.keys import Keyring

KIND_PATTERN = re.compile(r"^[a-z][a-z_]{0,31}$")
TOKEN_PATTERN = re.compile(r"^tok_[a-z2-7]{26}$")


def new_token() -> str:
    return "tok_" + base64.b32encode(secrets.token_bytes(16)).decode().rstrip("=").lower()


class VaultStore:
    def __init__(self, db: Database, keyring: Keyring):
        self.db = db
        self.keyring = keyring

    def _lookup(self, household_id: str, kind: str, value: str) -> bytes:
        lookup_key = hmac.new(self.keyring.data_key(household_id), b"vault-lookup", hashlib.sha256).digest()
        return hmac.new(lookup_key, f"{kind}\0{value}".encode(), hashlib.sha256).digest()

    def tokenize(self, household_id: str, kind: str, value: str) -> str:
        if not KIND_PATTERN.match(kind):
            raise ValueError("invalid kind")
        household_id = str(household_id)
        lookup = self._lookup(household_id, kind, value)
        token = new_token()
        sealed = self.keyring.encrypt(household_id, value.encode(), f"vault:{token}:{kind}")
        with self.db.tx(household_id) as c:
            c.execute(
                "INSERT INTO vault.entries (household_id, token, kind, lookup, sealed) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (household_id, kind, lookup) DO NOTHING",
                (household_id, token, kind, lookup, sealed),
            )
            row = c.execute(
                "SELECT token FROM vault.entries WHERE household_id = %s AND kind = %s AND lookup = %s",
                (household_id, kind, lookup),
            ).fetchone()
        return row["token"]

    def detokenize(self, household_id: str, token: str) -> tuple[str, str] | None:
        """(kind, value) for a token of this household, or None."""
        if not TOKEN_PATTERN.match(token):
            return None
        household_id = str(household_id)
        with self.db.tx(household_id) as c:
            row = c.execute(
                "SELECT kind, sealed FROM vault.entries WHERE household_id = %s AND token = %s",
                (household_id, token),
            ).fetchone()
        if not row:
            return None
        value = self.keyring.decrypt(household_id, bytes(row["sealed"]), f"vault:{token}:{row['kind']}")
        return row["kind"], value.decode()

    def count(self) -> int:
        """Entries across all households (for backup checks); counts household by household under RLS."""
        total = 0
        for hid in self.households():
            with self.db.tx(hid) as c:
                total += c.execute(
                    "SELECT count(*) AS n FROM vault.entries WHERE household_id = %s", (hid,)
                ).fetchone()["n"]
        return total

    def households(self) -> list[str]:
        with self.db.tx() as c:
            return [str(r["household_id"]) for r in c.execute("SELECT household_id FROM vault.household_keys")]
