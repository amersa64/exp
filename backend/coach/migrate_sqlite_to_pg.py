"""
One-shot migration: copy a live SQLite coach.db into Postgres/Supabase.

Run once when moving an existing brain onto Supabase. It copies rows verbatim
(no Pydantic round-trip) so it's a faithful backup, and upserts so it's safe to
re-run. The Postgres schema must already exist — PgStore creates it on first
connect, or apply schema_postgres.sql by hand.

    SUPABASE_DB_URL=postgresql://... \
        python -m coach.migrate_sqlite_to_pg /path/to/coach.db

Bypasses mirror integrity on purpose: this is a bulk copy of already-verified
state, not a live mutation.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys

from psycopg.types.json import Jsonb

# (table, columns, conflict_target, jsonb_columns)
_BLOB_TABLES = [
    "identities", "milestones", "habits", "actions", "profiles", "programs",
    "world", "journals", "ai_programs", "adjustments", "readiness", "places",
]


def _conflict_cols(table: str) -> str:
    user_keyed = {"profiles", "programs", "world", "journals", "ai_programs",
                  "adjustments", "readiness", "places"}
    return "user_id" if table in user_keyed else "id"


def migrate(sqlite_path: str, dsn: str) -> dict[str, int]:
    from .pg_store import PgStore  # ensures the schema exists

    pg = PgStore(dsn)
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    counts: dict[str, int] = {}

    try:
        with pg.pool.connection() as conn:
            # Simple (key, json) tables.
            for table in _BLOB_TABLES:
                key = _conflict_cols(table)
                rows = src.execute(f"SELECT {key}, json FROM {table}").fetchall()
                for r in rows:
                    conn.execute(
                        f"INSERT INTO {table} ({key}, json) VALUES (%s, %s) "
                        f"ON CONFLICT ({key}) DO UPDATE SET json = EXCLUDED.json",
                        (r[key], Jsonb(json.loads(r["json"]))),
                    )
                counts[table] = len(rows)

            # nudges (id, user_id, fired_at, json)
            rows = src.execute("SELECT id, user_id, fired_at, json FROM nudges").fetchall()
            for r in rows:
                conn.execute(
                    "INSERT INTO nudges (id, user_id, fired_at, json) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (id) DO UPDATE SET user_id=EXCLUDED.user_id, "
                    "fired_at=EXCLUDED.fired_at, json=EXCLUDED.json",
                    (r["id"], r["user_id"], r["fired_at"], Jsonb(json.loads(r["json"]))),
                )
            counts["nudges"] = len(rows)

            # verified_events (id, user_id, at, json)
            rows = src.execute("SELECT id, user_id, at, json FROM verified_events").fetchall()
            for r in rows:
                conn.execute(
                    "INSERT INTO verified_events (id, user_id, at, json) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (id) DO UPDATE SET user_id=EXCLUDED.user_id, "
                    "at=EXCLUDED.at, json=EXCLUDED.json",
                    (r["id"], r["user_id"], r["at"], Jsonb(json.loads(r["json"]))),
                )
            counts["verified_events"] = len(rows)

            # vitals (user_id, metric, at, value, unit)
            rows = src.execute(
                "SELECT user_id, metric, at, value, unit FROM vitals"
            ).fetchall()
            for r in rows:
                conn.execute(
                    "INSERT INTO vitals (user_id, metric, at, value, unit) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (user_id, metric, at) DO UPDATE SET "
                    "value=EXCLUDED.value, unit=EXCLUDED.unit",
                    (r["user_id"], r["metric"], r["at"], r["value"], r["unit"]),
                )
            counts["vitals"] = len(rows)
    finally:
        src.close()
        pg.close()

    return counts


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python -m coach.migrate_sqlite_to_pg <sqlite_path>  "
                 "(SUPABASE_DB_URL must be set)")
    dsn = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not dsn:
        sys.exit("SUPABASE_DB_URL (or DATABASE_URL) must be set")
    counts = migrate(sys.argv[1], dsn)
    total = sum(counts.values())
    print(f"migrated {total} rows:")
    for table, n in counts.items():
        if n:
            print(f"  {table}: {n}")


if __name__ == "__main__":
    main()
