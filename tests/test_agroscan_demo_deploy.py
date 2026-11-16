import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / 'tools' / 'agroscan_demo_gateway.py'
spec = importlib.util.spec_from_file_location('agroscan_demo_gateway', MOD)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class DemoGateTests(unittest.TestCase):
    def test_health_and_auth(self):
        self.assertTrue(module.allowed_path('/api/health'))
        self.assertTrue(module.allowed_path('/api/auth/login'))
        self.assertTrue(module.allowed_path('/api/auth/me'))
    def test_vision_and_history(self):
        self.assertTrue(module.allowed_path('/api/evaluations/E-000001/vision/geometry'))
        self.assertTrue(module.allowed_path('/api/images/I-000001'))
    def test_block_telemetry_write(self):
        self.assertFalse(module.allowed_path('/api/iot/measurements'))
        self.assertTrue(module.allowed_path('/api/iot/status'))
    def test_block_backup_restore(self):
        self.assertFalse(module.allowed_path('/api/admin/backups'))
        self.assertFalse(module.allowed_path('/api/admin/backups/restore'))
    def test_block_docs(self):
        self.assertFalse(module.allowed_path('/openapi.json'))
        self.assertFalse(module.allowed_path('/docs'))
        self.assertFalse(module.allowed_path('/'))
    def test_block_url_encoding_bypass(self):
        self.assertFalse(module.allowed_path('/api/evaluations/%2e%2e/admin'))
        self.assertFalse(module.allowed_path('/api//admin/backups'))
    def test_rate_limit(self):
        for _ in range(10):
            self.assertTrue(module.within_limit('test-ip-unique', '/api/auth/login', 'POST'))
        self.assertFalse(module.within_limit('test-ip-unique', '/api/auth/login', 'POST'))

if __name__ == '__main__':
    unittest.main()
