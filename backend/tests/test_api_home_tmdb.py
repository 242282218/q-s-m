from __future__ import annotations

from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.api.endpoints.home import SECTION_META


class FakeTmdbClient:
    def __init__(
        self,
        *,
        search_results: list[dict[str, Any]] | None = None,
        detail_payloads: dict[tuple[str, int, str | None], dict[str, Any]] | None = None,
    ) -> None:
        self._search_results = search_results or []
        self._detail_payloads = detail_payloads or {}
        self.search_queries: list[str] = []
        self.detail_calls: list[tuple[str, int, str | None]] = []

    async def search_multi(self, query: str) -> list[dict[str, Any]]:
        self.search_queries.append(query)
        return deepcopy(self._search_results)

    async def details(
        self,
        media_type: str,
        item_id: int,
        language_override: str | None = None,
    ) -> dict[str, Any]:
        call = (media_type, item_id, language_override)
        self.detail_calls.append(call)
        return deepcopy(self._detail_payloads[call])

    def image_url(self, path: str | None, size: str = "w500") -> str | None:
        if not path:
            return None
        return f"https://image.tmdb.org/t/p/{size}{path}"


@pytest.fixture
def install_tmdb_client(monkeypatch: pytest.MonkeyPatch):
    from app.main import app

    def _install(client: FakeTmdbClient) -> None:
        monkeypatch.setattr(app.state, "tmdb_client", client, raising=False)

    return _install


@pytest.mark.asyncio
async def test_get_home_feed_returns_normalized_sections_and_hero_items(
    async_client: AsyncClient,
    install_tmdb_client,
):
    fake_client = FakeTmdbClient()
    install_tmdb_client(fake_client)
    sections = {
        "anime_latest": [],
        "tv_latest": [],
        "top_rated": [],
        "tv_popular": [
            {
                "id": 101,
                "media_type": "tv",
                "name": "三体",
                "overview": "科幻剧集",
                "genre_ids": [878],
                "poster_path": "/poster-tv.jpg",
                "backdrop_path": "/backdrop-tv.jpg",
                "vote_average": 8.5,
                "first_air_date": "2023-01-15",
            },
            {
                "media_type": "tv",
                "name": "invalid-without-id",
            },
        ],
        "anime_popular": [],
    }
    hero_items = [
        {
            "id": 101,
            "media_type": "tv",
            "title": "三体",
            "year": 2023,
            "genres": ["科幻"],
            "runtime": 45,
            "vote": 8.5,
            "tagline": "文明的边界",
            "overview": "科幻剧集",
            "poster_url": "https://image.tmdb.org/t/p/w500/poster-tv.jpg",
            "backdrop_url": "https://image.tmdb.org/t/p/w1280/backdrop-tv.jpg",
        }
    ]

    with (
        patch(
            "app.api.endpoints.home.gather_sections",
            new=AsyncMock(return_value=sections),
        ),
        patch(
            "app.api.endpoints.home._get_hero_items",
            new=AsyncMock(return_value=hero_items),
        ),
    ):
        response = await async_client.get("/api/v1/home")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert [item["key"] for item in payload["data"]["section_order"]] == [
        meta.key for meta in SECTION_META
    ]
    assert len(payload["data"]["sections"]["tv_popular"]) == 1
    assert payload["data"]["sections"]["tv_popular"][0] == {
        "id": 101,
        "media_type": "tv",
        "title": "三体",
        "subtitle": "2023 · 评分 8.5",
        "overview": "科幻剧集",
        "genres": [878],
        "tone": "scifi",
        "poster_url": "https://image.tmdb.org/t/p/w500/poster-tv.jpg",
        "backdrop_url": "https://image.tmdb.org/t/p/w780/backdrop-tv.jpg",
    }
    assert payload["data"]["hero_items"] == hero_items


@pytest.mark.asyncio
async def test_search_media_endpoint_trims_query_and_filters_non_media_results(
    async_client: AsyncClient,
    install_tmdb_client,
):
    fake_client = FakeTmdbClient(
        search_results=[
            {
                "id": 129,
                "media_type": "movie",
                "title": "千与千寻",
                "overview": "奇幻冒险",
                "genre_ids": [16, 14],
                "poster_path": "/movie.jpg",
                "backdrop_path": "/movie-backdrop.jpg",
                "vote_average": 8.8,
                "release_date": "2001-07-20",
            },
            {
                "id": 204,
                "media_type": "person",
                "name": "宫崎骏",
            },
            {
                "id": 205,
                "media_type": "tv",
                "name": "攻壳机动队",
                "overview": "赛博朋克",
                "genre_ids": [16, 878],
                "poster_path": "/tv.jpg",
                "backdrop_path": "/tv-backdrop.jpg",
                "vote_average": 8.1,
                "first_air_date": "2002-10-01",
            },
        ]
    )
    install_tmdb_client(fake_client)

    response = await async_client.get("/api/v1/tmdb/search", params={"q": "  动画  "})

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["query"] == "动画"
    assert fake_client.search_queries == ["动画"]
    assert [item["id"] for item in payload["data"]["posters"]] == [129, 205]
    assert [item["media_type"] for item in payload["data"]["posters"]] == ["movie", "tv"]


@pytest.mark.asyncio
async def test_get_detail_page_data_falls_back_to_english_payload_when_primary_is_incomplete(
    async_client: AsyncClient,
    install_tmdb_client,
):
    zh_detail = {
        "id": 7,
        "media_type": "movie",
        "title": "霸王别姬",
        "release_date": "1993-01-01",
        "genres": [{"id": 18, "name": "剧情"}],
        "runtime": 171,
        "vote_average": 9.1,
        "tagline": "风华绝代",
        "overview": "一段半生传奇",
        "poster_path": "/farewell-poster.jpg",
        "backdrop_path": "/farewell-backdrop.jpg",
        "credits": {
            "cast": [
                {
                    "id": 1,
                    "name": "张国荣",
                    "character": "程蝶衣",
                    "profile_path": "/leslie.jpg",
                }
            ]
        },
        "videos": {"results": []},
        "recommendations": {"results": []},
        "similar": {"results": []},
    }
    en_detail = {
        **zh_detail,
        "videos": {
            "results": [
                {
                    "site": "YouTube",
                    "key": "abc123",
                    "name": "Official Trailer",
                    "type": "Trailer",
                    "official": True,
                }
            ]
        },
        "recommendations": {
            "results": [
                {
                    "id": 11,
                    "media_type": "movie",
                    "title": "阿飞正传",
                    "overview": "另一段青春",
                    "genre_ids": [18],
                    "poster_path": "/days-poster.jpg",
                    "backdrop_path": "/days-backdrop.jpg",
                    "release_date": "1990-12-15",
                    "vote_average": 8.3,
                }
            ]
        },
        "similar": {"results": []},
    }
    fake_client = FakeTmdbClient(
        detail_payloads={
            ("movie", 7, None): zh_detail,
            ("movie", 7, "en-US"): en_detail,
        }
    )
    install_tmdb_client(fake_client)

    response = await async_client.get("/api/v1/tmdb/detail/movie/7")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert fake_client.detail_calls == [
        ("movie", 7, None),
        ("movie", 7, "en-US"),
    ]
    assert payload["data"]["item"]["title"] == "霸王别姬"
    assert payload["data"]["item"]["videos"] == [
        {
            "key": "abc123",
            "name": "Official Trailer",
            "type": "Trailer",
            "official": True,
        }
    ]
    assert payload["data"]["recommendations"] == [
        {
            "id": 11,
            "media_type": "movie",
            "title": "阿飞正传",
            "subtitle": "1990 · 评分 8.3",
            "overview": "另一段青春",
            "genres": [18],
            "tone": "drama",
            "poster_url": "https://image.tmdb.org/t/p/w500/days-poster.jpg",
            "backdrop_url": "https://image.tmdb.org/t/p/w780/days-backdrop.jpg",
        }
    ]
