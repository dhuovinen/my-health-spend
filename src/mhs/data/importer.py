"""Validate an ingest file, preview what it would change, and save it.

Nothing is written unless the file passes schema and cross-reference validation. Records are
upserted by id, so re-importing a corrected file is how data is fixed. The one exception: a record the
owner changed in the app (Settings, provider notes) keeps the owner's version when the file differs,
unless the owner chooses to replace their edits at confirm time.
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Protocol

from jsonschema import Draft202012Validator, FormatChecker

from mhs.config import SCHEMA_PATH
from mhs.data.money import to_cents
from mhs.data.store import Store

SECTIONS = {
    "plans": "plan",
    "accounts": "account",
    "members": "member",
    "providers": "provider",
    "provider_relationships": "provider_relationship",
    "provider_notes": "provider_note",
    "visits": "visit",
    "documents": "document",
}

# (field, target kind) references checked on every record; list fields hold several ids.
REFERENCES = [
    ("provider_id", "provider"), ("related_provider_id", "provider"), ("visit_id", "visit"),
    ("plan_id", "plan"), ("member_id", "member"), ("account_id", "account"), ("from_account_id", "account"),
]
LIST_REFERENCES = [("member_ids", "member"), ("visit_ids", "visit"), ("payment_ids", "document")]


# Fields the importer adds to a document record; they don't count as differences on re-import.
BOOKKEEPING = ("stored_file", "file_sha256")


class FileSource(Protocol):
    """Where the files an ingest file attaches (documents[].file) are read from."""

    def exists(self, name: str) -> bool: ...

    def read(self, name: str) -> bytes: ...

    def missing(self, name: str) -> str:
        """Why a file is missing, for the preview's warning."""
        ...


class FolderSource:
    """Files beside the ingest file on disk (Release 0 import by path; the mhs-admin import command)."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)

    def exists(self, name: str) -> bool:
        return (self.base_dir / name).is_file()

    def read(self, name: str) -> bytes:
        return (self.base_dir / name).read_bytes()

    def missing(self, name: str) -> str:
        return f"file {name!r} not found"


class UploadedSource:
    """Files uploaded together with the ingest file, matched by file name (Release 1 import page)."""

    def __init__(self, files: dict[str, bytes]):
        self.files = {PurePosixPath(n).name: data for n, data in files.items()}

    def exists(self, name: str) -> bool:
        return PurePosixPath(name).name in self.files

    def read(self, name: str) -> bytes:
        return self.files[PurePosixPath(name).name]

    def missing(self, name: str) -> str:
        if not self.files:
            return f"file {name!r} not attached (add it with the ingest file to store it)"
        return f"file {name!r} not among the attached files"


class DocumentFiles(Protocol):
    """Where attached files are kept once imported. save() returns the fields to set on the document record."""

    def save(self, doc_id: str, name: str, data: bytes) -> dict: ...


class FolderFiles:
    """Release 0: plain copies in the data folder's documents/."""

    def __init__(self, documents_dir: Path):
        self.documents_dir = Path(documents_dir)

    def save(self, doc_id: str, name: str, data: bytes) -> dict:
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        stored = f"{doc_id}{PurePosixPath(name).suffix.lower()}"
        (self.documents_dir / stored).write_bytes(data)
        return {"stored_file": stored, "file_sha256": hashlib.sha256(data).hexdigest()}


@dataclass
class KeptEdit:
    section: str
    kind: str
    id: str
    fields: list[str]  # fields the file would change; empty when the owner deleted the record


@dataclass
class ImportPlan:
    source: str
    data: dict
    files: FileSource | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, dict[str, int]] = field(default_factory=dict)
    kept: list[KeptEdit] = field(default_factory=list)  # owner edits the file would overwrite

    @property
    def ok(self) -> bool:
        return not self.errors

    def kept_in(self, section: str) -> int:
        return sum(k.section == section for k in self.kept)


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _label(data: dict, path) -> str:
    parts = list(path)
    if len(parts) >= 2 and parts[0] in SECTIONS and isinstance(parts[1], int):
        rec = data.get(parts[0], [])[parts[1]]
        rid = rec.get("id", "?") if isinstance(rec, dict) else "?"
        rest = "/".join(str(p) for p in parts[2:])
        return f"{parts[0]}[{parts[1]}] ({rid})" + (f" {rest}" if rest else "")
    return "/".join(str(p) for p in parts) or "file"


def schema_errors(data: dict) -> list[str]:
    schema = _schema()
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = []
    doc_types = {k for k in schema["$defs"] if schema["$defs"][k].get("allOf")}
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = list(err.path)
        if len(path) == 2 and path[0] == "documents" and err.validator == "oneOf":
            # oneOf hides the real problem; re-check against the definition named by "type".
            doc = data["documents"][path[1]]
            dtype = doc.get("type") if isinstance(doc, dict) else None
            if dtype in doc_types:
                sub = Draft202012Validator({"$defs": schema["$defs"], "$ref": f"#/$defs/{dtype}"},
                                           format_checker=FormatChecker())
                for e in sub.iter_errors(doc):
                    errors.append(f"{_label(data, path + list(e.path))}: {e.message}")
                continue
            errors.append(f"{_label(data, path)}: unknown document type {dtype!r}")
            continue
        errors.append(f"{_label(data, path)}: {err.message}")
    return errors


def reference_errors(data: dict, store: Store) -> list[str]:
    known = {kind: store.ids(kind) for kind in SECTIONS.values()}
    errors = []
    for section, kind in SECTIONS.items():
        seen = set()
        for rec in data.get(section, []):
            if rec["id"] in seen:
                errors.append(f"{section}: id {rec['id']!r} appears more than once")
            seen.add(rec["id"])
        known[kind] |= seen
    payment_ids = {d["id"] for d in data.get("documents", []) if d.get("type") == "payment"}
    payment_ids |= {d["id"] for d in store.all("document") if d.get("type") == "payment"}

    def check(obj, where):
        if isinstance(obj, dict):
            for fname, kind in REFERENCES:
                if fname in obj and obj[fname] not in known[kind]:
                    errors.append(f"{where}: {fname} {obj[fname]!r} does not match any {kind}")
            for fname, kind in LIST_REFERENCES:
                for ref in obj.get(fname, []) if isinstance(obj.get(fname), list) else []:
                    valid = ref in payment_ids if fname == "payment_ids" else ref in known[kind]
                    if not valid:
                        target = "payment" if fname == "payment_ids" else kind
                        errors.append(f"{where}: {fname} entry {ref!r} does not match any {target}")
            for v in obj.values():
                if isinstance(v, (list, dict)):
                    check(v, where)
        elif isinstance(obj, list):
            for x in obj:
                check(x, where)

    for section in SECTIONS:
        for rec in data.get(section, []):
            check(rec, f"{section} ({rec['id']})")
    return errors


def _comparable(rec: dict) -> dict:
    """A record without bookkeeping and empty fields, so a missing list and an empty one compare equal."""
    return {k: v for k, v in rec.items() if k not in BOOKKEEPING and v not in (None, "", [], {})}


def _kept_edit(section: str, kind: str, rec: dict, old: dict | None, edited: set[str]) -> KeptEdit | None:
    """The owner's edit this record would overwrite, if any (old is the stored record, None if deleted)."""
    if rec["id"] not in edited:
        return None
    if old is None:
        return KeptEdit(section, kind, rec["id"], [])
    old, new = _comparable(old), _comparable(to_cents(rec))
    if old == new:
        return None
    return KeptEdit(section, kind, rec["id"], sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k)))


def prepare(data: dict, store: Store, source: str, files: Path | FileSource | None) -> ImportPlan:
    """files: where attached files are read from (a folder, or uploaded files); None when there are none."""
    if isinstance(files, Path):
        files = FolderSource(files)
    plan = ImportPlan(source=source, data=data, files=files)
    plan.errors = schema_errors(data)
    if plan.errors:
        return plan
    plan.errors = reference_errors(data, store)
    if plan.errors:
        return plan

    for section, kind in SECTIONS.items():
        records = data.get(section, [])
        if not records:
            continue
        existing = {r["id"]: r for r in store.all(kind)}
        edited = store.edited_ids(kind)
        c = {"new": 0, "updated": 0, "unchanged": 0}
        for rec in records:
            old = existing.get(rec["id"])
            if kept := _kept_edit(section, kind, rec, old, edited):
                plan.kept.append(kept)
            elif old is None:
                c["new"] += 1
            elif _comparable(old) == _comparable(to_cents(rec)):
                c["unchanged"] += 1
            else:
                c["updated"] += 1
        plan.counts[section] = c

    for doc in data.get("documents", []):
        if "file" not in doc:
            continue
        if files is None:
            plan.warnings.append(f"documents ({doc['id']}): file {doc['file']!r} not attached (uploaded JSON has no folder to read it from; import by path instead)")
        elif not files.exists(doc["file"]):
            plan.warnings.append(f"documents ({doc['id']}): {files.missing(doc['file'])}")
    return plan


def commit(plan: ImportPlan, store: Store, documents: Path | DocumentFiles, replace_edits: bool = False) -> dict:
    """Save the plan. documents: where attached files go (a folder for Release 0, or encrypted storage)."""
    if not plan.ok:
        raise ValueError("Cannot import a file with errors")
    if isinstance(documents, Path):
        documents = FolderFiles(documents)
    existing_docs = {d["id"]: d for d in store.all("document")}
    # Re-check owner edits now: the owner may have edited something since the preview.
    kept = set()
    for section, kind in SECTIONS.items():
        records = plan.data.get(section, [])
        if records:
            existing, edited = {r["id"]: r for r in store.all(kind)}, store.edited_ids(kind)
            kept |= {(kind, r["id"]) for r in records if _kept_edit(section, kind, r, existing.get(r["id"]), edited)}
    items = []
    for section, kind in SECTIONS.items():
        for rec in plan.data.get(section, []):
            if (kind, rec["id"]) in kept and not replace_edits:
                continue
            rec = to_cents(rec)
            if kind == "document":
                for k in BOOKKEEPING:  # only the importer sets these; never trust them from a file
                    rec.pop(k, None)
                if plan.files is not None and "file" in rec and plan.files.exists(rec["file"]):
                    rec.update(documents.save(rec["id"], rec["file"], plan.files.read(rec["file"])))
                elif rec["id"] in existing_docs:
                    rec.update({k: existing_docs[rec["id"]][k] for k in BOOKKEEPING if k in existing_docs[rec["id"]]})
            items.append((kind, rec))
    store.upsert_many(items)
    if replace_edits:
        store.clear_edited(sorted(kept))
    summary = {"counts": plan.counts, "warnings": len(plan.warnings)}
    if kept:
        summary["edits_replaced" if replace_edits else "edits_kept"] = len(kept)
    store.log_import(plan.source, summary)
    return summary


def record_errors(definition: str, record: dict) -> list[str]:
    """Validate one record (in ingest dollars) against a schema definition, e.g. 'plan'."""
    schema = _schema()
    validator = Draft202012Validator({"$defs": schema["$defs"], "$ref": f"#/$defs/{definition}"},
                                     format_checker=FormatChecker())
    return [f"{'/'.join(str(p) for p in e.path) or definition}: {e.message}" for e in validator.iter_errors(record)]
