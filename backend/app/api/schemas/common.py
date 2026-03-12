from __future__ import annotations

from datetime import datetime, timezone
from math import ceil
from typing import Generic, TypeVar, Any, Optional

from fastapi import Request
from pydantic import BaseModel, Field, ConfigDict

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """
    错误详情信息

    提供详细的错误定位信息，包括字段、值、原因等
    """
    model_config = ConfigDict(defer_build=True)

    field: Optional[str] = Field(None, description="出错的字段路径")
    value: Optional[Any] = Field(None, description="导致错误的值")
    reason: Optional[str] = Field(None, description="错误原因说明")
    context: Optional[dict[str, Any]] = Field(None, description="额外上下文信息")


class ApiResponse(BaseModel, Generic[T]):
    """
    统一 API 响应格式

    成功响应：
    - code: 0
    - message: "OK" 或成功消息
    - data: 响应数据
    - error: null

    失败响应：
    - code: 非 0 错误码
    - message: 错误消息
    - data: null 或部分数据
    - error: 错误详情
    """
    model_config = ConfigDict(defer_build=True)

    code: int = Field(..., description="业务错误码。0 表示成功，非 0 表示失败")
    message: str = Field(..., description="人类可读的消息")
    data: Optional[T] = Field(None, description="响应数据，失败时可能为 null 或部分数据")
    error: Optional[ErrorDetail] = Field(None, description="错误详情，仅在失败时提供")
    request_id: Optional[str] = Field(None, description="请求 ID，用于追踪和日志")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="响应时间戳")


class Pagination(BaseModel):
    """传统页码分页"""
    model_config = ConfigDict(defer_build=True)

    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=100)  # 限制最大 page_size 为 100
    total: int = Field(..., ge=0)
    total_pages: int = Field(..., ge=0)


class CursorPagination(BaseModel):
    """游标分页（适用于大数据量列表）"""
    model_config = ConfigDict(defer_build=True)

    limit: int = Field(..., ge=1, le=100)  # 限制最大 limit 为 100
    has_more: bool = Field(..., description="是否还有更多数据")
    next_cursor: Optional[str] = Field(None, description="下一页游标")
    prev_cursor: Optional[str] = Field(None, description="上一页游标")
    total: Optional[int] = Field(None, description="总数量（可选，大数据量时可能不返回）")


def build_pagination(*, page: int, page_size: int, total: int) -> Pagination:
    """构建传统页码分页"""
    # 限制 page_size 最大为 100
    page_size = min(page_size, 100)
    total_pages = ceil(total / page_size) if page_size > 0 else 0
    return Pagination(page=page, page_size=page_size, total=total, total_pages=total_pages)


def build_cursor_pagination(
    *,
    limit: int,
    has_more: bool,
    next_cursor: Optional[str] = None,
    prev_cursor: Optional[str] = None,
    total: Optional[int] = None,
) -> CursorPagination:
    """构建游标分页"""
    # 限制 limit 最大为 100
    limit = min(limit, 100)
    return CursorPagination(
        limit=limit,
        has_more=has_more,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
        total=total,
    )


def encode_cursor(data: dict) -> str:
    """将数据编码为游标字符串"""
    import base64
    import json
    json_str = json.dumps(data, separators=(',', ':'))
    return base64.urlsafe_b64encode(json_str.encode()).decode().rstrip('=')


def decode_cursor(cursor: str) -> dict:
    """将游标字符串解码为数据"""
    import base64
    import json
    # 添加可能缺失的填充
    padding = 4 - len(cursor) % 4
    if padding != 4:
        cursor += '=' * padding
    json_str = base64.urlsafe_b64decode(cursor.encode()).decode()
    return json.loads(json_str)


def ok(data: T, message: str = "OK", request_id: str | None = None) -> ApiResponse[T]:
    """构建成功响应"""
    return ApiResponse[T](
        code=0,
        message=message,
        data=data,
        error=None,
        request_id=request_id,
    )


def ok_with_request(data: T, request: Any, message: str = "OK") -> ApiResponse[T]:
    """构建成功响应，自动从 request 对象注入 request_id"""
    request_id = get_request_id(request)
    return ok(data, message, request_id)


def business_error(
    data: T | None = None,
    message: str = "",
    code: int = 1,
    error: ErrorDetail | None = None,
    request_id: str | None = None,
) -> ApiResponse[T | None]:
    """构建错误响应"""
    return ApiResponse[T | None](
        code=code,
        message=message or "操作失败",
        data=data,
        error=error,
        request_id=request_id,
    )


def validation_error(
    message: str = "验证错误",
    field: str | None = None,
    value: Any = None,
    reason: str | None = None,
    context: dict | None = None,
    request_id: str | None = None,
) -> ApiResponse[None]:
    """构建验证错误响应"""
    return ApiResponse[None](
        code=200,
        message=message,
        data=None,
        error=ErrorDetail(field=field, value=value, reason=reason, context=context),
        request_id=request_id,
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_request_id(request: Any) -> str | None:
    """从请求对象获取 request_id"""
    if hasattr(request, 'state') and hasattr(request.state, 'request_id'):
        return request.state.request_id
    return None


def inject_request_id(request: Request) -> str | None:
    """FastAPI 依赖项：自动注入 request_id"""
    return get_request_id(request)

