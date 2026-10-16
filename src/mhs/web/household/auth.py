"""Members, sign-in with MFA, and sessions for the application tier (PRV-11, ADR-031).

Sign-in is two steps: email and password (Argon2id), then a TOTP code. A session only reaches household data
once both have passed. Only a SHA-256 of the session cookie is stored; the token rotates after MFA.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from mhs.data.db import Database
from mhs.data.keys import Keyring

MIN_PASSWORD = 12
MAX_FAILED = 5
LOCK_MINUTES = 15
TOTP_ISSUER = "My Health Spend"

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


@dataclass(frozen=True)
class Session:
    token_hash: bytes
    member_id: str
    household_id: str
    mfa_passed: bool
    csrf_token: str
    display_name: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
        """Give a member a new TOTP secret and end their sessions (admin recovery until TC-PRV-07-3 is built)."""
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
        return totp_secret

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
        return Member(str(row["id"]), str(row["household_id"]), row["email"], row["display_name"])

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
                "UPDATE app.members SET totp_last_step = %s, failed_attempts = 0, locked_until = NULL WHERE id = %s",
                (step, member_id),
            )
        return True

    # --- sessions ---

    def start_session(self, member: Member) -> str:
        """A session that has passed the password only. Returns the cookie value."""
        token = secrets.token_urlsafe(32)
        with self.db.tx() as c:
            c.execute(
                "INSERT INTO app.sessions (token_hash, member_id, household_id, csrf_token) VALUES (%s, %s, %s, %s)",
                (_hash_token(token), member.id, member.household_id, secrets.token_urlsafe(24)),
            )
        return token

    def get_session(self, token: str | None) -> Session | None:
        if not token:
            return None
        h = _hash_token(token)
        with self.db.tx() as c:
            row = c.execute(
                "SELECT s.*, m.display_name FROM app.sessions s JOIN app.members m ON m.id = s.member_id "
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
                       row["display_name"])

    def pass_mfa(self, session: Session) -> str:
        """Mark MFA passed under a fresh token (the pre-MFA token stops working). Returns the new cookie value."""
        token = secrets.token_urlsafe(32)
        with self.db.tx() as c:
            c.execute(
                "UPDATE app.sessions SET token_hash = %s, mfa_passed = true, csrf_token = %s, created_at = now(), "
                "last_seen_at = now() WHERE token_hash = %s",
                (_hash_token(token), secrets.token_urlsafe(24), session.token_hash),
            )
        return token

    def end_session(self, token: str | None) -> None:
        if token:
            with self.db.tx() as c:
                c.execute("DELETE FROM app.sessions WHERE token_hash = %s", (_hash_token(token),))
