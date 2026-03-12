"""
认证模块 - 统一的 API 认证机制
"""
import secrets
from typing import Optional
from fastapi import Header, HTTPException
from .config import get_settings


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    """
    验证 API Key

    如果配置了 API_KEY，则要求请求头中包含有效的 X-API-Key
    如果未配置 API_KEY，则跳过验证（本地开发模式）
    """
    settings = get_settings()

    if not settings.api_key:
        return

    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=401,
            detail="无效或缺失 API Key"
        )
