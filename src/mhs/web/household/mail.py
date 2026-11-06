"""Forwarded email (ING-01, TC-ING-01-4, ADR-039): bills and EOBs sent to a household's private address.

Mail is accepted only from the household's members' own email addresses. Each PDF or photo attachment becomes an
upload; a message with no attachment whose body is a statement or an EOB becomes one too. From there it is the
same as an upload from the Uploads page: stored sealed, scrubbed, read by the worker, reviewed and confirmed.

`mhs-mail` serves this over SMTP on the local stack. In production an inbound-mail service (an account to set up)
posts the raw message to the same `handle_message`; its sender checks (SPF, DKIM) then stand in for the trust
that the local stack takes on faith.
"""

import email
import email.policy
import logging
import os
from email.utils import getaddresses

from mhs.data.db import Database
from mhs.ingest.extract import EXTRACTED, classify
from mhs.ingest.text import IMAGES, PDF, Unreadable, check_image, content_type, html_to_text, read_pdf
from mhs.web.household.inbound import household_for
from mhs.web.household.intake import Intake

log = logging.getLogger("mhs.mail")
MAX_MESSAGE = 25 * 1024 * 1024


def _member(db: Database, household_id: str, address: str) -> str | None:
    with db.tx() as c:
        row = c.execute("SELECT id FROM app.members WHERE household_id = %s AND lower(email) = %s",
                        (household_id, address.strip().lower())).fetchone()
    return str(row["id"]) if row else None


def handle_message(raw: bytes, recipient: str, it: Intake) -> tuple[int, str]:
    """Take one message for one recipient. Returns an SMTP reply code and text; nothing is stored on a refusal."""
    if len(raw) > MAX_MESSAGE:
        return 552, "Message too large"
    household_id = household_for(it.db, recipient)
    if household_id is None:
        return 550, "No such mailbox"
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    senders = [a for _, a in getaddresses(msg.get_all("From", [])) if a]
    member_id = _member(it.db, household_id, senders[0]) if len(senders) == 1 else None
    if member_id is None:
        log.info("refused mail for household %s: sender isn't a member", household_id)
        return 550, "The sender isn't a member of this household"

    stored, skipped = 0, 0
    for part in msg.walk():
        if part.is_multipart() or not (part.get_filename() or part.get_content_disposition() == "attachment"):
            continue
        filename = os.path.basename(part.get_filename() or "attachment")[:200]
        ctype = content_type(filename, part.get_content_type())
        data = part.get_payload(decode=True) or b""
        if ctype != PDF and ctype not in IMAGES:
            skipped += 1
            continue
        try:
            read_pdf(data) if ctype == PDF else check_image(data, ctype)
        except Unreadable:
            skipped += 1
            continue
        if not data or it.duplicate_of(household_id, data):
            skipped += 1
            continue
        upload_id = it.store_original(household_id, member_id, filename, ctype, data, "auto", via="email")
        it.read_in_background(household_id, upload_id, ctype, data, None)
        stored += 1

    if stored == 0:  # no usable attachment: is the body itself the statement?
        body = msg.get_body(preferencelist=("html", "plain"))
        if body is not None:
            text = body.get_content()
            ctype = "text/html" if body.get_content_type() == "text/html" else "text/plain"
            readable = html_to_text(text) if ctype == "text/html" else text
            if classify(readable)[0] in EXTRACTED:
                data = text.encode("utf-8")
                if not it.duplicate_of(household_id, data):
                    name = "email-body.html" if ctype == "text/html" else "email-body.txt"
                    upload_id = it.store_original(household_id, member_id, name, ctype, data, "auto", via="email")
                    it.read_in_background(household_id, upload_id, ctype, data, None)
                    stored += 1
    if stored == 0:
        return 550, "No bill, EOB or statement was found in the message"
    log.info("mail for household %s: %s document(s), %s skipped", household_id, stored, skipped)
    return 250, f"{stored} document(s) received"


class SmtpHandler:
    """aiosmtpd handler: recipients are checked as they're given, each message is handled per recipient."""

    def __init__(self, it: Intake):
        self.it = it

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        if household_for(self.it.db, address) is None:
            return "550 No such mailbox"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        import asyncio

        replies = [await asyncio.to_thread(handle_message, envelope.original_content or envelope.content, r, self.it)
                   for r in envelope.rcpt_tos]
        code, text = min(replies)  # a 250 for any recipient accepts the message
        return f"{code} {text}"


def main() -> None:
    """`mhs-mail`: the local stack's SMTP receiver for forwarded email."""
    import time

    from aiosmtpd.controller import Controller

    from mhs.data.keys import db_keyring, keys_from_env
    from mhs.data.objects import object_store_from_env
    from mhs.data.queue import JobQueue
    from mhs.ingest.ocr import get_engine
    from mhs.ingest.scrub import scrubber_class
    from mhs.stack import load_app_config
    from mhs.vault.client import VaultClient
    from mhs.web.household.auth import Accounts

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    config = load_app_config()
    db = Database(config.database_url, max_size=4)
    keyring = db_keyring(db, keys_from_env(config.key_file), "app.household_keys")
    accounts = Accounts(db, keyring)
    it = Intake(db, keyring, object_store_from_env(config.objects_dir), VaultClient(config.vault_url, config.vault_token),
                JobQueue(db), ocr=get_engine(config.ocr_engine), scrubber=scrubber_class(config.scrubber),
                ai_extraction=accounts.ai_extraction)
    port = int(os.environ.get("MHS_MAIL_PORT", "2525"))
    controller = Controller(SmtpHandler(it), hostname=os.environ.get("MHS_HOST", "127.0.0.1"), port=port,
                            data_size_limit=MAX_MESSAGE)
    controller.start()
    log.info("mail receiver on port %s for *@%s", port, os.environ.get("MHS_INBOUND_DOMAIN", "inbound.mhs.local"))
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        controller.stop()
