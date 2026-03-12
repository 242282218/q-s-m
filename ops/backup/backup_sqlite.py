from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


def resolve_default_path(*parts: str) -> Path:
    return Path(__file__).resolve().parents[2].joinpath(*parts)


def backup_database(source_path: Path, target_path: Path) -> None:
    with sqlite3.connect(source_path) as source, sqlite3.connect(target_path) as target:
        source.backup(target)


def export_schema(source_path: Path, schema_path: Path) -> None:
    with sqlite3.connect(source_path) as connection:
        rows = connection.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE sql IS NOT NULL
            ORDER BY type, name
            """
        ).fetchall()
    schema_path.write_text(";\n".join(row[0] for row in rows) + ";\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a timestamped SQLite backup.")
    parser.add_argument("--db", type=Path, default=resolve_default_path("storage", "db", "qsm.db"))
    parser.add_argument(
        "--config",
        type=Path,
        default=resolve_default_path("storage", "config", "settings.env"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=resolve_default_path("storage", "backups"),
    )
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    backup_path = args.out_dir / f"qsm-{timestamp}.db"
    schema_path = args.out_dir / f"qsm-{timestamp}.schema.sql"

    backup_database(args.db, backup_path)
    export_schema(args.db, schema_path)

    if args.config.exists():
        shutil.copy2(args.config, args.out_dir / f"qsm-{timestamp}.settings.env")

    print(f"backup created: {backup_path}")


if __name__ == "__main__":
    main()
