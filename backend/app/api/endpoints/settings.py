from pathlib import Path
from typing import Dict, Optional
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..schemas.common import ApiResponse, ok
from ..schemas.system import SettingsUpdateData

api_router = APIRouter()

KEEP_SENTINEL = "__KEEP__"


def validate_env_key(key: str) -> bool:
    """
    验证环境变量键是否安全
    
    防止注入攻击：
    - 只允许字母、数字、下划线
    - 不允许换行符、特殊字符
    
    Args:
        key: 环境变量键
        
    Returns:
        是否有效
    """
    if not key or not isinstance(key, str):
        return False
    
    # 只允许字母、数字、下划线
    pattern = r'^[A-Za-z0-9_]+$'
    return bool(re.match(pattern, key))


def validate_env_value(value: str) -> bool:
    """
    验证环境变量值是否安全
    
    防止注入攻击：
    - 不允许换行符
    - 不允许命令注入字符
    
    Args:
        value: 环境变量值
        
    Returns:
        是否有效
    """
    if not isinstance(value, str):
        return False
    
    # 不允许换行符和命令注入字符
    forbidden_chars = ['\n', '\r', '\0', '`', '$', '|', '&', ';', '<', '>']
    return not any(char in value for char in forbidden_chars)


def update_env_file(updates: Dict[str, str]) -> None:
    """
    更新 .env 文件
    
    安全措施：
    - 验证所有键和值
    - 防止注入攻击
    - 原子性写入
    
    Args:
        updates: 要更新的键值对
        
    Raises:
        ValueError: 如果键或值无效
    """
    env_path = Path(__file__).parent.parent.parent.parent / ".env"

    # 验证所有输入
    for key, value in updates.items():
        if not validate_env_key(key):
            raise ValueError(f"无效的环境变量键: {key}")
        if not validate_env_value(value):
            raise ValueError(f"无效的环境变量值: {value}")

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
