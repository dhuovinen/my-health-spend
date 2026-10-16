"""PRV-07 encrypted vault backup and scripted restore: TC-PRV-07-1 and TC-PRV-07-2."""

import pytest

from mhs.data.db import Database
from mhs.data.keys import db_keyring
from mhs.vault import cli
from mhs.vault.backup import BackupError, make_backup, read_backup, restore_backup
from mhs.vault.store import VaultStore

pytestmark = pytest.mark.postgres

PASSPHRASE = "correct horse battery staple"
PEOPLE = {"name": "Pat Example", "dob": "1970-01-01", "member_id": "XZ123456789"}


@pytest.fixture
def filled(vault_store):
    """Two households' vault entries."""
    tokens = {}
    for hid in ("11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"):
        tokens[hid] = {kind: vault_store.tokenize(hid, kind, f"{value} {hid[:1]}") for kind, value in PEOPLE.items()}
    return tokens


@pytest.fixture
def fresh_vault(pg_server, vault_keys):
    """A second, empty database: the 'fresh server' the backup is restored onto, with the same vault key."""
    pgdb = pg_server.create_database()
    db = Database(pgdb.url("vault"), max_size=2)
    yield pgdb, db, VaultStore(db, db_keyring(db, vault_keys, "vault.household_keys"))
    db.close()


def test_tc_prv_07_1_restore_onto_a_fresh_server(vault_db, filled, fresh_vault):
    blob = make_backup(vault_db, PASSPHRASE)
    assert b"Pat Example" not in blob and b"XZ123456789" not in blob
    _, db, restored = fresh_vault
    assert restore_backup(db, blob, PASSPHRASE) == {"households": 2, "entries": 6}
    for hid, tokens in filled.items():
        for kind, token in tokens.items():
            assert restored.detokenize(hid, token) == (kind, f"{PEOPLE[kind]} {hid[:1]}")
        # New tokenization of a known value finds the restored token rather than minting a new one.
        assert restored.tokenize(hid, "name", f"Pat Example {hid[:1]}") == tokens["name"]
    assert restored.count() == 6


def test_tc_prv_07_2_wrong_passphrase_fails_without_a_hint(vault_db, filled, fresh_vault):
    blob = make_backup(vault_db, PASSPHRASE)
    _, db, restored = fresh_vault
    with pytest.raises(BackupError) as e:
        restore_backup(db, blob, "wrong passphrase here")
    assert str(e.value) == "The backup could not be opened."
    assert restored.count() == 0 and restored.households() == []
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(BackupError, match="could not be opened"):
        read_backup(tampered, PASSPHRASE)
    with pytest.raises(BackupError, match="not a vault backup"):
        read_backup(b"garbage", PASSPHRASE)


def test_restore_refuses_a_vault_that_is_not_empty(vault_db, filled):
    blob = make_backup(vault_db, PASSPHRASE)
    with pytest.raises(BackupError, match="not empty"):
        restore_backup(vault_db, blob, PASSPHRASE)


def test_short_passphrase_refused(vault_db):
    with pytest.raises(BackupError, match="at least"):
        make_backup(vault_db, "short")


def test_scripted_backup_and_restore(vault_db, filled, fresh_vault, pgdb, tmp_path, monkeypatch, capsys):
    """The mhs-vault commands as run in the vault container: backup on one server, restore on another."""
    key_file = tmp_path / "keys" / "vault.kek"  # the vault_keys fixture's file
    monkeypatch.setenv("MHS_KEY_FILE", str(key_file))
    monkeypatch.setenv("MHS_BACKUP_PASSPHRASE", PASSPHRASE)
    monkeypatch.setenv("MHS_DATABASE_URL", pgdb.url("vault"))
    out = tmp_path / "backups" / "vault.mhsvb"
    cli.main(["backup", "--out", str(out)])
    assert "6 entries, 2 household(s)" in capsys.readouterr().out
    fresh_pgdb, _, restored = fresh_vault
    monkeypatch.setenv("MHS_DATABASE_URL", fresh_pgdb.url("vault"))
    cli.main(["restore", "--in", str(out)])
    assert "6 entries, 2 household(s)" in capsys.readouterr().out
    hid, tokens = next(iter(filled.items()))
    assert restored.detokenize(hid, tokens["dob"]) == ("dob", f"1970-01-01 {hid[:1]}")
    monkeypatch.setenv("MHS_BACKUP_PASSPHRASE", "wrong passphrase here")
    with pytest.raises(SystemExit, match="restore failed: The backup could not be opened"):
        cli.main(["restore", "--in", str(out)])
