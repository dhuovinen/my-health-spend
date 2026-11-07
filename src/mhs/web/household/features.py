"""Settings for the whole service that the owner changes on the admin screen (PLT-09, ADR-049).

They are records, not environment settings, so a change needs no deploy, and every change is a security log line
(`setting_<name>_on` or `_off`) with the owner who made it. Nothing here touches household data.
"""

from mhs.data.db import Database
from mhs.web.household import privacy

REQUIRE_CODE = "require_code"
DEFAULTS = {REQUIRE_CODE: True}  # the code starts on: an upgrade never quietly removes protection (ADR-049)


def provider_setting(provider: str) -> str:
    return f"signin_{provider}"


class Features:
    def __init__(self, db: Database):
        self.db = db

    def get(self, name: str) -> bool:
        with self.db.tx() as c:
            row = c.execute("SELECT value FROM app.service_settings WHERE name = %s", (name,)).fetchone()
        return row["value"] if row else DEFAULTS.get(name, True)

    def all(self) -> dict[str, bool]:
        with self.db.tx() as c:
            rows = c.execute("SELECT name, value FROM app.service_settings").fetchall()
        return {**DEFAULTS, **{r["name"]: r["value"] for r in rows}}

    def require_code(self) -> bool:
        return self.get(REQUIRE_CODE)

    def provider_on(self, provider: str) -> bool:
        return self.get(provider_setting(provider))

    def set(self, name: str, value: bool, *, member_id: str | None = None, household_id: str | None = None) -> bool:
        """Change a setting and log it. Returns whether it changed. Turning the code on ends every session that
        didn't enter one, so nobody stays in on the weaker sign-in."""
        if self.get(name) == value:
            return False
        with self.db.tx() as c:
            c.execute("INSERT INTO app.service_settings (name, value, updated_by) VALUES (%s, %s, %s) "
                      "ON CONFLICT (name) DO UPDATE SET value = excluded.value, updated_at = now(), "
                      "updated_by = excluded.updated_by", (name, value, member_id))
            if name == REQUIRE_CODE and value:
                c.execute("DELETE FROM app.sessions WHERE mfa_passed AND NOT code_passed")  # waiting ones get asked
        privacy.log_event(self.db, household_id, member_id, f"setting_{name}_{'on' if value else 'off'}")
        return True

    def changes(self, limit: int = 20) -> list[dict]:
        """Recent setting changes: what, when, and which owner (by name), for the admin screen."""
        with self.db.tx() as c:
            return c.execute(
                "SELECT l.at, l.event, m.display_name FROM app.security_log l "
                "LEFT JOIN app.members m ON m.id = l.member_id "
                "WHERE l.event LIKE 'setting\\_%%' ORDER BY l.id DESC LIMIT %s", (limit,)).fetchall()

    def counts(self) -> dict[str, int]:
        """Counts only, over every household: no names, records or amounts (ADR-049)."""
        with self.db.tx() as c:
            row = c.execute(
                "SELECT (SELECT count(*) FROM app.households) AS households, "
                "(SELECT count(*) FROM app.members) AS members, "
                "(SELECT count(*) FROM app.members WHERE totp_confirmed) AS confirmed, "
                "(SELECT count(*) FROM app.members WHERE signed_in_without_code AND NOT totp_confirmed) AS no_code, "
                "(SELECT count(*) FROM app.members WHERE is_owner) AS owners").fetchone()
            linked = c.execute("SELECT provider, count(*) AS n FROM app.member_identities GROUP BY provider").fetchall()
        return {**row, **{f"linked_{r['provider']}": r["n"] for r in linked}}
