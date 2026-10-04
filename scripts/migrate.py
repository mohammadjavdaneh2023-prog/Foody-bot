from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.migrations import migrate


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    versions = migrate(database_url)
    print("Migrations applied:" if versions else "Database already current", ", ".join(versions))


if __name__ == "__main__":
    main()
