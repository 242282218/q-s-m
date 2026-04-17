import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.collection import routes as collection_routes
from app.core.auth import verify_api_key
from app.main import app, liveness_check, readiness_check
from app.middleware.rate_limit import _RATE_LIMIT_SKIP_PREFIXES
from app.transfer import routes as transfer_routes
from app.api.endpoints.settings import validate_env_value


class ApiSecurityTests(unittest.TestCase):
    def _get_route_dependencies(self, router, endpoint):
        route = next(route for route in router.routes if getattr(route, "endpoint", None) is endpoint)
        return [dependency.call for dependency in route.dependant.dependencies]

    def _get_app_route_dependencies(self, endpoint):
        route = next(route for route in app.routes if getattr(route, "endpoint", None) is endpoint)
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

    def test_validate_link_requires_api_key(self):
        dependencies = self._get_route_dependencies(
            transfer_routes.router,
            transfer_routes.validate_link,
        )
        self.assertIn(verify_api_key, dependencies)

    def test_health_probe_endpoints_do_not_require_api_key(self):
        self.assertEqual(self._get_app_route_dependencies(liveness_check), [])
        self.assertEqual(self._get_app_route_dependencies(readiness_check), [])

    def test_health_probe_endpoints_are_exempt_from_rate_limiter(self):
        self.assertTrue(any("/api/v1/health/live".startswith(prefix) for prefix in _RATE_LIMIT_SKIP_PREFIXES))
        self.assertTrue(any("/api/v1/health/ready".startswith(prefix) for prefix in _RATE_LIMIT_SKIP_PREFIXES))


if __name__ == "__main__":
    unittest.main()
