"""
速率限制中间件
"""
import logging
import time
from collections import defaultdict
from typing import Any, Dict, Optional, Set, Tuple
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    简单的内存速率限制器
    
    使用滑动窗口算法实现速率限制
    自动清理过期记录以防止内存泄漏
    """
    
    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        cleanup_interval_seconds: int = 300,
        inactive_seconds: int = 7200,
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.requests: Dict[str, list[float]] = defaultdict(list)
        self._cleanup_interval_seconds = cleanup_interval_seconds
        self._inactive_seconds = inactive_seconds
        self._last_cleanup_at = time.time()

    def _maybe_cleanup(self, now: float) -> None:
        if now - self._last_cleanup_at < self._cleanup_interval_seconds:
            return
        self.cleanup_inactive_keys(inactive_seconds=self._inactive_seconds, now=now)
        self._last_cleanup_at = now
    
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
        self._maybe_cleanup(now)
        
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
        
        return True, {
            "limit": self.requests_per_minute,
            "window": "minute",
            "remaining": self.requests_per_minute - recent_minute - 1,
            "retry_after": 0
        }
    
    def cleanup_inactive_keys(self, inactive_seconds: int = 7200, now: float | None = None):
        """
        清理长时间不活跃的 key，释放内存
        
        Args:
            inactive_seconds: 不活跃时间阈值（秒），默认 2 小时
        """
        now = time.time() if now is None else now
        cutoff = now - inactive_seconds
        keys_to_remove = []
        
        for key, timestamps in list(self.requests.items()):
            # 如果所有记录都已过期，标记删除
            if not timestamps or all(t < cutoff for t in timestamps):
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.requests[key]
        
        if keys_to_remove:
            logger.debug(f"Cleaned up {len(keys_to_remove)} inactive rate limit keys")


class RedisRateLimiter:
    """Redis-backed fixed-window limiter for cross-process consistency."""

    def __init__(
        self,
        redis_url: str,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        key_prefix: str = "qsm:rate_limit",
        redis_client: Any | None = None,
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.key_prefix = key_prefix
        if redis_client is not None:
            self._redis = redis_client
            return
        import redis.asyncio as redis

        self._redis = redis.from_url(redis_url, decode_responses=True)

    def _window_keys(self, key: str, now: int) -> tuple[str, str]:
        minute_bucket = now // 60
        hour_bucket = now // 3600
        minute_key = f"{self.key_prefix}:{key}:m:{minute_bucket}"
        hour_key = f"{self.key_prefix}:{key}:h:{hour_bucket}"
        return minute_key, hour_key

    @staticmethod
    def _ttl_or_fallback(ttl: int, fallback: int) -> int:
        return ttl if ttl > 0 else fallback

    async def is_allowed(self, key: str) -> Tuple[bool, dict]:
        now = int(time.time())
        minute_key, hour_key = self._window_keys(key, now)

        minute_count = int(await self._redis.incr(minute_key))
        if minute_count == 1:
            await self._redis.expire(minute_key, 60)

        hour_count = int(await self._redis.incr(hour_key))
        if hour_count == 1:
            await self._redis.expire(hour_key, 3600)

        minute_ttl = int(await self._redis.ttl(minute_key))
        hour_ttl = int(await self._redis.ttl(hour_key))

        if minute_count > self.requests_per_minute:
            return False, {
                "limit": self.requests_per_minute,
                "window": "minute",
                "remaining": 0,
                "retry_after": self._ttl_or_fallback(minute_ttl, 60),
            }

        if hour_count > self.requests_per_hour:
            return False, {
                "limit": self.requests_per_hour,
                "window": "hour",
                "remaining": 0,
                "retry_after": self._ttl_or_fallback(hour_ttl, 3600),
            }

        minute_remaining = max(0, self.requests_per_minute - minute_count)
        hour_remaining = max(0, self.requests_per_hour - hour_count)
        return True, {
            "limit": self.requests_per_minute,
            "window": "minute",
            "remaining": min(minute_remaining, hour_remaining),
            "retry_after": 0,
        }


# 生产环境标准限制：60 次/分钟，1000 次/小时
# 本地开发环境可适当放宽，但不应过高以避免资源耗尽
rate_limiter = RateLimiter(requests_per_minute=60, requests_per_hour=1000)


def _build_redis_rate_limiter() -> tuple[Optional[RedisRateLimiter], int]:
    settings = get_settings()
    failure_cooldown_seconds = max(0, settings.rate_limit_redis_failure_cooldown_seconds)
    if not settings.cache_enabled or settings.cache_type != "redis":
        return None, failure_cooldown_seconds
    try:
        limiter = RedisRateLimiter(
            redis_url=settings.redis_url,
            requests_per_minute=rate_limiter.requests_per_minute,
            requests_per_hour=rate_limiter.requests_per_hour,
        )
        return limiter, failure_cooldown_seconds
    except Exception as exc:
        logger.warning("Redis rate limiter disabled, fallback to in-memory limiter: %s", exc)
        return None, failure_cooldown_seconds


_redis_rate_limiter, _redis_rate_limiter_failure_cooldown_seconds = _build_redis_rate_limiter()
_redis_rate_limiter_retry_at = 0.0
_settings = get_settings()
_trusted_proxy_ips: Set[str] = set(_settings.trusted_proxy_ips)


def _extract_client_ip(request: Request) -> str:
    client_ip = request.client.host if request.client else "unknown"
    if not _settings.trust_proxy_headers:
        return client_ip
    if client_ip not in _trusted_proxy_ips:
        return client_ip

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        forwarded_ips = [ip.strip() for ip in forwarded_for.split(",") if ip.strip()]
        if forwarded_ips:
            return forwarded_ips[0]

    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()

    return client_ip


async def _is_allowed_with_fallback(key: str) -> Tuple[bool, dict]:
    global _redis_rate_limiter_retry_at

    if _redis_rate_limiter is None:
        return rate_limiter.is_allowed(key)

    now = time.time()
    if _redis_rate_limiter_retry_at > now:
        return rate_limiter.is_allowed(key)

    try:
        allowed, info = await _redis_rate_limiter.is_allowed(key)
        _redis_rate_limiter_retry_at = 0.0
        return allowed, info
    except Exception as exc:
        if _redis_rate_limiter_failure_cooldown_seconds > 0:
            _redis_rate_limiter_retry_at = now + _redis_rate_limiter_failure_cooldown_seconds
            logger.warning(
                "Redis rate limiter runtime error, fallback to in-memory limiter for %ss: %s",
                _redis_rate_limiter_failure_cooldown_seconds,
                exc,
            )
        else:
            logger.warning("Redis rate limiter runtime error, fallback to in-memory limiter: %s", exc)
        return rate_limiter.is_allowed(key)

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
    client_ip = _extract_client_ip(request)

    # 先检查是否允许 —— 不允许则直接返回 429，不执行下游请求
    allowed, info = await _is_allowed_with_fallback(client_ip)

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
