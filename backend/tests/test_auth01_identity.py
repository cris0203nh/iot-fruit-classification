"""Regresion de sesiones persistentes en Google e invitaciones, sin OAuth externo."""
import unittest
from fastapi.testclient import TestClient
import test_saas06_identity as identity_fixture
from app.main import app
from app.identity_models import GoogleIdentity
from app.services.browser_sessions import COOKIE


class BrowserIdentitySessionTests(unittest.TestCase):
    setUpClass = classmethod(identity_fixture.IdentityInvitationTests.setUpClass.__func__)
    restore_override = identity_fixture.IdentityInvitationTests.restore_override
    auth = identity_fixture.IdentityInvitationTests.auth
    challenge = identity_fixture.IdentityInvitationTests.challenge
    credential = identity_fixture.IdentityInvitationTests.credential
    invitation = identity_fixture.IdentityInvitationTests.invitation

    def setUp(self):
        identity_fixture.IdentityInvitationTests.setUp(self)
        self.client = TestClient(app, base_url='https://testserver')
        self.addCleanup(self.client.close)

    def test_google_login_restores_existing_identity_without_auto_linking(self):
        with self.Session() as db:
            db.add(GoogleIdentity(subject='subject-a', user_id=self.users['adminA'], email='recipient@example.test'))
            db.commit()
        nonce = self.challenge()
        signed = self.client.post('/api/auth/google/login', headers={'X-AgroScan-Session':'browser'},
            json={'credential':self.credential(nonce)})
        self.assertEqual(signed.status_code, 200, signed.text)
        self.assertIn(COOKIE, self.client.cookies)
        self.assertEqual(self.client.get('/api/auth/session').status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me').json()['id'], self.users['adminA'])

    def test_local_invitation_registration_restores_new_membership(self):
        invitation = self.invitation()
        signed = self.client.post('/api/auth/invitations/register', headers={'X-AgroScan-Session':'browser'},
            json={'token':invitation['token'],'username':'synthetic-invited','fullName':'Synthetic invited',
                  'password':'Synthetic-Invited-Password-Only!'})
        self.assertEqual(signed.status_code, 201, signed.text)
        self.assertIn(COOKIE, self.client.cookies)
        self.assertEqual(self.client.get('/api/auth/session').json()['organization_id'], 1)
        self.assertEqual(self.client.get('/api/auth/me').json()['roles'], ['operador'])

    def test_google_invitation_restores_invited_organization(self):
        invitation = self.invitation()
        nonce = self.challenge()
        signed = self.client.post('/api/auth/google/accept-invitation', headers={'X-AgroScan-Session':'browser'},
            json={'token':invitation['token'],'credential':self.credential(nonce)})
        self.assertEqual(signed.status_code, 200, signed.text)
        self.assertIn(COOKIE, self.client.cookies)
        self.assertEqual(self.client.get('/api/auth/session').json()['organization_id'], 1)
        self.assertEqual(self.client.get('/api/auth/me').json()['roles'], ['operador'])
