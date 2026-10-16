"""Release 1 adapters that need no database: keys, object storage, OCR stub, stack secrets."""

import base64
import stat

import pytest

from mhs.data.keys import DecryptError, Keyring, LocalKeyFile, open_sealed, seal
from mhs.data.objects import LocalObjectStore
from mhs.ingest.ocr import OcrUnavailable, StubOcr, TesseractOcr, get_engine
from mhs.stack import SECRET_LAYOUT, init_secrets


def memory_keyring(keys) -> Keyring:
    stored: dict[str, bytes] = {}
    return Keyring(keys, stored.get, lambda hid, w: stored.setdefault(hid, w))


def test_seal_round_trip_and_context_binding():
    key = b"k" * 32
    blob = seal(key, b"secret", "household-a|original:doc1")
    assert b"secret" not in blob
    assert open_sealed(key, blob, "household-a|original:doc1") == b"secret"
    with pytest.raises(DecryptError):
        open_sealed(key, blob, "household-b|original:doc1")  # moved to another household
    with pytest.raises(DecryptError):
        open_sealed(b"x" * 32, blob, "household-a|original:doc1")  # wrong key
    with pytest.raises(DecryptError):
        open_sealed(key, blob[:-1] + bytes([blob[-1] ^ 1]), "household-a|original:doc1")  # tampered
    with pytest.raises(DecryptError):
        open_sealed(key, b"plain", "x")


def test_local_key_file_created_private_and_reused(tmp_path):
    path = tmp_path / "keys" / "kek"
    keys = LocalKeyFile.create(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    wrapped = keys.wrap(b"d" * 32, "household:1")
    assert LocalKeyFile.create(path).unwrap(wrapped, "household:1") == b"d" * 32  # same file, same key
    other = LocalKeyFile.create(tmp_path / "other")
    with pytest.raises(DecryptError):
        other.unwrap(wrapped, "household:1")


def test_local_key_file_rejects_bad_files(tmp_path):
    with pytest.raises(RuntimeError):
        LocalKeyFile(tmp_path / "missing")
    short = tmp_path / "short"
    short.write_text(base64.b64encode(b"x" * 16).decode())
    with pytest.raises(RuntimeError):
        LocalKeyFile(short)


def test_keyring_per_household_keys(tmp_path):
    ring = memory_keyring(LocalKeyFile.create(tmp_path / "kek"))
    a, b = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
    assert ring.data_key(a) != ring.data_key(b)
    assert ring.data_key(a) == ring.data_key(a)
    blob = ring.encrypt(a, b"hello", "original:doc1")
    assert ring.decrypt(a, blob, "original:doc1") == b"hello"
    with pytest.raises(DecryptError):
        ring.decrypt(b, blob, "original:doc1")


def test_local_object_store(tmp_path):
    store = LocalObjectStore(tmp_path / "objects")
    store.put("households/h1/originals/doc_1", b"abc")
    assert store.exists("households/h1/originals/doc_1")
    assert store.get("households/h1/originals/doc_1") == b"abc"
    store.put("households/h1/originals/doc_1", b"def")  # replaced atomically
    assert store.get("households/h1/originals/doc_1") == b"def"
    store.delete("households/h1/originals/doc_1")
    assert not store.exists("households/h1/originals/doc_1")
    assert not any(p.name.startswith(".tmp-") for p in (tmp_path / "objects").rglob("*"))
    for bad in ("../escape", "a/../../b", "/abs", "a//b", "", ".hidden"):
        with pytest.raises(ValueError):
            store.put(bad, b"x")


def test_ocr_engines_are_chosen_by_name():
    engine = get_engine()
    assert isinstance(engine, StubOcr)
    with pytest.raises(OcrUnavailable):
        engine.read(b"%PDF", "application/pdf")
    assert isinstance(get_engine("tesseract"), TesseractOcr)
    with pytest.raises(ValueError):
        get_engine("nope")


def test_init_secrets_layout_and_idempotence(tmp_path):
    written = init_secrets(tmp_path, chown=False)
    assert len(written) == sum(len(c) for c in SECRET_LAYOUT.values())
    # Copies of one secret agree; different secrets differ.
    assert (tmp_path / "app/db_password").read_text() == (tmp_path / "migrate/db_app_password").read_text()
    assert (tmp_path / "app/vault_token").read_text() == (tmp_path / "vault/vault_token").read_text()
    assert (tmp_path / "app/kek").read_text() != (tmp_path / "vault/kek").read_text()
    assert len(base64.b64decode((tmp_path / "app/kek").read_text())) == 32
    # Each service folder holds only what that service needs: the worker gets no key and no vault token.
    assert sorted(p.name for p in (tmp_path / "worker").iterdir()) == ["db_password"]
    assert "kek" not in [p.name for p in (tmp_path / "postgres").iterdir()]
    assert stat.S_IMODE((tmp_path / "app/kek").stat().st_mode) == 0o400
    before = (tmp_path / "app/kek").read_text()
    assert init_secrets(tmp_path, chown=False) == []
    assert (tmp_path / "app/kek").read_text() == before
