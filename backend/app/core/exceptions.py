"""
统一异常处理体系
"""
from typing import Any, Optional
from app.core.error_codes import ErrorCode, ErrorContext


class QSMException(Exception):
    """QSM 基础异常"""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        context: Optional[ErrorContext] = None,
        details: Optional[dict] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.context = context
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        result = {
            "message": self.message,
            "code": int(self.code),
            "category": self.code.category
        }
        if self.context:
            result["context"] = self.context.to_dict()
        if self.details:
            result["details"] = self.details
        return result


class TransferException(QSMException):
    """转存异常"""

    def __init__(self, message: str, code: ErrorCode = ErrorCode.TRANSFER_FAILED, **kwargs):
        super().__init__(message, code, **kwargs)


class RenameException(QSMException):
    """重命名异常"""

    def __init__(self, message: str, code: ErrorCode = ErrorCode.RENAME_FAILED, **kwargs):
        super().__init__(message, code, **kwargs)


class CleanupException(QSMException):
    """清理异常"""

    def __init__(self, message: str, code: ErrorCode = ErrorCode.OPERATION_FAILED, **kwargs):
        super().__init__(message, code, **kwargs)


class QuarkException(QSMException):
    """夸克服务异常"""

    def __init__(self, message: str, code: ErrorCode = ErrorCode.QUARK_SERVICE_ERROR, **kwargs):
        super().__init__(message, code, **kwargs)


class LockException(QSMException):
    """分布式锁异常"""

    def __init__(self, message: str, code: ErrorCode = ErrorCode.RESOURCE_CONFLICT, **kwargs):
        super().__init__(message, code, **kwargs)
