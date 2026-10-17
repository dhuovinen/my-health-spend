"""Google Cloud adapters before the account (ADR-036): Cloud Storage, Cloud KMS and Document AI against fakes that
answer in the APIs' shapes (and the fake GCS server on the stack), plus import previews kept in the database."""

import base64
import json
import os
import re
import uuid
from urllib.parse import unquote

import httpx
import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from mhs.data.gcp import GoogleError, StaticToken
from mhs.data.keys import CloudKms, DecryptError, Keyring, LocalKeyFile, keys_from_env
from mhs.data.objects import GcsObjectStore, LocalObjectStore, object_store_from_env
from mhs.ingest.ocr import DocumentAiOcr, OcrUnavailable, documentai_result, get_engine
from mhs.ingest.text import PDF, read_text
from tests.conftest import admin_sql
from tests.pdfs import make_image, make_scanned_pdf


# --- Cloud Storage -------------------------------------------------------------------------------------

class FakeGcs:
    """The JSON API calls the store makes: media upload, metadata, media download, delete."""

    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.auth: set[str] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.auth.add(request.headers.get("authorization", ""))
        url = request.url
        if request.method == "POST" and url.path.startswith("/upload/storage/v1/b/"):
            bucket = url.path.split("/")[5]
            self.objects[(bucket, url.params["name"])] = request.content
            return httpx.Response(200, json={"name": url.params["name"]})
        m = re.match(r"^/storage/v1/b/([^/]+)/o/(.+)$", url.raw_path.decode().split("?")[0])
        if not m:
            return httpx.Response(400)
        bucket, name = m.group(1), unquote(m.group(2))
        if (bucket, name) not in self.objects:
            return httpx.Response(404)
        if request.method == "DELETE":
            del self.objects[(bucket, name)]
            return httpx.Response(204)
        if url.params.get("alt") == "media":
            return httpx.Response(200, content=self.objects[(bucket, name)])
        return httpx.Response(200, json={"name": name})


def test_gcs_store_round_trip():
    fake = FakeGcs()
    store = GcsObjectStore("mhs-staging", http=httpx.Client(transport=httpx.MockTransport(fake)),
                           token=StaticToken("t-1"), endpoint="http://gcs.test")
    key = "households/abc/originals/upl_1"
    store.put(key, b"\x00sealed bytes")
    assert ("mhs-staging", key) in fake.objects  # the slashes stay part of one object name
    assert store.exists(key) and store.get(key) == b"\x00sealed bytes"
    store.delete(key)
    store.delete(key)  # deleting what isn't there is fine
    assert not store.exists(key)
    with pytest.raises(FileNotFoundError):
        store.get(key)
    assert fake.auth == {"Bearer t-1"}
    for bad in ("../escape", "a//b", "/abs"):
        with pytest.raises(ValueError):
            store.put(bad, b"x")


def test_gcs_errors_name_only_the_operation():
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503, text="secret details")))
    store = GcsObjectStore("b", http=http, token=StaticToken(), endpoint="http://gcs.test")
    with pytest.raises(GoogleError, match=r"^storage put failed: HTTP 503$"):
        store.put("k", b"x")


@pytest.mark.stack
def test_gcs_store_against_the_fake_gcs_server():
    """The same store against the fake GCS server container (compose test profile)."""
    endpoint = os.environ.get("MHS_TEST_GCS_ENDPOINT")
    if not endpoint:
        pytest.skip("runs in the compose tests runner (MHS_TEST_GCS_ENDPOINT)")
    bucket = f"mhs-test-{uuid.uuid4().hex[:8]}"
    httpx.post(f"{endpoint}/storage/v1/b", params={"project": "test"}, json={"name": bucket}).raise_for_status()
    store = GcsObjectStore(bucket, endpoint=endpoint)
    store.put("households/h1/documents/doc_1", b"ciphertext")
    assert store.get("households/h1/documents/doc_1") == b"ciphertext"
    assert store.exists("households/h1/documents/doc_1") and not store.exists("households/h1/documents/doc_2")
    store.delete("households/h1/documents/doc_1")
    assert not store.exists("households/h1/documents/doc_1")


# --- Cloud KMS -----------------------------------------------------------------------------------------

class FakeKms:
    """encrypt/decrypt as Cloud KMS does them: the key stays inside; the AAD must match on decrypt."""

    def __init__(self):
        self.key = AESGCM.generate_key(bit_length=256)
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        verb = request.url.path.rsplit(":", 1)[1]
        self.calls.append(request.url.path)
        body = json.loads(request.content)
        aad = base64.b64decode(body.get("additionalAuthenticatedData", ""))
        if verb == "encrypt":
            nonce = os.urandom(12)
            ct = nonce + AESGCM(self.key).encrypt(nonce, base64.b64decode(body["plaintext"]), aad)
            return httpx.Response(200, json={"ciphertext": base64.b64encode(ct).decode()})
        raw = base64.b64decode(body["ciphertext"])
        try:
            pt = AESGCM(self.key).decrypt(raw[:12], raw[12:], aad)
        except InvalidTag:
            return httpx.Response(400, json={"error": {"status": "INVALID_ARGUMENT"}})
        return httpx.Response(200, json={"plaintext": base64.b64encode(pt).decode()})


KEY = "projects/mhs-staging/locations/us/keyRings/mhs/cryptoKeys/app"


def kms(fake=None) -> tuple[CloudKms, FakeKms]:
    fake = fake or FakeKms()
    return CloudKms(KEY, http=httpx.Client(transport=httpx.MockTransport(fake)), token=StaticToken(),
                    endpoint="http://kms.test"), fake


def test_kms_wraps_household_keys_bound_to_their_household():
    service, fake = kms()
    stored: dict = {}
    ring = Keyring(service, stored.get, lambda hid, w: stored.setdefault(hid, w))
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    blob = ring.encrypt(a, b"statement bytes", "original:upl_1")
    assert ring.decrypt(a, blob, "original:upl_1") == b"statement bytes"
    assert ring.data_key(a) != ring.data_key(b)
    assert fake.calls[0] == f"/v1/{KEY}:encrypt"
    with pytest.raises(DecryptError):  # a wrapped key moved to another household doesn't open
        service.unwrap(stored[a], f"household:{b}")
    other, _ = kms()  # another KMS key
    with pytest.raises(DecryptError):
        other.unwrap(stored[a], f"household:{a}")


def test_kms_errors_name_only_the_operation():
    service = CloudKms(KEY, http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403))),
                       token=StaticToken(), endpoint="http://kms.test")
    with pytest.raises(GoogleError, match=r"^kms encrypt failed: HTTP 403$"):
        service.wrap(b"k" * 32, "household:x")


# --- Document AI ---------------------------------------------------------------------------------------

def documentai_response(pages: list[str], confidence: float = 0.97) -> dict:
    """A `process` response in Document AI's shape: one text, pages with text anchors and word tokens."""
    text, out_pages = "", []
    for page in pages:
        start = len(text)
        tokens, y = [], 0.05
        for line in page.splitlines():
            x = 0.05
            for word in line.split():
                tokens.append((word, x, y))
                x += 0.02 * (len(word) + 1)
            y += 0.03
        text += page + "\n"
        out_tokens, cursor = [], start
        for word, x, y in tokens:
            at = text.index(word, cursor)
            cursor = at + len(word)
            out_tokens.append({"layout": {
                "textAnchor": {"textSegments": [{"startIndex": str(at), "endIndex": str(cursor)}]},
                "confidence": confidence,
                "boundingPoly": {"normalizedVertices": [{"x": x, "y": y}, {"x": x + 0.02 * len(word), "y": y},
                                                        {"x": x + 0.02 * len(word), "y": y + 0.02},
                                                        {"x": x, "y": y + 0.02}]}}})
        out_pages.append({"pageNumber": len(out_pages) + 1, "tokens": out_tokens,
                          "layout": {"textAnchor": {"textSegments": [{"startIndex": str(start),
                                                                      "endIndex": str(len(text))}]}}})
    return {"document": {"text": text, "pages": out_pages}}


class FakeDocAi:
    def __init__(self, pages: list[str], status: int = 200):
        self.pages, self.status, self.sent = pages, status, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.sent.append((request.url.path, json.loads(request.content)))
        if self.status != 200:
            return httpx.Response(self.status)
        return httpx.Response(200, json=documentai_response(self.pages))


PROCESSOR = "projects/mhs-staging/locations/us/processors/abc123"
EOB_TEXT = "Example Health\nEXPLANATION OF BENEFITS\nAmount billed: $320.00\nYour responsibility: $45.00"


def docai(fake) -> DocumentAiOcr:
    return DocumentAiOcr(PROCESSOR, http=httpx.Client(transport=httpx.MockTransport(fake)), token=StaticToken(),
                         endpoint="http://docai.test")


def test_documentai_reads_text_words_and_confidence():
    fake = FakeDocAi([EOB_TEXT])
    result = docai(fake).read(make_image(EOB_TEXT), "image/png")
    path, body = fake.sent[0]
    assert path == f"/v1/{PROCESSOR}:process" and body["rawDocument"]["mimeType"] == "image/png"
    assert body["skipHumanReview"] is True
    assert "Amount billed: $320.00" in result.text and result.engine == "documentai"
    assert result.words[0].text == "Example" and result.words[0].page == 1
    left, top, right, bottom = result.words[0].box
    assert 0 <= left < right <= 1 and 0 <= top < bottom <= 1
    assert result.confidence == 0.97


def test_documentai_gets_heic_as_jpeg():
    fake = FakeDocAi([EOB_TEXT])
    docai(fake).read(make_image(EOB_TEXT, "HEIC"), "image/heic")
    assert fake.sent[0][1]["rawDocument"]["mimeType"] == "image/jpeg"


def test_documentai_reads_a_scanned_pdf_through_read_text():
    fake = FakeDocAi(["Page one: Amount billed: $320.00", "Page two: Your responsibility: $45.00"])
    doc = read_text(PDF, make_scanned_pdf("one", "two"), docai(fake))
    assert doc.how == "scanned PDF, OCR (documentai)" and doc.pages == 2
    assert "Your responsibility: $45.00" in doc.text


def test_documentai_unconfigured_and_failing():
    with pytest.raises(OcrUnavailable):
        DocumentAiOcr("").read(b"x", "image/png")
    with pytest.raises(GoogleError, match=r"^document ai process failed: HTTP 500$"):
        docai(FakeDocAi([], status=500)).read(make_image("x"), "image/png")
    assert isinstance(get_engine("documentai"), DocumentAiOcr)


def test_documentai_result_without_pages():
    assert documentai_result({"text": "hello"}).text == "hello"


# --- choosing adapters ---------------------------------------------------------------------------------

def test_adapters_chosen_by_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("MHS_OBJECT_STORE", raising=False)
    monkeypatch.delenv("MHS_KEYS", raising=False)
    monkeypatch.delenv("MHS_OBJECTS_DIR", raising=False)
    monkeypatch.delenv("MHS_KEY_FILE", raising=False)
    LocalKeyFile.create(tmp_path / "kek")
    assert isinstance(object_store_from_env(tmp_path / "objects"), LocalObjectStore)
    assert isinstance(keys_from_env(tmp_path / "kek"), LocalKeyFile)
    monkeypatch.setenv("MHS_OBJECT_STORE", "gcs")
    with pytest.raises(SystemExit, match="MHS_GCS_BUCKET"):
        object_store_from_env(tmp_path)
    monkeypatch.setenv("MHS_GCS_BUCKET", "mhs-staging")
    monkeypatch.setenv("MHS_GCS_ENDPOINT", "http://fake-gcs:4443")
    assert isinstance(object_store_from_env(tmp_path), GcsObjectStore)
    monkeypatch.setenv("MHS_KEYS", "kms")
    with pytest.raises(SystemExit, match="MHS_KMS_KEY"):
        keys_from_env(tmp_path / "kek")
    monkeypatch.setenv("MHS_KMS_KEY", KEY)
    monkeypatch.setenv("MHS_KMS_ENDPOINT", "http://kms.test")
    assert isinstance(keys_from_env(tmp_path / "kek"), CloudKms)
    monkeypatch.setenv("MHS_OBJECT_STORE", "s3")
    with pytest.raises(SystemExit, match="unknown"):
        object_store_from_env(tmp_path)


# --- import previews in the database -------------------------------------------------------------------

@pytest.mark.postgres
def test_import_preview_can_be_confirmed_on_another_app_instance(household, tmp_path, app_db, app_keyring,
                                                                 vault_client, pgdb):
    """ADR-036: the preview lives in the database, sealed, so a second app instance confirms it."""
    from mhs.data.household_store import HouseholdStore
    from mhs.data.objects import LocalObjectStore as Local
    from mhs.stack import AppConfig
    from mhs.web.household.app import create_app
    from tests.conftest import SAMPLE, VAULT_TOKEN
    from tests.test_web import CsrfClient

    who = household.enrol()
    first = household.sign_in(who)
    client = CsrfClient(first, household.csrf(first))
    preview = client.post("/import", files=[("file", ("ingest.json", SAMPLE.read_bytes(), "application/json"))])
    token = re.search(r'name="token" value="([^"]+)"', preview.text).group(1)
    [(sealed,)] = admin_sql(pgdb, "SELECT sealed FROM app.import_previews WHERE household_id = %s", (who.household_id,))
    assert b"Example Family Medicine" not in bytes(sealed)  # sealed with the household's key

    config = AppConfig(database_url="unused", objects_dir=tmp_path / "objects2", key_file=tmp_path / "unused",
                       vault_url="http://vault", vault_token=VAULT_TOKEN)
    second_app = create_app(config, db=app_db, keyring=app_keyring, objects=Local(tmp_path / "objects2"),
                            vault=vault_client)
    from fastapi.testclient import TestClient

    second = TestClient(second_app)
    second.cookies.set("mhs_session", first.cookies["mhs_session"])
    r = second.post("/import/confirm", data={"token": token, "csrf_token": household.csrf(first)},
                    follow_redirects=False)
    assert r.headers["location"] == "/import?done=1"
    assert len(HouseholdStore(app_db, who.household_id).all("visit")) == 6
    assert admin_sql(pgdb, "SELECT count(*) FROM app.import_previews WHERE household_id = %s",
                     (who.household_id,))[0][0] == 0  # used once
    again = client.post("/import/confirm", data={"token": token}, follow_redirects=False)
    assert again.headers["location"] == "/import"


@pytest.mark.postgres
def test_a_stale_import_preview_is_refused(household, app_db, pgdb):
    from mhs.data.household_store import HouseholdStore
    from tests.conftest import SAMPLE
    from tests.test_web import CsrfClient

    who = household.enrol()
    raw = household.sign_in(who)
    client = CsrfClient(raw, household.csrf(raw))
    preview = client.post("/import", files=[("file", ("ingest.json", SAMPLE.read_bytes(), "application/json"))])
    token = re.search(r'name="token" value="([^"]+)"', preview.text).group(1)
    admin_sql(pgdb, "UPDATE app.import_previews SET created_at = now() - interval '2 hours' WHERE household_id = %s",
              (who.household_id,))
    r = client.post("/import/confirm", data={"token": token}, follow_redirects=False)
    assert r.headers["location"] == "/import"
    assert HouseholdStore(app_db, who.household_id).all("visit") == []
