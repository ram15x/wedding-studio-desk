"""Optional Supabase Postgres connection adapter used by the demo server."""
from __future__ import annotations

import re


class PostgresCompatConnection:
    """Keep the app's small DB API compatible with SQLite-style placeholders."""

    dialect = "postgres"

    def __init__(self, raw):
        self.raw = raw

    @staticmethod
    def _sql(statement: str) -> str:
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            return "BEGIN"
        statement = re.sub(r'(?i)(\bstatus\s*=\s*)"(open|active|replied|confirmed|released)"', r"\1'\2'", statement)
        return statement.replace("?", "%s")

    def execute(self, statement: str, parameters=()):
        return self.raw.execute(self._sql(statement), parameters)

    def executemany(self, statement: str, parameters):
        return self.raw.cursor().executemany(self._sql(statement), parameters)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


def connect_postgres(url: str) -> PostgresCompatConnection:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("Postgres support requires psycopg. Install requirements.txt and restart.") from exc
    # Supabase transaction-pooler URLs require avoiding connection-scoped
    # prepared statements.
    raw = psycopg.connect(url, row_factory=dict_row, connect_timeout=10, prepare_threshold=None)
    return PostgresCompatConnection(raw)


def is_integrity_error(exc: Exception) -> bool:
    if exc.__class__.__module__.startswith("sqlite3"):
        return True
    return exc.__class__.__name__ in {"IntegrityError", "UniqueViolation", "ForeignKeyViolation", "CheckViolation"}
