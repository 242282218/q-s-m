from __future__ import annotations

from datetime import datetime, timezone
from math import ceil
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(..., description="Business code. 0 means success.")
    message: str = Field(..., description="Human-readable message.")
    data: T


class Pagination(BaseModel):
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
    total: int = Field(..., ge=0)
    total_pages: int = Field(..., ge=0)


def build_pagination(*, page: int, page_size: int, total: int) -> Pagination:
    total_pages = ceil(total / page_size) if page_size > 0 else 0
    return Pagination(page=page, page_size=page_size, total=total, total_pages=total_pages)


def ok(data: T, message: str = "OK") -> ApiResponse[T]:
    return ApiResponse[T](code=0, message=message, data=data)


def business_error(data: T, message: str, code: int = 1) -> ApiResponse[T]:
    return ApiResponse[T](code=code, message=message, data=data)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

