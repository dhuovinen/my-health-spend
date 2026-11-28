"""Scan an insurance card, front and back, to fill in a plan (ING-11, ADR-062).

OCR and the layout rules (`ingest/card.py`) run here, in the application tier: the worker never sees a card. Member
IDs, the group number and names are kept as vault tokens. The images are sealed with the household's key and held
only while the member reviews the scan; they are deleted when it is confirmed or cancelled, or after 24 hours,
unless the owner's `keep_card_images` setting is on at confirmation (then they are kept like originals, linked to
the plan). Nothing is saved to a plan before the member confirms, and a scan never sets `terms_confirmed`.
"""

import hashlib
import io
import logging
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from mhs.core import costshare
from mhs.data import importer
from mhs.data.db import Database
from mhs.data.household_store import HouseholdStore
from mhs.data.keys import Keyring
from mhs.data.money import to_dollars
from mhs.data.objects import ObjectStore
from mhs.ingest import card, card_plan
from mhs.ingest.ocr import OcrEngine, page_images
from mhs.ingest.resolve import Members, slug
from mhs.ingest.scrub import normalize
from mhs.ingest.text import IMAGES, PDF, Unreadable, check_image, content_type, read_pdf, read_text
from mhs.ingest.values import parse_amount
from mhs.vault.client import VaultClient, VaultError
from mhs.web.household.auth import Session
from mhs.web.household.features import Features

log = logging.getLogger("mhs.card_scan")
MAX_CARD = 12 * 1024 * 1024
EXPIRE_HOURS = 24
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
TOKEN = re.compile(r"tok_[a-z2-7]{26}")
SIDES = ("front", "back")


class ScanRefused(Exception):
    def __init__(self, message: str, status: int = 400):
        self.message, self.status = message, status


@dataclass
class CardStore:
    """The scan records and sealed images, in the application tier only."""

    db: Database
    keyring: Keyring
    objects: ObjectStore

    def create(self, hid: str, member_id: str, reading: dict, images: dict[str, tuple[str, bytes]],
               target_plan: str | None = None) -> str:
        scan_id = "scn_" + secrets.token_hex(12)
        rows = []
        for side, (ctype, data) in images.items():
            image_id = f"crd_{secrets.token_hex(10)}"
            key = f"households/{hid}/cards/{image_id}"
            self.objects.put(key, self.keyring.encrypt(hid, data, f"card:{image_id}"))
            rows.append((image_id, hid, scan_id, side, ctype, key, hashlib.sha256(data).hexdigest()))
        from psycopg.types.json import Jsonb

        with self.db.tx(hid) as c:
            c.execute("INSERT INTO app.card_scans (id, household_id, created_by, reading) VALUES (%s, %s, %s, %s)",
                      (scan_id, hid, member_id, Jsonb({**reading, "target_plan": target_plan})))
            for row in rows:
                c.execute("INSERT INTO app.card_images (id, household_id, scan_id, side, content_type, object_key, "
                          "sha256) VALUES (%s, %s, %s, %s, %s, %s, %s)", row)
        return scan_id

    def scan(self, hid: str, scan_id: str) -> dict | None:
        if not ID_PATTERN.match(scan_id):
            return None
        with self.db.tx(hid) as c:
            row = c.execute("SELECT id, created_by, created_at, reading FROM app.card_scans WHERE household_id = %s "
                            "AND id = %s", (hid, scan_id)).fetchone()
        return None if row is None else {**row["reading"], "id": row["id"], "created_by": str(row["created_by"]),
                                         "created_at": row["created_at"]}

    def images(self, hid: str, scan_id: str) -> list[dict]:
        with self.db.tx(hid) as c:
            return c.execute("SELECT id, side, content_type, object_key, sha256, state FROM app.card_images "
                             "WHERE household_id = %s AND scan_id = %s ORDER BY side", (hid, scan_id)).fetchall()

    def image_bytes(self, hid: str, row: dict) -> bytes:
        data = self.keyring.decrypt(hid, self.objects.get(row["object_key"]), f"card:{row['id']}")
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise HTTPException(500)
        return data

    def kept(self, hid: str, plan_ids: list[str]) -> dict[str, list[dict]]:
        if not plan_ids:
            return {}
        with self.db.tx(hid) as c:
            rows = c.execute("SELECT id, side, plan_id FROM app.card_images WHERE household_id = %s AND state = 'kept' "
                             "AND plan_id = ANY(%s) ORDER BY created_at, side", (hid, plan_ids)).fetchall()
        out: dict[str, list[dict]] = {}
        for r in rows:
            out.setdefault(r["plan_id"], []).append({"id": r["id"], "side": r["side"]})
        return out

    def kept_image(self, hid: str, image_id: str) -> dict | None:
        if not ID_PATTERN.match(image_id):
            return None
        with self.db.tx(hid) as c:
            return c.execute("SELECT id, side, content_type, object_key, sha256, state FROM app.card_images "
                             "WHERE household_id = %s AND id = %s AND state = 'kept'", (hid, image_id)).fetchone()

    def finish(self, hid: str, scan_id: str, keep: bool, plan_id: str | None = None) -> int:
        """The scan is over (confirmed or cancelled): its record goes, and its images are deleted or, when the
        owner keeps them, linked to the plan. Returns how many images were kept."""
        images = self.images(hid, scan_id)
        with self.db.tx(hid) as c:
            c.execute("DELETE FROM app.card_scans WHERE household_id = %s AND id = %s", (hid, scan_id))
            if keep and plan_id:
                c.execute("UPDATE app.card_images SET state = 'kept', plan_id = %s WHERE household_id = %s AND "
                          "scan_id = %s", (plan_id, hid, scan_id))
            else:
                c.execute("DELETE FROM app.card_images WHERE household_id = %s AND scan_id = %s", (hid, scan_id))
        if not (keep and plan_id):
            for row in images:
                self.objects.delete(row["object_key"])
            return 0
        return len(images)

    def expire(self, hours: int = EXPIRE_HOURS) -> int:
        """Scans left open for longer than `hours`, in every household: removed with their images."""
        with self.db.tx() as c:
            keys = [r["object_key"] for r in c.execute("SELECT object_key FROM app.expire_card_scans(%s)", (hours,))]
        for key in keys:
            self.objects.delete(key)
        return len(keys)


def _tel(phone: str) -> str:
    return "+1" + re.sub(r"\D", "", phone)[-10:]


def add_card_scan(app: FastAPI, templates: Jinja2Templates, *, db: Database, keyring: Keyring, objects: ObjectStore,
                  vault: VaultClient, ocr: Callable[[], OcrEngine], features: Features, member: Callable[[Request], Session],
                  check_csrf: Callable, collect_for: Callable[[str, str], bool],
                  ai_extraction: Callable[[str], bool] = lambda household_id: False) -> CardStore:
    cards = CardStore(db, keyring, objects)

    def page(request: Request, name: str, status: int = 200, **ctx) -> HTMLResponse:
        return templates.TemplateResponse(request, name, ctx, status_code=status)

    def token(hid: str, kind: str, value: str) -> str:
        # one spelling per identifier (PRV-03), the same normalization uploads use
        return vault.tokenize(hid, kind, normalize("name" if kind == "name" else "member_id", value))

    def real(hid: str, value):
        """Tokens back to what the card said, only for the signed-in member's own page."""
        if isinstance(value, str) and "tok_" in value:
            def one(m: re.Match) -> str:
                try:
                    found = vault.detokenize(hid, m.group(0))
                except VaultError:
                    return ""
                return found[1] if found else ""

            return TOKEN.sub(one, value).strip()
        return value

    def pretty(kind: str, value: str) -> str:
        return " ".join(w.capitalize() for w in value.split()) if kind == "name" else value

    def scan_or_404(session: Session, scan_id: str) -> dict:
        scan = cards.scan(session.household_id, scan_id)
        if scan is None or scan["created_by"] != session.member_id:  # a scan is the scanning member's own
            raise HTTPException(404)
        return scan

    async def read_upload(file) -> tuple[str, bytes] | None:
        if file is None or not getattr(file, "filename", ""):
            return None
        data = await file.read(MAX_CARD + 1)
        if not data:
            return None
        name = file.filename.rsplit("/", 1)[-1]
        if len(data) > MAX_CARD:
            raise ScanRefused(f"{name} is larger than {MAX_CARD // (1024 * 1024)} MB.", 413)
        ctype = content_type(name, file.content_type or "")
        if ctype != PDF and ctype not in IMAGES:
            raise ScanRefused(f"{name}: a card can be a photo (JPG, PNG, HEIC) or a PDF scan.", 415)
        try:
            if ctype == PDF:
                read_pdf(data)
            else:
                check_image(data, ctype)
        except Unreadable as e:
            raise ScanRefused(f"{name}: {e}") from e
        return ctype, data

    def read_side(ctype: str, data: bytes):
        try:
            return read_text(ctype, data, ocr())
        except Unreadable as e:
            raise ScanRefused(str(e)) from e

    def scan_page(request: Request, session: Session, status: int = 200, **ctx) -> HTMLResponse:
        store = HouseholdStore(db, session.household_id)
        plan = store.get("plan", ctx.get("plan_id") or "") if ctx.get("plan_id") else None
        return page(request, "card_scan.html", status, plan=plan, **ctx)

    @app.get("/coverage/card", response_class=HTMLResponse)
    def scan_form(request: Request, plan: str = ""):
        session = member(request)
        cards.expire()
        return scan_page(request, session, plan_id=plan if ID_PATTERN.match(plan) else "")

    @app.post("/coverage/card")
    async def scan_card(request: Request):
        session = member(request)
        form = await request.form()
        check_csrf(session, form.get("csrf_token"))
        hid = session.household_id
        plan_id = form.get("plan") or ""
        plan_id = plan_id if ID_PATTERN.match(plan_id) else ""
        try:
            if not collect_for(hid, session.member_id):
                raise ScanRefused("CareBack can't take documents from you without your consent. Give it on the Consent "
                                  "page (from your Account page), or ask why it's needed.")
            front = await read_upload(form.get("front"))
            back = await read_upload(form.get("back"))
            if plan_id:  # adding the back to a plan made from the front
                store = HouseholdStore(db, hid)
                if store.get("plan", plan_id) is None:
                    raise HTTPException(404)
                if back is None and front is not None:
                    front, back = None, front
                if back is None:
                    raise ScanRefused("Choose a photo of the back of the card.")
            elif front is None:
                raise ScanRefused("Choose a photo of the front of the card. The back can wait.")
            texts, confidences = {}, []
            for side, got in (("front", front), ("back", back)):
                if got is None:
                    texts[side] = ""
                    continue
                doc = read_side(*got)
                texts[side] = doc.text
                if doc.words:
                    confidences.append(doc.confidence)
            if not any(t.strip() for t in texts.values()):
                raise ScanRefused("CareBack couldn't read any text on this card. Try a clearer, well-lit photo with the "
                                  "whole card in view, or type the plan in on Coverage.")
            reading = card.read_card(texts["front"], texts["back"], min(confidences) if confidences else 1.0)
            if reading.kind == "vision":
                raise ScanRefused(reading.refusal)
            if plan_id:
                if not (reading.contacts or "payer_id" in reading.fields):
                    raise ScanRefused("This doesn't look like the back of an insurance card (no phone numbers or "
                                      "claims address found). Try a clearer photo.")
            elif not reading.looks_like_card:
                raise ScanRefused(reading.refusal)
            record = card.reading_dict(reading, lambda kind, value: token(hid, kind, value))
        except ScanRefused as e:
            return scan_page(request, session, e.status, error=e.message, plan_id=plan_id)
        except VaultError:
            return scan_page(request, session, 503, error="The identity vault isn't reachable, so the card wasn't "
                                                          "read. Try again in a moment.", plan_id=plan_id)
        images = {side: got for side, got in (("front", front), ("back", back)) if got is not None}
        cards.expire()
        scan_id = cards.create(hid, session.member_id, record, images, plan_id or None)
        HouseholdStore(db, hid, actor=session.member_id).log("create", "card_scan", scan_id)
        return RedirectResponse(f"/coverage/card/{scan_id}", status_code=303)

    # --- review ---

    def review_context(session: Session, scan: dict, form=None) -> dict:
        hid = session.household_id
        store = HouseholdStore(db, hid)
        members = store.all("member")
        by_name = Members(members)
        fields = scan["fields"]

        def value(key: str) -> str:
            f = fields.get(key)
            return "" if not f else str(real(hid, f["value"]))

        def mark(key: str) -> bool:
            f = fields.get(key)
            return bool(f) and f["confidence"] < card.CHECK_BELOW

        start = fields.get("effective_date", {}).get("value") or ""
        year = int(start[:4]) if start[:4].isdigit() else None
        from datetime import date

        year = year or date.today().year
        kind = "dental" if scan["kind"] == "dental" else "medical"
        target = store.get("plan", scan["target_plan"]) if scan.get("target_plan") else None
        if target:  # the back of a card for a plan we already have: the plan decides these
            kind, year = card_plan.kind_of(target), target["plan_year"]
        group_token = fields.get("group_number", {}).get("value")
        plans = store.all("plan")
        this_year, other = (target, None) if target else card_plan.find_plan(
            plans, value("insurer"), group_token, kind, year)
        people = []
        for i, p in enumerate(scan["people"]):
            name = real(hid, p["name"])
            number = real(hid, (p.get("member_number") or {}).get("value") or "")
            people.append({"i": i, "name": pretty("name", name), "role": p["role"], "subscriber": p["subscriber"],
                           "number": number, "match": by_name.find(name) or "",
                           "low": p["confidence"] < card.CHECK_BELOW})
        preview = {"copays": {k: f["value"] for k, f in scan["copays"].items()}, "limits": scan["limits"],
                   "plan_type": value("plan_type") or None, "coverage_start": start or None,
                   "plan_name": value("plan_name") or None}
        names = {m["id"]: m["name"] for m in members}
        base = this_year or other
        what = card_plan.changes(base, preview, names, costshare.SERVICE_TYPES)
        copay_lines = "\n".join(f"{k}: {f['value'] / 100:.2f}" for k, f in scan["copays"].items())
        coins = fields.get("coinsurance_pct", {}).get("value")
        return {
            "scan": scan, "fields": fields, "value": value, "mark": mark, "year": year, "kind": kind,
            "insurer": target["insurer"] if target else value("insurer"), "plan_name": value("plan_name"), "plan_type": value("plan_type"),
            "group": value("group_number"), "payer_id": value("payer_id"), "start": start, "people": people,
            "rx": {"bin": value("rx_bin"), "pcn": value("rx_pcn"), "group": value("rx_group")},
            "copay_lines": copay_lines, "coinsurance": coins if coins is not None else "",
            "limits": scan["limits"], "contacts": scan["contacts"], "members": members,
            "hsa": bool(fields.get("hsa_eligible_plan")) or value("plan_type") == "HDHP",
            "order": value("coverage_order"), "this_year": this_year, "other_year": other, "target": target,
            "images": cards.images(hid, scan["id"]), "keep": features.keep_card_images(),
            "check_below": card.CHECK_BELOW, "service_types": costshare.SERVICE_TYPES, "form": form or {},
            "back_only": bool(target), "tel": _tel, "what": what,
        }

    @app.get("/coverage/card/{scan_id}", response_class=HTMLResponse)
    def review(request: Request, scan_id: str):
        session = member(request)
        scan = scan_or_404(session, scan_id)
        HouseholdStore(db, session.household_id, actor=session.member_id).log("view", "card_scan", scan_id)
        return page(request, "card_review.html", **review_context(session, scan))

    @app.get("/coverage/card/{scan_id}/{side}")
    def scan_image(request: Request, scan_id: str, side: str):
        """The scan's own picture, for the review only: upright, as JPEG, made on the fly."""
        session = member(request)
        scan_or_404(session, scan_id)
        row = next((r for r in cards.images(session.household_id, scan_id) if r["side"] == side), None)
        if row is None:
            raise HTTPException(404)
        return picture(cards.image_bytes(session.household_id, row), row["content_type"])

    def picture(data: bytes, ctype: str) -> Response:
        try:
            image = page_images(data, ctype)[0]
        except Exception:  # noqa: BLE001 - a card that can't be pictured just has no picture
            raise HTTPException(404) from None
        image.thumbnail((1400, 1400))
        buf = io.BytesIO()
        image.convert("RGB").save(buf, "JPEG", quality=85)
        return Response(buf.getvalue(), media_type="image/jpeg",
                        headers={"Content-Disposition": "inline", "Cache-Control": "private, no-store"})

    @app.get("/coverage/card-image/{image_id}")
    def kept_image(request: Request, image_id: str):
        """A card image the owner's setting kept, for the signed-in member's own household (logged as a download)."""
        session = member(request)
        row = cards.kept_image(session.household_id, image_id)
        if row is None:
            raise HTTPException(404)
        HouseholdStore(db, session.household_id, actor=session.member_id).log("download", "card_image", image_id)
        return picture(cards.image_bytes(session.household_id, row), row["content_type"])

    @app.post("/coverage/card/{scan_id}/cancel")
    async def cancel(request: Request, scan_id: str):
        session = member(request)
        form = await request.form()
        check_csrf(session, form.get("csrf_token"))
        scan_or_404(session, scan_id)
        cards.finish(session.household_id, scan_id, keep=False)
        HouseholdStore(db, session.household_id, actor=session.member_id).log("delete", "card_scan", scan_id)
        return RedirectResponse("/coverage", status_code=303)

    # --- confirm ---

    def money(text: str, label: str) -> int:
        try:
            cents = parse_amount(text.strip())
        except (InvalidOperation, ValueError):
            cents = None
        if cents is None or cents < 0:
            raise ScanRefused(f"{label}: {text!r} isn't an amount")
        return cents

    def plan_from_form(hid: str, form, scan: dict, store: HouseholdStore) -> tuple[dict, list[dict], dict[str, str]]:
        """The card's values as the member left them on the form: (plan fields, new household members, names)."""
        insurer = (form.get("insurer") or "").strip()
        if not insurer:
            raise ScanRefused("Enter the insurer.")
        target = store.get("plan", scan["target_plan"]) if scan.get("target_plan") else None
        incoming: dict = {"insurer": insurer, "coverage_kind": card_plan.kind_of(target) if target
                          else ("dental" if scan["kind"] == "dental" else "medical")}
        for key in ("plan_name", "plan_type", "coverage_order", "coverage_start", "payer_id"):
            if value := (form.get(key) or "").strip():
                incoming[key] = value
        if incoming.get("plan_type") not in (None, "PPO", "HMO", "EPO", "POS", "HDHP"):
            raise ScanRefused("Choose a plan type from the list.")
        if incoming.get("coverage_order") not in (None, "primary", "secondary", "tertiary"):
            raise ScanRefused("Choose primary, secondary or tertiary.")
        year = (form.get("plan_year") or "").strip()
        if not year.isdigit():
            raise ScanRefused("Enter the plan year.")
        incoming["plan_year"] = int(year)
        if form.get("hsa_eligible_plan") == "on":
            incoming["hsa_eligible_plan"] = True
        if group := (form.get("group_number") or "").strip():
            incoming["group_number"] = token(hid, "group_number", group)
        rx = {k: (form.get(f"rx_{k}") or "").strip() for k in ("bin", "pcn", "group")}
        if rx["group"]:
            rx["group"] = token(hid, "group_number", rx["group"])
        if any(rx.values()):
            incoming["rx"] = {k: v for k, v in rx.items() if v}
        if rate := (form.get("coinsurance_pct") or "").strip():
            try:
                incoming["coinsurance_rate"] = float(Decimal(rate) / 100)
            except InvalidOperation:
                raise ScanRefused(f"Coinsurance: {rate!r} isn't a percentage") from None
        copays = {}
        for line in (form.get("copays") or "").splitlines():
            if line.strip():
                if ":" not in line:
                    raise ScanRefused(f"Copay line {line.strip()!r} should look like 'specialist: 60'")
                k, v = line.split(":", 1)
                copays[slug(k).replace("-", "_")] = money(v, f"Copay {k.strip()}")
        if copays:
            incoming["copays"] = copays
        limits = []
        for i, l in enumerate(scan["limits"]):
            if form.get(f"limit_{i}") == "on":
                limits.append({"type": l["type"], "network": l["network"], "level": l["level"],
                               "amount": money(form.get(f"limit_{i}_amount") or "", f"{l['type']} amount")})
        if limits:
            incoming["limits"] = limits
        contacts = []
        for i in range(len(scan["contacts"])):
            if form.get(f"contact_{i}") == "on":
                c = {"label": (form.get(f"contact_{i}_label") or "").strip() or "Contact"}
                for k in ("phone", "address", "url"):
                    if v := (form.get(f"contact_{i}_{k}") or "").strip():
                        c[k] = v
                contacts.append(c)
        if contacts:
            incoming["contacts"] = contacts
        members, member_ids, numbers, names, new_members = store.all("member"), [], {}, {}, []
        for i, p in enumerate(scan["people"]):
            name = (form.get(f"person_{i}_name") or "").strip()
            choice = form.get(f"person_{i}") or ""
            if choice in ("none",):
                continue
            if choice == "add":
                mid = f"mbr-{slug(name)}"
                if any(m["id"] == mid for m in members):
                    mid += "-card"
                new_members.append({"id": mid, "name": name})
                members = members + [{"id": mid, "name": name}]
            elif any(m["id"] == choice for m in members):
                mid = choice
            else:
                raise ScanRefused(f"Choose what to do with {name or 'a name on the card'}: match them to a household "
                                  "member, add them, or say they aren't in this household.")
            member_ids.append(mid)
            entry: dict = {}
            if number := (form.get(f"person_{i}_number") or "").strip():
                entry["member_number"] = token(hid, "member_id", number)
            if form.get(f"person_{i}_subscriber") == "on":
                entry["subscriber"] = True
            if entry:
                numbers[mid] = entry
            names[mid] = name
        if member_ids:
            incoming["member_ids"] = member_ids
        if numbers:
            incoming["member_numbers"] = numbers
        return incoming, new_members, names

    @app.post("/coverage/card/{scan_id}/confirm")
    async def confirm(request: Request, scan_id: str):
        session = member(request)
        form = await request.form()
        check_csrf(session, form.get("csrf_token"))
        hid = session.household_id
        scan = scan_or_404(session, scan_id)
        store = HouseholdStore(db, hid, actor=session.member_id)
        try:
            incoming, new_members, names = plan_from_form(hid, form, scan, store)
            plans = store.all("plan")
            target = store.get("plan", scan["target_plan"]) if scan.get("target_plan") else None
            this_year, _ = (target, None) if target else card_plan.find_plan(
                plans, incoming["insurer"], incoming.get("group_number"), incoming["coverage_kind"],
                incoming["plan_year"])
            keep = features.keep_card_images()
            if not scan["has_back"] and not (this_year or {}).get("contacts"):
                incoming["card_back_missing"] = True  # Coverage offers adding the back (TC-ING-11-6)
            elif (this_year or {}).get("card_back_missing"):
                incoming["card_back_missing"] = False
            merged = card_plan.merge(this_year, incoming)
            if this_year is not None and merged == this_year and not new_members and not (
                    keep and not this_year.get("card_documents")):
                cards.finish(hid, scan_id, keep=False)
                return RedirectResponse(f"/coverage?year={this_year['plan_year']}&card=on_file#plan-{this_year['id']}",
                                        status_code=303)
            if this_year is None:
                label = incoming.get("plan_name") or ("Dental" if incoming["coverage_kind"] == "dental" else "Medical")
                base = f"plan-{incoming['plan_year']}-{slug(label)}"
                plan_id, n = base, 2
                while store.get("plan", plan_id):
                    plan_id, n = f"{base}-{n}", n + 1
                merged["id"] = plan_id
                merged.setdefault("limits", [])
            if keep:
                merged["card_documents"] = sorted({*merged.get("card_documents", []),
                                                   *(r["id"] for r in cards.images(hid, scan_id))})
            problems = importer.record_errors("plan", to_dollars(merged))
            if problems:
                raise ScanRefused("; ".join(problems))
            for m in new_members:
                if bad := importer.record_errors("member", m):
                    raise ScanRefused("; ".join(bad))
        except ScanRefused as e:
            return page(request, "card_review.html", e.status, error=e.message,
                        **review_context(session, scan, dict(form)))
        for m in new_members:
            store.upsert("member", m, edited=True)
        store.upsert("plan", merged, edited=True)
        cards.finish(hid, scan_id, keep=keep, plan_id=merged["id"])
        return RedirectResponse(f"/coverage?year={merged['plan_year']}&saved=1#plan-{merged['id']}", status_code=303)

    return cards
