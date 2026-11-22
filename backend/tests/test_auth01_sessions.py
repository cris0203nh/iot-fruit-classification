"""Cookies y SQLite temporales: no usa bases operativas, SMTP ni Google reales."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select, update
import test_saas03_organizations as fixture
from app.main import app
from app.identity_models import BrowserSession
from app.models import User
from app.organization_models import OrganizationMembership
from app.platform_models import PlatformOwner
from app.services.browser_sessions import COOKIE, digest, now
from app.security import hash_password


class BrowserSessionTests(unittest.TestCase):
    setUpClass = classmethod(fixture.OrganizationIsolationTests.setUpClass.__func__)
    restore_override = fixture.OrganizationIsolationTests.restore_override
    auth = fixture.OrganizationIsolationTests.auth

    def setUp(self):
        fixture.OrganizationIsolationTests.setUp(self)
        self.browser = TestClient(app, base_url='https://testserver')
        self.addCleanup(self.browser.close)

    def login(self, username='adminA', browser=None):
        browser = browser or self.browser
        response = browser.post('/api/auth/login', data={'username': username, 'password': self.password},
            headers={'X-AgroScan-Session': 'browser', 'Origin': str(browser.base_url).rstrip('/')})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def csrf(self, response):
        return {'X-CSRF-Token': response.json()['csrf_token']}

    def test_reload_cookie_and_server_side_organization_selection(self):
        signed = self.login('shared')
        cookie = signed.headers['set-cookie']
        for value in ('HttpOnly', 'Secure', 'SameSite=strict', 'Path=/api', 'Max-Age='):
            self.assertIn(value, cookie)
        self.assertEqual(self.browser.get('/api/auth/me').status_code, 409)
        selected = self.browser.put('/api/auth/session/organization',
            headers={**self.csrf(signed), 'X-Organization-ID': '2'})
        self.assertEqual(selected.status_code, 200, selected.text)
        with TestClient(app, base_url='https://testserver') as reopened:
            reopened.cookies.update(self.browser.cookies)
            restored = reopened.get('/api/auth/session')
            self.assertEqual(restored.status_code, 200, restored.text)
            self.assertEqual(restored.json()['organization_id'], 2)
            self.assertEqual(reopened.get('/api/auth/me').json()['roles'], ['revisor'])
            self.assertEqual(reopened.get('/api/auth/me').headers['cache-control'], 'no-store')
        with self.Session() as db:
            row = db.scalar(select(BrowserSession))
            self.assertEqual(row.token_hash, digest(self.browser.cookies[COOKIE]))
            self.assertNotEqual(row.token_hash, self.browser.cookies[COOKIE])

    def test_csrf_missing_wrong_and_cross_origin_do_not_mutate(self):
        signed = self.login()
        for headers in ({}, {'X-CSRF-Token': 'wrong'},
                        {**self.csrf(signed), 'Origin': 'https://evil.example'},
                        {**self.csrf(signed), 'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.browser.post('/api/auth/logout', headers=headers).status_code, 403)
        self.assertEqual(self.browser.get('/api/auth/me').status_code, 200)
        self.assertEqual(self.browser.post('/api/auth/login', data={'username':'adminA','password':self.password},
            headers={'X-AgroScan-Session':'browser','Origin':'https://evil.example'}).status_code, 403)
        # Un visitante con cookie previa conserva el formulario publico tras F5.
        self.assertEqual(self.browser.post('/api/commercial/applications', json={}).status_code, 422)

    def test_logout_revokes_cookie_and_previously_issued_jwt(self):
        signed = self.login()
        old = self.browser.cookies[COOKIE]
        token = signed.json()['access_token']
        self.assertEqual(self.browser.post('/api/auth/logout', headers=self.csrf(signed)).status_code, 204)
        self.assertNotIn(COOKIE, self.browser.cookies)
        self.assertEqual(self.browser.get('/api/auth/session').status_code, 401)
        self.assertEqual(self.client.get('/api/auth/me', headers={'Authorization':'Bearer '+token}).status_code, 401)
        self.browser.cookies.set(COOKIE, old)
        self.assertEqual(self.browser.get('/api/auth/me').status_code, 401)

    def test_expired_idle_absolute_and_revoked_sessions_cannot_refresh(self):
        for field in ('expires_at', 'absolute_expires_at', 'revoked_at'):
            with self.subTest(field=field):
                signed = self.login()
                with self.Session() as db:
                    db.execute(update(BrowserSession).values(**{field: now()-timedelta(seconds=1)})); db.commit()
                self.assertEqual(self.browser.get('/api/auth/session').status_code, 401)
                self.assertEqual(self.browser.post('/api/auth/session/refresh', headers=self.csrf(signed)).status_code, 401)

    def test_refresh_is_bounded_and_logout_cannot_be_undone_by_concurrency(self):
        signed = self.login()
        with self.Session() as db:
            db.execute(update(BrowserSession).values(expires_at=now()+timedelta(minutes=1),
                absolute_expires_at=now()+timedelta(hours=1))); db.commit()
        renewed = self.browser.post('/api/auth/session/refresh', headers=self.csrf(signed))
        self.assertEqual(renewed.status_code, 200, renewed.text)
        with self.Session() as db:
            row = db.scalar(select(BrowserSession))
            self.assertEqual(row.expires_at, row.absolute_expires_at)
        cookie = self.browser.cookies[COOKIE]
        def operation(path):
            with TestClient(app, base_url='https://testserver') as client:
                client.cookies.set(COOKIE, cookie)
                return client.post(path, headers=self.csrf(signed)).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(operation, ['/api/auth/session/refresh', '/api/auth/logout']))
        self.assertIn(results[0], (200, 401)); self.assertEqual(results[1], 204)
        self.assertEqual(self.browser.get('/api/auth/session').status_code, 401)

    def test_user_password_membership_organization_and_role_are_revalidated(self):
        signed = self.login()
        self.assertEqual(self.browser.put('/api/auth/session/organization',
            headers={**self.csrf(signed), 'X-Organization-ID':'2'}).status_code, 403)
        self.assertEqual(self.browser.get('/api/lots/3').status_code, 404)
        with self.Session() as db:
            db.execute(update(OrganizationMembership).where(OrganizationMembership.user_id == self.users['adminA'])
                .values(role_id=3)); db.commit()
        self.assertEqual(self.browser.get('/api/auth/me').json()['roles'], ['revisor'])
        self.assertEqual(self.browser.get('/api/users').status_code, 403)
        with self.Session() as db:
            db.execute(update(OrganizationMembership).where(OrganizationMembership.user_id == self.users['adminA'])
                .values(is_active=False)); db.commit()
        self.assertEqual(self.browser.get('/api/auth/me').status_code, 403)
        with self.Session() as db:
            db.get(User, self.users['adminA']).is_active = False; db.commit()
        self.assertEqual(self.browser.get('/api/auth/session').status_code, 401)
        with self.Session() as db:
            user = db.get(User, self.users['adminA']); user.is_active = True
            user.password_hash = hash_password('Different-Synthetic-Password-Only!'); db.commit()
        self.assertEqual(self.browser.get('/api/auth/me').status_code, 401)

    def test_owner_restoration_does_not_confer_operational_memberships(self):
        with self.Session() as db:
            db.add(PlatformOwner(id=1, user_id=self.users['without_membership'])); db.commit()
        signed = self.login('without_membership')
        self.assertTrue(signed.json()['is_superadmin'])
        self.assertEqual(self.browser.get('/api/platform/me').status_code, 200)
        self.assertEqual(self.browser.get('/api/lots').status_code, 403)
        with self.Session() as db:
            db.delete(db.get(PlatformOwner, 1)); db.commit()
        self.assertFalse(self.browser.get('/api/auth/session').json()['is_superadmin'])
        self.assertEqual(self.browser.get('/api/platform/me').status_code, 403)

    def test_http_only_loopback_and_no_forwarded_header_bypass(self):
        with TestClient(app, base_url='http://127.0.0.1:8778', client=('127.0.0.1', 12345)) as local:
            response = local.post('/api/auth/login', headers={'X-AgroScan-Session':'browser'},
                data={'username':'adminA','password':self.password})
            self.assertEqual(response.status_code, 400)
        with patch.dict('os.environ', {'AGROSCAN_SESSION_ALLOW_LOOPBACK_HTTP':'true'}), TestClient(
                app, base_url='http://127.0.0.1:8778', client=('127.0.0.1', 12345)) as local:
            signed = self.login(browser=local)
            self.assertNotIn('Secure;', signed.headers['set-cookie'])
            self.assertEqual(local.get('/api/auth/session').status_code, 200)
        for host in ('http://testserver', 'http://192.168.1.2', 'http://localhost'):
            with TestClient(app, base_url=host) as remote:
                response = remote.post('/api/auth/login', headers={'X-AgroScan-Session':'browser',
                    'X-Forwarded-For':'127.0.0.1', 'X-Forwarded-Proto':'https'},
                    data={'username':'adminA','password':self.password})
                self.assertEqual(response.status_code, 400)

    def test_localhost_origin_through_ipv4_proxy_preserves_cookie_session_and_csrf(self):
        with patch.dict('os.environ', {'AGROSCAN_SESSION_ALLOW_LOOPBACK_HTTP':'true'}), TestClient(
                app, base_url='http://127.0.0.1:8000', client=('127.0.0.1',12345)) as client:
            signed = client.post('/api/auth/login',headers={'X-AgroScan-Session':'browser','Origin':'http://localhost:5173',
                'Sec-Fetch-Site':'same-origin'},data={'username':'adminA','password':self.password})
            self.assertEqual(signed.status_code,200,signed.text)
            self.assertNotIn('Domain=',signed.headers['set-cookie'])
            self.assertIn('HttpOnly',signed.headers['set-cookie'])
            self.assertIn('SameSite=strict',signed.headers['set-cookie'])
            self.assertEqual(client.get('/api/auth/session').status_code,200)
            self.assertEqual(client.post('/api/auth/session/refresh',headers={'Origin':'http://localhost:5173'}).status_code,403)
            self.assertEqual(client.post('/api/auth/logout',headers={'Origin':'http://localhost:5173',
                'X-CSRF-Token':signed.json()['csrf_token']}).status_code,204)

    def test_relogin_rotates_cookie_and_invalidates_previous_session(self):
        first = self.login()
        token = first.json()['access_token']
        cookie = self.browser.cookies[COOKIE]
        self.login()
        self.assertNotEqual(cookie, self.browser.cookies[COOKIE])
        self.assertEqual(self.client.get('/api/auth/me', headers={'Authorization':'Bearer '+token}).status_code, 401)
