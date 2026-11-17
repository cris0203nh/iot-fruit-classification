"""Cambios de permisos SaaS-04; reutiliza fixtures A/B, sin repetir su auditoría."""
import io
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

import test_saas03_organizations as organizations_fixture
from app import bootstrap_owner
from app.database import get_db
from app.dependencies import require_superadmin
from app.main import app
from app.models import Role, User
from app.organization_models import Organization, OrganizationMembership
from app.platform_models import PlatformOwner
from app.security import JWT_SECRET


class OrganizationPermissionTests(unittest.TestCase):
    setUpClass = organizations_fixture.OrganizationIsolationTests.__dict__['setUpClass']
    setUp = organizations_fixture.OrganizationIsolationTests.setUp
    restore_override = organizations_fixture.OrganizationIsolationTests.restore_override
    auth = organizations_fixture.OrganizationIsolationTests.auth

    def probe(self):
        # Ruta exclusiva del ensayo: no añade un panel ni endpoints de plataforma a producción.
        probe = FastAPI()
        probe.dependency_overrides[get_db] = app.dependency_overrides[get_db]

        @probe.get('/platform-test')
        def platform_only(user=Depends(require_superadmin)):
            return {'ownerId': user.id}

        client = TestClient(probe)
        self.addCleanup(client.close)
        return client

    def test_superadmin_solo_propietario_y_sin_bypass_de_empresas(self):
        with self.Session() as db:
            bootstrap_owner.assign_first_owner(db, self.users['without_membership'])
        probe = self.probe()
        for name in ('adminA', 'adminB', 'operatorA', 'shared'):
            self.assertEqual(probe.get('/platform-test', headers=self.auth(name)).status_code, 403)
        token = self.auth('without_membership')
        self.assertEqual(probe.get('/platform-test', headers=token).status_code, 200)
        self.assertEqual(self.client.get('/api/lots', headers=token).status_code, 403)
        for endpoint in ('/api/iot/status', '/api/admin/backups'):
            response = self.client.request('GET' if '/iot/' in endpoint else 'POST', endpoint, headers=token)
            self.assertEqual(response.status_code, 403 if '/iot/' in endpoint else 503)
        with self.Session() as db:
            db.get(User, self.users['without_membership']).is_active = False
            db.commit()
        self.assertEqual(probe.get('/platform-test', headers=token).status_code, 401)

    def test_claims_roles_y_cuerpos_no_conceden_superadmin(self):
        now = datetime.now(timezone.utc)
        claimed = jwt.encode({'sub': str(self.users['adminA']), 'iat': now,
            'exp': now + timedelta(minutes=5), 'isSuperadmin': True, 'roles': ['superadmin']},
            JWT_SECRET, algorithm='HS256')
        self.assertEqual(self.probe().get('/platform-test',
            headers={'Authorization': 'Bearer ' + claimed}).status_code, 403)
        for payload in ({'role': 'superadmin'}, {'role': 'administrador', 'isSuperadmin': True},
                        {'role': 'administrador', 'organization_id': 2}):
            response = self.client.patch(f'/api/users/{self.users["operatorA"]}/role',
                                         headers=self.auth(), json=payload)
            self.assertEqual(response.status_code, 422, response.text)
        response = self.client.post('/api/users', headers=self.auth(), json={
            'username': 'public-owner', 'fullName': 'Synthetic owner',
            'password': self.password, 'role': 'superadmin'})
        self.assertEqual(response.status_code, 422)
        with self.Session() as db:
            db.add(Role(id=20, name='superadmin'))
            db.flush()
            db.add(OrganizationMembership(organization_id=1, user_id=self.users['operatorA'], role_id=20))
            db.commit()
        self.assertEqual(self.probe().get('/platform-test', headers=self.auth('operatorA')).status_code, 403)
        profile = self.client.get('/api/auth/me', headers=self.auth('operatorA'))
        self.assertEqual(profile.json()['roles'], ['operador'])
        self.assertFalse(profile.json()['isSuperadmin'])

    def test_revocar_membresia_invalida_jwt_emitido_solo_en_esa_empresa(self):
        issued_a, issued_b = self.auth('shared', 1), self.auth('shared', 2)
        self.assertEqual(self.client.get('/api/lots', headers=issued_a).status_code, 200)
        revoked = self.client.delete(f'/api/users/{self.users["shared"]}/membership', headers=self.auth())
        self.assertEqual(revoked.status_code, 204, revoked.text)
        self.assertEqual(self.client.get('/api/lots', headers=issued_a).status_code, 403)
        self.assertEqual(self.client.get('/api/lots', headers=issued_b).status_code, 200)
        self.assertEqual(self.client.delete(f'/api/users/{self.users["adminB"]}/membership',
            headers=self.auth()).status_code, 404)
        self.assertEqual(self.client.delete(f'/api/users/{self.users["adminA"]}/membership',
            headers=self.auth()).status_code, 409)
        self.assertEqual(self.client.delete(f'/api/users/{self.users["adminA"]}/membership',
            headers=self.auth('operatorA')).status_code, 403)
        with self.Session() as db:
            self.assertTrue(db.get(User, self.users['shared']).is_active)

    def test_desactivacion_y_cambio_de_rol_se_aplican_al_mismo_token(self):
        issued = self.auth('operatorA')
        issued_b = self.auth('adminB')
        valid = {'code': 'BEFORE-CHANGE', 'product': 'mango', 'responsible': 'Synthetic'}
        self.assertEqual(self.client.post('/api/lots', headers=issued, json=valid).status_code, 201)
        changed = self.client.patch(f'/api/users/{self.users["operatorA"]}/role',
            headers=self.auth(), json={'role': 'revisor'})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.client.post('/api/lots', headers=issued, json={**valid, 'code': 'DENIED'}).status_code, 403)
        self.assertEqual(self.client.get('/api/reviews/queue', headers=issued).status_code, 200)
        disabled = self.client.patch(f'/api/users/{self.users["operatorA"]}/status',
            headers=self.auth(), json={'isActive': False})
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(self.client.get('/api/lots', headers=issued).status_code, 403)
        with self.Session() as db:
            db.get(User, self.users['adminB']).is_active = False
            db.commit()
        self.assertEqual(self.client.get('/api/lots', headers=issued_b).status_code, 401)

    def test_administrador_empresarial_no_puede_retirar_el_privilegio_global(self):
        with self.Session() as db:
            bootstrap_owner.assign_first_owner(db, self.users['shared'])
        issued = self.auth('shared', 1)
        probe = self.probe()
        self.assertEqual(probe.get('/platform-test', headers=issued).status_code, 200)
        disabled = self.client.patch(f'/api/users/{self.users["shared"]}/status',
            headers=self.auth(), json={'isActive': False})
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(self.client.get('/api/lots', headers=issued).status_code, 403)
        self.assertEqual(probe.get('/platform-test', headers=issued).status_code, 200)
        self.assertEqual(self.client.get('/api/lots', headers=self.auth('shared', 2)).status_code, 200)

    def test_propietario_unico_inicializacion_concurrente_y_retiro_efectivo(self):
        def assign(name):
            with self.Session() as db:
                try:
                    bootstrap_owner.assign_first_owner(db, self.users[name])
                    return True
                except ValueError:
                    db.rollback()
                    return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(assign, ('adminA', 'adminB')))
        self.assertEqual(sorted(result), [False, True])
        with self.Session() as db:
            owner = db.get(PlatformOwner, 1)
            owner_name = next(name for name in ('adminA', 'adminB') if self.users[name] == owner.user_id)
        issued = self.auth(owner_name)
        probe = self.probe()
        self.assertEqual(probe.get('/platform-test', headers=issued).status_code, 200)
        with self.assertRaises(IntegrityError), self.Session() as db:
            db.add(PlatformOwner(id=2, user_id=self.users['without_membership']))
            db.commit()
        with self.Session() as db:
            db.execute(delete(PlatformOwner))
            db.commit()
        self.assertEqual(probe.get('/platform-test', headers=issued).status_code, 403)

    def test_inicializacion_privada_sin_credenciales_predeterminadas_ni_membresias(self):
        output = io.StringIO()
        new_password = 'Private-Synthetic-Owner-Password!'
        with patch.object(bootstrap_owner, 'SessionLocal', self.Session), \
                patch('builtins.input', side_effect=['private-owner', 'Synthetic Owner']), \
                patch.object(bootstrap_owner, 'getpass', side_effect=[new_password, new_password]), \
                redirect_stdout(output):
            self.assertEqual(bootstrap_owner.main(['--create-user']), 0)
        self.assertNotIn(new_password, output.getvalue())
        with self.Session() as db:
            owner = db.get(PlatformOwner, 1)
            user = db.get(User, owner.user_id)
            self.assertEqual(user.username, 'private-owner')
            self.assertNotEqual(user.password_hash, new_password)
            self.assertTrue(user.password_hash.startswith('$argon2'))
            self.assertEqual(db.scalars(select(OrganizationMembership).where(
                OrganizationMembership.user_id == user.id)).all(), [])
            self.assertEqual(user.roles, [])
        with patch.object(bootstrap_owner, 'SessionLocal', self.Session), redirect_stdout(output):
            self.assertEqual(bootstrap_owner.main(['--user-id', str(self.users['adminA'])]), 1)

    def test_inicializacion_rechaza_cuenta_inexistente_inactiva_y_clave_invalida(self):
        with self.Session() as db:
            db.get(User, self.users['operatorA']).is_active = False
            db.commit()
        for user_id in (999999, self.users['operatorA']):
            with self.Session() as db, self.assertRaises(ValueError):
                bootstrap_owner.assign_first_owner(db, user_id)
        with patch.object(bootstrap_owner, 'SessionLocal', self.Session), \
                patch('builtins.input', side_effect=['private-owner', 'Synthetic Owner']), \
                patch.object(bootstrap_owner, 'getpass', side_effect=['short', 'different']), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(bootstrap_owner.main(['--create-user']), 1)
        with self.Session() as db:
            self.assertIsNone(db.get(PlatformOwner, 1))
            self.assertIsNone(db.scalar(select(User).where(User.username == 'private-owner')))


if __name__ == '__main__':
    unittest.main()
