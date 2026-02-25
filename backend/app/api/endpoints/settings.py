from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ...core.config import Settings, get_settings

router = APIRouter()
api_router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

KEEP_SENTINEL = "__KEEP__"


def mask_secret(value: Optional[str], *, keep_start: int = 3, keep_end: int = 2) -> str:
    if not value:
        return ""
    text = str(value)
    if len(text) <= keep_start + keep_end:
        return "*" * max(6, len(text))
    return f"{text[:keep_start]}***{text[-keep_end:]}"


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


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, settings: Settings = Depends(get_settings)):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "page_title": "系统设置",
            "settings": settings,
            "masked": {
                "tmdb_api_key": mask_secret(settings.tmdb_api_key),
                "quark_transfer_cookie": mask_secret(settings.quark_transfer_cookie),
            },
            "keep_sentinel": KEEP_SENTINEL,
        },
    )


@api_router.post("/update")
async def update_settings(update_data: SettingsUpdate):
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
        return {"success": True, "message": "没有需要更新的配置"}

    try:
        update_env_file(updates)
        return {"success": True, "message": "配置已更新，请重启服务以确保所有更改生效"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")
