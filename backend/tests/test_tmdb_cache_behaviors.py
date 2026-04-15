import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import tmdb


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, object] = {}
        self.set_calls = 0

    async def get(self, key: str) -> object | None:
        return self.store.get(key)

    async def set(self, key: str, value: object, ttl: int) -> None:
        _ = ttl
        self.set_calls += 1
        self.store[key] = value


class FakeSectionsClient:
    def __init__(self, delay: float = 0.02) -> None:
        self.delay = delay
        self.calls = {
            "anime_latest": 0,
            "tv_latest": 0,
            "top_rated": 0,
            "tv_popular": 0,
            "anime_popular": 0,
        }

    async def _fetch(self, key: str, item_id: int) -> list[dict[str, object]]:
        self.calls[key] += 1
        await asyncio.sleep(self.delay)
        return [{"id": item_id, "media_type": "tv", "popularity": 10}]

    async def anime_latest(self) -> list[dict[str, object]]:
        return await self._fetch("anime_latest", 1)

    async def tv_latest(self) -> list[dict[str, object]]:
        return await self._fetch("tv_latest", 2)

    async def movies(self, category: str) -> list[dict[str, object]]:
        self.calls["top_rated"] += 1
        await asyncio.sleep(self.delay)
        return [{"id": 3, "media_type": "movie", "category": category}]

    async def tv_popular(self) -> list[dict[str, object]]:
        return await self._fetch("tv_popular", 4)

    async def anime_popular(self) -> list[dict[str, object]]:
        return await self._fetch("anime_popular", 5)


class TmdbCacheBehaviorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        tmdb._home_sections_cache_locks.clear()

    async def test_gather_sections_concurrent_miss_refreshes_once(self) -> None:
        client = FakeSectionsClient()
        cache = FakeCache()

        with patch("app.services.tmdb.get_cache", return_value=cache):
            first, second = await asyncio.gather(
                tmdb.gather_sections(client),
                tmdb.gather_sections(client),
            )

        self.assertEqual(first, second)
        self.assertEqual(cache.set_calls, 1)
        self.assertEqual(client.calls["anime_latest"], 1)
        self.assertEqual(client.calls["tv_latest"], 1)
        self.assertEqual(client.calls["top_rated"], 1)
        self.assertEqual(client.calls["tv_popular"], 1)
        self.assertEqual(client.calls["anime_popular"], 1)

    async def test_gather_sections_cache_hit_skips_remote_fetch(self) -> None:
        client = FakeSectionsClient()
        cache = FakeCache()
        cached_payload = {
            "anime_latest": [{"id": 11}],
            "tv_latest": [],
            "top_rated": [],
            "tv_popular": [],
            "anime_popular": [],
        }
        cache.store[tmdb.HOME_SECTIONS_CACHE_KEY] = cached_payload

        with patch("app.services.tmdb.get_cache", return_value=cache):
            result = await tmdb.gather_sections(client)

        self.assertEqual(result, cached_payload)
        self.assertEqual(client.calls["anime_latest"], 0)
        self.assertEqual(client.calls["tv_latest"], 0)
        self.assertEqual(client.calls["top_rated"], 0)
        self.assertEqual(client.calls["tv_popular"], 0)
        self.assertEqual(client.calls["anime_popular"], 0)

    def test_tmdb_cache_key_is_order_independent(self) -> None:
        key_a = tmdb._build_tmdb_cache_key(
            "/discover/tv",
            {"page": 1, "sort_by": "popularity.desc", "language": "zh-CN"},
        )
        key_b = tmdb._build_tmdb_cache_key(
            "/discover/tv",
            {"language": "zh-CN", "sort_by": "popularity.desc", "page": 1},
        )
        key_c = tmdb._build_tmdb_cache_key(
            "/discover/tv",
            {"language": "zh-CN", "sort_by": "vote_average.desc", "page": 1},
        )

        self.assertEqual(key_a, key_b)
        self.assertNotEqual(key_a, key_c)


if __name__ == "__main__":
    unittest.main()
