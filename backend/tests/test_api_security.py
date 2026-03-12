import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.collection import routes as collection_routes
from app.core.auth import verify_api_key
from app.transfer import routes as transfer_routes
from app.api.endpoints.settings import validate_env_value


class ApiSecurityTests(unittest.TestCase):
    def _get_route_dependencies(self, router, endpoint):
        route = next(route for route in router.routes if getattr(route, "endpoint", None) is endpoint)
        return [dependency.call for dependency in route.dependant.dependencies]

    def test_validate_env_value_accepts_real_cookie_header(self):
        cookie_value = "sid=abc123; kps=xyz789; __uid=42"
        self.assertTrue(validate_env_value(cookie_value))

    def test_verify_single_collection_requires_api_key(self):
        dependencies = self._get_route_dependencies(
            collection_routes.router,
            collection_routes.verify_single_collection,
        )
        self.assertIn(verify_api_key, dependencies)

    def test_batch_add_sse_requires_api_key(self):
        dependencies = self._get_route_dependencies(
            collection_routes.router,
            collection_routes.batch_add_collections_sse,
        )
        self.assertIn(verify_api_key, dependencies)

    def test_batch_transfer_sse_requires_api_key(self):
        dependencies = self._get_route_dependencies(
            transfer_routes.router,
            transfer_routes.batch_transfer_sse,
        )
        self.assertIn(verify_api_key, dependencies)


if __name__ == "__main__":
    unittest.main()
