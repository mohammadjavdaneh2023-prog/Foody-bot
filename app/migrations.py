from __future__ import annotations

import hashlib
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def migrate(database_url: str) -> list[str]:
    """Apply immutable SQL migrations transactionally and return applied versions."""
    applied_now: list[str] = []
    with psycopg.connect(database_url) as conn, conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('foody:migrations'))")
        conn.execute(
            """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
        )
        applied = dict(conn.execute("SELECT version, checksum FROM schema_migrations").fetchall())
        for path in migration_files():
            version = path.name.split("_", 1)[0]
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            if version in applied:
                if applied[version] != checksum:
                    raise RuntimeError(f"Applied migration {version} was modified")
                continue
            conn.execute(sql, prepare=False)
            conn.execute(
                "INSERT INTO schema_migrations(version, checksum) VALUES (%s, %s)",
                (version, checksum),
            )
            applied_now.append(version)
    return applied_now


def migrations_current(database_url: str) -> bool:
    expected = {path.name.split("_", 1)[0] for path in migration_files()}
    try:
        with psycopg.connect(database_url, connect_timeout=3) as conn:
            rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        return {row[0] for row in rows} == expected
    except (psycopg.Error, RuntimeError):
        return False
