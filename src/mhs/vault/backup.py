"""Encrypted vault backup and restore (PRV-07, ADR-031).

A backup holds every vault row as stored: entries still sealed with the household data keys, and those keys
still wrapped by the vault's key-encryption key. The whole file is then sealed with a passphrase (scrypt,
AES-256-GCM). Restoring therefore needs both the passphrase and the vault's key-encryption key (the key file
locally, Cloud KMS in production), and goes into an empty vault only.
"""

import base64
import json
import os
from datetime import datetime, timezone

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from mhs.data.db import Database

MAGIC = b"MHSVB1"
FORMAT_VERSION = 1
MIN_PASSPHRASE = 12
SCRYPT_N = 2**15


class BackupError(Exception):
    """The backup could not be made or restored. Messages never say why a passphrase failed."""


def _key(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=SCRYPT_N, r=8, p=1).derive(passphrase.encode())


def _b64(b: bytes) -> str:
    return base64.b64encode(bytes(b)).decode()


def make_backup(db: Database, passphrase: str) -> bytes:
    if len(passphrase) < MIN_PASSPHRASE:
        raise BackupError(f"The passphrase must be at least {MIN_PASSPHRASE} characters.")
    keys, entries = [], []
    with db.tx() as c:
        for r in c.execute("SELECT household_id, wrapped, created_at FROM vault.household_keys ORDER BY household_id"):
            keys.append({"household_id": str(r["household_id"]), "wrapped": _b64(r["wrapped"]),
                         "created_at": r["created_at"].isoformat()})
    for k in keys:
        hid = k["household_id"]
        with db.tx(hid) as c:
            rows = c.execute(
                "SELECT token, kind, lookup, sealed, created_at FROM vault.entries WHERE household_id = %s "
                "ORDER BY token",
                (hid,),
            )
            for r in rows:
                entries.append({"household_id": hid, "token": r["token"], "kind": r["kind"],
                                "lookup": _b64(r["lookup"]), "sealed": _b64(r["sealed"]),
                                "created_at": r["created_at"].isoformat()})
    body = json.dumps({
        "format": FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "household_keys": keys,
        "entries": entries,
    }).encode()
    salt, nonce = os.urandom(16), os.urandom(12)
    return MAGIC + salt + nonce + AESGCM(_key(passphrase, salt)).encrypt(nonce, body, MAGIC)


def read_backup(blob: bytes, passphrase: str) -> dict:
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 28 + 16:
        raise BackupError("This is not a vault backup file.")
    salt = blob[len(MAGIC) : len(MAGIC) + 16]
    nonce = blob[len(MAGIC) + 16 : len(MAGIC) + 28]
    try:
        body = AESGCM(_key(passphrase, salt)).decrypt(nonce, blob[len(MAGIC) + 28 :], MAGIC)
    except InvalidTag:
        raise BackupError("The backup could not be opened.") from None
    data = json.loads(body)
    if data.get("format") != FORMAT_VERSION:
        raise BackupError("Unsupported backup format.")
    return data


def restore_backup(db: Database, blob: bytes, passphrase: str) -> dict:
    """Restore into an empty vault, all or nothing. Returns counts."""
    data = read_backup(blob, passphrase)
    with db.tx() as c:
        if c.execute("SELECT 1 FROM vault.household_keys LIMIT 1").fetchone():
            raise BackupError("The vault is not empty; restore only onto a fresh vault.")
        for k in data["household_keys"]:
            c.execute(
                "INSERT INTO vault.household_keys (household_id, wrapped, created_at) VALUES (%s, %s, %s)",
                (k["household_id"], base64.b64decode(k["wrapped"]), k["created_at"]),
            )
        for e in data["entries"]:
            c.execute("SELECT set_config('mhs.household_id', %s, true)", (e["household_id"],))
            c.execute(
                "INSERT INTO vault.entries (household_id, token, kind, lookup, sealed, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (e["household_id"], e["token"], e["kind"], base64.b64decode(e["lookup"]),
                 base64.b64decode(e["sealed"]), e["created_at"]),
            )
    return {"households": len(data["household_keys"]), "entries": len(data["entries"])}
