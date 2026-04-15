from unittest.mock import patch

from app.middleware.rate_limit import RateLimiter


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
