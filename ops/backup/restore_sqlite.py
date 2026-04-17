from __future__ import annotations

import argparse
import sqlite3
import shutil
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.paths import resolve_data_dir, resolve_runtime_env_path


def resolve_default_database_path() -> Path:
    return resolve_data_dir() / "qsm.db"


def resolve_default_config_path() -> Path:
    return resolve_runtime_env_path()


def copy_database(source_path: Path, target_path: Path) -> None:
    with closing(sqlite3.connect(source_path)) as source, closing(sqlite3.connect(target_path)) as target:
        source.backup(target)


def restore_database(backup_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f".{target_path.name}.restore-tmp")
    if temp_path.exists():
        temp_path.unlink()
    try:
        copy_database(backup_path, temp_path)
        copy_database(temp_path, target_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def snapshot_existing_file(path: Path, timestamp: str) -> Path:
    snapshot_path = path.with_name(f"{path.stem}.pre-restore-{timestamp}{path.suffix}")
    shutil.copy2(path, snapshot_path)
    return snapshot_path


def resolve_settings_backup_path(backup_path: Path) -> Path:
    return backup_path.with_suffix(".settings.env")


def restore_settings(backup_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f".{target_path.name}.restore-tmp")
    if temp_path.exists():
        temp_path.unlink()
    try:
        shutil.copy2(backup_path, temp_path)
        temp_path.replace(target_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore SQLite database from a backup file.")
    parser.add_argument("--backup-file", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=resolve_default_database_path())
    parser.add_argument("--config", type=Path, default=resolve_default_config_path())
    args = parser.parse_args()

    if not args.backup_file.exists():
        raise SystemExit(f"Backup not found: {args.backup_file}")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if args.db.exists():
        snapshot_path = args.db.with_name(f"{args.db.stem}.pre-restore-{timestamp}{args.db.suffix}")
        copy_database(args.db, snapshot_path)
        print(f"current database snapshot: {snapshot_path}")

    restore_database(args.backup_file, args.db)
    print(f"database restored: {args.db}")

    settings_backup_path = resolve_settings_backup_path(args.backup_file)
    if not settings_backup_path.exists():
        return

    if args.config.exists():
        snapshot_path = snapshot_existing_file(args.config, timestamp)
        print(f"current settings snapshot: {snapshot_path}")

    restore_settings(settings_backup_path, args.config)
    print(f"settings restored: {args.config}")


if __name__ == "__main__":
    main()
