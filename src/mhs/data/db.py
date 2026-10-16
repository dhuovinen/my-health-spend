"""Records database connection (Postgres, ADR-027): a pool and household-scoped transactions."""

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class Database:
    def __init__(self, url: str, min_size: int = 1, max_size: int = 10):
        self.pool = ConnectionPool(
            url, min_size=min_size, max_size=max_size, kwargs={"row_factory": dict_row}, open=True
        )

    @contextmanager
    def tx(self, household_id: str | None = None) -> Iterator[psycopg.Connection]:
        """A transaction; commits on success, rolls back on error.

        With household_id, row-level security limits every household table to that household for the rest of
        the transaction. Without it, household tables return no rows.
        """
        with self.pool.connection() as conn:
            if household_id is not None:
                conn.execute("SELECT set_config('mhs.household_id', %s, true)", (str(household_id),))
            yield conn

    def close(self) -> None:
        self.pool.close()
