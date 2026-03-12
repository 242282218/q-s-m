from __future__ import annotations

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def resolve_project_root() -> Path:
    repo_root = BACKEND_ROOT.parent
    markers = ("frontend", "README.md", ".gitignore")
    if any((repo_root / marker).exists() for marker in markers):
        return repo_root
    return BACKEND_ROOT


PROJECT_ROOT = resolve_project_root()
LEGACY_ENV_FILE = BACKEND_ROOT / ".env"
LEGACY_DATA_DIR = BACKEND_ROOT / "data"
DEFAULT_STORAGE_ROOT = PROJECT_ROOT / "storage"


def _read_path_from_env(env_name: str) -> Path | None:
    raw_value = os.getenv(env_name)
    if not raw_value:
        return None
    path = Path(raw_value).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_default_env_path() -> Path:
    explicit_path = _read_path_from_env("QSM_ENV_FILE")
    if explicit_path is not None:
        return explicit_path

    default_env = PROJECT_ROOT / ".env"
    if default_env.exists():
        return default_env
    return LEGACY_ENV_FILE


def resolve_storage_root() -> Path:
    explicit_path = _read_path_from_env("QSM_STORAGE_ROOT")
    if explicit_path is not None:
        return explicit_path
    return DEFAULT_STORAGE_ROOT


def resolve_runtime_env_path() -> Path:
    explicit_path = _read_path_from_env("QSM_RUNTIME_ENV_FILE")
    if explicit_path is not None:
        return explicit_path

    candidates = [
        resolve_storage_root() / "config" / "settings.env",
        LEGACY_DATA_DIR / "settings.env",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def resolve_data_dir() -> Path:
    explicit_path = _read_path_from_env("QSM_DATA_DIR")
    if explicit_path is not None:
        return explicit_path

    preferred_dir = resolve_storage_root() / "db"
    preferred_database = preferred_dir / "qsm.db"
    legacy_database = LEGACY_DATA_DIR / "qsm.db"
    if preferred_database.exists():
        return preferred_dir
    if legacy_database.exists():
        return LEGACY_DATA_DIR
    if LEGACY_DATA_DIR.exists() and any(LEGACY_DATA_DIR.iterdir()):
        return LEGACY_DATA_DIR
    return preferred_dir


def resolve_log_dir(raw_value: str | None = None) -> Path:
    explicit_path = _read_path_from_env("QSM_LOG_DIR")
    if explicit_path is not None:
        return explicit_path

    if raw_value:
        configured_path = Path(raw_value).expanduser()
        if configured_path.is_absolute():
            return configured_path
        return PROJECT_ROOT / configured_path

    return resolve_storage_root() / "logs"
