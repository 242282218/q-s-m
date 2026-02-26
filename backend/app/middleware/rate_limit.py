"""
速率限制中间件
"""
import time
from collections import defaultdict
from typing import Dict, Tuple
from fastapi import Request, HTTPException, Response
from fastapi.responses import JSONResponse


class RateLimiter:
    """
    简单的内存速率限制器
    
    使用滑动窗口算法实现速率限制
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
            (是否允许, 限制信息)
        """
        now = time.time()
        minute_ago = now - 60
        hour_ago = now - 3600
        
        # 获取该 key 的所有请求时间戳
        timestamps = self.requests[key]
        
        # 清理过期的请求记录
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


rate_limiter = RateLimiter(requests_per_minute=60, requests_per_hour=1000)


async def rate_limit_middleware(request: Request, call_next):
    """
    速率限制中间件
    
    基于 IP 地址进行速率限制
    """
    # 获取客户端 IP
    client_ip = request.client.host if request.client else "unknown"
    
    # 检查是否允许
    allowed, info = rate_limiter.is_allowed(client_ip)
    
    # 添加速率限制响应头
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(info["limit"])
    response.headers["X-RateLimit-Window"] = info["window"]
    response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
    
    if not allowed:
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + info["retry_after"]))
        response.headers["Retry-After"] = str(int(info["retry_after"]))
        
        return JSONResponse(
            status_code=429,
            content={
                "code": 429,
                "message": "请求过于频繁，请稍后再试",
                "data": info
            }
        )
    
    return response
