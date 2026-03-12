"""
速率限制中间件
"""
import time
import logging
from collections import defaultdict
from typing import Dict, Tuple
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    简单的内存速率限制器
    
    使用滑动窗口算法实现速率限制
    自动清理过期记录以防止内存泄漏
    """
    
    def __init__(self, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.requests: Dict[str, list[float]] = defaultdict(list)
    
    def is_allowed(self, key: str) -> Tuple[bool, dict]:
        """
        检查请求是否允许
        
        Args:
            key: 唯一标识（如 IP 地址）
            
        Returns:
            (是否允许，限制信息)
        """
        now = time.time()
        minute_ago = now - 60
        hour_ago = now - 3600
        
        # 获取该 key 的所有请求时间戳
        timestamps = self.requests[key]
        
        # 清理过期的请求记录（清理窗口外的记录，防止内存泄漏）
        # 只保留最近 1 小时内的请求记录
        timestamps[:] = [t for t in timestamps if t > hour_ago]
        
        # 统计最近一分钟和一小时的请求数
        recent_minute = sum(1 for t in timestamps if t > minute_ago)
        recent_hour = len(timestamps)
        
        # 检查是否超过限制
        if recent_minute >= self.requests_per_minute:
            return False, {
                "limit": self.requests_per_minute,
                "window": "minute",
                "remaining": 0,
                "retry_after": 60 - (now - min(timestamps[-self.requests_per_minute:]))
            }
        
        if recent_hour >= self.requests_per_hour:
            return False, {
                "limit": self.requests_per_hour,
                "window": "hour",
                "remaining": 0,
                "retry_after": 3600 - (now - timestamps[0])
            }
        
        # 记录当前请求
        timestamps.append(now)
        
        # 如果该 key 已长时间无活动，清理其记录以释放内存
        if not timestamps:
            del self.requests[key]
        
        return True, {
            "limit": self.requests_per_minute,
            "window": "minute",
            "remaining": self.requests_per_minute - recent_minute - 1,
            "retry_after": 0
        }
    
    def cleanup_inactive_keys(self, inactive_seconds: int = 7200):
        """
        清理长时间不活跃的 key，释放内存
        
        Args:
            inactive_seconds: 不活跃时间阈值（秒），默认 2 小时
        """
        now = time.time()
        cutoff = now - inactive_seconds
        keys_to_remove = []
        
        for key, timestamps in self.requests.items():
            # 如果所有记录都已过期，标记删除
            if all(t < cutoff for t in timestamps):
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.requests[key]
        
        if keys_to_remove:
            logger.debug(f"Cleaned up {len(keys_to_remove)} inactive rate limit keys")


# 生产环境标准限制：60 次/分钟，1000 次/小时
# 本地开发环境可适当放宽，但不应过高以避免资源耗尽
rate_limiter = RateLimiter(requests_per_minute=60, requests_per_hour=1000)

# 不参与限流的路径前缀（静态资源、HMR、健康检查等）
_RATE_LIMIT_SKIP_PREFIXES = (
    "/assets",
    "/static",
    "/@vite",
    "/@fs",
    "/__vite",
    "/node_modules",
    "/src",          # Vite dev HMR
    "/favicon.ico",
    "/api/v1/health",
)


async def rate_limit_middleware(request: Request, call_next):
    """
    速率限制中间件

    基于 IP 地址进行速率限制，仅对 API 请求生效。
    """
    path = request.url.path

    # 跳过静态资源和 HMR 等非业务请求
    if any(path.startswith(prefix) for prefix in _RATE_LIMIT_SKIP_PREFIXES):
        return await call_next(request)

    # 获取客户端 IP
    client_ip = request.client.host if request.client else "unknown"

    # 先检查是否允许 —— 不允许则直接返回 429，不执行下游请求
    allowed, info = rate_limiter.is_allowed(client_ip)

    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "code": 429,
                "message": "请求过于频繁，请稍后再试",
                "data": info,
            },
            headers={
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Window": info["window"],
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time() + info["retry_after"])),
                "Retry-After": str(int(info["retry_after"])),
            },
        )

    # 请求允许 —— 执行下游并附加限流响应头
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(info["limit"])
    response.headers["X-RateLimit-Window"] = info["window"]
    response.headers["X-RateLimit-Remaining"] = str(info["remaining"])

    return response
