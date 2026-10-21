from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env", override=False)

import config
from history_store import (
    backend_name,
    migrate_sqlite_history_to_postgres,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate Smart Document Finder SQLite activity history to PostgreSQL."
    )
    parser.add_argument(
        "--sqlite-path",
        default=str(config.DATABASE_PATH),
        help="Path to the existing local SQLite database (default: data/documents.db).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing PostgreSQL activity history before importing.",
    )
    args = parser.parse_args()

    if backend_name() != "postgresql":
        print(
            "PostgreSQL is not selected. Set DATABASE_BACKEND=postgresql and "
            "DATABASE_URL in .env before running this migration."
        )
        return 2

    result = migrate_sqlite_history_to_postgres(
        args.sqlite_path,
        overwrite=args.overwrite,
    )
    if result.get("skipped"):
        print("Migration skipped: PostgreSQL already contains activity rows or no SQLite history was found.")
    else:
        print(f"Migration completed: {result.get('migrated', 0)} activity rows imported.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
