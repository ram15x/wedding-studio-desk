"""Copy the current SQLite state into an empty Supabase Postgres database.

Run this once after exporting the Railway volume database to a local file and
setting SUPABASE_DB_URL. It refuses to overwrite a non-empty destination.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

TABLES = (
    "wedding_guests",
    "wedding_facts",
    "guest_sessions",
    "guest_messages",
    "family_inbox",
    "holds",
    "escalations",
)


def migrate(source_path: str) -> dict[str, int]:
    if not (os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")):
        raise RuntimeError("Set SUPABASE_DB_URL to the Supabase Postgres connection string first.")
    source_file = Path(source_path).expanduser().resolve()
    if not source_file.is_file():
        raise FileNotFoundError(f"SQLite export not found: {source_file}")

    import app  # noqa: PLC0415 - app loads .env.local before opening the destination

    source = sqlite3.connect(f"file:{source_file.as_posix()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    destination = app.db()
    try:
        for table in TABLES:
            existing = destination.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            if existing:
                raise RuntimeError(f"Destination table {table} is not empty; migration stopped without writing anything.")
        counts = {}
        destination.execute("BEGIN")
        for table in TABLES:
            try:
                rows = source.execute(f"SELECT * FROM {table}").fetchall()
            except sqlite3.OperationalError:
                counts[table] = 0
                continue
            if not rows:
                counts[table] = 0
                continue
            columns = list(rows[0].keys())
            sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})"
            destination.executemany(sql, [tuple(row[column] for column in columns) for row in rows])
            counts[table] = len(rows)
            if "id" in columns:
                destination.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table}"
                )
        destination.commit()
        return counts
    except Exception:
        destination.rollback()
        raise
    finally:
        source.close()
        destination.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python migrate_sqlite_to_supabase.py <exported-sqlite-file>")
    result = migrate(sys.argv[1])
    print("Migrated rows:")
    for table, count in result.items():
        print(f"  {table}: {count}")
