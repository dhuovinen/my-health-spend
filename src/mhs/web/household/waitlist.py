"""The landing page's waitlist (ADR-061): people ask to be told when CareBack opens sign-up.

Only an address, the consent wording's version and a time are kept, in `app.waitlist`, outside every household. The
page never echoes the address and answers the same whether or not it was already on the list. Nothing is emailed:
the owner lists the addresses with `mhs-admin waitlist list` and writes to them by hand.
"""

import re

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse

from mhs.data.db import Database

# Bump when the consent wording beside the box in landing.html changes.
CONSENT_VERSION = "2026-11-26"
CONSENT_TEXT = ("Email me when CareBack opens sign-up. I can ask to be removed at any time; "
                "the privacy notice says how.")
MAX_EMAIL = 254
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def normalize(email: str) -> str | None:
    """The address as stored (trimmed, lower-cased), or None when it isn't one."""
    email = (email or "").strip().lower()
    return email if len(email) <= MAX_EMAIL and EMAIL.match(email) else None


class Waitlist:
    def __init__(self, db: Database):
        self.db = db

    def join(self, email: str, consent_version: str = CONSENT_VERSION) -> None:
        with self.db.tx() as c:
            c.execute("INSERT INTO app.waitlist (email, consent_version) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                      (email, consent_version))

    def count(self) -> int:
        with self.db.tx() as c:
            return c.execute("SELECT count(*) AS n FROM app.waitlist").fetchone()["n"]

    def entries(self) -> list[dict]:
        with self.db.tx() as c:
            return c.execute("SELECT email, consent_version, joined_at FROM app.waitlist "
                             "ORDER BY joined_at").fetchall()

    def remove(self, email: str) -> bool:
        with self.db.tx() as c:
            return c.execute("DELETE FROM app.waitlist WHERE email = %s",
                             ((email or "").strip().lower(),)).rowcount > 0


def add_waitlist(app: FastAPI, *, waitlist: Waitlist) -> None:
    @app.post("/waitlist")
    def join(request: Request, email: str = Form(""), agree: str = Form("")):
        # The app's guard already refuses posts from other sites. Nothing is stored without the tick.
        address = normalize(email)
        if address is None:
            state = "invalid"
        elif agree != "yes":
            state = "consent"
        else:
            waitlist.join(address)
            state = "joined"
        return RedirectResponse(f"/welcome?waitlist={state}#start", status_code=303)
