"""
公共事件工具
用于构建进度事件 payload
"""
from typing import Any, Dict


def build_event_payload(
    *,
    event_type: str,
    current: int = 0,
    total: int = 0,
    message: str = "",
    level: str = "info",
    **extra: Any,
) -> Dict[str, Any]:
    """
    构建进度事件 payload。

    Args:
        event_type: 事件类型 (log/progress/complete/error)
        current: 当前进度
        total: 总数
        message: 消息内容
        level: 日志级别 (info/warning/error)
        **extra: 额外字段

    Returns:
        事件 payload 字典
    """
    percentage = 100 if total <= 0 else int((current / total) * 100)
    payload: Dict[str, Any] = {
        "type": event_type,
        "current": current,
        "total": total,
        "percentage": percentage,
        "message": message,
        "level": level,
    }
    payload.update(extra)
    return payload
