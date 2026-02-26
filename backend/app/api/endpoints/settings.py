from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..schemas.common import ApiResponse, ok
from ..schemas.system import SettingsUpdateData

api_router = APIRouter()

KEEP_SENTINEL = "__KEEP__"


def update_env_file(updates: Dict[str, str]) -> None:
    env_path = Path(__file__).parent.parent.parent.parent / ".env"

    lines = []
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    updated_keys = set()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        key_match = False
        for key, value in updates.items():
            if stripped.startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                updated_keys.add(key)
                key_match = True
                break

        if not key_match:
            new_lines.append(line)

    if lines and not lines[-1].endswith("\n"):
        new_lines.append("\n")

    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    get_settings.cache_clear()


class SettingsUpdate(BaseModel):
    LOG_LEVEL: Optional[str] = None
    TMDB_API_KEY: Optional[str] = None
    HTTP_PROXY: Optional[str] = None
    QUARK_TRANSFER_COOKIE: Optional[str] = None
    TRANSFER_KEEP_EXTRAS: Optional[bool] = None
    TRANSFER_KEEP_SUBTITLES: Optional[bool] = None
    TRANSFER_DRY_RUN: Optional[bool] = None
    TRANSFER_CLEANUP_ENABLED: Optional[bool] = None
    TRANSFER_CLEANUP_DELETE_NON_VIDEO: Optional[bool] = None
    TRANSFER_CLEANUP_DELETE_UNSELECTED_VIDEO: Optional[bool] = None
    TRANSFER_CLEANUP_DELETE_EMPTY_DIRS: Optional[bool] = None


@api_router.post("/update", response_model=ApiResponse[SettingsUpdateData])
async def update_settings(update_data: SettingsUpdate) -> ApiResponse[SettingsUpdateData]:
    updates: Dict[str, str] = {}
    data = update_data.model_dump(exclude_none=True)

    for key, value in data.items():
        if isinstance(value, bool):
            updates[key] = "true" if value else "false"
            continue

        text = str(value).strip()
        if text == KEEP_SENTINEL:
            continue
        updates[key] = text

    if not updates:
        return ok(
            SettingsUpdateData(updated_keys=[], restart_required=False),
            message="没有需要更新的配置",
        )

    try:
        update_env_file(updates)
        return ok(
            SettingsUpdateData(updated_keys=sorted(updates.keys()), restart_required=True),
            message="配置已更新，请重启服务以确保所有更改生效",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")
