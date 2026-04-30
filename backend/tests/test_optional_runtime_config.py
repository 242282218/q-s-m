import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api.endpoints.home import get_home_feed
from app.api.endpoints.tmdb import search_media
from app.collection.routes import verify_single_collection
from app.core.exceptions import QSMException
from app.quark.api.routes.search import search_by_tmdb_id


class OptionalRuntimeConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_home_feed_degrades_without_tmdb_client(self):
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(tmdb_client=None)))

        with patch("app.api.endpoints.home.get_settings") as mock_get_settings:
            mock_get_settings.return_value = SimpleNamespace(debug=True, tmdb_api_key=None)
            response = await get_home_feed(request)

        self.assertEqual(response.code, 0)
        self.assertEqual(response.message, "TMDB 未可用，开发环境返回演示首页数据")
        self.assertTrue(response.data.hero_items)
        self.assertTrue(all(items for items in response.data.sections.values()))

    async def test_tmdb_search_returns_config_error_without_tmdb_client(self):
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(tmdb_client=None)))

        response = await search_media(request, q="inception")

        self.assertEqual(response.code, 423)
        self.assertEqual(response.error.field, "TMDB_API_KEY")

    async def test_quark_search_by_tmdb_id_returns_config_error_without_tmdb_key(self):
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(quark_client=None)))

        with patch("app.quark.api.routes.search.get_settings") as mock_get_settings:
            mock_get_settings.return_value = SimpleNamespace(tmdb_api_key=None)
            with self.assertRaises(QSMException) as context:
                await search_by_tmdb_id(request, tmdb_id=27205)

        self.assertEqual(int(context.exception.code), 423)
        self.assertIsNotNone(context.exception.context)
        self.assertEqual(context.exception.context.field, "TMDB_API_KEY")

    async def test_verify_single_collection_returns_config_error_without_quark_cookie(self):
        response = await verify_single_collection(
            collection_id=1,
            db=None,
            settings=SimpleNamespace(quark_transfer_cookie=None),
            _=None,
        )

        self.assertEqual(response.code, 423)
        self.assertEqual(response.error.field, "QUARK_TRANSFER_COOKIE")
