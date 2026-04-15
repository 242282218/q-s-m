import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api.endpoints import home
from app.api.schemas.home import HomePosterItem


class FakeTmdbClient:
    def __init__(self, delay: float = 0.02) -> None:
        self.delay = delay
        self.details_calls = 0
        self.backdrop_calls = 0

    def image_url(self, path: str | None, size: str = "w500") -> str | None:
        if not path:
            return None
        return f"https://image.tmdb.org/t/p/{size}{path}"

    async def details(self, media_type: str, item_id: int) -> dict:
        _ = media_type
        self.details_calls += 1
        await asyncio.sleep(self.delay)
        return {
            "id": item_id,
            "media_type": "tv",
            "name": f"title-{item_id}",
            "first_air_date": "2024-01-01",
            "genres": [{"name": "Drama"}],
            "runtime": 50,
            "vote_average": 8.5,
            "tagline": "tagline",
            "overview": f"overview-{item_id}",
            "poster_path": f"/poster-{item_id}.jpg",
            "backdrop_path": f"/backdrop-{item_id}.jpg",
            "credits": {"cast": []},
            "videos": {"results": []},
            "recommendations": {"results": []},
            "similar": {"results": []},
        }

    async def get_best_backdrop(self, media_type: str, item_id: int) -> str:
        _ = media_type
        self.backdrop_calls += 1
        await asyncio.sleep(self.delay)
        return f"https://cdn.example.com/backdrop-{item_id}.jpg"


def build_sections() -> dict[str, list[HomePosterItem]]:
    posters = [
        HomePosterItem(
            id=i,
            media_type="tv",
            title=f"poster-{i}",
            subtitle="2024",
            overview=f"overview-{i}",
            poster_url=f"https://cdn.example.com/poster-{i}.jpg",
            backdrop_url=f"https://cdn.example.com/backdrop-{i}.jpg",
        )
        for i in range(1, 8)
    ]
    return {
        "tv_popular": posters[0:3],
        "tv_latest": posters[3:5],
        "top_rated": posters[5:7],
        "anime_popular": [],
    }


class HomeHeroCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        home._hero_cache["data"] = None
        home._hero_cache["timestamp"] = 0
        home._hero_cache_locks.clear()

    async def test_concurrent_cache_miss_only_refreshes_once(self) -> None:
        tmdb_client = FakeTmdbClient()
        sections = build_sections()

        with patch("app.api.endpoints.home.random.sample", side_effect=lambda items, count: list(items)[:count]):
            first, second = await asyncio.gather(
                home._get_hero_items(tmdb_client, sections),
                home._get_hero_items(tmdb_client, sections),
            )

        self.assertEqual(len(first), 5)
        self.assertEqual(len(second), 5)
        self.assertEqual(tmdb_client.details_calls, 5)
        self.assertEqual(tmdb_client.backdrop_calls, 5)

    async def test_cached_result_skips_follow_up_tmdb_calls(self) -> None:
        tmdb_client = FakeTmdbClient()
        sections = build_sections()

        with patch("app.api.endpoints.home.random.sample", side_effect=lambda items, count: list(items)[:count]):
            first = await home._get_hero_items(tmdb_client, sections)
            second = await home._get_hero_items(tmdb_client, sections)

        self.assertEqual([item.id for item in first], [item.id for item in second])
        self.assertEqual(tmdb_client.details_calls, 5)
        self.assertEqual(tmdb_client.backdrop_calls, 5)


if __name__ == "__main__":
    unittest.main()
