"""Members, sign-in with MFA, and sessions for the application tier (PRV-11, ADR-031).

Sign-in is two steps: email and password (Argon2id), then a TOTP code. A session only reaches household data
once both have passed, or the first alone when the owner has turned the code off for members (ADR-049; owners
always enter it). Only a SHA-256 of the session cookie is stored; the token rotates after MFA.
"""

import base64
import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import psycopg
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from mhs.data.db import Database
from mhs.data.keys import Keyring

MIN_PASSWORD = 12
MAX_FAILED = 5
LOCK_MINUTES = 15
TOTP_ISSUER = "CareBack"  # new enrolments only: existing authenticator entries keep the old label (ADR-060)
ENROLMENT_LINK_MINUTES = 15
RECOVERY_CODES = 10
RECOVERY_LINK_MINUTES = 15
SIGNUP_MINUTES = 15
MAX_NAME = 80
EMAIL_TAKEN = "There's already an account for {email}."

_hasher = PasswordHasher()
# Verified against when the email is unknown, so a wrong email takes as long as a wrong password.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


class AccountError(ValueError):
    pass


@dataclass(frozen=True)
class Member:
    id: str
    household_id: str
    email: str
    display_name: str
    is_owner: bool = False
    has_password: bool = True


def _member(row: dict) -> Member:
    return Member(str(row["id"]), str(row["household_id"]), row["email"], row["display_name"], row["is_owner"],
                  row["password_hash"] is not None)


@dataclass(frozen=True)
class Session:
    token_hash: bytes
    member_id: str
    household_id: str
    mfa_passed: bool
    csrf_token: str
    display_name: str
    code_passed: bool = False
    is_owner: bool = False
    has_password: bool = True
    started_at: datetime | None = None  # when the sign-in was completed (or begun, before the code)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _recovery_code() -> str:
    raw = base64.b32encode(secrets.token_bytes(7)).decode()[:10]  # 50 bits
    return f"{raw[:5]}-{raw[5:]}"


def _code_hash(code: str) -> bytes:
    return hashlib.sha256(re.sub(r"[\s-]+", "", code or "").upper().encode()).digest()


def _hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


class Accounts:
    def __init__(self, db: Database, keyring: Keyring, idle_minutes: int = 15, max_hours: int = 12):
        self.db = db
        self.keyring = keyring
        self.idle = timedelta(minutes=idle_minutes)
        self.max_age = timedelta(hours=max_hours)

    # --- households and members (admin) ---

    def create_household(self, name: str) -> str:
        hid = str(uuid.uuid4())
        with self.db.tx() as c:
            c.execute("INSERT INTO app.households (id, name) VALUES (%s, %s)", (hid, name.strip()))
        self.keyring.data_key(hid)  # create the household's data key now
        return hid

    def find_household(self, name: str) -> str | None:
        """The oldest household with this name, if any."""
        with self.db.tx() as c:
            row = c.execute("SELECT id FROM app.households WHERE name = %s ORDER BY created_at LIMIT 1",
                            (name.strip(),)).fetchone()
        return str(row["id"]) if row else None

    def household_name(self, household_id: str) -> str | None:
        with self.db.tx() as c:
            row = c.execute("SELECT name FROM app.households WHERE id = %s", (household_id,)).fetchone()
        return row["name"] if row else None

    def ai_extraction(self, household_id: str) -> bool:
        """Whether the household's documents may be read by Claude (scrubbed text only; ADR-028, ADR-034)."""
        with self.db.tx() as c:
            row = c.execute("SELECT ai_extraction FROM app.households WHERE id = %s", (household_id,)).fetchone()
        return bool(row and row["ai_extraction"])

    def set_ai_extraction(self, household_id: str, on: bool) -> None:
        with self.db.tx() as c:
            if c.execute("UPDATE app.households SET ai_extraction = %s WHERE id = %s",
                         (on, household_id)).rowcount != 1:
                raise AccountError("No such household.")

    def add_member(self, household_id: str, email: str, display_name: str, password: str) -> tuple[Member, str]:
        """Create a member. Returns the member and the TOTP secret to enrol in an authenticator app."""
        email = email.strip().lower()
        if "@" not in email:
            raise AccountError("Enter an email address.")
        if len(password) < MIN_PASSWORD:
            raise AccountError(f"The password must be at least {MIN_PASSWORD} characters.")
        if self.household_name(household_id) is None:
            raise AccountError("No such household.")
        member_id = str(uuid.uuid4())
        totp_secret = pyotp.random_base32()
        sealed = self.keyring.encrypt(household_id, totp_secret.encode(), f"totp:{member_id}")
        with self.db.tx() as c:
            if c.execute("SELECT 1 FROM app.members WHERE lower(email) = %s", (email,)).fetchone():
                raise AccountError("That email is already a member.")
            c.execute(
                "INSERT INTO app.members (id, household_id, email, display_name, password_hash, totp_secret) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (member_id, household_id, email, display_name.strip(), _hasher.hash(password), sealed),
            )
        return Member(member_id, str(household_id), email, display_name.strip()), totp_secret

    def reset_mfa(self, email: str) -> str:
        """Give a member a new TOTP secret and end their sessions (admin reset, and the end of self-service recovery)."""
        row = self._member_row(email)
        if row is None:
            raise AccountError("No such member.")
        totp_secret = pyotp.random_base32()
        sealed = self.keyring.encrypt(str(row["household_id"]), totp_secret.encode(), f"totp:{row['id']}")
        with self.db.tx() as c:
            c.execute(
                "UPDATE app.members SET totp_secret = %s, totp_last_step = 0, failed_attempts = 0, locked_until = NULL "
                "WHERE id = %s",
                (sealed, row["id"]),
            )
            c.execute("DELETE FROM app.sessions WHERE member_id = %s", (row["id"],))
            c.execute("DELETE FROM app.enrolment_links WHERE member_id = %s", (row["id"],))
        return totp_secret

    def set_password(self, email: str, password: str) -> None:
        """Give a member a new password, unlock the account and end their sessions (admin)."""
        if len(password) < MIN_PASSWORD:
            raise AccountError(f"The password must be at least {MIN_PASSWORD} characters.")
        row = self._member_row(email)
        if row is None:
            raise AccountError("No such member.")
        with self.db.tx() as c:
            c.execute("UPDATE app.members SET password_hash = %s, failed_attempts = 0, locked_until = NULL "
                      "WHERE id = %s", (_hasher.hash(password), row["id"]))
            c.execute("DELETE FROM app.sessions WHERE member_id = %s", (row["id"],))

    def set_owner(self, email: str, on: bool) -> None:
        """Give or take away the owner role (ADR-049). Ends the member's sessions, so an owner's next one enters
        the code."""
        row = self._member_row(email)
        if row is None:
            raise AccountError("No such member.")
        with self.db.tx() as c:
            c.execute("UPDATE app.members SET is_owner = %s WHERE id = %s", (on, row["id"]))
            c.execute("DELETE FROM app.sessions WHERE member_id = %s", (row["id"],))

    def is_owner(self, email: str) -> bool:
        row = self._member_row(email)
        return bool(row and row["is_owner"])

    def code_setup_secret(self, member_id: str) -> str | None:
        """The authenticator secret to show at sign-in, for a member who has signed in without a code and never
        confirmed one (ADR-049): once the code is back on, they set it up here rather than being locked out. Also for
        a member who signed up with a provider and hasn't entered a first code yet (PRV-13, ADR-059). None for
        everyone else; a member who never signed in uses the enrolment link instead."""
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM app.members WHERE id = %s", (member_id,)).fetchone()
        if row is None or row["totp_confirmed"] or not (row["signed_in_without_code"] or row["signed_up_with"]):
            return None
        return self.keyring.decrypt(str(row["household_id"]), bytes(row["totp_secret"]), f"totp:{member_id}").decode()

    def member_household(self, email: str) -> str | None:
        row = self._member_row(email)
        return str(row["household_id"]) if row else None

    # --- enrolment links: the authenticator QR code, shown once ---

    def create_enrolment_link(self, email: str, minutes: int = ENROLMENT_LINK_MINUTES) -> str:
        """A single-use token for /enrol/<token>, which shows the member's current TOTP secret as a QR code.
        Only its hash is stored; it expires after `minutes`, and a new secret (reset_mfa) cancels it."""
        row = self._member_row(email)
        if row is None:
            raise AccountError("No such member.")
        token = secrets.token_urlsafe(32)
        with self.db.tx() as c:
            c.execute("DELETE FROM app.enrolment_links WHERE expires_at <= now()")
            c.execute("INSERT INTO app.enrolment_links (token_hash, member_id, expires_at) "
                      "VALUES (%s, %s, now() + make_interval(mins => %s))", (_hash_token(token), row["id"], minutes))
        return token

    def enrolment_link_valid(self, token: str, purpose: str = "enrol") -> bool:
        with self.db.tx() as c:
            return c.execute("SELECT 1 FROM app.enrolment_links WHERE token_hash = %s AND expires_at > now() "
                             "AND purpose = %s", (_hash_token(token), purpose)).fetchone() is not None

    def redeem_enrolment_link(self, token: str) -> tuple[str, str] | None:
        """Use a link: it is deleted whether or not it was still valid. Returns the member's email and TOTP
        secret, or None for an unknown, used or expired link."""
        with self.db.tx() as c:
            link = c.execute("DELETE FROM app.enrolment_links WHERE token_hash = %s AND purpose = 'enrol' "
                             "RETURNING member_id, expires_at > now() AS valid", (_hash_token(token),)).fetchone()
            if link is None or not link["valid"]:
                return None
            row = c.execute("SELECT * FROM app.members WHERE id = %s", (link["member_id"],)).fetchone()
        secret = self.keyring.decrypt(str(row["household_id"]), bytes(row["totp_secret"]), f"totp:{row['id']}")
        return row["email"], secret.decode()

    # --- recovery codes and self-service recovery (TC-PRV-07-3, ADR-037) ---

    def new_recovery_codes(self, email: str) -> list[str]:
        """Ten new single-use codes for the member, replacing any they had. Shown once; only hashes are kept."""
        row = self._member_row(email)
        if row is None:
            raise AccountError("No such member.")
        codes = [_recovery_code() for _ in range(RECOVERY_CODES)]
        with self.db.tx() as c:
            c.execute("DELETE FROM app.recovery_codes WHERE member_id = %s", (row["id"],))
            with c.cursor() as cur:
                cur.executemany("INSERT INTO app.recovery_codes (member_id, code_hash) VALUES (%s, %s)",
                                [(row["id"], _code_hash(code)) for code in codes])
        return codes

    def email_of(self, member_id: str) -> str:
        with self.db.tx() as c:
            return c.execute("SELECT email FROM app.members WHERE id = %s", (member_id,)).fetchone()["email"]

    def recovery_codes_left(self, member_id: str) -> int:
        with self.db.tx() as c:
            return c.execute("SELECT count(*) AS n FROM app.recovery_codes WHERE member_id = %s AND used_at IS NULL",
                             (member_id,)).fetchone()["n"]

    def start_recovery(self, email: str, code: str) -> str | None:
        """A recovery code in place of the password and the authenticator. On success the code is used up, the
        member's sessions end, and a short-lived recovery link (its own kind) is returned for setting a new
        password and authenticator. None for an unknown email, a wrong or used code, or a locked account; a
        wrong code counts toward the lock like a wrong password."""
        row = self._member_row(email)
        if row is None:
            _code_hash(code)  # the same work for an unknown email
            return None
        if self._locked(row):
            return None
        with self.db.tx() as c:
            used = c.execute("UPDATE app.recovery_codes SET used_at = now() WHERE member_id = %s AND code_hash = %s "
                             "AND used_at IS NULL RETURNING 1", (row["id"], _code_hash(code))).fetchone()
            if used:
                c.execute("DELETE FROM app.sessions WHERE member_id = %s", (row["id"],))
        if not used:
            self._record_failure(row["id"])
            return None
        token = secrets.token_urlsafe(32)
        with self.db.tx() as c:
            c.execute("DELETE FROM app.enrolment_links WHERE expires_at <= now()")
            c.execute("INSERT INTO app.enrolment_links (token_hash, member_id, expires_at, purpose) "
                      "VALUES (%s, %s, now() + make_interval(mins => %s), 'recover')",
                      (_hash_token(token), row["id"], RECOVERY_LINK_MINUTES))
        return token

    def finish_recovery(self, token: str, password: str) -> tuple[str, str, list[str]] | None:
        """Use a recovery link: a new password, a new authenticator secret and new recovery codes. Returns
        (email, TOTP secret, codes), or None for an unknown, used or expired link. Household data and keys
        are untouched, so everything the member had is there when they sign in again."""
        if len(password) < MIN_PASSWORD:
            raise AccountError(f"The password must be at least {MIN_PASSWORD} characters.")
        with self.db.tx() as c:
            link = c.execute("DELETE FROM app.enrolment_links WHERE token_hash = %s AND purpose = 'recover' "
                             "RETURNING member_id, expires_at > now() AS valid", (_hash_token(token),)).fetchone()
            if link is None or not link["valid"]:
                return None
            email = c.execute("SELECT email FROM app.members WHERE id = %s", (link["member_id"],)).fetchone()["email"]
        self.set_password(email, password)
        totp_secret = self.reset_mfa(email)
        return email, totp_secret, self.new_recovery_codes(email)

    @staticmethod
    def provisioning_uri(email: str, totp_secret: str) -> str:
        return pyotp.TOTP(totp_secret).provisioning_uri(name=email, issuer_name=TOTP_ISSUER)

    # --- sign-in ---

    def _member_row(self, email: str) -> dict | None:
        with self.db.tx() as c:
            return c.execute(
                "SELECT * FROM app.members WHERE lower(email) = %s", (email.strip().lower(),)
            ).fetchone()

    def _locked(self, row: dict) -> bool:
        return row["locked_until"] is not None and row["locked_until"] > _now()

    def _record_failure(self, member_id) -> None:
        with self.db.tx() as c:
            c.execute(
                "UPDATE app.members SET failed_attempts = failed_attempts + 1, "
                "locked_until = CASE WHEN failed_attempts + 1 >= %s THEN now() + make_interval(mins => %s) END "
                "WHERE id = %s",
                (MAX_FAILED, LOCK_MINUTES, member_id),
            )

    def check_password(self, email: str, password: str) -> Member | None:
        """First factor. None for an unknown email, a wrong password, or a locked account (indistinguishable)."""
        row = self._member_row(email)
        if row is None:
            try:
                _hasher.verify(_DUMMY_HASH, password)
            except VerificationError:
                pass
            return None
        if row["password_hash"] is None:  # signed up with a provider (ADR-059): nothing to guess, so no lock
            try:
                _hasher.verify(_DUMMY_HASH, password)
            except VerificationError:
                pass
            return None
        if self._locked(row):
            return None
        try:
            _hasher.verify(row["password_hash"], password)
        except (VerificationError, InvalidHashError):
            self._record_failure(row["id"])
            return None
        if _hasher.check_needs_rehash(row["password_hash"]):
            with self.db.tx() as c:
                c.execute("UPDATE app.members SET password_hash = %s WHERE id = %s", (_hasher.hash(password), row["id"]))
        return _member(row)

    def check_totp(self, member_id: str, code: str) -> bool:
        """Second factor. A code (time step) is accepted once; failures count toward the lock."""
        with self.db.tx() as c:
            row = c.execute("SELECT * FROM app.members WHERE id = %s", (member_id,)).fetchone()
        if row is None or self._locked(row):
            return False
        code = code.strip().replace(" ", "")
        totp_secret = self.keyring.decrypt(str(row["household_id"]), bytes(row["totp_secret"]), f"totp:{member_id}")
        totp = pyotp.TOTP(totp_secret.decode())
        now = _now()
        step = None
        for offset in (0, -1, 1):  # allow one 30-second step of clock drift
            at = now + timedelta(seconds=30 * offset)
            if code.isdigit() and secrets.compare_digest(totp.at(at), code):
                step = totp.timecode(at)
                break
        if step is None or step <= row["totp_last_step"]:
            self._record_failure(member_id)
            return False
        with self.db.tx() as c:
            c.execute(
                "UPDATE app.members SET totp_last_step = %s, totp_confirmed = true, failed_attempts = 0, "
                "locked_until = NULL WHERE id = %s",
                (step, member_id),
            )
        return True

    # --- social sign-in (PRV-12, ADR-048): linked by provider and subject, never by email ---

    def member_for_identity(self, provider: str, subject: str) -> Member | None:
        """The first factor through a provider. None for an unlinked account or a locked member (indistinguishable)."""
        with self.db.tx() as c:
            row = c.execute("SELECT m.* FROM app.member_identities i JOIN app.members m ON m.id = i.member_id "
                            "WHERE i.provider = %s AND i.subject = %s", (provider, subject)).fetchone()
        if row is None or self._locked(row):
            return None
        return _member(row)

    def identity_linked(self, provider: str, subject: str) -> bool:
        """Whether this provider account is linked to anyone, locked or not: a locked member's account mustn't be
        offered sign-up as if it were new."""
        with self.db.tx() as c:
            return c.execute("SELECT 1 FROM app.member_identities WHERE provider = %s AND subject = %s",
                             (provider, subject)).fetchone() is not None

    def start_identity_link(self, member_id: str, state: str, minutes: int) -> None:
        """Remember who is linking an account, against the flow's state, until the provider sends them back."""
        with self.db.tx() as c:
            c.execute("DELETE FROM app.enrolment_links WHERE expires_at <= now()")
            c.execute("INSERT INTO app.enrolment_links (token_hash, member_id, expires_at, purpose) "
                      "VALUES (%s, %s, now() + make_interval(mins => %s), 'link_identity')",
                      (_hash_token(state), member_id, minutes))

    def take_identity_link(self, state: str) -> str | None:
        """The member linking under this state, if any. The entry is used up either way."""
        with self.db.tx() as c:
            row = c.execute("DELETE FROM app.enrolment_links WHERE token_hash = %s AND purpose = 'link_identity' "
                            "RETURNING member_id, expires_at > now() AS valid", (_hash_token(state),)).fetchone()
        return str(row["member_id"]) if row and row["valid"] else None

    def start_payer_pull(self, member_id: str, state: str, minutes: int) -> None:
        """ING-09 (ADR-054): remember who started an insurer pull, until the payer sends them back."""
        with self.db.tx() as c:
            c.execute("DELETE FROM app.enrolment_links WHERE expires_at <= now()")
            c.execute("INSERT INTO app.enrolment_links (token_hash, member_id, expires_at, purpose) "
                      "VALUES (%s, %s, now() + make_interval(mins => %s), 'payer_pull')",
                      (_hash_token(state), member_id, minutes))

    def take_payer_pull(self, state: str) -> Member | None:
        """The member who started the pull under this state, if still valid and not locked. Used up either way."""
        with self.db.tx() as c:
            row = c.execute("DELETE FROM app.enrolment_links WHERE token_hash = %s AND purpose = 'payer_pull' "
                            "RETURNING member_id, expires_at > now() AS valid", (_hash_token(state),)).fetchone()
            if not row or not row["valid"]:
                return None
            member = c.execute("SELECT * FROM app.members WHERE id = %s", (row["member_id"],)).fetchone()
        if member is None or self._locked(member):
            return None
        return _member(member)

    def link_identity(self, member_id: str, provider: str, subject: str, email: str) -> None:
        with self.db.tx() as c:
            added = c.execute("INSERT INTO app.member_identities (provider, subject, member_id, email) "
                              "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                              (provider, subject, member_id, email)).rowcount
        if added != 1:
            raise AccountError("That account couldn't be linked. It may already be linked to a member, or you may "
                               "already have one linked. Unlink the old one first.")

    def unlink_identity(self, member_id: str, provider: str) -> bool:
        with self.db.tx() as c:
            return c.execute("DELETE FROM app.member_identities WHERE member_id = %s AND provider = %s",
                             (member_id, provider)).rowcount == 1

    def identities_of(self, member_id: str) -> dict[str, str]:
        """Each linked provider and the account's email at the time it was linked."""
        with self.db.tx() as c:
            rows = c.execute("SELECT provider, email FROM app.member_identities WHERE member_id = %s",
                             (member_id,)).fetchall()
        return {r["provider"]: r["email"] for r in rows}

    def has_password(self, member_id: str) -> bool:
        with self.db.tx() as c:
            row = c.execute("SELECT password_hash IS NOT NULL AS has FROM app.members WHERE id = %s",
                            (member_id,)).fetchone()
        return bool(row and row["has"])

    # --- self-service sign-up (PRV-13, ADR-059) ---

    def email_taken(self, email: str) -> bool:
        return self._member_row(email) is not None

    def start_signup(self, provider: str, subject: str, email: str, minutes: int = SIGNUP_MINUTES) -> tuple[str, str]:
        """Hold who came back from the provider until they create the account. Returns the cookie token and the form
        token; only a hash of the first is stored."""
        token, form_token = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        with self.db.tx() as c:
            c.execute("DELETE FROM app.pending_signups WHERE expires_at <= now()")
            c.execute("INSERT INTO app.pending_signups (token_hash, provider, subject, email, form_token, expires_at) "
                      "VALUES (%s, %s, %s, %s, %s, now() + make_interval(mins => %s))",
                      (_hash_token(token), provider, subject, email.strip().lower(), form_token, minutes))
        return token, form_token

    def pending_signup(self, token: str | None) -> dict | None:
        """The pending sign-up under this cookie token, if it hasn't expired. Not used up."""
        if not token:
            return None
        with self.db.tx() as c:
            row = c.execute("SELECT provider, subject, email, form_token FROM app.pending_signups "
                            "WHERE token_hash = %s AND expires_at > now()", (_hash_token(token),)).fetchone()
        return dict(row) if row else None

    def end_signup(self, token: str | None) -> bool:
        """Use up a pending sign-up. Returns whether this call was the one that used it, so two posts racing with
        the same token make one account."""
        if not token:
            return False
        with self.db.tx() as c:
            return c.execute("DELETE FROM app.pending_signups WHERE token_hash = %s",
                             (_hash_token(token),)).rowcount == 1

    def sign_up(self, provider: str, subject: str, email: str, display_name: str, terms_version: str,
                privacy_version: str) -> Member:
        """A new household with this person as its first member, no password, and the provider account linked, all
        or nothing. Raises AccountError if the email or the provider account is already in use."""
        email, name = email.strip().lower(), " ".join(display_name.split())
        if not name or len(name) > MAX_NAME:
            raise AccountError(f"Enter your name (up to {MAX_NAME} characters).")
        if "@" not in email:
            raise AccountError("The provider didn't give an email address.")
        household_id = self.create_household(f"{name}'s household")
        member_id = str(uuid.uuid4())
        sealed = self.keyring.encrypt(household_id, pyotp.random_base32().encode(), f"totp:{member_id}")
        try:
            with self.db.tx() as c:
                c.execute(
                    "INSERT INTO app.members (id, household_id, email, display_name, password_hash, totp_secret, "
                    "signed_up_with, terms_version, privacy_version, terms_accepted_at) "
                    "VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, %s, now())",
                    (member_id, household_id, email, name, sealed, provider, terms_version, privacy_version))
                c.execute("INSERT INTO app.member_identities (provider, subject, member_id, email) "
                          "VALUES (%s, %s, %s, %s)", (provider, subject, member_id, email))
        except BaseException as e:
            with self.db.tx() as c:  # nothing else is in a household this new
                c.execute("DELETE FROM app.households WHERE id = %s", (household_id,))
            if isinstance(e, psycopg.errors.UniqueViolation):
                raise AccountError(EMAIL_TAKEN.format(email=email)) from None
            raise
        return Member(member_id, household_id, email, name, False, False)

    # --- sessions ---

    def start_session(self, member: Member, without_code: bool = False) -> str:
        """A session that has passed the first factor only, or, with without_code, one that is complete without a
        code because the owner turned it off (ADR-049; never for an owner). Returns the cookie value."""
        if without_code and member.is_owner:
            raise AccountError("An owner always enters the code.")
        token = secrets.token_urlsafe(32)
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO app.sessions (token_hash, member_id, household_id, csrf_token, mfa_passed) "
                "VALUES (%s, %s, %s, %s, %s)",
                (_hash_token(token), member.id, member.household_id, secrets.token_urlsafe(24), without_code),
            )
            if without_code:
                c.execute("UPDATE app.members SET signed_in_without_code = true WHERE id = %s", (member.id,))
        return token

    def get_session(self, token: str | None) -> Session | None:
        if not token:
            return None
        h = _hash_token(token)
        with self.db.tx() as c:
            row = c.execute(
                "SELECT s.*, m.display_name, m.is_owner, m.password_hash IS NOT NULL AS has_password "
                "FROM app.sessions s JOIN app.members m ON m.id = s.member_id "
                "WHERE s.token_hash = %s",
                (h,),
            ).fetchone()
            if row is None:
                return None
            now = _now()
            if now - row["last_seen_at"] > self.idle or now - row["created_at"] > self.max_age:
                c.execute("DELETE FROM app.sessions WHERE token_hash = %s", (h,))
                return None
            c.execute("UPDATE app.sessions SET last_seen_at = now() WHERE token_hash = %s", (h,))
        return Session(h, str(row["member_id"]), str(row["household_id"]), row["mfa_passed"], row["csrf_token"],
                       row["display_name"], row["code_passed"], row["is_owner"], row["has_password"], row["created_at"])

    def pass_mfa(self, session: Session, code_passed: bool = True) -> str:
        """Mark MFA passed under a fresh token (the pre-MFA token stops working). Returns the new cookie value.
        code_passed=False completes a session left waiting when the owner turned the code off (ADR-049)."""
        if not code_passed and session.is_owner:
            raise AccountError("An owner always enters the code.")
        token = secrets.token_urlsafe(32)
        with self.db.tx() as c:
            c.execute(
                "UPDATE app.sessions SET token_hash = %s, mfa_passed = true, code_passed = %s, csrf_token = %s, "
                "created_at = now(), last_seen_at = now() WHERE token_hash = %s",
                (_hash_token(token), code_passed, secrets.token_urlsafe(24), session.token_hash),
            )
            if not code_passed:
                c.execute("UPDATE app.members SET signed_in_without_code = true WHERE id = %s", (session.member_id,))
        return token

    def end_session(self, token: str | None) -> None:
        if token:
            with self.db.tx() as c:
                c.execute("DELETE FROM app.sessions WHERE token_hash = %s", (_hash_token(token),))
