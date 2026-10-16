"""Create the tier roles and apply the SQL migrations in data/migrations/, in order, once each.

Runs with an admin connection (the compose `migrate` job; a Cloud Run job later). The admin role owns the
tables, so row-level security applies to the app, worker and vault roles.
"""

from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql

MIGRATIONS = Path(__file__).parent / "migrations"


@dataclass(frozen=True)
class Roles:
    app: str = "mhs_app"
    worker: str = "mhs_worker"
    vault: str = "mhs_vault"

    def as_dict(self) -> dict[str, str]:
        return {"app": self.app, "worker": self.worker, "vault": self.vault}


def ensure_role(conn: psycopg.Connection, name: str, password: str) -> None:
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,)).fetchone()
    verb = "ALTER" if exists else "CREATE"
    # Utility statements can't take bind parameters; the password is quoted as a literal.
    conn.execute(
        sql.SQL(verb + " ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD {}").format(
            sql.Identifier(name), sql.Literal(password)
        )
    )


def migrate(admin_url: str, roles: Roles, passwords: dict[str, str]) -> list[str]:
    """Ensure roles exist with the given passwords, then apply pending migrations. Returns the names applied."""
    applied = []
    with psycopg.connect(admin_url, autocommit=False) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(31031)")  # one migrator at a time
        for key, name in roles.as_dict().items():
            ensure_role(conn, name, passwords[key])
        db = conn.execute("SELECT current_database()").fetchone()[0]
        conn.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}, {}").format(
                sql.Identifier(db), *(sql.Identifier(r) for r in roles.as_dict().values())
            )
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS public.schema_migrations "
            "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {r[0] for r in conn.execute("SELECT name FROM public.schema_migrations")}
        idents = {k: sql.Identifier(v) for k, v in roles.as_dict().items()}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.stem in done:
                continue
            conn.execute(sql.SQL(path.read_text()).format(**idents))
            conn.execute("INSERT INTO public.schema_migrations (name) VALUES (%s)", (path.stem,))
            applied.append(path.stem)
        conn.commit()
    return applied
