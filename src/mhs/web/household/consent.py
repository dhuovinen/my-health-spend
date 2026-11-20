"""Consent (CMP-02) and the privacy notice (CMP-03), ADR-055.

Each member's consent is a household record (`consent`), so it goes with export and delete: collection of health
data, and separately sharing with the AI service (ADR-028), both unticked until the member ticks them, each with the
notice version and the date. Requiring consent before collection is the owner's toggle on the admin screen
(`require_consent`); a member who withdrew is always refused, whatever the toggle says.
"""

from collections.abc import Callable
from datetime import date

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from mhs.data.db import Database
from mhs.data.records import HouseholdRecords
from mhs.web.household import privacy

KIND = "consent"
NOTICE_VERSION = "2026-11-12"


def record_id(member_id: str) -> str:
    return f"consent-{member_id}"


def record_of(db: Database, household_id: str, member_id: str) -> dict | None:
    return HouseholdRecords(db, household_id).get(KIND, record_id(member_id))


def collection_given(rec: dict | None) -> bool:
    c = (rec or {}).get("collection") or {}
    return bool(c.get("given")) and c.get("version") == NOTICE_VERSION


def withdrawn(rec: dict | None) -> bool:
    return ((rec or {}).get("collection") or {}).get("given") is False


def may_collect(db: Database, household_id: str, member_id: str, required: bool) -> bool:
    """Whether documents and claims may be collected for this member now (TC-CMP-02-1, TC-CMP-02-2)."""
    rec = record_of(db, household_id, member_id)
    if withdrawn(rec):
        return False
    return collection_given(rec) or not required


def save(db: Database, household_id: str, member_id: str, collection: bool, ai: bool, today: str) -> dict:
    records = HouseholdRecords(db, household_id)
    rec = records.get(KIND, record_id(member_id)) or {"id": record_id(member_id), "member_id": member_id,
                                                      "history": []}
    entry = {"version": NOTICE_VERSION, "date": today}
    rec["collection"] = {"given": collection, **entry}
    rec["ai_sharing"] = {"given": ai, **entry}
    rec["history"] = [*rec.get("history", []), {"collection": collection, "ai_sharing": ai, **entry}][-50:]
    records.put(KIND, rec)
    return rec


def add_consent(app: FastAPI, *, db: Database, page: Callable, member: Callable, check_csrf: Callable,
                required: Callable[[], bool], set_ai: Callable[[str, bool], None]) -> None:

    @app.get("/privacy-notice", response_class=HTMLResponse)
    def notice(request: Request):
        """Public: anyone can read what MHS does with data before signing in."""
        return page(request, "privacy_notice.html", version=NOTICE_VERSION)

    @app.get("/consent", response_class=HTMLResponse)
    def consent_page(request: Request, saved: str = ""):
        session = member(request)
        rec = record_of(db, session.household_id, session.member_id)
        return page(request, "consent.html", rec=rec, version=NOTICE_VERSION, saved=saved,
                    current=collection_given(rec), withdrawn=withdrawn(rec), required=required())

    @app.post("/consent")
    def give(request: Request, collection: str = Form(""), ai_sharing: str = Form(""), csrf_token: str = Form("")):
        session = member(request)
        check_csrf(session, csrf_token)
        before = record_of(db, session.household_id, session.member_id)
        given, ai = collection == "on", ai_sharing == "on" and collection == "on"
        save(db, session.household_id, session.member_id, given, ai, date.today().isoformat())
        if not ai:  # TC-CMP-02-2: sharing stops for the household; the owner turns it on again with mhs-admin
            set_ai(session.household_id, False)
        if given != collection_given(before):
            privacy.log_event(db, session.household_id, session.member_id,
                              "consent_given" if given else "consent_withdrawn")
        return RedirectResponse("/consent?saved=1", status_code=303)
