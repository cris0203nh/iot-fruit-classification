"""Panel SaaS con fixtures A/B existentes y propietario sintético exclusivo."""
import io
import unittest
import warnings
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

import test_saas03_organizations as fixture
from app import bootstrap_owner
from app.database import Base, enable_sqlite_foreign_keys, get_db
from app.main import app
from app.models import Evaluation, Role, User
from app.organization_models import Organization, OrganizationMembership
from app.platform_models import PlatformOwner
from app.security import create_access_token


class PlatformAdministrationTests(unittest.TestCase):
    setUpClass = fixture.OrganizationIsolationTests.__dict__['setUpClass']
    auth = fixture.OrganizationIsolationTests.auth
    restore_override = fixture.OrganizationIsolationTests.restore_override

    def setUp(self):
        fixture.OrganizationIsolationTests.setUp(self)
        with self.Session() as db:
            bootstrap_owner.assign_first_owner(db, self.users['without_membership'])
        self.owner = self.auth('without_membership')

    def test_todas_las_operaciones_globales_exclusivas_del_propietario(self):
        for path, methods in app.openapi()['paths'].items():
            if not path.startswith('/api/platform/'):
                continue
            url = path.replace('{organization_id}', '2').replace('{user_id}', str(self.users['operatorA']))
            for method in methods:
                if method not in ('get', 'post', 'put', 'patch', 'delete'):
                    continue
                for name in (None, 'adminA', 'adminB', 'operatorA', 'shared'):
                    with self.subTest(path=path, method=method, user=name):
                        headers = self.auth(name, 1) if name else {}
                        headers['X-Platform-Authorized'] = 'true'
                        reply = self.client.request(method, url, headers=headers, json={})
                        self.assertEqual(reply.status_code, 403 if name else 401, reply.text)
        self.assertEqual(self.client.get('/api/platform/me', headers=self.owner).status_code, 200)
        self.assertEqual(self.client.get('/api/lots', headers=self.owner).status_code, 403)
        self.assertEqual(self.client.get('/api/evaluations', headers=self.auth()).json()[0]['id'], 'E-000001')

    def test_metricas_reales_y_usuarios_sin_hashes_ni_roles_globales_filtrados(self):
        reply = self.client.get('/api/platform/metrics', headers={**self.owner, 'X-Organization-ID': '1'})
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(reply.json(), {'organizations': 2, 'activeOrganizations': 2,
                                       'users': 5, 'activeUsers': 5, 'evaluations': 2})
        companies = self.client.get('/api/platform/organizations', headers=self.owner).json()
        self.assertEqual([(c['id'], c['userCount'], c['evaluationCount']) for c in companies], [(1,3,1),(2,2,1)])
        users = self.client.get('/api/platform/users', headers=self.owner)
        self.assertEqual(users.status_code, 200)
        for row in users.json():
            self.assertEqual(set(row), {'id', 'username', 'fullName', 'isActive'})
        self.assertNotIn(self.hashed, users.text)
        with self.Session() as db:
            self.assertEqual(db.scalar(select(func.count(Evaluation.id))), 2)

    def test_registro_concurrente_no_duplica_y_no_modifica_cuentas_historicas(self):
        with self.Session() as db:
            before = [(user.id, user.username, user.password_hash) for user in db.scalars(select(User).order_by(User.id))]
        def register(_):
            return self.client.post('/api/platform/organizations', headers=self.owner, json={'name': ' New Company '})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(register, range(2)))
        self.assertEqual(sorted(r.status_code for r in responses), [201,409])
        created = next(r.json() for r in responses if r.status_code == 201)
        self.assertEqual(created['name'], 'New Company')
        self.assertEqual((created['userCount'], created['evaluationCount']), (0,0))
        self.assertEqual(self.client.post('/api/platform/organizations', headers=self.owner,
                                         json={'name': 'new company'}).status_code, 409)
        self.assertEqual(self.client.post('/api/platform/organizations', headers=self.owner,
                                         json={'name': 'Extra', 'isSuperadmin': True}).status_code, 422)
        with self.Session() as db:
            after = [(user.id, user.username, user.password_hash) for user in db.scalars(select(User).order_by(User.id))]
            self.assertEqual(before, after)

    def test_designacion_y_retiro_solo_cambian_el_rol_empresarial_con_jwt_previo(self):
        issued_b = self.auth('operatorA', 2)
        endpoint = f'/api/platform/organizations/2/administrators/{self.users["operatorA"]}'
        self.assertEqual(self.client.get('/api/users', headers=issued_b).status_code, 403)
        for _ in range(2):
            reply = self.client.put(endpoint, headers=self.owner)
            self.assertEqual(reply.status_code, 200, reply.text)
            self.assertEqual(reply.json()['role'], 'administrador')
        company_b_users = self.client.get('/api/users', headers=issued_b)
        self.assertEqual(company_b_users.status_code, 200)
        self.assertNotIn('adminA', [row['username'] for row in company_b_users.json()])
        self.assertEqual(self.client.get('/api/users', headers=self.auth('operatorA', 1)).status_code, 403)
        self.assertEqual(self.client.get('/api/platform/metrics', headers=issued_b).status_code, 403)
        self.assertEqual(self.client.patch(f'/api/users/{self.users["adminA"]}/status',
            headers=issued_b, json={'isActive': False}).status_code, 404)
        admins = self.client.get('/api/platform/organizations/2/administrators', headers=self.owner).json()
        self.assertIn('operatorA', [row['username'] for row in admins])
        with self.Session() as db:
            self.assertEqual(db.get(PlatformOwner, 1).user_id, self.users['without_membership'])
        self.assertEqual(self.client.delete(endpoint, headers=self.owner).status_code, 204)
        self.assertEqual(self.client.get('/api/users', headers=issued_b).status_code, 403)
        self.assertEqual(self.client.get('/api/lots', headers=self.auth('operatorA', 1)).status_code, 200)

    def test_nuevo_administrador_local_sin_acceso_global_o_a_otras_empresas(self):
        created = self.client.post('/api/platform/organizations', headers=self.owner, json={'name': 'Customer'})
        company = created.json()['id']
        payload = {'username': 'customer-admin', 'fullName': 'Customer Admin', 'password': self.password}
        endpoint = f'/api/platform/organizations/{company}/administrators'
        response = self.client.post(endpoint, headers=self.owner, json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(set(response.json()), {'id','username','fullName','isActive'})
        self.assertNotIn(self.password, response.text)
        login = self.client.post('/api/auth/login', data={'username': payload['username'], 'password': self.password})
        self.assertFalse(login.json()['is_superadmin'])
        headers = {'Authorization': 'Bearer '+login.json()['access_token'], 'X-Organization-ID': str(company)}
        self.assertEqual(self.client.get('/api/users', headers=headers).status_code, 200)
        self.assertEqual(self.client.get('/api/platform/metrics', headers=headers).status_code, 403)
        self.assertEqual(self.client.get('/api/users', headers={**headers,'X-Organization-ID':'1'}).status_code, 403)
        self.assertEqual(self.client.post(endpoint, headers=self.owner, json=payload).status_code, 409)
        with self.Session() as db:
            account = db.get(User,response.json()['id'])
            self.assertTrue(account.password_hash.startswith('$argon2'))
            self.assertEqual(db.get(PlatformOwner,1).user_id, self.users['without_membership'])

    def test_errores_del_alta_privada_no_devuelven_contrasenas(self):
        for payload in ({'password':'SENSITIVE-TEST-ONLY'},
                        {'username':'customer', 'fullName':'Customer','password':'p@ss-9'},
                        {'username':'customer', 'fullName':'Customer','password':self.password,'role':'superadmin'}):
            response = self.client.post('/api/platform/organizations/1/administrators', headers=self.owner, json=payload)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertNotIn(payload['password'],response.text)
            self.assertNotIn('input',response.text)

    def test_instalacion_nueva_registra_administrador_y_permite_alta_de_operador(self):
        engine = create_engine(f'sqlite:///{(self.root / "fresh.db").as_posix()}', connect_args={'check_same_thread':False})
        self.addCleanup(engine.dispose)
        event.listen(engine,'connect',enable_sqlite_foreign_keys)
        Base.metadata.create_all(engine)
        Session = sessionmaker(engine)
        with Session() as db:
            db.add(Organization(id=1,name='Fresh Company'))
            db.add(User(id=90,username='fresh-owner',full_name='Fresh Owner',password_hash=self.hashed))
            db.commit()
        with Session() as db:
            bootstrap_owner.assign_first_owner(db,90)
        def fresh_db():
            with Session(info={'organization_required':True}) as db:
                yield db
        original = app.dependency_overrides[get_db]
        app.dependency_overrides[get_db] = fresh_db
        try:
            response = self.client.post('/api/platform/organizations/1/administrators',
                headers={'Authorization':'Bearer '+create_access_token(90)},
                json={'username':'fresh-admin','fullName':'Fresh Admin','password':self.password})
            self.assertEqual(response.status_code,201,response.text)
            login = self.client.post('/api/auth/login',data={'username':'fresh-admin','password':self.password})
            operator = self.client.post('/api/users',headers={'Authorization':'Bearer '+login.json()['access_token']},
                json={'username':'fresh-operator','fullName':'Fresh Operator','password':self.password,'role':'operador'})
            self.assertEqual(operator.status_code,201,operator.text)
            with Session() as db:
                self.assertEqual(set(db.scalars(select(Role.name))),{'administrador','operador','revisor'})
        finally:
            app.dependency_overrides[get_db] = original

    def test_suspension_deniega_operaciones_y_fotos_sin_reactivar_membresias_revocadas(self):
        issued_b = self.auth('adminB')
        with self.Session() as db:
            db.get(OrganizationMembership, (2,self.users['shared'],3)).is_active = False
            db.commit()
        photos = {p: p.read_bytes() for p in (self.root / 'images').rglob('*.jpg')}
        status = '/api/platform/organizations/2/status'
        self.assertEqual(self.client.patch(status, headers=self.owner, json={'isActive': False}).status_code, 200)
        self.assertEqual(self.client.get('/api/lots', headers=issued_b).status_code, 403)
        self.assertEqual(self.client.get('/api/images/I-000002', headers=issued_b).status_code, 403)
        self.assertEqual(self.client.get('/api/lots', headers=self.auth('adminA')).status_code, 200)
        denied = self.client.put(f'/api/platform/organizations/2/administrators/{self.users["operatorA"]}', headers=self.owner)
        self.assertEqual(denied.status_code, 409)
        self.assertEqual(self.client.patch(status, headers=self.owner, json={'isActive': True}).status_code, 200)
        self.assertEqual(self.client.get('/api/lots', headers=issued_b).status_code, 200)
        self.assertEqual(self.client.get('/api/lots', headers=self.auth('shared',2)).status_code, 403)
        self.assertEqual(photos, {p: p.read_bytes() for p in photos})

    def test_propietario_revocado_y_usuario_inactivo_pierden_el_panel(self):
        self.assertEqual(self.client.get('/api/platform/metrics', headers=self.owner).status_code, 200)
        with self.Session() as db:
            db.get(User, self.users['without_membership']).is_active = False
            db.commit()
        self.assertEqual(self.client.get('/api/platform/metrics', headers=self.owner).status_code, 401)
        with self.Session() as db:
            db.get(User, self.users['without_membership']).is_active = True
            db.delete(db.get(PlatformOwner,1))
            db.commit()
        self.assertEqual(self.client.get('/api/platform/metrics', headers=self.owner).status_code, 403)

    def test_login_propietario_sin_membresia_y_operaciones_globales_bloqueadas(self):
        login = self.client.post('/api/auth/login', data={'username': 'without_membership', 'password': self.password})
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.json()['is_superadmin'])
        self.assertFalse(self.client.post('/api/auth/login', data={'username': 'adminA', 'password': self.password}).json()['is_superadmin'])
        for method,path in (('GET','/api/iot/status'),('POST','/api/admin/backups'),('POST','/api/admin/backups/restore')):
            self.assertEqual(self.client.request(method,path,headers=self.owner,json={}).status_code,403 if '/iot/' in path else 503)

    def test_bootstrap_check_solo_lectura_y_no_crea_archivos_si_falta_la_base(self):
        with self.Session() as db:
            db.delete(db.get(PlatformOwner,1)); db.commit()
        database = Path(self.engine.url.database)
        before = database.read_bytes()
        with patch.object(bootstrap_owner,'SessionLocal',self.Session), redirect_stdout(io.StringIO()):
            self.assertEqual(bootstrap_owner.main(['--check']),0)
        self.assertEqual(database.read_bytes(),before)
        missing = self.root/'absent.db'
        engine = create_engine(f'sqlite:///{missing.as_posix()}')
        self.addCleanup(engine.dispose)
        with patch.object(bootstrap_owner,'SessionLocal',sessionmaker(engine)), redirect_stdout(io.StringIO()):
            self.assertEqual(bootstrap_owner.main(['--check']),1)
        self.assertFalse(missing.exists())

    def test_bootstrap_cancela_si_la_consola_no_puede_ocultar_la_clave(self):
        with self.Session() as db:
            db.delete(db.get(PlatformOwner,1)); db.commit()
        def insecure_prompt(_):
            warnings.warn('No echo control', bootstrap_owner.GetPassWarning)
            self.fail('No debe leer una contraseña mediante entrada visible')
        with patch.object(bootstrap_owner,'SessionLocal',self.Session), \
                patch('builtins.input',side_effect=['private-owner','Private Owner']), \
                patch.object(bootstrap_owner,'getpass',side_effect=insecure_prompt), redirect_stdout(io.StringIO()):
            self.assertEqual(bootstrap_owner.main(['--create-user']),1)
        with self.Session() as db:
            self.assertIsNone(db.get(PlatformOwner,1))
            self.assertIsNone(db.scalar(select(User).where(User.username=='private-owner')))


if __name__ == '__main__':
    unittest.main()
