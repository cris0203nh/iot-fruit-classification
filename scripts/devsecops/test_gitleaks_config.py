"""Exact synthetic findings may be excluded; default secret detection remains on."""
from pathlib import Path
import re
import tomllib
import unittest


class GitleaksConfigurationTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[2] / '.gitleaks.toml'
        self.config = tomllib.loads(path.read_text(encoding='utf-8'))

    def allowed(self, path, match):
        return any(any(re.search(p, path) for p in rule['paths'])
                   and any(re.search(p, match) for p in rule['regexes'])
                   for rule in self.config['allowlists'])

    def test_default_rules_and_all_conjunctive_scopes(self):
        self.assertTrue(self.config['extend']['useDefault'])
        self.assertNotIn('disabledRules', self.config['extend'])
        self.assertEqual(len(self.config['allowlists']), 6)
        for rule in self.config['allowlists']:
            self.assertEqual(rule['condition'], 'AND')
            self.assertEqual(rule['targetRules'], ['generic-api-key'])
            self.assertEqual(rule['regexTarget'], 'match')
            self.assertNotIn('commits', rule)
            self.assertNotIn('stopwords', rule)

    def test_reviewed_idempotency_and_negative_cases(self):
        path = 'backend/tests/test_com04_initial_admin.py'
        match = "idempotencyKey='replacement-synthetic-1'"
        self.assertTrue(self.allowed(path, match))
        self.assertFalse(self.allowed('backend/app/real_service.py', match))
        self.assertFalse(self.allowed(path, "idempotencyKey='different-value'"))
        self.assertFalse(self.allowed(path, "api_key='replacement-synthetic-1'"))
        self.assertFalse(self.allowed(path, match + 'actual-secret'))

    def test_historical_password_is_only_allowed_in_its_original_test(self):
        match = 'password": "ClaveSegura12345"'
        self.assertTrue(self.allowed('backend/tests/test_agrop47_user_management.py', match))
        self.assertFalse(self.allowed('backend/app/security.py', match))
        self.assertFalse(self.allowed('backend/tests/test_agrop47_user_management.py', 'password": "AnotherCredential123"'))
