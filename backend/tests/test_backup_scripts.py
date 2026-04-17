from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative_path: str):
    module_path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


backup_sqlite = load_module("qsm_backup_sqlite", "ops/backup/backup_sqlite.py")
restore_sqlite = load_module("qsm_restore_sqlite", "ops/backup/restore_sqlite.py")


def write_database(path: Path, value: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE items (value TEXT NOT NULL)")
        connection.execute("INSERT INTO items(value) VALUES (?)", (value,))
        connection.commit()


def read_database_values(path: Path) -> list[str]:
    with sqlite3.connect(path) as connection:
        return [row[0] for row in connection.execute("SELECT value FROM items ORDER BY rowid")]


def test_backup_creates_database_schema_and_settings_snapshot(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "db" / "qsm.db"
    database_path.parent.mkdir(parents=True)
    settings_path = tmp_path / "config" / "settings.env"
    settings_path.parent.mkdir(parents=True)
    backup_dir = tmp_path / "backups"
    write_database(database_path, "fresh-data")
    settings_path.write_text("API_KEY=from-settings\n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "backup_sqlite.py",
            "--db",
            str(database_path),
            "--config",
            str(settings_path),
            "--out-dir",
            str(backup_dir),
        ],
    )

    backup_sqlite.main()

    backup_files = list(backup_dir.glob("qsm-*.db"))
    schema_files = list(backup_dir.glob("qsm-*.schema.sql"))
    settings_files = list(backup_dir.glob("qsm-*.settings.env"))

    assert len(backup_files) == 1
    assert len(schema_files) == 1
    assert len(settings_files) == 1
    assert read_database_values(backup_files[0]) == ["fresh-data"]
    assert "CREATE TABLE items" in schema_files[0].read_text(encoding="utf-8")
    assert settings_files[0].read_text(encoding="utf-8") == "API_KEY=from-settings\n"


def test_restore_restores_database_and_matching_settings_snapshot(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "db" / "qsm.db"
    database_path.parent.mkdir(parents=True)
    settings_path = tmp_path / "config" / "settings.env"
    settings_path.parent.mkdir(parents=True)
    write_database(database_path, "before-restore")
    settings_path.write_text("API_KEY=old\n", encoding="utf-8")

    backup_path = tmp_path / "backups" / "qsm-20260417-220000.db"
    backup_path.parent.mkdir(parents=True)
    write_database(backup_path, "after-restore")
    backup_path.with_suffix(".settings.env").write_text("API_KEY=new\n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "restore_sqlite.py",
            "--backup-file",
            str(backup_path),
            "--db",
            str(database_path),
            "--config",
            str(settings_path),
        ],
    )

    restore_sqlite.main()

    assert read_database_values(database_path) == ["after-restore"]
    assert settings_path.read_text(encoding="utf-8") == "API_KEY=new\n"

    database_snapshots = list(database_path.parent.glob("qsm.pre-restore-*.db"))
    settings_snapshots = list(settings_path.parent.glob("settings.pre-restore-*.env"))
    assert len(database_snapshots) == 1
    assert len(settings_snapshots) == 1
    assert read_database_values(database_snapshots[0]) == ["before-restore"]
    assert settings_snapshots[0].read_text(encoding="utf-8") == "API_KEY=old\n"


def test_restore_without_matching_settings_backup_keeps_current_settings(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "db" / "qsm.db"
    database_path.parent.mkdir(parents=True)
    settings_path = tmp_path / "config" / "settings.env"
    settings_path.parent.mkdir(parents=True)
    write_database(database_path, "before-restore")
    settings_path.write_text("API_KEY=keep-me\n", encoding="utf-8")

    backup_path = tmp_path / "backups" / "qsm-20260417-220100.db"
    backup_path.parent.mkdir(parents=True)
    write_database(backup_path, "after-restore")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "restore_sqlite.py",
            "--backup-file",
            str(backup_path),
            "--db",
            str(database_path),
            "--config",
            str(settings_path),
        ],
    )

    restore_sqlite.main()

    assert read_database_values(database_path) == ["after-restore"]
    assert settings_path.read_text(encoding="utf-8") == "API_KEY=keep-me\n"
    assert list(settings_path.parent.glob("settings.pre-restore-*.env")) == []


def test_backup_and_restore_default_paths_follow_runtime_env_overrides(monkeypatch, tmp_path) -> None:
    data_dir = tmp_path / "custom-data"
    storage_root = tmp_path / "custom-storage"
    runtime_env = tmp_path / "custom-config" / "settings.env"

    monkeypatch.setenv("QSM_DATA_DIR", str(data_dir))
    monkeypatch.setenv("QSM_STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("QSM_RUNTIME_ENV_FILE", str(runtime_env))

    assert backup_sqlite.resolve_default_database_path() == data_dir / "qsm.db"
    assert backup_sqlite.resolve_default_config_path() == runtime_env
    assert backup_sqlite.resolve_default_backup_dir() == storage_root / "backups"
    assert restore_sqlite.resolve_default_database_path() == data_dir / "qsm.db"
    assert restore_sqlite.resolve_default_config_path() == runtime_env
