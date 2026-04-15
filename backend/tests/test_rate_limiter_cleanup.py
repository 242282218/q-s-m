from unittest.mock import patch

import pytest

from app.middleware import rate_limit as rate_limit_module
from app.middleware.rate_limit import RateLimiter, RedisRateLimiter


class FakeRedisClient:
    def __init__(self):
        self._counter: dict[str, int] = {}
        self._ttl: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self._counter[key] = self._counter.get(key, 0) + 1
        return self._counter[key]

    async def expire(self, key: str, seconds: int) -> bool:
        self._ttl[key] = seconds
        return True

    async def ttl(self, key: str) -> int:
        return self._ttl.get(key, -1)


def test_rate_limiter_auto_cleanup_removes_inactive_keys():
    limiter = RateLimiter(
        requests_per_minute=60,
        requests_per_hour=1000,
        cleanup_interval_seconds=1,
        inactive_seconds=10,
    )
    limiter.requests["stale_ip"].append(80.0)
    limiter.requests["active_ip"].append(95.0)
    limiter._last_cleanup_at = 90.0

    with patch("app.middleware.rate_limit.time.time", return_value=101.0):
        allowed, _ = limiter.is_allowed("active_ip")

    assert allowed is True
    assert "stale_ip" not in limiter.requests
    assert "active_ip" in limiter.requests


def test_rate_limiter_auto_cleanup_respects_interval():
    limiter = RateLimiter(
        requests_per_minute=60,
        requests_per_hour=1000,
        cleanup_interval_seconds=60,
        inactive_seconds=10,
    )
    limiter.requests["stale_ip"].append(0.0)
    limiter._last_cleanup_at = 100.0

    with patch("app.middleware.rate_limit.time.time", return_value=120.0):
        allowed, _ = limiter.is_allowed("fresh_ip")

    assert allowed is True
    assert "stale_ip" in limiter.requests


@pytest.mark.asyncio
async def test_redis_rate_limiter_enforces_minute_limit():
    limiter = RedisRateLimiter(
        redis_url="redis://unused",
        requests_per_minute=2,
        requests_per_hour=10,
        redis_client=FakeRedisClient(),
    )

    first_allowed, _ = await limiter.is_allowed("ip_1")
    second_allowed, _ = await limiter.is_allowed("ip_1")
    third_allowed, info = await limiter.is_allowed("ip_1")

    assert first_allowed is True
    assert second_allowed is True
    assert third_allowed is False
    assert info["window"] == "minute"
    assert info["retry_after"] == 60


@pytest.mark.asyncio
async def test_redis_rate_limiter_enforces_hour_limit():
    limiter = RedisRateLimiter(
        redis_url="redis://unused",
        requests_per_minute=10,
        requests_per_hour=2,
        redis_client=FakeRedisClient(),
    )

    first_allowed, _ = await limiter.is_allowed("ip_2")
    second_allowed, _ = await limiter.is_allowed("ip_2")
    third_allowed, info = await limiter.is_allowed("ip_2")

    assert first_allowed is True
    assert second_allowed is True
    assert third_allowed is False
    assert info["window"] == "hour"
    assert info["retry_after"] == 3600


class BrokenRedisRateLimiter:
    async def is_allowed(self, _: str):
        raise RuntimeError("redis unavailable")


@pytest.mark.asyncio
async def test_rate_limiter_fallback_to_memory_when_redis_fails(monkeypatch):
    memory_limiter = RateLimiter(requests_per_minute=1, requests_per_hour=10)
    monkeypatch.setattr(rate_limit_module, "rate_limiter", memory_limiter)
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter", BrokenRedisRateLimiter())

    first_allowed, _ = await rate_limit_module._is_allowed_with_fallback("fallback_ip")
    second_allowed, info = await rate_limit_module._is_allowed_with_fallback("fallback_ip")

    assert first_allowed is True
    assert second_allowed is False
    assert info["window"] == "minute"
