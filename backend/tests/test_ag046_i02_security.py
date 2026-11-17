"""AG-046 I02: auditoría de seguridad de API con SQLite y usuarios sintéticos.

No usa backend/data/agroscan.db, imágenes reales, hardware ni credenciales personales.
Ejecutar con AGROSCAN_JWT_SECRET sintético en el entorno del proceso de pruebas.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.organization_models import Organization, OrganizationMembership
from app.database import Base, get_db
from app.main import app
from app.models import Evaluation, Image, Lot, Measurement, Review, Role, User
from app.routers import backup as backup_router
from app.routers import review_decisions
from app.security import JWT_SECRET, create_access_token, hash_password

PASSWORD_TEST = 'Ag046-ClaveSintetica-NoUsarFueraDePruebas-2026!'


class AG046I02SecurityTests(unittest.TestCase):
    """Solo almacena datos generados en un TemporaryDirectory por prueba."""

    @classmethod
    def setUpClass(cls):
        if os.getenv('AGROSCAN_JWT_SECRET') != JWT_SECRET:
            raise RuntimeError('I02 exige AGROSCAN_JWT_SECRET explícito para las pruebas')
        cls.password_hash = hash_password(PASSWORD_TEST)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ag046-i02-security-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = create_engine(
            'sqlite:///' + str(self.root / 'security.sqlite'),
            connect_args={'check_same_thread': False, 'timeout': 5},
        )
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(Organization.__table__.insert().values(id=1, name="AgroScan Inicial", is_active=True))
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, info={"organization_id": 1})
        self.ids = {}
        with self.Session() as db:
            for role in ('operador', 'revisor', 'administrador'):
                user = User(
                    username=f'ag046_{role}', full_name=f'AG046 {role}',
                    password_hash=self.password_hash, is_active=True,
                    roles=[Role(name=role)],
                )
                db.add(user)
                db.flush()
                db.add(OrganizationMembership(organization_id=1, user_id=user.id, role_id=user.roles[0].id))
                self.ids[role] = user.id
            lot = Lot(code='AG046-I02', product='tomate', status='open')
            db.add(lot)
            db.flush()
            evaluation = Evaluation(
                lot_id=lot.id, piece_id='AG046-PZ-01', product='tomate',
                status='pending_review', image_count=1,
            )
            db.add(evaluation)
            db.flush()
            self.evaluation_pk = evaluation.id
            relative = 'images/AG046/evidence.jpg'
            image_file = self.root / relative
            image_file.parent.mkdir(parents=True, exist_ok=True)
            image_bytes = b'\xff\xd8\xffAG046 - SOLO EVIDENCIA SINTETICA\xff\xd9'
            image_file.write_bytes(image_bytes)
            image = Image(
                evaluation_id=evaluation.id, view='frontal',
                relative_path=relative, content_type='image/jpeg',
                size_bytes=len(image_bytes),
            )
            db.add(image)
            db.flush()
            self.image_pk = image.id
            db.commit()

        def isolated_db():
            with self.Session() as db:
                yield db

        # Nunca sobrescribir otras dependencias presentes en la sesión de pruebas.
        previous = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = isolated_db
        def restore_override():
            if previous is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = previous
        self.addCleanup(restore_override)

        for target in ('app.routers.review_decisions.DATA_DIR', 'app.review_queue.DATA_DIR'):
            p = patch(target, self.root)
            p.start()
            self.addCleanup(p.stop)

        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.evaluation_id = f'E-{self.evaluation_pk:06d}'
        self.image_id = f'I-{self.image_pk:06d}'
        self.decision_url = f'/api/evaluations/{self.evaluation_id}/review-decisions'

    def auth(self, role):
        return {'Authorization': 'Bearer ' + create_access_token(self.ids[role])}

    def counts(self):
        with self.Session() as db:
            return (
                db.scalar(select(func.count(User.id))),
                db.scalar(select(func.count(Review.id))),
                db.scalar(select(func.count(Measurement.id))),
            )

    def decision_body(self):
        return {
            'action': 'initial_label', 'imageId': self.image_id,
            'newValue': 'E1',
            'reason': 'Evaluación únicamente con bytes de prueba AG046',
            'expectedReviewId': None, 'requestId': str(uuid4()),
        }

    def test_sec01_rechaza_secreto_corto_y_algoritmo_no_autorizado(self):
        """Fallo aislado de importación, sin leer ni registrar secretos reales."""
        backend = Path(__file__).resolve().parents[1]
        cases = (
            ('corto', {'AGROSCAN_JWT_SECRET': 'corto', 'AGROSCAN_JWT_ALGORITHM': 'HS256'}),
            ('algoritmo', {'AGROSCAN_JWT_SECRET': 'A' * 40, 'AGROSCAN_JWT_ALGORITHM': 'HS384'}),
        )
        for label, overrides in cases:
            with self.subTest(case=label):
                env = os.environ.copy()
                env.update(overrides)
                env['PYTHONPATH'] = str(backend)
                result = subprocess.run(
                    [sys.executable, '-c', 'import app.security'],
                    cwd=backend, env=env, capture_output=True,
                    text=True, errors='replace', timeout=25, check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('RuntimeError', result.stderr)
                self.assertNotIn('A' * 40, result.stderr)

    def test_sec02_tokens_invalidos_y_requisitos_de_claims(self):
        now = datetime.now(timezone.utc)
        uid = self.ids['revisor']
        base = {'sub': str(uid), 'iat': now, 'exp': now + timedelta(minutes=5)}
        samples = {
            'malformado': 'un.jwt.invalido',
            'firma_ajena': jwt.encode(base, 'Z' * 48, algorithm='HS256'),
            'algoritmo_ajeno': jwt.encode(base, JWT_SECRET, algorithm='HS384'),
            'expirado': jwt.encode({**base, 'exp': now - timedelta(seconds=5)}, JWT_SECRET, algorithm='HS256'),
            'sin_sub': jwt.encode({k: v for k, v in base.items() if k != 'sub'}, JWT_SECRET, algorithm='HS256'),
            'sin_iat': jwt.encode({k: v for k, v in base.items() if k != 'iat'}, JWT_SECRET, algorithm='HS256'),
            'sin_exp': jwt.encode({k: v for k, v in base.items() if k != 'exp'}, JWT_SECRET, algorithm='HS256'),
            'sub_inexistente': create_access_token(99999999),
        }
        for label, token in samples.items():
            with self.subTest(case=label):
                response = self.client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + token})
                self.assertEqual(response.status_code, 401, f'{label}: {response.text}')
                self.assertNotIn(token, response.text)

    def test_sec03_login_y_hash_no_revelan_credenciales(self):
        response = self.client.post('/api/auth/login', data={
            'username': 'ag046_operador', 'password': PASSWORD_TEST,
        })
        self.assertEqual(response.status_code, 200, response.text)
        token = response.json()['access_token']
        self.assertEqual(response.json()['token_type'], 'bearer')
        who = self.client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + token})
        self.assertEqual(who.status_code, 200)
        self.assertEqual(who.json()['roles'], ['operador'])
        with self.Session() as db:
            user = db.get(User, self.ids['operador'])
            self.assertNotEqual(user.password_hash, PASSWORD_TEST)
            self.assertTrue(user.password_hash.startswith('$argon2'))
        self.assertNotIn(PASSWORD_TEST, response.text)

    def test_sec03_login_invalido_y_usuario_inactivo(self):
        for username, password in (('ag046_operador', 'contraseña_incorrecta'), ('desconocido', PASSWORD_TEST)):
            result = self.client.post('/api/auth/login', data={'username': username, 'password': password})
            self.assertEqual(result.status_code, 401)
        issued = self.auth('operador')
        with self.Session() as db:
            db.get(User, self.ids['operador']).is_active = False
            db.commit()
        self.assertEqual(self.client.get('/api/auth/me', headers=issued).status_code, 401)
        result = self.client.post('/api/auth/login', data={'username': 'ag046_operador', 'password': PASSWORD_TEST})
        self.assertEqual(result.status_code, 401)

    def test_sec05_rutas_protegidas_requieren_token_sin_modificaciones(self):
        before = self.counts()
        paths = (
            '/api/auth/me', '/api/lots', '/api/evaluations',
            f'/api/evaluations/{self.evaluation_id}/traceability',
            f'/api/images/{self.image_id}', '/api/users',
            '/api/reviews/queue',
            self.decision_url,
        )
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                # El contrato de acceso requiere autenticación antes del recurso.
                self.assertEqual(response.status_code, 401, f'{path}: {response.text}')
        self.assertEqual(self.counts(), before)

    def test_sec06_operador_no_puede_corregir_anular_ni_decidir(self):
        before = self.counts()
        credential = self.auth('operador')
        requests = (
            ('reviews', self.client.post(f'/api/evaluations/{self.evaluation_id}/reviews',
                headers=credential, json={'actorId': 'forjado', 'reason': 'Motivo sintético de prueba', 'newValue': 'E1'})),
            ('cancel', self.client.post(f'/api/evaluations/{self.evaluation_id}/cancel',
                headers=credential, json={'actorId': 'forjado', 'reason': 'Motivo sintético de prueba'})),
            ('decision', self.client.post(self.decision_url, headers=credential, json=self.decision_body())),
        )
        for label, response in requests:
            with self.subTest(operation=label):
                self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.counts(), before)

    def test_sec07_revisor_registra_decision_real_y_no_puede_anular(self):
        reviewer = self.auth('revisor')
        reply = self.client.post(self.decision_url, headers=reviewer, json=self.decision_body())
        self.assertEqual(reply.status_code, 201, reply.text)
        self.assertEqual(reply.json()['actorId'], 'ag046_revisor')
        with self.Session() as db:
            reviews = list(db.scalars(select(Review)).all())
            self.assertEqual(len(reviews), 1)
            self.assertEqual(reviews[0].actor_id, 'ag046_revisor')
        forbidden = self.client.post(f'/api/evaluations/{self.evaluation_id}/cancel',
            headers=reviewer, json={'actorId': 'ag046_revisor', 'reason': 'Solo test'})
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(self.counts()[1], 1)

    def test_sec08_administracion_denegada_a_no_admin(self):
        before = self.counts()
        payload = {'username': 'otro_ag046', 'fullName': 'Prueba adicional',
                   'password': PASSWORD_TEST, 'role': 'operador'}
        for role in ('operador', 'revisor'):
            headers = self.auth(role)
            checks = (
                self.client.get('/api/users', headers=headers),
                self.client.post('/api/users', headers=headers, json=payload),
                self.client.patch(f'/api/users/{self.ids["operador"]}/role',
                    headers=headers, json={'role': 'administrador'}),
                self.client.patch(f'/api/users/{self.ids["operador"]}/status',
                    headers=headers, json={'isActive': False}),
            )
            for response in checks:
                with self.subTest(role=role):
                    self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.counts(), before)

    def test_sec08_admin_puede_gestionar_usuarios_sinteticos(self):
        headers = self.auth('administrador')
        self.assertEqual(self.client.get('/api/users', headers=headers).status_code, 200)
        created = self.client.post('/api/users', headers=headers, json={
            'username': 'nuevo_ag046', 'fullName': 'Nuevo AG046',
            'password': PASSWORD_TEST, 'role': 'operador',
        })
        self.assertEqual(created.status_code, 201, created.text)
        new_id = created.json()['id']
        changed = self.client.patch(f'/api/users/{new_id}/role',
            headers=headers, json={'role': 'revisor'})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()['roles'], ['revisor'])
        inactive = self.client.patch(f'/api/users/{new_id}/status',
            headers=headers, json={'isActive': False})
        self.assertEqual(inactive.status_code, 200)
        self.assertFalse(inactive.json()['isActive'])

    def test_token_emitido_pierde_privilegios_al_cambiar_rol(self):
        credential = self.auth('administrador')
        self.assertEqual(self.client.get('/api/users', headers=credential).status_code, 200)
        with self.Session() as db:
            user = db.get(User, self.ids['administrador'])
            memberships = db.scalars(select(OrganizationMembership).where(OrganizationMembership.user_id == user.id)).all()
            for membership in memberships:
                db.delete(membership)
            db.flush()
            db.add(OrganizationMembership(organization_id=1, user_id=user.id, role_id=db.scalar(select(Role.id).where(Role.name == 'operador'))))
            db.commit()
        # El mismo JWT debe consultar permisos vigentes, sin esperar su expiración.
        self.assertEqual(self.client.get('/api/users', headers=credential).status_code, 403)
        with patch.object(backup_router, 'create_backup') as backup_mock:
            self.assertEqual(self.client.post('/api/admin/backups', headers=credential).status_code, 503)
            backup_mock.assert_not_called()

    def test_sec09_respaldo_y_restore_bloqueados_hasta_saas07(self):
        before = self.counts()
        with patch.object(backup_router, 'create_backup') as create, patch.object(backup_router, 'restore_backup') as restore:
            for role in ('operador', 'revisor', 'administrador', None):
                headers = self.auth(role) if role else {}
                self.assertEqual(self.client.post('/api/admin/backups', headers=headers).status_code, 503)
                self.assertEqual(self.client.post('/api/admin/backups/restore', headers=headers,
                    files={'file': ('respaldo.zip', b'SYNTHETIC', 'application/zip')}).status_code, 503)
            create.assert_not_called()
            restore.assert_not_called()
        self.assertEqual(self.counts(), before)

    def test_sec09_bloqueo_respaldo_no_crea_archivos(self):
        destination = self.root / 'not-created'
        with patch.object(backup_router, 'BACKUP_DIR', destination):
            response = self.client.post('/api/admin/backups/restore', headers=self.auth('administrador'),
                files={'file': ('respaldo.zip', b'SYNTHETIC', 'application/zip')})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(destination.exists())

    def test_sec10_bandeja_acceso_por_rol(self):
        self.assertEqual(self.client.get('/api/reviews/queue').status_code, 401)
        self.assertEqual(self.client.get('/api/reviews/queue', headers=self.auth('operador')).status_code, 403)
        for role in ('revisor', 'administrador'):
            reply = self.client.get('/api/reviews/queue', headers=self.auth(role))
            self.assertEqual(reply.status_code, 200, reply.text)
            self.assertIn('items', reply.json())

    def test_sec11_iot_sin_credencial_dispositivo_observacion_no_aprobacion(self):
        """Caracteriza H01. Un HTTP 200 prueba ausencia del control, NO seguridad."""
        before = self.counts()[2]
        response = self.client.post('/api/iot/measurements', json={
            'schema_version': 1, 'device_id': 'AG046-FAKE',
            'boot_id': 'boot-test', 'seq': 1, 'weight_g': 183.0,
            'stable': True, 'zero_confirmed': True,
            'calibration_version': 'AG046-TEST',
            'observed_at': datetime.now(timezone.utc).isoformat(),
        })
        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(self.counts()[2], before)
        # SEC-11 continuará PENDIENTE DE POLÍTICA/ENDURECIMIENTO.

    def test_sec12_permisos_distintos_para_anotacion_y_decision_formal(self):
        """Solo caracterización. La aprobación de política corresponde al equipo."""
        url = '/api/evaluations/E-999999/vision/quality/reviews'
        payload = {
            'imageId': 'I-999999', 'predictionId': 999999,
            'grade': 'E1', 'roi': [0, 0, 10, 10],
            'roiConfirmed': True, 'humanConfirmed': True,
            'rubricVersion': 'ag046-test-v1',
            'evidence': 'Anotación exclusivamente sintética para prueba de permisos',
            'expectedLastEventId': None,
        }
        reviewer = self.client.post(url, headers=self.auth('revisor'), json=payload)
        operator = self.client.post(url, headers=self.auth('operador'), json=payload)
        self.assertEqual(reviewer.status_code, 404, reviewer.text)
        self.assertEqual(operator.status_code, 404, operator.text)
        self.assertEqual(self.counts(), (3, 0, 0))


if __name__ == '__main__':
    unittest.main()
