"""Uploads: provider statements, itemized bills, EOBs, HSA exports and insurer claims exports (ADR-033).

Exports are parsed here and confirmed on the import preview. Documents are stored sealed, read, scrubbed of
identifiers (vault tokens) and queued for the worker, which classifies them and extracts fields. The member then
reviews the fields, re-identified for display, corrects and confirms them; only confirmed documents reach
reconciliation (ING-05), and every correction is kept beside what was extracted (PLT-04).
"""

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from mhs.data import importer
from mhs.data.db import Database
from mhs.data.household_store import HouseholdStore
from mhs.data.importer import UploadedSource
from mhs.data.keys import Keyring
from mhs.data.objects import ObjectStore
from mhs.data.queue import JobQueue
from mhs.ingest import claims, hsa
from mhs.ingest.extract import EXTRACTED, REVIEW_THRESHOLD, TYPES
from mhs.ingest.resolve import Members, Providers, plan_for, slug
from mhs.ingest.scrub import Scrubber
from mhs.ingest.text import IMAGES, PDF, Unreadable, content_type, read_text
from mhs.ingest.values import dollars, parse_amount, parse_date
from mhs.vault.client import VaultClient
from mhs.web.household.auth import Session
from mhs.web.household.files import EncryptedFiles

ORIGINAL = "original"  # uploaded files; not ingest documents
EXTRACTION = "extraction"  # what the worker read from an original, awaiting or past review
MAX_UPLOAD = 20 * 1024 * 1024
EXPORT_TYPES = {"text/csv", "application/vnd.ms-excel",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
UPLOAD_KINDS = {
    "auto": "Let the app decide",
    "provider_statement": "Provider bill or statement",
    "itemized_bill": "Itemized bill",
    "eob": "EOB from the insurer",
    "hsa_export": "HSA/FSA transaction export (CSV, XLS, XLSX)",
    "claims_export": "Insurer claims export (CSV)",
}
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
EOB_MONEY = ("billed", "adjustment", "allowed", "insurer_paid", "deductible", "copay", "coinsurance", "not_covered",
             "patient_responsibility")
STATEMENT_MONEY = ("balance_due", "billed", "insurance_paid", "adjustment", "patient_paid")
FIELD_ORDER = ("provider", "claim_number", "account_number", "service_start", "service_end", "statement_date",
               "processed_date", "due_date", "billed", "adjustment", "allowed", "insurer_paid", "insurance_paid",
               "deductible", "copay", "coinsurance", "not_covered", "patient_responsibility", "patient_paid",
               "balance_due", "claim_status", "network_status", "notice")
LABELS = {
    "patient": "Patient", "provider": "Provider name (used for a new provider)", "claim_number": "Claim number", "service_start": "Service from",
    "service_end": "Service to", "processed_date": "Processed", "billed": "Billed", "adjustment": "Plan discount",
    "allowed": "Allowed", "insurer_paid": "Plan paid", "deductible": "Deductible", "copay": "Copay",
    "coinsurance": "Coinsurance", "not_covered": "Not covered", "patient_responsibility": "You owe (EOB)",
    "claim_status": "Claim status", "network_status": "Network", "account_number": "Account number",
    "statement_date": "Statement date", "due_date": "Due date", "balance_due": "Amount due",
    "insurance_paid": "Insurance paid", "patient_paid": "Your payments", "notice": "Notice",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Intake:
    db: Database
    keyring: Keyring
    objects: ObjectStore
    vault: VaultClient
    queue: JobQueue
    member: Callable[[Request], Session]
    check_csrf: Callable
    household_name: Callable[[str], str | None]
    preview_import: Callable


class UploadRefused(Exception):
    def __init__(self, message: str, status: int = 400):
        self.message, self.status = message, status


def add_intake(app: FastAPI, templates: Jinja2Templates, it: Intake) -> None:
    def page(request: Request, name: str, status: int = 200, **ctx) -> HTMLResponse:
        return templates.TemplateResponse(request, name, ctx, status_code=status)

    def original_name(hid: str, rec: dict) -> str:
        return it.keyring.decrypt(hid, bytes.fromhex(rec["filename_sealed"]), f"filename:{rec['id']}").decode()

    def original_bytes(hid: str, rec: dict) -> bytes:
        data = it.keyring.decrypt(hid, it.objects.get(rec["object_key"]), f"original:{rec['id']}")
        if hashlib.sha256(data).hexdigest() != rec["sha256"]:
            raise HTTPException(500)
        return data

    def status_of(rec: dict, extraction: dict | None) -> str:
        if extraction:
            return extraction.get("status", "review")
        return "export" if rec.get("doc_kind") in ("hsa_export", "claims_export") else "reading"

    def view(hid: str, rec: dict, extraction: dict | None) -> dict:
        out = {k: rec.get(k) for k in ("id", "content_type", "size", "sha256", "uploaded_at", "doc_kind")}
        out["filename"] = original_name(hid, rec)
        out["status"] = status_of(rec, extraction)
        if extraction:
            out["doc_type"] = extraction.get("doc_type")
            out["document_id"] = extraction.get("document_id")
            out["visit_ids"] = extraction.get("visit_ids", [])
        return out

    def uploads_list(session: Session) -> list[dict]:
        store = HouseholdStore(it.db, session.household_id)
        extractions = {e["id"]: e for e in store.all(EXTRACTION)}
        rows = [view(session.household_id, r, extractions.get(r["id"])) for r in store.all(ORIGINAL)]
        return sorted(rows, key=lambda r: r["uploaded_at"], reverse=True)

    def get_original(session: Session, upload_id: str) -> dict:
        rec = HouseholdStore(it.db, session.household_id).get(ORIGINAL, upload_id) if ID_PATTERN.match(upload_id) else None
        if rec is None:
            raise HTTPException(404)
        return rec

    def uploads_page(request: Request, session: Session, status: int = 200, **ctx) -> HTMLResponse:
        return page(request, "uploads.html", status, household=it.household_name(session.household_id),
                    originals=uploads_list(session), kinds=UPLOAD_KINDS, types=TYPES, **ctx)

    def store_original(session: Session, filename: str, ctype: str, data: bytes, doc_kind: str) -> str:
        hid = session.household_id
        upload_id = "upl_" + secrets.token_hex(12)
        object_key = f"households/{hid}/originals/{upload_id}"
        it.objects.put(object_key, it.keyring.encrypt(hid, data, f"original:{upload_id}"))
        HouseholdStore(it.db, hid).put(ORIGINAL, {
            "id": upload_id, "content_type": ctype, "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),  # ING-10: originals are hashed and never modified
            "object_key": object_key, "doc_kind": doc_kind,
            "filename_sealed": it.keyring.encrypt(hid, filename.encode(), f"filename:{upload_id}").hex(),
            "uploaded_at": _now(), "uploaded_by": session.member_id,
        })
        return upload_id

    def scrub_and_queue(session: Session, upload_id: str, ctype: str, data: bytes, forced_type: str | None) -> None:
        """Read the text here, swap identifiers for vault tokens, and hand only that to the worker (PRV-01)."""
        hid = session.household_id
        text, pages, how = read_text(ctype, data)
        store = HouseholdStore(it.db, hid)
        names = [n for m in store.all("member") for n in [m["name"], *m.get("aliases", [])]]
        scrubbed = Scrubber(lambda kind, value: it.vault.tokenize(hid, kind, value), names).scrub(text)
        it.queue.enqueue(hid, "extract", {"upload_id": upload_id, "text": scrubbed.text, "pages": pages,
                                          "how_read": how, "forced_type": forced_type})

    # --- upload ---

    @app.get("/uploads", response_class=HTMLResponse)
    def uploads(request: Request, uploaded: str | None = None):
        return uploads_page(request, it.member(request), uploaded=uploaded)

    @app.post("/uploads")
    async def upload(request: Request):
        session = it.member(request)
        form = await request.form()
        it.check_csrf(session, form.get("csrf_token"))
        file = form.get("file")
        kind = form.get("kind") or "auto"
        try:
            if file is None or not getattr(file, "filename", ""):
                raise UploadRefused("Choose a file to upload.")
            if kind not in UPLOAD_KINDS:
                raise UploadRefused("Choose what kind of document this is.")
            data = await file.read(MAX_UPLOAD + 1)
            filename = Path(file.filename).name[:200]
            if len(data) > MAX_UPLOAD:
                raise UploadRefused(f"{filename} is larger than {MAX_UPLOAD // (1024 * 1024)} MB.", 413)
            if not data:
                raise UploadRefused(f"{filename} is empty.")
            ctype = content_type(filename, file.content_type or "")
            digest = hashlib.sha256(data).hexdigest()
            for rec in HouseholdStore(it.db, session.household_id).all(ORIGINAL):
                if rec["sha256"] == digest:  # TC-ING-07-1
                    raise UploadRefused(f"{filename} was already uploaded on {rec['uploaded_at'][:10]} as "
                                        f"{original_name(session.household_id, rec)}; it wasn't added again.", 409)
            if ctype in EXPORT_TYPES or kind in ("hsa_export", "claims_export"):
                return export_upload(request, session, filename, ctype, data, kind)
            if ctype != PDF and ctype not in IMAGES:
                raise UploadRefused(f"{filename}: only PDFs, photos (JPG, PNG, HEIC) and CSV, XLS or XLSX exports "
                                    "can be uploaded.", 415)
            if ctype == PDF:
                read_text(PDF, data)  # refuse damaged and password-protected PDFs before storing anything
        except UploadRefused as e:
            return uploads_page(request, session, e.status, error=e.message)
        except Unreadable as e:
            return uploads_page(request, session, 400, error=f"{filename}: {e}")
        upload_id = store_original(session, filename, ctype, data, kind)
        scrub_and_queue(session, upload_id, ctype, data, kind if kind in TYPES else None)
        return RedirectResponse(f"/uploads?uploaded={upload_id}", status_code=303)

    def export_upload(request: Request, session: Session, filename: str, ctype: str, data: bytes, kind: str):
        store = HouseholdStore(it.db, session.household_id)
        if kind == "claims_export" or (kind == "auto" and claims.is_claims_export(filename, data)):
            records = {k: store.all(k) for k in ("provider", "member", "plan", "visit")}
            ingest, errors, notes = claims.to_ingest(filename, data, records)
            doc_kind = "claims_export"
        else:
            export = hsa.parse_export(filename, data)
            errors, ingest, notes = export.errors, None, list(export.warnings)
            if not errors:
                ingest, more = hsa.to_ingest(export, store.all("provider"), store.all("account"))
                notes += more
            doc_kind = "hsa_export"
        if errors:
            raise UploadRefused(f"{filename}: " + " ".join(errors))
        store_original(session, filename, ctype, data, doc_kind)
        return it.preview_import(request, store, ingest, filename, None, notes)

    @app.get("/uploads/{upload_id}")
    def download(request: Request, upload_id: str):
        session = it.member(request)
        rec = get_original(session, upload_id)
        data = original_bytes(session.household_id, rec)
        name = re.sub(r"[^A-Za-z0-9._ -]", "_", original_name(session.household_id, rec))
        return Response(data, media_type=rec["content_type"],
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/api/uploads")
    def api_uploads(request: Request):
        return uploads_list(it.member(request))

    @app.get("/api/uploads/{upload_id}")
    def api_upload(request: Request, upload_id: str):
        session = it.member(request)
        rec = get_original(session, upload_id)
        return view(session.household_id, rec, HouseholdStore(it.db, session.household_id).get(EXTRACTION, upload_id))

    # --- review and confirm ---

    def reidentify(hid: str, value):
        if isinstance(value, str) and value.startswith("tok_"):
            found = it.vault.detokenize(hid, value)
            return found[1] if found else ""
        return value

    def review_context(session: Session, rec: dict, ext: dict) -> dict:
        hid = session.household_id
        store = HouseholdStore(it.db, hid)
        fields = {}
        extracted = ext.get("fields", {})
        order = [n for n in FIELD_ORDER if n in extracted] + [n for n in extracted if n not in FIELD_ORDER]
        patient = reidentify(hid, (extracted.get("patient") or {}).get("value")) or ""
        for name in order:  # JSONB doesn't keep key order, so the form sets its own
            if name == "patient":
                continue  # shown read-only beside the member choice; identifiers aren't edited here
            f = extracted[name]
            value = reidentify(hid, f.get("value"))
            if name in EOB_MONEY + STATEMENT_MONEY and isinstance(value, int):
                value = f"{value / 100:.2f}"
            fields[name] = {"label": LABELS.get(name, name), "value": "" if value is None else value,
                            "confidence": f.get("confidence", 0), "note": f.get("note", ""),
                            "low": f.get("confidence", 0) < REVIEW_THRESHOLD}
        providers, members = store.all("provider"), store.all("member")
        provider_id = Providers(providers).find(str(fields.get("provider", {}).get("value", "")))
        member_id = Members(members).find(str(patient))
        when = fields.get("service_start", {}).get("value") or (ext.get("lines") or [{}])[0].get("service_date") or ""
        visits = [v for v in store.all("visit") if not provider_id or v["provider_id"] == provider_id]
        lines = [{**l, **{k: f"{l[k] / 100:.2f}" for k in l if isinstance(l.get(k), int)}} for l in ext.get("lines", [])]
        return {
            "rec": view(hid, rec, ext), "ext": ext, "fields": fields, "patient": str(patient).title(), "lines": lines, "types": TYPES,
            "extracted": ext.get("doc_type") in EXTRACTED, "threshold": REVIEW_THRESHOLD,
            "providers": sorted(providers, key=lambda p: p["name"].lower()), "provider_id": provider_id or "",
            "members": members, "member_id": member_id or "", "plans": store.all("plan"),
            "plan_id": plan_for(store.all("plan"), int(when[:4])) if re.match(r"\d{4}", when) else "",
            "visits": sorted(visits, key=lambda v: v["date"], reverse=True),
            "visit_id": next((v["id"] for v in visits if v["date"] == when and provider_id), ""),
        }

    @app.get("/uploads/{upload_id}/review", response_class=HTMLResponse)
    def review(request: Request, upload_id: str):
        session = it.member(request)
        rec = get_original(session, upload_id)
        ext = HouseholdStore(it.db, session.household_id).get(EXTRACTION, upload_id)
        if ext is None:
            return RedirectResponse(f"/uploads?reading={upload_id}", status_code=303)
        return page(request, "review.html", **review_context(session, rec, ext))

    @app.post("/uploads/{upload_id}/reclassify")
    async def reclassify(request: Request, upload_id: str):
        """ING-02 TC-4: the member's type persists and extraction runs again with it."""
        session = it.member(request)
        form = await request.form()
        it.check_csrf(session, form.get("csrf_token"))
        rec = get_original(session, upload_id)
        doc_type = form.get("doc_type")
        if doc_type not in TYPES:
            raise HTTPException(400, "Choose a document type")
        store = HouseholdStore(it.db, session.household_id)
        if ext := store.get(EXTRACTION, upload_id):
            if ext.get("status") == "confirmed":
                raise HTTPException(400, "This document is already confirmed")
            store.delete(EXTRACTION, upload_id)
        scrub_and_queue(session, upload_id, rec["content_type"], original_bytes(session.household_id, rec), doc_type)
        return RedirectResponse(f"/uploads?reading={upload_id}", status_code=303)

    @app.post("/uploads/{upload_id}/confirm")
    async def confirm(request: Request, upload_id: str):
        session = it.member(request)
        form = await request.form()
        it.check_csrf(session, form.get("csrf_token"))
        hid = session.household_id
        rec = get_original(session, upload_id)
        store = HouseholdStore(it.db, hid)
        ext = store.get(EXTRACTION, upload_id)
        if ext is None:
            raise HTTPException(404)
        if ext["doc_type"] not in EXTRACTED:
            ext.update(status="filed", confirmed_at=_now(), confirmed_by=session.member_id)
            store.put(EXTRACTION, ext)
            return RedirectResponse("/uploads", status_code=303)
        try:
            data, created, document_id, visit_ids = build_records(store, form, ext, rec, upload_id,
                                                                  original_name(hid, rec))
        except ValueError as e:
            ctx = review_context(session, rec, ext)
            return page(request, "review.html", 400, error=str(e), **ctx)
        files = UploadedSource({original_name(hid, rec): original_bytes(hid, rec)})
        plan = importer.prepare(data, store, f"upload {upload_id}", files)
        if not plan.ok:
            return page(request, "review.html", 400, error="; ".join(plan.errors), **review_context(session, rec, ext))
        importer.commit(plan, store, EncryptedFiles(it.objects, it.keyring, hid), replace_edits=True)
        for kind, record_id in created:  # the member's confirmed values win over later imports (ADR-011)
            store._mark_edited(kind, record_id)
        ext.setdefault("corrections", []).extend(corrections(ext, form, session))
        ext.update(status="confirmed", confirmed_at=_now(), confirmed_by=session.member_id,
                   document_id=document_id, visit_ids=visit_ids)
        store.put(EXTRACTION, ext)
        return RedirectResponse(f"/visits/{visit_ids[0]}" if visit_ids else "/visits", status_code=303)


def _money(form, name: str, required: bool = False) -> float | None:
    raw = (form.get(name) or "").strip()
    if not raw:
        if required:
            raise ValueError(f"{LABELS.get(name, name)} is needed.")
        return None
    cents = parse_amount(raw)
    if cents is None:
        raise ValueError(f"{LABELS.get(name, name)}: {raw!r} isn't an amount.")
    return dollars(cents)


def _date(form, name: str, required: bool = False) -> str | None:
    raw = (form.get(name) or "").strip()
    value = parse_date(raw) if raw else None
    if raw and not value:
        raise ValueError(f"{LABELS.get(name, name)}: {raw!r} isn't a date.")
    if required and not value:
        raise ValueError(f"{LABELS.get(name, name)} is needed.")
    return value


def corrections(ext: dict, form, session: Session) -> list[dict]:
    """Each change the member makes, against the value they last confirmed or else what was extracted
    (TC-ING-05-3, PLT-04). The extracted value is kept with every entry. Identifiers aren't recorded."""
    out = []
    latest = {c["field"]: c["confirmed"] for c in ext.get("corrections", [])}
    for name, f in ext.get("fields", {}).items():
        if name in ("patient", "account_number") or name not in form:
            continue
        extracted, given = f.get("value"), (form.get(name) or "").strip()
        previous = latest.get(name, extracted)
        if name in EOB_MONEY + STATEMENT_MONEY:
            given_value = parse_amount(given) if given else None
        elif name.endswith("date") or name.startswith("service_"):
            given_value = parse_date(given) if given else None
        else:
            given_value = given or None
        if given_value != previous:
            out.append({"field": name, "extracted": extracted, "previous": previous, "confirmed": given_value,
                        "at": _now(), "by": session.member_id})
    return out


def build_records(store: HouseholdStore, form, ext: dict, rec: dict, upload_id: str,
                  filename: str) -> tuple[dict, list[tuple[str, str]], str, list[str]]:
    """Ingest records (dollars) for a confirmed document: the document, its provider and visits if new."""
    doc_type = ext["doc_type"]
    providers = Providers(store.all("provider"))
    provider_choice = form.get("provider_id") or ""
    if provider_choice and provider_choice != "new":
        if provider_choice not in providers.records:
            raise ValueError("Choose a provider.")
        provider_id = provider_choice
    else:
        name = (form.get("provider") or "").strip()
        if not name:
            raise ValueError("Name the provider, or choose one you already have.")
        provider_id = providers.resolve(name)
    member_id = form.get("member_id") or None
    if member_id and not store.get("member", member_id):
        raise ValueError("Choose a household member.")
    data: dict = {"schema_version": "0.1", "visits": [], "documents": []}
    created: list[tuple[str, str]] = []
    if providers.new:
        data["providers"] = list(providers.new.values())
        created += [("provider", p) for p in providers.new]
    existing_visits = {v["id"]: v for v in store.all("visit")}

    def visit_for(when: str, choice: str = "", plan_id: str | None = None) -> str:
        if choice and choice != "new":
            if choice not in existing_visits:
                raise ValueError("Choose a visit.")
            return choice
        for v in existing_visits.values():
            if v["provider_id"] == provider_id and v["date"] == when and not choice:
                return v["id"]
        vid = base = f"v-{when}-{provider_id.removeprefix('prov-')}"
        n = 2
        while vid in existing_visits or any(v["id"] == vid for v in data["visits"]):
            vid, n = f"{base}-{n}", n + 1
        visit = {"id": vid, "date": when, "provider_id": provider_id, "category": "provider_visit",
                 "description": f"From an uploaded {TYPES[doc_type].lower()}", "extensions": {"upload_id": upload_id}}
        if member_id:
            visit["member_id"] = member_id
        if plan_id:
            visit["plan_id"] = plan_id
        data["visits"].append(visit)
        created.append(("visit", vid))
        return vid

    if doc_type == "eob":
        start = _date(form, "service_start", required=True)
        plan_id = form.get("plan_id") or ""
        if not store.get("plan", plan_id):
            raise ValueError(f"Choose the plan that processed this claim (add the {start[:4]} plan in Settings first "
                             "if it isn't listed).")
        visit_id = visit_for(start, form.get("visit_id") or "", plan_id)
        claim = (form.get("claim_number") or "").strip()
        doc_id = f"eob-{slug(claim)}" if claim else f"eob-{upload_id}"
        doc = {"id": doc_id, "type": "eob", "date": _date(form, "processed_date") or start, "file": filename,
               "plan_id": plan_id, "provider_id": provider_id, "visit_id": visit_id,
               "claim_status": form.get("claim_status") or "processed",
               "network_status": form.get("network_status") or "unknown",
               "extensions": {"upload_id": upload_id}}
        if claim:
            doc["claim_number"] = claim
        for name in EOB_MONEY:
            value = _money(form, name, required=name in ("billed", "allowed", "insurer_paid", "patient_responsibility"))
            if value is not None:
                doc[name] = value
        lines = []
        for l in ext.get("lines", []):
            line = {k: l[k] for k in ("service_date", "description", "code") if l.get(k)}
            line.update({k: dollars(l[k]) for k in ("billed", "allowed", "insurer_paid", "patient_responsibility")
                         if isinstance(l.get(k), int)})
            lines.append(line)
        if lines:
            doc["lines"] = lines
        visit_ids = [visit_id]
    else:
        statement_date = _date(form, "statement_date", required=True)
        balance_due = _money(form, "balance_due", required=True)
        groups: dict[str, list[dict]] = {}
        for l in ext.get("lines", []):
            if l.get("service_date"):
                groups.setdefault(l["service_date"], []).append(l)
        bill_lines = []
        if groups:
            for when, items in groups.items():
                vid = visit_for(when)
                cents = lambda k: sum(i.get(k) or 0 for i in items)  # noqa: E731
                balance = cents("balance") if any("balance" in i for i in items) else cents("charge")
                patient_amount = cents("patient_amount") or balance + cents("patient_paid")
                line = {"visit_id": vid, "description": "; ".join(i.get("description", "") for i in items),
                        "billed_charge": dollars(cents("charge")), "patient_amount": dollars(patient_amount),
                        "balance": dollars(balance)}
                for k in ("insurance_paid", "adjustment", "patient_paid"):
                    if any(i.get(k) for i in items):
                        line[k] = dollars(cents(k))
                bill_lines.append(line)
        else:  # TC-ING-04-2: no line detail on the statement; one line for the visit it's for, no invented items
            when = _date(form, "service_start", required=not form.get("visit_id") or form.get("visit_id") == "new")
            vid = visit_for(when or statement_date, form.get("visit_id") or "")
            bill_lines.append({"visit_id": vid, "description": "Statement total (no line detail)",
                               "patient_amount": balance_due, "balance": balance_due})
        doc_id = f"bill-{provider_id.removeprefix('prov-')}-{statement_date}"
        doc = {"id": doc_id, "type": "provider_bill", "date": statement_date, "file": filename,
               "provider_id": provider_id, "balance_due": balance_due, "lines": bill_lines,
               "extensions": {"upload_id": upload_id}}
        if due := _date(form, "due_date"):
            doc["due_date"] = due
        if notice := (form.get("notice") or "").strip():
            doc["notice"] = notice
        if form.get("network_status") in ("in_network", "out_of_network"):
            doc["network_status_shown"] = form.get("network_status")
        visit_ids = list(dict.fromkeys(l["visit_id"] for l in bill_lines))
    data["documents"].append(doc)
    created.append(("document", doc["id"]))
    if not data["visits"]:
        del data["visits"]
    return data, created, doc["id"], visit_ids
