"""PRV-06 encryption at rest: TC-PRV-06-2 (unreadable without the key) and TC-PRV-06-3 (other tiers can't decrypt)."""

import hashlib

import pytest

from mhs.data.keys import DecryptError, LocalKeyFile, db_keyring
from tests.conftest import admin_sql

pytestmark = pytest.mark.postgres

MARKER = b"SYNTHETIC-MARKER-7f3a9c Pat Example DOB 1970-01-01"


def upload(household, client, name="Pat Example statement.pdf", data=b"%PDF-1.4 " + MARKER):
    r = client.post("/documents", files={"file": (name, data, "application/pdf")},
                    data={"csrf_token": household.csrf(client)}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r.headers["location"].split("uploaded=")[1]


def test_tc_prv_06_2_original_is_unreadable_on_disk(household, pgdb):
    who = household.enrol()
    c = household.sign_in(who)
    doc_id = upload(household, c)
    stored = (household.objects_dir / "households" / who.household_id / "originals" / doc_id).read_bytes()
    assert MARKER not in stored and b"%PDF" not in stored
    # The records database holds the hash and metadata, never the file name in the clear.
    rows = admin_sql(pgdb, "SELECT data::text FROM app.records WHERE kind = 'document'")
    assert "Pat Example" not in rows[0][0]
    # The member gets the original back, byte for byte, with its recorded hash.
    data = c.get(f"/documents/{doc_id}").content
    assert data == b"%PDF-1.4 " + MARKER
    assert c.get(f"/api/documents/{doc_id}").json()["sha256"] == hashlib.sha256(data).hexdigest()
    assert 'filename="Pat Example statement.pdf"' in c.get(f"/documents/{doc_id}").headers["content-disposition"]


def test_tc_prv_06_2_vault_entries_and_totp_secrets_are_sealed(household, vault_client, pgdb):
    who = household.enrol()
    vault_client.tokenize(who.household_id, "name", "Pat Example")
    dump = admin_sql(pgdb, "SELECT kind, lookup, sealed FROM vault.entries")
    assert all(b"Pat Example" not in bytes(col) for row in dump for col in row[1:])
    secret = admin_sql(pgdb, "SELECT totp_secret FROM app.members WHERE id = %s", (who.member_id,))[0][0]
    assert who.totp_secret.encode() not in bytes(secret)
    wrapped = admin_sql(pgdb, "SELECT wrapped FROM app.household_keys")
    assert len(wrapped) == 1 and len(bytes(wrapped[0][0])) > 32  # stored wrapped, never the raw key


def test_tc_prv_06_3_other_keys_cannot_decrypt(household, app_db, tmp_path):
    """Without the application tier's key (the worker has none), the originals can't be opened."""
    who = household.enrol()
    c = household.sign_in(who)
    doc_id = upload(household, c)
    stored = (household.objects_dir / "households" / who.household_id / "originals" / doc_id).read_bytes()
    stranger = db_keyring(app_db, LocalKeyFile.create(tmp_path / "stranger.kek"), "app.household_keys")
    with pytest.raises(DecryptError):
        stranger.decrypt(who.household_id, stored, f"original:{doc_id}")


def test_ciphertext_moved_between_households_does_not_open(household, app_keyring):
    a, b = household.enrol("A"), household.enrol("B")
    ca = household.sign_in(a)
    doc_a = upload(household, ca)
    path = household.objects_dir / "households" / a.household_id / "originals" / doc_a
    with pytest.raises(DecryptError):
        app_keyring.decrypt(b.household_id, path.read_bytes(), f"original:{doc_a}")


def test_upload_rules(household):
    who = household.enrol()
    c = household.sign_in(who)
    csrf = household.csrf(c)
    assert c.post("/documents", files={"file": ("x.exe", b"MZ", "application/octet-stream")},
                  data={"csrf_token": csrf}).status_code == 415
    assert c.post("/documents", files={"file": ("x.pdf", b"", "application/pdf")},
                  data={"csrf_token": csrf}).status_code == 400
    assert c.post("/documents", files={"file": ("x.png", b"\x89PNG", "image/png")},
                  data={"csrf_token": csrf}, follow_redirects=False).status_code == 303
