"""Export a household's data, and delete an account and its data (PRV-09, ADR-025).

The export is a ZIP a member can keep or re-import: the records as an ingest file (the files it attaches beside
it, so `mhs-admin import` or Release 0's import by path takes it back), the uploads with what was read from them,
the household's identifiers from the vault, and a manifest with every file's SHA-256 (TC-PRV-09-1).

Deleting the last member's account deletes the household: its vault entries and vault data key, its stored files,
and every record and the app's household data key, at once (TC-PRV-09-2). Only a security log line without health
content stays, for a year (TC-PRV-09-3). Backups age out on their normal rotation (ADR-025: within 35 days).
"""

import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone

from mhs.data.db import Database
from mhs.data.household_store import HouseholdStore
from mhs.data.importer import BOOKKEEPING, SECTIONS
from mhs.data.keys import Keyring
from mhs.data.money import to_dollars
from mhs.data.objects import ObjectStore
from mhs.vault.client import VaultClient
from mhs.web.household.files import EncryptedFiles

LOG_DAYS = 365
OTHER_KINDS = ("original", "extraction")


def log_event(db: Database, household_id: str | None, member_id: str | None, event: str) -> int:
    """A security log line (no health content); lines older than a year are removed as new ones are written."""
    with db.tx() as c:
        c.execute("DELETE FROM app.security_log WHERE at < now() - make_interval(days => %s)", (LOG_DAYS,))
        return c.execute("INSERT INTO app.security_log (household_id, member_id, event) VALUES (%s, %s, %s) "
                         "RETURNING id", (household_id, member_id, event)).fetchone()["id"]


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:120] or "file"


def export_household(db: Database, keyring: Keyring, objects: ObjectStore, vault: VaultClient, household_id: str,
                     household_name: str) -> bytes:
    store = HouseholdStore(db, household_id)
    files = EncryptedFiles(objects, keyring, household_id)
    buf = io.BytesIO()
    manifest = {"exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "household": household_name,
                "records": {}, "files": []}

    def add(path: str, data: bytes) -> None:
        z.writestr(path, data)
        manifest["files"].append({"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        ingest: dict = {"schema_version": "0.1",
                        "source": {"prepared_by": "My Health Spend export", "prepared_on": manifest["exported_at"][:10]}}
        for section, kind in SECTIONS.items():
            records = []
            for rec in store.all(kind):
                out = {k: v for k, v in rec.items() if k not in BOOKKEEPING}
                if kind == "document" and rec.get("stored_file"):
                    name = f"files/documents/{_safe(rec['id'])}-{_safe(str(rec.get('file', 'file')).split('/')[-1])}"
                    add(name, files.read(rec))
                    out["file"] = name
                records.append(to_dollars(out))
            if records:
                ingest[section] = records
            manifest["records"][kind] = len(records)
        add("ingest.json", json.dumps(ingest, indent=2).encode())

        uploads = []
        for rec in store.all("original"):
            name = keyring.decrypt(household_id, bytes.fromhex(rec["filename_sealed"]), f"filename:{rec['id']}").decode()
            data = keyring.decrypt(household_id, objects.get(rec["object_key"]), f"original:{rec['id']}")
            path = f"files/uploads/{_safe(rec['id'])}-{_safe(name)}"
            add(path, data)
            uploads.append({k: rec[k] for k in ("id", "content_type", "size", "sha256", "uploaded_at", "doc_kind")
                            if k in rec} | {"filename": name, "file": path,
                                            "extraction": store.get("extraction", rec["id"])})
        manifest["records"]["original"] = len(uploads)
        add("uploads.json", json.dumps(uploads, indent=2).encode())
        identifiers = vault.entries(household_id)
        manifest["records"]["vault_entry"] = len(identifiers)
        add("identifiers.json", json.dumps(identifiers, indent=2).encode())
        z.writestr("README.txt", (
            "My Health Spend export\n\n"
            "ingest.json      your records (plans, members, providers, visits, documents, notes); import it again\n"
            "                 with the files folder beside it\n"
            "files/           the statements, EOBs and uploads you stored, unchanged\n"
            "uploads.json     your uploads and what was read from them, with your corrections\n"
            "identifiers.json names and numbers that appear in your records as tokens (tok_...)\n"
            "manifest.json    counts and a SHA-256 for every file\n"))
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
    return buf.getvalue()


def member_email(db: Database, member_id: str) -> str:
    with db.tx() as c:
        return c.execute("SELECT email FROM app.members WHERE id = %s", (member_id,)).fetchone()["email"]


def member_count(db: Database, household_id: str) -> int:
    with db.tx() as c:
        return c.execute("SELECT count(*) AS n FROM app.members WHERE household_id = %s", (household_id,)).fetchone()["n"]


def delete_household(db: Database, objects: ObjectStore, vault: VaultClient, household_id: str,
                     member_id: str) -> int:
    """Delete everything of a household at once. Returns the security log reference shown on the confirmation.
    The vault goes first: if it can't be reached nothing else is deleted, so the member can try again."""
    store = HouseholdStore(db, household_id)
    keys = [r["object_key"] for r in store.all("original")]
    keys += [d["stored_file"] for d in store.all("document") if d.get("stored_file")]
    vault.delete_household(household_id)
    for key in keys:
        objects.delete(key)
    reference = log_event(db, household_id, member_id, "household_deleted")
    with db.tx() as c:  # members, sessions, records, jobs, keys, edits and import history go with it
        c.execute("DELETE FROM app.households WHERE id = %s", (household_id,))
    return reference


def delete_member(db: Database, household_id: str, member_id: str) -> int:
    """Delete one member's account; the household and its data stay for the others."""
    reference = log_event(db, household_id, member_id, "member_deleted")
    with db.tx() as c:
        c.execute("DELETE FROM app.members WHERE id = %s AND household_id = %s", (member_id, household_id))
    return reference
