"""Object storage adapter: originals and, later, scrubbed images (ARCHITECTURE.md "Environments").

Locally a folder on a Docker volume (LocalObjectStore); in Google Cloud a Cloud Storage bucket behind the same
interface. Callers encrypt before put: the store only ever sees ciphertext.
"""

import os
import re
import tempfile
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from mhs.data.gcp import check, default_token

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]*(/[A-Za-z0-9_-][A-Za-z0-9._-]*)*$")


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...


class LocalObjectStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / check_key(key)

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


def check_key(key: str) -> str:
    if not KEY_PATTERN.match(key) or ".." in key.split("/"):
        raise ValueError(f"invalid object key: {key!r}")
    return key


class GcsObjectStore:
    """Cloud Storage over its JSON API (ADR-036). `endpoint` points at the fake GCS server in tests."""

    def __init__(self, bucket: str, http=None, token=None, endpoint: str = "https://storage.googleapis.com"):
        self.bucket = bucket
        self.endpoint = endpoint.rstrip("/")
        self.http = http or httpx.Client(timeout=60)
        self.tokens = token or default_token(emulated=endpoint != "https://storage.googleapis.com")

    def _url(self, key: str, upload: bool = False) -> str:
        name = quote(check_key(key), safe="")
        if upload:
            return f"{self.endpoint}/upload/storage/v1/b/{self.bucket}/o?uploadType=media&name={name}"
        return f"{self.endpoint}/storage/v1/b/{self.bucket}/o/{name}"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.tokens.token()}"}

    def put(self, key: str, data: bytes) -> None:
        check(self.http.post(self._url(key, upload=True), content=data,
                             headers={**self._headers(), "Content-Type": "application/octet-stream"}), "storage put")

    def get(self, key: str) -> bytes:
        r = self.http.get(self._url(key), params={"alt": "media"}, headers=self._headers())
        if r.status_code == 404:
            raise FileNotFoundError(key)
        return check(r, "storage get").content

    def exists(self, key: str) -> bool:
        r = self.http.get(self._url(key), headers=self._headers())
        if r.status_code == 404:
            return False
        check(r, "storage exists")
        return True

    def delete(self, key: str) -> None:
        r = self.http.delete(self._url(key), headers=self._headers())
        if r.status_code != 404:
            check(r, "storage delete")


def object_store_from_env(default_dir: Path) -> ObjectStore:
    """MHS_OBJECT_STORE=local (default: a folder) or gcs (MHS_GCS_BUCKET, optional MHS_GCS_ENDPOINT)."""
    kind = os.environ.get("MHS_OBJECT_STORE", "local")
    if kind == "local":
        return LocalObjectStore(Path(os.environ.get("MHS_OBJECTS_DIR", default_dir)))
    if kind == "gcs":
        bucket = os.environ.get("MHS_GCS_BUCKET")
        if not bucket:
            raise SystemExit("MHS_OBJECT_STORE=gcs needs MHS_GCS_BUCKET")
        return GcsObjectStore(bucket, endpoint=os.environ.get("MHS_GCS_ENDPOINT", "https://storage.googleapis.com"))
    raise SystemExit(f"unknown MHS_OBJECT_STORE {kind!r}: local or gcs")
