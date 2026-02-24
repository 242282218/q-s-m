import os
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ...core.config import get_settings, Settings

router = APIRouter()
api_router = APIRouter()

# Templates configuration
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Helper function to update .env file
def update_env_file(updates: Dict[str, str]):
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    
    # Read existing content
    lines = []
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    
    # Process updates
    new_lines = []
    updated_keys = set()
    
    for line in lines:
        stripped = line.strip()
        # Skip comments and empty lines
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
            
        # Check if line contains a key we want to update
        key_match = False
        for key, value in updates.items():
            if stripped.startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                updated_keys.add(key)
                key_match = True
                break
        
        if not key_match:
            new_lines.append(line)
    
    # Add new keys that weren't in the file
    if lines and not lines[-1].endswith("\n"):
        new_lines.append("\n")
        
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")
            
    # Write back to file
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    
    # Force reload settings
    get_settings.cache_clear()


class SettingsUpdate(BaseModel):
    # App
    LOG_LEVEL: Optional[str] = None
    
    # TMDB
    TMDB_API_KEY: Optional[str] = None
    HTTP_PROXY: Optional[str] = None
    
    # Quark Transfer
    QUARK_TRANSFER_COOKIE: Optional[str] = None


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, settings: Settings = Depends(get_settings)):
    """配置页面"""
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "page_title": "系统设置",
            "settings": settings,
        },
    )


@api_router.post("/update")
async def update_settings(update_data: SettingsUpdate):
    """更新配置"""
    updates = {}
    
    # Filter out None values and convert to dict
    data = update_data.model_dump(exclude_none=True)
    
    for key, value in data.items():
        updates[key] = str(value)
        
    if not updates:
        return {"success": True, "message": "没有需要更新的配置"}
        
    try:
        update_env_file(updates)
        return {"success": True, "message": "配置已更新，请重启服务以确保所有更改生效"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")
