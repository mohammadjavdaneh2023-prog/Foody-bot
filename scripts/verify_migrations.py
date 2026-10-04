from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from psycopg.conninfo import conninfo_to_dict

from app.migrations import migrate, migrations_current


def main() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        raise SystemExit("TEST_DATABASE_URL is required")
    dbname = conninfo_to_dict(database_url).get("dbname", "")
    if "test" not in dbname.lower():
        raise SystemExit("Refusing to reset a database whose name does not contain 'test'")
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    first = migrate(database_url)
    second = migrate(database_url)
    if not first or second or not migrations_current(database_url):
        raise SystemExit("Fresh migration or idempotency verification failed")
    print("Fresh PostgreSQL migration and idempotent rerun verified")


if __name__ == "__main__":
    main()
