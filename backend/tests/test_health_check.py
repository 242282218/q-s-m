import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import health_check


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


class _FakeCache:
    def __init__(self, stats):
        self._stats = stats

    async def get_stats(self):
        return self._stats


class HealthCheckTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_check_supports_multi_level_cache_stats(self):
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(tmdb_client=object())))
        cache_stats = {
            "multi_level": True,
            "l1": {"valid": 3, "total": 5, "hits": 1, "misses": 0},
            "total_hits": 1,
            "total_misses": 0,
        }

        with patch("app.db.session.engine", _FakeEngine()), patch(
            "app.quark.core.cache.get_cache",
            return_value=_FakeCache(cache_stats),
        ):
            response = await health_check(request)

        self.assertEqual(response.data.status, "ok")
        self.assertEqual(response.data.checks["cache"].status, "ok")
        self.assertEqual(response.data.checks["cache"].message, "Cache operational: 3/5 entries")


if __name__ == "__main__":
    unittest.main()
