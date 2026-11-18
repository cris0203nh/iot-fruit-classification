import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from select_jobs import MODULES, classify, full_selection, git_changes


class SelectionTests(unittest.TestCase):
    def test_documentation_only_skips_all_expensive_modules(self):
        self.assertEqual(classify(['docs/ci/ETAPA05.md', 'README.md']),
                         {name: False for name in MODULES})

    def test_frontend_style_only(self):
        selected = classify(['frontend/src/App.css'])
        self.assertTrue(selected['frontend'])
        self.assertFalse(selected['backend'])
        self.assertFalse(selected['integracion'])
        self.assertFalse(selected['dast'])

    def test_frontend_code_adds_integration(self):
        selected = classify(['frontend/src/pages/Login.tsx'])
        self.assertTrue(selected['frontend'])
        self.assertTrue(selected['integracion'])
        self.assertFalse(selected['backend'])

    def test_backend_shared_requires_iot_vision_and_dast(self):
        self.assertEqual(classify(['backend/app/dependencies.py']),
                         dict(backend=True, frontend=False, iot=True,
                              vision=True, integracion=True, dast=True))

    def test_backend_requirements_and_migrations_trigger_shared_contracts(self):
        for name in ('backend/requirements.txt', 'backend/alembic/versions/s007iot_saas07.py'):
            with self.subTest(path=name):
                selected = classify([name])
                self.assertTrue(selected['backend'] and selected['vision'] and selected['iot'])

    def test_backend_test_only(self):
        selected = classify(['backend/tests/test_saas08_pilot.py'])
        self.assertEqual(selected, dict(backend=True, frontend=False, iot=False,
                                        vision=False, integracion=True, dast=True))

    def test_firmware_only(self):
        self.assertEqual(classify(['firmware/tools/serial_bridge.py']),
                         dict(backend=False, frontend=False, iot=True,
                              vision=False, integracion=True, dast=False))

    def test_vision_changes_validate_backend_contract(self):
        selected = classify(['vision/tests/test_ag055_v2.py'])
        self.assertTrue(selected['backend'] and selected['vision']
                        and selected['integracion'] and selected['dast'])
        self.assertFalse(selected['iot'])

    def test_root_and_ci_security_changes_run_all(self):
        for name in ['.github/workflows/ci.yml', 'scripts/ci/check_gate.py',
                     'scripts/devsecops/normalize.py', '.gitignore', 'database/schema.sql']:
            with self.subTest(path=name):
                self.assertEqual(classify([name]), full_selection())

    def test_specific_iot_and_geometry_tests(self):
        self.assertTrue(classify(['tests/test_scale_core.cpp'])['iot'])
        self.assertTrue(classify(['tests/test_agroscan_i03_pixel_scale.py'])['vision'])

    def test_empty_diff_and_untrusted_path_fail_safe(self):
        for files in ([], ['../secrets'], [''], ['unknown-subtree/file.ts']):
            self.assertEqual(classify(files), full_selection())

    def test_manual_forces_full(self):
        self.assertEqual(classify(['README.md'], force_full=True), full_selection())

    def test_unknown_base_fails_to_full(self):
        self.assertIsNone(git_changes(''))
        self.assertIsNone(git_changes('0' * 40))


if __name__ == '__main__':
    unittest.main()
