"""Regresiones de cabeceras, autorización y CORS de AgroScan."""

from types import SimpleNamespace
import unittest

from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.main import app


class HttpSecurityTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()

    def assert_base_headers(self, response):
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["cross-origin-resource-policy"], "same-origin")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")

    def assert_api_not_stored(self, response):
        self.assert_base_headers(response)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn("public", response.headers["cache-control"])

    def test_health_headers_and_response_contract(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assert_api_not_stored(response)
        self.assertEqual(response.headers["content-type"], "application/json")

    def test_unauthenticated_endpoints_preserve_401_and_no_store(self):
        for path in ("/api/auth/me", "/api/iot/status", "/api/users"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers["www-authenticate"], "Bearer")
                self.assert_api_not_stored(response)

    def test_403_for_non_admin_retains_security_headers(self):
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            roles=[SimpleNamespace(name="operador")]
        )
        response = self.client.get("/api/users")
        self.assertEqual(response.status_code, 403)
        self.assert_api_not_stored(response)

    def test_errors_404_405_422_are_not_cached(self):
        cases = (
            ("get", "/api/unknown", 404),
            ("post", "/api/health", 405),
            ("post", "/api/auth/login", 422),
        )
        for method, path, expected in cases:
            with self.subTest(path=path, method=method):
                response = getattr(self.client, method)(path)
                self.assertEqual(response.status_code, expected)
                self.assert_api_not_stored(response)

    def test_allowed_cors_origin_works_on_json_responses(self):
        for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
            with self.subTest(origin=origin):
                response = self.client.get("/api/health", headers={"Origin": origin})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["access-control-allow-origin"], origin)
                self.assert_api_not_stored(response)
                self.assertIn("origin", response.headers.get("vary", "").lower())

    def test_preflight_allows_auth_and_device_key_headers(self):
        response = self.client.options(
            "/api/iot/measurements",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,x-device-key,content-type",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")
        self.assert_base_headers(response)
        self.assert_api_not_stored(response)
        allowed = response.headers["access-control-allow-headers"].lower()
        for header in ("authorization", "x-device-key", "content-type"):
            self.assertIn(header, allowed)

    def test_untrusted_origin_is_not_allowed_even_with_security_headers(self):
        response = self.client.get(
            "/api/health", headers={"Origin": "https://untrusted.example"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("access-control-allow-origin", response.headers)
        self.assert_api_not_stored(response)

        preflight = self.client.options(
            "/api/health",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(preflight.status_code, 400)
        self.assertNotIn("access-control-allow-origin", preflight.headers)
        self.assert_api_not_stored(preflight)

    def test_docs_are_not_forced_into_coep(self):
        for path in ("/docs", "/redoc"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.headers["content-type"])
                self.assert_base_headers(response)
                self.assertEqual(response.headers["cross-origin-opener-policy"], "same-origin")
                self.assertNotIn("cross-origin-embedder-policy", response.headers)
                self.assertNotIn("cache-control", response.headers)

    def test_openapi_and_unknown_route_have_security_headers(self):
        schema = self.client.get("/openapi.json")
        self.assertEqual(schema.status_code, 200)
        self.assertIn("openapi", schema.json())
        self.assert_base_headers(schema)
        unknown = self.client.get("/not-an-api-route")
        self.assertEqual(unknown.status_code, 404)
        self.assert_base_headers(unknown)
        self.assertNotIn("cache-control", unknown.headers)


if __name__ == "__main__":
    unittest.main()
