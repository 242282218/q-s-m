from collections import deque

import pytest

from app.main import app, build_request_stats_store, reset_metrics


def test_build_request_stats_store_uses_bounded_deque():
    stats = build_request_stats_store()

    assert stats["total_requests"] == 0
    assert stats["total_time"] == 0.0
    assert isinstance(stats["slow_requests"], deque)
    assert stats["slow_requests"].maxlen == 100


@pytest.mark.asyncio
async def test_reset_metrics_reinitializes_request_stats_shape():
    app.state.request_stats = {
        "total_requests": 9,
        "total_time": 12.3,
        "slow_requests": [{"path": "/api/v1/foo"}],
    }

    response = await reset_metrics()
    stats = app.state.request_stats

    assert response.data.reset is True
    assert stats["total_requests"] == 0
    assert stats["total_time"] == 0.0
    assert isinstance(stats["slow_requests"], deque)
    assert stats["slow_requests"].maxlen == 100
    assert len(stats["slow_requests"]) == 0
