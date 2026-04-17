from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.core.error_codes import ErrorCode
from app.quark.core.media_fetcher import MediaFetcher
from app.quark.schemas.search import SearchResponse
from app.quark.services.search_service import SearchService


@pytest.mark.asyncio
async def test_search_service_close_closes_internal_clients():
    service = SearchService()
    fake_quark_client = SimpleNamespace(close=AsyncMock())
    fake_tmdb_client = SimpleNamespace(close=AsyncMock())
    fetcher = MediaFetcher()
    fetcher._internal_client = fake_tmdb_client

    service._internal_quark_client = fake_quark_client
    service._internal_media_fetcher = fetcher

    await service.close()

    fake_quark_client.close.assert_awaited_once()
    fake_tmdb_client.close.assert_awaited_once()
    assert fetcher._internal_client is None


@pytest.mark.asyncio
async def test_quark_search_by_tmdb_id_reuses_app_tmdb_client_and_closes_service(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.main import app

    sentinel_tmdb = object()
    sentinel_quark = object()
    monkeypatch.setattr(app.state, "tmdb_client", sentinel_tmdb, raising=False)
    monkeypatch.setattr(app.state, "quark_client", sentinel_quark, raising=False)
    monkeypatch.setattr(
        "app.quark.api.routes.search.get_settings",
        lambda: SimpleNamespace(tmdb_api_key="tmdb-key"),
    )

    instances: list[FakeSearchService] = []

    class FakeSearchService:
        def __init__(self, tmdb_client=None, quark_client=None):
            self.tmdb_client = tmdb_client
            self.quark_client = quark_client
            self.closed = False
            instances.append(self)

        async def search_by_tmdb_id(self, tmdb_id: int, max_results: int, media_type: str):
            assert tmdb_id == 7
            assert max_results == 5
            assert media_type == "movie"
            return SearchResponse(success=True, message="OK", media=None, resources=[], total=0)

        async def close(self):
            self.closed = True

    monkeypatch.setattr("app.quark.api.routes.search.SearchService", FakeSearchService)

    response = await async_client.get(
        "/api/v1/quark/searches/tmdb/7",
        params={"media_type": "movie", "max_results": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert len(instances) == 1
    assert instances[0].tmdb_client is sentinel_tmdb
    assert instances[0].quark_client is sentinel_quark
    assert instances[0].closed is True


@pytest.mark.asyncio
async def test_quark_search_by_title_closes_service_on_failure(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.main import app

    sentinel_tmdb = object()
    monkeypatch.setattr(app.state, "tmdb_client", sentinel_tmdb, raising=False)
    monkeypatch.setattr(app.state, "quark_client", object(), raising=False)

    instances: list[FakeSearchService] = []

    class FakeSearchService:
        def __init__(self, tmdb_client=None, quark_client=None):
            self.tmdb_client = tmdb_client
            self.quark_client = quark_client
            self.closed = False
            instances.append(self)

        async def search_by_title(self, title: str, year: int | None, max_results: int):
            assert title == "Alien"
            assert year == 1979
            assert max_results == 3
            return SearchResponse(success=False, message="搜索失败", media=None, resources=[], total=0)

        async def close(self):
            self.closed = True

    monkeypatch.setattr("app.quark.api.routes.search.SearchService", FakeSearchService)

    response = await async_client.get(
        "/api/v1/quark/searches/by-title",
        params={"title": "Alien", "year": 1979, "max_results": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == ErrorCode.SEARCH_FAILED
    assert payload["error"]["field"] == "title"
    assert len(instances) == 1
    assert instances[0].tmdb_client is sentinel_tmdb
    assert instances[0].closed is True
