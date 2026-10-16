"""Keys adapter: envelope encryption with per-household data keys (ADR-025, ADR-031).

A KeyService wraps and unwraps data keys the way Cloud KMS encrypt/decrypt does. Locally the key-encryption
key (KEK) is a file on a Docker volume (LocalKeyFile); in Google Cloud it will be a Cloud KMS key behind the
same interface. Each service (application tier, vault) has its own KEK and its own data key per household,
kept only in wrapped form. Content is sealed with AES-256-GCM, bound to the household and object it belongs
to, so a ciphertext copied to another household or object fails to open.
"""

import base64
import os
import secrets
from pathlib import Path
from typing import Callable, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"MHS1"
NONCE_BYTES = 12


class DecryptError(Exception):
    """A sealed value could not be opened: wrong key, wrong context, or tampered."""


def seal(key: bytes, plaintext: bytes, context: str) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, plaintext, context.encode())


def open_sealed(key: bytes, blob: bytes, context: str) -> bytes:
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + NONCE_BYTES + 16:
        raise DecryptError("not a sealed value")
    nonce = blob[len(MAGIC) : len(MAGIC) + NONCE_BYTES]
    try:
        return AESGCM(key).decrypt(nonce, blob[len(MAGIC) + NONCE_BYTES :], context.encode())
    except InvalidTag:
        raise DecryptError("could not decrypt") from None


class KeyService(Protocol):
    """Wraps data keys under a key-encryption key that never leaves the key service."""

    def wrap(self, data_key: bytes, context: str) -> bytes: ...

    def unwrap(self, wrapped: bytes, context: str) -> bytes: ...


class LocalKeyFile:
    """KeyService backed by a 256-bit key in a file (base64). Local stack and tests only."""

    def __init__(self, path: Path):
        try:
            key = base64.b64decode(Path(path).read_text().strip(), validate=True)
        except (OSError, ValueError) as e:
            raise RuntimeError(f"key file {path} is missing or unreadable") from e
        if len(key) != 32:
            raise RuntimeError(f"key file {path} must hold 32 bytes")
        self._kek = key

    @staticmethod
    def create(path: Path) -> "LocalKeyFile":
        path = Path(path)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(base64.b64encode(secrets.token_bytes(32)).decode() + "\n")
        return LocalKeyFile(path)

    def wrap(self, data_key: bytes, context: str) -> bytes:
        return seal(self._kek, data_key, "wrap:" + context)

    def unwrap(self, wrapped: bytes, context: str) -> bytes:
        return open_sealed(self._kek, wrapped, "wrap:" + context)


class Keyring:
    """One service's per-household data keys.

    load_wrapped(household_id) returns the stored wrapped key or None; save_wrapped(household_id, wrapped)
    stores it unless one already exists and returns whichever is stored, so two first uses can't diverge.
    """

    def __init__(
        self,
        keys: KeyService,
        load_wrapped: Callable[[str], bytes | None],
        save_wrapped: Callable[[str, bytes], bytes],
    ):
        self.keys = keys
        self._load = load_wrapped
        self._save = save_wrapped
        self._cache: dict[str, bytes] = {}

    def data_key(self, household_id: str) -> bytes:
        household_id = str(household_id)
        if household_id not in self._cache:
            context = f"household:{household_id}"
            wrapped = self._load(household_id)
            if wrapped is None:
                wrapped = self._save(household_id, self.keys.wrap(AESGCM.generate_key(bit_length=256), context))
            self._cache[household_id] = self.keys.unwrap(wrapped, context)
        return self._cache[household_id]

    def encrypt(self, household_id: str, plaintext: bytes, context: str) -> bytes:
        return seal(self.data_key(household_id), plaintext, f"{household_id}|{context}")

    def decrypt(self, household_id: str, blob: bytes, context: str) -> bytes:
        return open_sealed(self.data_key(household_id), blob, f"{household_id}|{context}")


def db_keyring(db, keys: KeyService, table: str) -> Keyring:
    """A Keyring whose wrapped keys live in `table` (app.household_keys or vault.household_keys)."""
    if table not in ("app.household_keys", "vault.household_keys"):
        raise ValueError(table)

    def load(household_id: str) -> bytes | None:
        with db.tx() as c:
            row = c.execute(f"SELECT wrapped FROM {table} WHERE household_id = %s", (household_id,)).fetchone()
        return bytes(row["wrapped"]) if row else None

    def save(household_id: str, wrapped: bytes) -> bytes:
        with db.tx() as c:
            c.execute(
                f"INSERT INTO {table} (household_id, wrapped) VALUES (%s, %s) ON CONFLICT (household_id) DO NOTHING",
                (household_id, wrapped),
            )
            row = c.execute(f"SELECT wrapped FROM {table} WHERE household_id = %s", (household_id,)).fetchone()
        return bytes(row["wrapped"])

    return Keyring(keys, load, save)
