"""
统一错误码体系

错误码分类：
- 1xx: 业务逻辑错误
- 2xx: 验证错误
- 3xx: 第三方服务错误
- 4xx: 系统错误
"""
from enum import Enum
from typing import Any


class ErrorCode(int, Enum):
    """
    统一错误码枚举
    
    使用方式：
    - 返回错误时使用 ErrorCode 枚举值
    - 错误码对应的描述信息通过 message 属性获取
    """
    
    # ============ 1xx: 业务逻辑错误 ============
    # 通用业务错误 (100-199)
    BUSINESS_ERROR = 100
    RESOURCE_NOT_FOUND = 104  # 资源不存在
    RESOURCE_ALREADY_EXISTS = 109  # 资源已存在
    RESOURCE_CONFLICT = 110  # 资源冲突
    OPERATION_NOT_ALLOWED = 103  # 操作不允许
    OPERATION_FAILED = 105  # 操作失败
    
    # 收藏相关 (120-129)
    COLLECTION_NOT_FOUND = 120
    COLLECTION_ALREADY_EXISTS = 121
    COLLECTION_LINK_INVALID = 122  # 分享链接无效
    COLLECTION_VERIFY_FAILED = 123  # 收藏验证失败
    
    # 转存相关 (130-139)
    TRANSFER_FAILED = 130
    TRANSFER_TIMEOUT = 131
    TRANSFER_LINK_EXPIRED = 132  # 分享链接已过期
    TRANSFER_DIR_NOT_FOUND = 133  # 目标目录不存在
    TRANSFER_NO_FILES = 134  # 没有可转存的文件
    
    # 重命名相关 (140-149)
    RENAME_FAILED = 140
    RENAME_NOT_FOUND = 141  # 重命名资源不存在
    RENAME_CONFLICT = 142  # 重命名冲突
    
    # 搜索相关 (150-159)
    SEARCH_FAILED = 150
    SEARCH_NO_RESULTS = 154  # 搜索无结果
    
    # TMDB 相关 (160-169)
    TMDB_NOT_FOUND = 164  # TMDB 资源不存在
    TMDB_API_ERROR = 165  # TMDB API 错误
    
    # ============ 2xx: 验证错误 ============
    # 参数验证 (200-209)
    VALIDATION_ERROR = 200
    INVALID_PARAM = 201  # 无效参数
    MISSING_PARAM = 202  # 缺少必需参数
    INVALID_FORMAT = 203  # 参数格式错误
    INVALID_RANGE = 204  # 参数范围错误
    
    # 认证授权 (210-219)
    AUTHENTICATION_REQUIRED = 210  # 需要认证
    AUTHENTICATION_FAILED = 211  # 认证失败
    PERMISSION_DENIED = 213  # 权限不足
    TOKEN_EXPIRED = 214  # Token 过期
    TOKEN_INVALID = 215  # Token 无效
    
    # 请求验证 (220-229)
    REQUEST_TOO_LARGE = 220  # 请求体过大
    RATE_LIMIT_EXCEEDED = 229  # 请求频率超限
    
    # ============ 3xx: 第三方服务错误 ============
    # 夸克服务 (300-309)
    QUARK_SERVICE_ERROR = 300
    QUARK_API_ERROR = 301  # 夸克 API 调用失败
    QUARK_AUTH_FAILED = 302  # 夸克认证失败
    QUARK_COOKIE_INVALID = 303  # 夸克 Cookie 无效
    QUARK_SPACE_INSUFFICIENT = 304  # 夸克空间不足
    QUARK_LINK_EXPIRED = 305  # 夸克链接过期
    
    # 外部服务 (310-319)
    EXTERNAL_SERVICE_ERROR = 310
    EXTERNAL_API_TIMEOUT = 311  # 外部 API 超时
    EXTERNAL_API_UNAVAILABLE = 312  # 外部服务不可用
    
    # ============ 4xx: 系统错误 ============
    # 系统错误 (400-409)
    INTERNAL_ERROR = 400
    DATABASE_ERROR = 401  # 数据库错误
    CACHE_ERROR = 402  # 缓存错误
    FILE_SYSTEM_ERROR = 403  # 文件系统错误
    NETWORK_ERROR = 404  # 网络错误
    
    # 服务不可用 (410-419)
    SERVICE_UNAVAILABLE = 410
    SERVICE_MAINTENANCE = 411  # 服务维护中
    DEPENDENCY_UNAVAILABLE = 412  # 依赖服务不可用
    
    # 运行时错误 (420-429)
    RUNTIME_ERROR = 420
    TIMEOUT_ERROR = 421  # 超时错误
    MEMORY_ERROR = 422  # 内存错误
    CONFIG_ERROR = 423  # 配置错误
    
    @property
    def message(self) -> str:
        """获取错误码的默认描述信息"""
        messages = {
            # 1xx: 业务逻辑错误
            ErrorCode.BUSINESS_ERROR: "业务错误",
            ErrorCode.RESOURCE_NOT_FOUND: "资源不存在",
            ErrorCode.RESOURCE_ALREADY_EXISTS: "资源已存在",
            ErrorCode.RESOURCE_CONFLICT: "资源冲突",
            ErrorCode.OPERATION_NOT_ALLOWED: "操作不允许",
            ErrorCode.OPERATION_FAILED: "操作失败",
            
            ErrorCode.COLLECTION_NOT_FOUND: "收藏不存在",
            ErrorCode.COLLECTION_ALREADY_EXISTS: "收藏已存在",
            ErrorCode.COLLECTION_LINK_INVALID: "分享链接无效",
            ErrorCode.COLLECTION_VERIFY_FAILED: "收藏验证失败",
            
            ErrorCode.TRANSFER_FAILED: "转存失败",
            ErrorCode.TRANSFER_TIMEOUT: "转存超时",
            ErrorCode.TRANSFER_LINK_EXPIRED: "分享链接已过期",
            ErrorCode.TRANSFER_DIR_NOT_FOUND: "目标目录不存在",
            ErrorCode.TRANSFER_NO_FILES: "没有可转存的文件",
            
            ErrorCode.RENAME_FAILED: "重命名失败",
            ErrorCode.RENAME_NOT_FOUND: "重命名资源不存在",
            ErrorCode.RENAME_CONFLICT: "重命名冲突",
            
            ErrorCode.SEARCH_FAILED: "搜索失败",
            ErrorCode.SEARCH_NO_RESULTS: "搜索无结果",
            
            ErrorCode.TMDB_NOT_FOUND: "TMDB 资源不存在",
            ErrorCode.TMDB_API_ERROR: "TMDB API 错误",
            
            # 2xx: 验证错误
            ErrorCode.VALIDATION_ERROR: "验证错误",
            ErrorCode.INVALID_PARAM: "无效参数",
            ErrorCode.MISSING_PARAM: "缺少必需参数",
            ErrorCode.INVALID_FORMAT: "参数格式错误",
            ErrorCode.INVALID_RANGE: "参数范围错误",
            
            ErrorCode.AUTHENTICATION_REQUIRED: "需要认证",
            ErrorCode.AUTHENTICATION_FAILED: "认证失败",
            ErrorCode.PERMISSION_DENIED: "权限不足",
            ErrorCode.TOKEN_EXPIRED: "Token 过期",
            ErrorCode.TOKEN_INVALID: "Token 无效",
            
            ErrorCode.REQUEST_TOO_LARGE: "请求体过大",
            ErrorCode.RATE_LIMIT_EXCEEDED: "请求频率超限",
            
            # 3xx: 第三方服务错误
            ErrorCode.QUARK_SERVICE_ERROR: "夸克服务错误",
            ErrorCode.QUARK_API_ERROR: "夸克 API 调用失败",
            ErrorCode.QUARK_AUTH_FAILED: "夸克认证失败",
            ErrorCode.QUARK_COOKIE_INVALID: "夸克 Cookie 无效",
            ErrorCode.QUARK_SPACE_INSUFFICIENT: "夸克空间不足",
            ErrorCode.QUARK_LINK_EXPIRED: "夸克链接过期",
            
            ErrorCode.EXTERNAL_SERVICE_ERROR: "外部服务错误",
            ErrorCode.EXTERNAL_API_TIMEOUT: "外部 API 超时",
            ErrorCode.EXTERNAL_API_UNAVAILABLE: "外部服务不可用",
            
            # 4xx: 系统错误
            ErrorCode.INTERNAL_ERROR: "内部错误",
            ErrorCode.DATABASE_ERROR: "数据库错误",
            ErrorCode.CACHE_ERROR: "缓存错误",
            ErrorCode.FILE_SYSTEM_ERROR: "文件系统错误",
            ErrorCode.NETWORK_ERROR: "网络错误",
            
            ErrorCode.SERVICE_UNAVAILABLE: "服务不可用",
            ErrorCode.SERVICE_MAINTENANCE: "服务维护中",
            ErrorCode.DEPENDENCY_UNAVAILABLE: "依赖服务不可用",
            
            ErrorCode.RUNTIME_ERROR: "运行时错误",
            ErrorCode.TIMEOUT_ERROR: "超时错误",
            ErrorCode.MEMORY_ERROR: "内存错误",
            ErrorCode.CONFIG_ERROR: "配置错误",
        }
        return messages.get(self, "未知错误")
    
    @property
    def category(self) -> str:
        """获取错误码分类"""
        if 100 <= self < 200:
            return "BUSINESS"
        elif 200 <= self < 300:
            return "VALIDATION"
        elif 300 <= self < 400:
            return "EXTERNAL"
        elif 400 <= self < 500:
            return "SYSTEM"
        return "UNKNOWN"


class ErrorContext:
    """
    错误上下文信息
    
    用于提供更详细的错误定位和调试信息
    """
    def __init__(
        self,
        field: str | None = None,
        value: Any = None,
        reason: str | None = None,
        extra: dict | None = None,
    ):
        self.field = field
        self.value = value
        self.reason = reason
        self.extra = extra or {}
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        result = {}
        if self.field:
            result["field"] = self.field
        if self.value is not None:
            result["value"] = self.value
        if self.reason:
            result["reason"] = self.reason
        if self.extra:
            result["extra"] = self.extra
        return result
