"""Tests de regresión del contrato HTTP del smoke DAST."""

import unittest
from email.message import Message

from dast_smoke import check_security_headers


class DastSmokeHeaderTests(unittest.TestCase):
    def setUp(self):
        self.headers = Message()
        self.headers["X-Content-Type-Options"] = "nosniff"
        self.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        self.headers["Referrer-Policy"] = "no-referrer"
        self.headers["Cache-Control"] = "no-store"

    def test_valid_api_headers(self):
        check_security_headers(self.headers)

    def test_missing_mime_header_is_rejected(self):
        del self.headers["X-Content-Type-Options"]
        with self.assertRaises(AssertionError):
            check_security_headers(self.headers)

    def test_missing_cache_policy_is_rejected(self):
        del self.headers["Cache-Control"]
        with self.assertRaises(AssertionError):
            check_security_headers(self.headers)

    def test_non_api_openapi_does_not_require_cache_policy(self):
        del self.headers["Cache-Control"]
        check_security_headers(self.headers, api=False)


if __name__ == "__main__":
    unittest.main()
