"""DevSecOps: limitación de ataques de fuerza bruta en inicio de sesión."""
import secrets
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.login_throttle import login_throttle
from app.main import app
from app.models import Role, User
from app.security import hash_password


class LoginSecurityTests(unittest.TestCase):
    def setUp(self):
        login_throttle.clear()
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.password = secrets.token_hex(16)
        self.db.add(User(username='auth_test_account', full_name='Test',
                         password_hash=hash_password(self.password),
                         is_active=True, roles=[Role(name='operador')]))
        self.db.commit()
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.db.close()
        self.engine.dispose()
        login_throttle.clear()

    def login(self, username, password, headers=None):
        return self.client.post('/api/auth/login', data={'username': username, 'password': password}, headers=headers)

    def test_five_failures_lead_to_429_and_retry_after(self):
        for _ in range(5):
            self.assertEqual(self.login('auth_test_account', 'incorrect').status_code, 401)
        locked = self.login('auth_test_account', self.password)
        self.assertEqual(locked.status_code, 429)
        self.assertGreater(int(locked.headers['retry-after']), 0)
        self.assertNotIn('access_token', locked.text)

    def test_nonexistent_account_is_rate_limited_equally(self):
        with patch('app.routers.auth.verify_password', return_value=False) as verifier:
            for _ in range(5):
                self.assertEqual(self.login('unknown_test_account', 'incorrect').status_code, 401)
            self.assertEqual(self.login('unknown_test_account', 'incorrect').status_code, 429)
            self.assertEqual(verifier.call_count, 5)

    def test_successful_login_still_works(self):
        self.assertEqual(self.login('auth_test_account', 'incorrect').status_code, 401)
        ok = self.login('auth_test_account', self.password)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()['token_type'], 'bearer')
        self.assertEqual(self.login('auth_test_account', 'incorrect').status_code, 401)

    def test_rotating_usernames_hits_ip_threshold(self):
        with patch('app.routers.auth.verify_password', return_value=False):
            for index in range(20):
                self.assertEqual(self.login(f'invalid_{index}', 'incorrect').status_code, 401)
        self.assertEqual(self.login('auth_test_account', self.password).status_code, 429)

    def test_forwarded_header_cannot_bypass_limit(self):
        for index in range(5):
            reply = self.login('auth_test_account', 'incorrect', headers={'X-Forwarded-For': f'203.0.113.{index + 1}'})
            self.assertEqual(reply.status_code, 401)
        self.assertEqual(self.login('auth_test_account', 'incorrect',
                         headers={'X-Forwarded-For': '198.51.100.8'}).status_code, 429)


if __name__ == '__main__':
    unittest.main()
