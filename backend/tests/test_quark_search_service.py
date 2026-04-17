from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.quark.services.search_service import SearchService


class FakeQuarkClient:
    def __init__(self):
        self.calls: list[tuple[str, int]] = []

    async def search_resources(self, keyword: str, page_size: int):
        self.calls.append((keyword, page_size))
        return []


@pytest.mark.asyncio
async def test_search_direct_falls_back_to_runtime_page_size(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "app.quark.services.search_service.get_settings",
        lambda: SimpleNamespace(quark_search_max_results=7),
    )
    client = FakeQuarkClient()
    service = SearchService(quark_client=client)

    response = await service._search_direct("Alien", 0)

    assert response.success is True
    assert client.calls == [("Alien", 7)]


@pytest.mark.asyncio
async def test_search_common_falls_back_to_runtime_page_size(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "app.quark.services.search_service.get_settings",
        lambda: SimpleNamespace(quark_search_max_results=9),
    )
    client = FakeQuarkClient()
    service = SearchService(quark_client=client)
    media_info = SimpleNamespace(
        tmdb_id=1,
        title="Alien",
        original_title="Alien",
        year=1979,
        rating=8.5,
        overview="",
        poster_path="",
        backdrop_path="",
        media_type="movie",
    )

    response = await service._search_common(media_info, "Alien", 0)

    assert response.success is True
    assert response.media is not None
    assert client.calls == [("Alien", 9)]
