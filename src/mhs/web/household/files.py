"""Encrypted storage of documents' attached files (ADR-032, ADR-033)."""

import hashlib
import re

from fastapi import HTTPException

from mhs.data.keys import Keyring
from mhs.data.objects import ObjectStore

ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class EncryptedFiles:
    """Attached files from an import, sealed with the household's data key and hashed (ING-10)."""

    def __init__(self, objects: ObjectStore, keyring: Keyring, household_id: str):
        self.objects, self.keyring, self.household_id = objects, keyring, household_id

    def key(self, doc_id: str) -> str:
        return f"households/{self.household_id}/documents/{doc_id}"

    def save(self, doc_id: str, name: str, data: bytes) -> dict:
        self.objects.put(self.key(doc_id), self.keyring.encrypt(self.household_id, data, f"document:{doc_id}"))
        return {"stored_file": self.key(doc_id), "file_sha256": hashlib.sha256(data).hexdigest()}

    def read(self, doc: dict) -> bytes:
        if not ID_PATTERN.match(doc["id"]) or doc.get("stored_file") != self.key(doc["id"]):
            raise HTTPException(404)
        data = self.keyring.decrypt(self.household_id, self.objects.get(self.key(doc["id"])), f"document:{doc['id']}")
        if doc.get("file_sha256") and hashlib.sha256(data).hexdigest() != doc["file_sha256"]:
            raise HTTPException(500)
        return data
