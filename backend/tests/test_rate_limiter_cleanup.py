from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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
    def __init__(self):
        self.call_count = 0

    async def is_allowed(self, _: str):
        self.call_count += 1
        raise RuntimeError("redis unavailable")


@pytest.mark.asyncio
async def test_rate_limiter_fallback_to_memory_when_redis_fails(monkeypatch):
    memory_limiter = RateLimiter(requests_per_minute=1, requests_per_hour=10)
    broken_limiter = BrokenRedisRateLimiter()
    monkeypatch.setattr(rate_limit_module, "rate_limiter", memory_limiter)
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter", broken_limiter)
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter_failure_cooldown_seconds", 0)
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter_retry_at", 0.0)

    first_allowed, _ = await rate_limit_module._is_allowed_with_fallback("fallback_ip")
    second_allowed, info = await rate_limit_module._is_allowed_with_fallback("fallback_ip")

    assert first_allowed is True
    assert second_allowed is False
    assert info["window"] == "minute"
    assert broken_limiter.call_count == 2


@pytest.mark.asyncio
async def test_rate_limiter_skips_redis_calls_during_failure_cooldown(monkeypatch):
    memory_limiter = RateLimiter(requests_per_minute=5, requests_per_hour=10)
    broken_limiter = BrokenRedisRateLimiter()
    monkeypatch.setattr(rate_limit_module, "rate_limiter", memory_limiter)
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter", broken_limiter)
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter_failure_cooldown_seconds", 30)
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter_retry_at", 0.0)

    first_allowed, _ = await rate_limit_module._is_allowed_with_fallback("cooldown_ip")
    second_allowed, _ = await rate_limit_module._is_allowed_with_fallback("cooldown_ip")

    assert first_allowed is True
    assert second_allowed is True
    assert broken_limiter.call_count == 1
    assert rate_limit_module._redis_rate_limiter_retry_at > 0.0


class RecoveringRedisRateLimiter:
    def __init__(self):
        self.call_count = 0

    async def is_allowed(self, _: str):
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("temporary redis error")
        return True, {
            "limit": 60,
            "window": "minute",
            "remaining": 59,
            "retry_after": 0,
        }


@pytest.mark.asyncio
async def test_rate_limiter_retries_redis_after_cooldown(monkeypatch):
    memory_limiter = RateLimiter(requests_per_minute=5, requests_per_hour=10)
    recovering_limiter = RecoveringRedisRateLimiter()
    monkeypatch.setattr(rate_limit_module, "rate_limiter", memory_limiter)
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter", recovering_limiter)
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter_failure_cooldown_seconds", 30)
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter_retry_at", 0.0)

    first_allowed, first_info = await rate_limit_module._is_allowed_with_fallback("recover_ip")
    second_allowed, second_info = await rate_limit_module._is_allowed_with_fallback("recover_ip")

    # Simulate cooldown elapsed and allow one retry on Redis limiter.
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter_retry_at", 0.0)
    third_allowed, third_info = await rate_limit_module._is_allowed_with_fallback("recover_ip")

    assert first_allowed is True
    assert first_info["window"] == "minute"
    assert second_allowed is True
    assert second_info["window"] == "minute"
    assert third_allowed is True
    assert third_info["remaining"] == 59
    assert recovering_limiter.call_count == 2
    assert rate_limit_module._redis_rate_limiter_retry_at == 0.0


def _create_probe_app() -> FastAPI:
    app = FastAPI()

    @app.get("/probe")
    async def probe():
        return {"ok": True}

    app.middleware("http")(rate_limit_module.rate_limit_middleware)
    return app


def test_rate_limit_uses_remote_ip_when_proxy_trust_disabled(monkeypatch):
    limiter = RateLimiter(requests_per_minute=10, requests_per_hour=20)
    captured: list[str] = []

    def fake_is_allowed(key: str):
        captured.append(key)
        return True, {"limit": 10, "window": "minute", "remaining": 9, "retry_after": 0}

    monkeypatch.setattr(rate_limit_module, "rate_limiter", limiter)
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter", None)
    monkeypatch.setattr(rate_limit_module._settings, "trust_proxy_headers", False)
    monkeypatch.setattr(limiter, "is_allowed", fake_is_allowed)

    with TestClient(_create_probe_app()) as client:
        response = client.get(
            "/probe",
            headers={"X-Forwarded-For": "198.51.100.24"},
        )

    assert response.status_code == 200
    assert captured == ["testclient"]


def test_rate_limit_uses_x_forwarded_for_when_proxy_trusted(monkeypatch):
    limiter = RateLimiter(requests_per_minute=10, requests_per_hour=20)
    captured: list[str] = []

    def fake_is_allowed(key: str):
        captured.append(key)
        return True, {"limit": 10, "window": "minute", "remaining": 9, "retry_after": 0}

    monkeypatch.setattr(rate_limit_module, "rate_limiter", limiter)
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter", None)
    monkeypatch.setattr(rate_limit_module._settings, "trust_proxy_headers", True)
    monkeypatch.setattr(rate_limit_module, "_trusted_proxy_ips", {"testclient"})
    monkeypatch.setattr(limiter, "is_allowed", fake_is_allowed)

    with TestClient(_create_probe_app()) as client:
        response = client.get(
            "/probe",
            headers={"X-Forwarded-For": "198.51.100.24, 203.0.113.8"},
        )

    assert response.status_code == 200
    assert captured == ["203.0.113.8"]


def test_rate_limit_ignores_spoofed_leftmost_xff_when_proxy_appends(monkeypatch):
    limiter = RateLimiter(requests_per_minute=10, requests_per_hour=20)
    captured: list[str] = []

    def fake_is_allowed(key: str):
        captured.append(key)
        return True, {"limit": 10, "window": "minute", "remaining": 9, "retry_after": 0}

    monkeypatch.setattr(rate_limit_module, "rate_limiter", limiter)
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter", None)
    monkeypatch.setattr(rate_limit_module._settings, "trust_proxy_headers", True)
    monkeypatch.setattr(rate_limit_module, "_trusted_proxy_ips", {"testclient"})
    monkeypatch.setattr(limiter, "is_allowed", fake_is_allowed)

    with TestClient(_create_probe_app()) as client:
        response = client.get(
            "/probe",
            headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.8, testclient"},
        )

    assert response.status_code == 200
    assert captured == ["203.0.113.8"]


def test_rate_limit_parses_forwarded_for_with_ports_and_invalid_values(monkeypatch):
    limiter = RateLimiter(requests_per_minute=10, requests_per_hour=20)
    captured: list[str] = []

    def fake_is_allowed(key: str):
        captured.append(key)
        return True, {"limit": 10, "window": "minute", "remaining": 9, "retry_after": 0}

    monkeypatch.setattr(rate_limit_module, "rate_limiter", limiter)
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter", None)
    monkeypatch.setattr(rate_limit_module._settings, "trust_proxy_headers", True)
    monkeypatch.setattr(rate_limit_module, "_trusted_proxy_ips", {"testclient", "127.0.0.1"})
    monkeypatch.setattr(limiter, "is_allowed", fake_is_allowed)

    app = _create_probe_app()
    with TestClient(app) as client:
        response = client.get(
            "/probe",
            headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.10:4321, bad-ip, 127.0.0.1"},
        )

    assert response.status_code == 200
    assert captured == ["203.0.113.10"]


def test_rate_limit_falls_back_to_remote_ip_when_proxy_headers_invalid(monkeypatch):
    limiter = RateLimiter(requests_per_minute=10, requests_per_hour=20)
    captured: list[str] = []

    def fake_is_allowed(key: str):
        captured.append(key)
        return True, {"limit": 10, "window": "minute", "remaining": 9, "retry_after": 0}

    monkeypatch.setattr(rate_limit_module, "rate_limiter", limiter)
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter", None)
    monkeypatch.setattr(rate_limit_module._settings, "trust_proxy_headers", True)
    monkeypatch.setattr(rate_limit_module, "_trusted_proxy_ips", {"testclient"})
    monkeypatch.setattr(limiter, "is_allowed", fake_is_allowed)

    with TestClient(_create_probe_app()) as client:
        response = client.get(
            "/probe",
            headers={"X-Forwarded-For": "not-an-ip, ???", "X-Real-IP": "still-not-ip"},
        )

    assert response.status_code == 200
    assert captured == ["testclient"]


def test_rate_limit_falls_back_to_x_real_ip_when_forwarded_for_missing(monkeypatch):
    limiter = RateLimiter(requests_per_minute=10, requests_per_hour=20)
    captured: list[str] = []

    def fake_is_allowed(key: str):
        captured.append(key)
        return True, {"limit": 10, "window": "minute", "remaining": 9, "retry_after": 0}

    monkeypatch.setattr(rate_limit_module, "rate_limiter", limiter)
    monkeypatch.setattr(rate_limit_module, "_redis_rate_limiter", None)
    monkeypatch.setattr(rate_limit_module._settings, "trust_proxy_headers", True)
    monkeypatch.setattr(rate_limit_module, "_trusted_proxy_ips", {"testclient"})
    monkeypatch.setattr(limiter, "is_allowed", fake_is_allowed)

    with TestClient(_create_probe_app()) as client:
        response = client.get(
            "/probe",
            headers={"X-Real-IP": "198.51.100.25"},
        )

    assert response.status_code == 200
    assert captured == ["198.51.100.25"]
