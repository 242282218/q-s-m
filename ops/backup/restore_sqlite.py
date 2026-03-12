from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path


def resolve_default_path(*parts: str) -> Path:
    return Path(__file__).resolve().parents[2].joinpath(*parts)


def copy_database(source_path: Path, target_path: Path) -> None:
    with sqlite3.connect(source_path) as source, sqlite3.connect(target_path) as target:
        source.backup(target)


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore SQLite database from a backup file.")
    parser.add_argument("--backup-file", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=resolve_default_path("storage", "db", "qsm.db"))
    args = parser.parse_args()

    if not args.backup_file.exists():
        raise SystemExit(f"Backup not found: {args.backup_file}")

    args.db.parent.mkdir(parents=True, exist_ok=True)

    if args.db.exists():
        snapshot_name = f"{args.db.stem}.pre-restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}{args.db.suffix}"
        snapshot_path = args.db.with_name(snapshot_name)
        copy_database(args.db, snapshot_path)
        print(f"current database snapshot: {snapshot_path}")

    if args.db.exists():
        args.db.unlink()

    copy_database(args.backup_file, args.db)
    print(f"database restored: {args.db}")


if __name__ == "__main__":
    main()
