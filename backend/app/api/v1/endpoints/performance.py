"""
性能监控端点
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db, get_query_stats, get_slow_query_stats
from app.quark.core.cache import get_cache
from app.middleware.rate_limit import rate_limiter

router = APIRouter()


@router.get("/stats")
async def get_performance_stats(db: Session = Depends(get_db)):
    """获取性能统计信息"""
    cache = get_cache()

    return {
        "database": get_query_stats(),
        "slow_queries": get_slow_query_stats(),
        "cache": await cache.get_stats() if cache.enabled else None,
        "rate_limit": {
            "active_keys": len(rate_limiter.requests),
            "requests_per_minute": rate_limiter.requests_per_minute,
            "requests_per_hour": rate_limiter.requests_per_hour,
        }
    }
