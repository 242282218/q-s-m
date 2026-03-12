"""
SSE (Server-Sent Events) 统一事件数据结构

定义标准的 SSE 事件格式，确保所有 SSE 端点使用一致的数据结构。
"""
from datetime import datetime
from typing import Any, Optional, Literal
from pydantic import BaseModel, Field


class SseEvent(BaseModel):
    """
    统一的 SSE 事件数据结构
    
    Attributes:
        type: 事件类型 (log, progress, complete, error)
        data: 事件数据负载
        timestamp: 事件时间戳 (ISO 8601 格式)
        request_id: 请求唯一标识，用于追踪和日志关联
        message: 人类可读的消息描述（可选）
        level: 日志级别 (info, warning, error)（可选）
        code: 业务错误码（可选，仅在 error 类型时使用）
    """
    type: Literal["log", "progress", "complete", "error"] = Field(
        ...,
        description="事件类型",
        examples=["progress"]
    )
    data: Any = Field(
        default=None,
        description="事件数据负载",
        examples=[{"current": 10, "total": 100, "percentage": 10}]
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="事件时间戳 (ISO 8601 格式)",
        examples=["2026-02-28T10:30:00.123456"]
    )
    request_id: Optional[str] = Field(
        default=None,
        description="请求唯一标识，用于追踪和日志关联",
        examples=["req-12345-abcde"]
    )
    message: Optional[str] = Field(
        default=None,
        description="人类可读的消息描述",
        examples=["处理进度：10%"]
    )
    level: Optional[Literal["info", "success", "warning", "error", "debug"]] = Field(
        default="info",
        description="日志级别",
        examples=["info"]
    )
    code: Optional[int] = Field(
        default=None,
        description="业务错误码（仅在 error 类型时使用）",
        examples=[500]
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "progress",
                "data": {"current": 10, "total": 100, "percentage": 10},
                "timestamp": "2026-02-28T10:30:00.123456",
                "request_id": "req-12345-abcde",
                "message": "处理进度：10%",
                "level": "info"
            }
        }


class SseLogEvent(SseEvent):
    """日志类型的 SSE 事件"""
    type: Literal["log"] = "log"
    level: Literal["info", "success", "warning", "error", "debug"] = "info"


class SseProgressEvent(SseEvent):
    """进度类型的 SSE 事件"""
    type: Literal["progress"] = "progress"
    level: Literal["info"] = "info"


class SseCompleteEvent(SseEvent):
    """完成类型的 SSE 事件"""
    type: Literal["complete"] = "complete"
    level: Literal["info"] = "info"


class SseErrorEvent(SseEvent):
    """错误类型的 SSE 事件"""
    type: Literal["error"] = "error"
    level: Literal["error"] = "error"
    code: int = Field(..., description="错误码")


def create_sse_event(
    event_type: str,
    data: Any = None,
    message: str = "",
    level: Literal["info", "success", "warning", "error", "debug"] = "info",
    code: Optional[int] = None,
    request_id: Optional[str] = None,
) -> SseEvent:
    """
    创建统一的 SSE 事件
    
    Args:
        event_type: 事件类型 (log, progress, complete, error)
        data: 事件数据
        message: 消息描述
        level: 日志级别
        code: 错误码（仅 error 类型需要）
        request_id: 请求 ID
        
    Returns:
        SseEvent 实例
    """
    return SseEvent(
        type=event_type,  # type: ignore
        data=data,
        message=message,
        level=level,
        code=code,
        request_id=request_id,
    )
