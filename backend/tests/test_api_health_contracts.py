from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement):
        return statement


class _FakeEngine:
    def connect(self):
        return _FakeConnection()


class _BrokenEngine:
    def connect(self):
        raise RuntimeError("db unavailable")


class _FakeCache:
    def __init__(self, stats):
        self._stats = stats

    async def get_stats(self):
        return self._stats


@pytest.mark.asyncio
async def test_health_endpoint_keeps_200_contract_for_degraded_status(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.main import app

    monkeypatch.setattr(app.state, "tmdb_client", None, raising=False)

    with patch("app.db.session.engine", _BrokenEngine()), patch(
        "app.quark.core.cache.get_cache",
        return_value=_FakeCache({"valid": 1, "total": 1}),
    ):
        response = await async_client.get("/api/v1/health")

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["status"] == "degraded"
    assert payload["data"]["checks"]["database"]["status"] == "error"


@pytest.mark.asyncio
async def test_liveness_endpoint_returns_lightweight_ok_payload(async_client: AsyncClient):
    response = await async_client.get("/api/v1/health/live")

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["message"] == "Service alive"
    assert payload["data"]["status"] == "ok"
    assert payload["data"]["checks"] == {
        "app": {"status": "ok", "message": "Process running"},
    }


@pytest.mark.asyncio
async def test_readiness_endpoint_returns_200_when_core_dependency_is_ready(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.main import app

    monkeypatch.setattr(app.state, "tmdb_client", object(), raising=False)

    with patch("app.db.session.engine", _FakeEngine()), patch(
        "app.quark.core.cache.get_cache",
        return_value=_FakeCache({"valid": 1, "total": 1}),
    ):
        response = await async_client.get("/api/v1/health/ready")

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["message"] == "Service ready"
    assert payload["data"]["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_endpoint_returns_503_when_database_is_unavailable(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.main import app

    monkeypatch.setattr(app.state, "tmdb_client", object(), raising=False)

    with patch("app.db.session.engine", _BrokenEngine()), patch(
        "app.quark.core.cache.get_cache",
        return_value=_FakeCache({"valid": 1, "total": 1}),
    ):
        response = await async_client.get("/api/v1/health/ready")

    payload = response.json()
    assert response.status_code == 503
    assert payload["code"] == 503
    assert payload["message"] == "Service not ready"
    assert payload["data"]["status"] == "degraded"
    assert payload["data"]["checks"]["database"]["status"] == "error"
