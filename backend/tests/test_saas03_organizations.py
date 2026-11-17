"""Aislamiento HTTP/ORM/SQLite con dos organizaciones y evidencia sintética."""
import hashlib
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database import Base, enable_sqlite_foreign_keys, get_db
from app.dependencies import block_global_operations, require_operational_context
from app.main import app
from app.models import Evaluation, Image, Lot, Measurement, Piece, Review, Role, User
from app.iot_models import IotStation, IotDevice
from app.organization_models import Organization, OrganizationMembership
from app.quality_prediction_models import QualityPrediction
from app.fruit_geometry_models import FruitGeometry
from app.planar_calibration_models import PlanarCalibration
from app.board_calibration_models import BoardCalibration, DimensionalComparison
from app.auto_registration_models import VisionPrecheck
from app.security import create_access_token, hash_password
from app.vision_assessment_models import VisionAssessment


class OrganizationIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = 'SaaS03-Synthetic-Password-Only!'
        cls.hashed = hash_password(cls.password)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='saas03-isolation-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.engine = create_engine(f'sqlite:///{(self.root / "test.db").as_posix()}',
                                    connect_args={'check_same_thread': False})
        self.addCleanup(self.engine.dispose)
        event.listen(self.engine, 'connect', enable_sqlite_foreign_keys)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        self.users = {}
        with self.Session() as db:
            db.add_all([Organization(id=1, name='Empresa A'), Organization(id=2, name='Empresa B')])
            db.add_all([Role(id=1, name='administrador'), Role(id=2, name='operador'), Role(id=3, name='revisor')])
            db.flush()
            for name in ('adminA', 'adminB', 'operatorA', 'shared', 'without_membership'):
                user = User(username=name, full_name=name, password_hash=self.hashed,
                            is_active=True, roles=[db.get(Role, 1)])
                db.add(user)
                db.flush()
                self.users[name] = user.id
            for name, org, role in (('adminA', 1, 1), ('adminB', 2, 1), ('operatorA', 1, 2),
                                    ('shared', 1, 2), ('shared', 2, 3)):
                db.add(OrganizationMembership(user_id=self.users[name], organization_id=org, role_id=role))
            for org in (1, 2):
                db.add(IotStation(id=org, organization_id=org, code='test', name='Test'))
            db.flush()
            for org in (1, 2):
                db.add(IotDevice(id=org, organization_id=org, station_id=org, device_id='shared-device'))
            db.flush()
            for org in (1, 2):
                db.add(Lot(id=org, organization_id=org, code='SHARED', product='mango'))
                db.add(Measurement(id=org, organization_id=org, device_id='shared-device',
                    boot_id='same-boot', seq=1, weight_g=100 * org, stable=True, calibration_version='test'))
            db.flush()
            db.add(Lot(id=3, organization_id=2, code='B-ONLY', product='mango'))
            for org in (1, 2):
                db.add(Piece(id=org, organization_id=org, lot_id=org, code=f'PIECE-{org}'))
            db.flush()
            for org in (1, 2):
                db.add(Evaluation(id=org, organization_id=org, lot_id=org, piece_ref_id=org,
                    piece_id=f'PIECE-{org}', product='mango', status='pending_review', image_count=1,
                    weight_pre_measurement_id=org))
            db.flush()
            self.photo_bytes = {}
            for org in (1, 2):
                relative = f'images/E-{org:06d}/evidence.jpg'
                content = b'\xff\xd8\xffSYNTHETIC-' + str(org).encode() + b'\xff\xd9'
                self.photo_bytes[org] = content
                target = self.root / relative
                target.parent.mkdir(parents=True)
                target.write_bytes(content)
                db.add(Image(id=org, organization_id=org, evaluation_id=org, view='front',
                    relative_path=relative, content_type='image/jpeg', size_bytes=len(content)))
            db.flush()
            for org in (1, 2):
                db.add(VisionAssessment(organization_id=org, evaluation_id=org, image_id=org,
                    image_sha256=hashlib.sha256(self.photo_bytes[org]).hexdigest(),
                    model_version=f'model-{org}', rules_version='test', inference_size=512,
                    inference_confidence=.25, acceptance_threshold=.4, outcome='pending_review',
                    reason=f'org-{org}', confidence=.9, candidate_count=1, detections_json='[]'))
                db.add(QualityPrediction(organization_id=org, evaluation_id=org, product='mango',
                    source_fingerprint=str(org)*64, model_sha256=str(org)*64, model_version=f'model-{org}',
                    status='test', reason=f'org-{org}', details_json='{}'))
                db.add(FruitGeometry(id=org, organization_id=org, evaluation_id=org, image_id=org,
                    image_sha256=str(org)*64, model_version=f'model-{org}', rules_version='test',
                    status='test', reason='test', candidate_count=1, frame_width=10, frame_height=10,
                    box_json='[]', polygon_json='[]', measurements_json='{}'))
            db.flush()
            for org in (1, 2):
                common = dict(organization_id=org, evaluation_id=org, image_id=org, geometry_id=org,
                    operator_id=self.users['adminA' if org == 1 else 'adminB'],
                    image_sha256=str(org)*64, model_version=f'model-{org}', rules_version='test',
                    status='test', reason='test', platform_level_declared=True, measurements_json='{}')
                # Planar usa un nombre distinto para la declaración del plano.
                planar = {key: value for key, value in common.items() if key != 'platform_level_declared'}
                db.add(PlanarCalibration(id=org, **planar, platform_plane_declared=True,
                    marker_id=0, marker_side_mm=30, marker_corners_json='[]'))
                db.add(BoardCalibration(id=org, **common, board_version='test', marker_ids_json='[]',
                    corners_json='[]', independent_support_declared=True,
                    printed_scale_verified_declared=True, fixed_camera_declared=True))
            db.flush()
            for org in (1, 2):
                db.add(DimensionalComparison(id=org, organization_id=org, board_calibration_id=org,
                    operator_id=self.users['adminA' if org == 1 else 'adminB'], rules_version='test',
                    major_manual_cm=10, minor_manual_cm=5, instrument_id=f'org-{org}',
                    comparison_json=json.dumps({'major': {'absoluteErrorCm': org, 'relativeAbsoluteErrorPct': org},
                                                'minor': {'absoluteErrorCm': org}})))
                db.add(VisionPrecheck(token=str(org)*64, organization_id=org,
                    operator_id=self.users['adminA' if org == 1 else 'adminB'], product='mango',
                    confidence=.9, image_sha256=hashlib.sha256(self.photo_bytes[org]).hexdigest(),
                    registered_lot_id=org, evaluation_id=org))
            db.commit()

        def isolated_db():
            with self.Session(info={'organization_required': True}) as db:
                yield db
        self.previous = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = isolated_db
        self.addCleanup(self.restore_override)
        for target in ('app.routers.images.DATA_DIR', 'app.routers.review_decisions.DATA_DIR',
                       'app.routers.uncertainty.DATA_DIR', 'app.review_queue.DATA_DIR'):
            mocked = patch(target, self.root)
            mocked.start()
            self.addCleanup(mocked.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def restore_override(self):
        if self.previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = self.previous

    def auth(self, name='adminA', org=None):
        headers = {'Authorization': 'Bearer ' + create_access_token(self.users[name])}
        if org is not None:
            headers['X-Organization-ID'] = str(org)
        return headers

    def test_login_compatible_contexto_autorizado_y_roles_de_membresia(self):
        login = self.client.post('/api/auth/login', data={'username': 'adminA', 'password': self.password})
        self.assertEqual(login.status_code, 200)
        me = self.client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + login.json()['access_token']})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()['organizationId'], 1)
        self.assertEqual(self.client.get('/api/lots', headers=self.auth(org=2)).status_code, 403)
        self.assertEqual(self.client.get('/api/lots', headers=self.auth(org='invalid')).status_code, 400)
        self.assertEqual(self.client.get('/api/lots', headers=self.auth('without_membership')).status_code, 403)
        self.assertEqual(self.client.get('/api/users', headers=self.auth('operatorA')).status_code, 403)
        self.assertEqual(self.client.get('/api/auth/me', headers=self.auth('shared')).status_code, 409)
        mine = self.client.get('/api/auth/organizations', headers=self.auth())
        shared = self.client.get('/api/auth/organizations', headers=self.auth('shared'))
        self.assertEqual([item['id'] for item in mine.json()], [1])
        self.assertEqual([item['id'] for item in shared.json()], [1, 2])
        for org, role in ((1, 'operador'), (2, 'revisor')):
            me = self.client.get('/api/auth/me', headers=self.auth('shared', org))
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()['roles'], [role])
        self.assertEqual(self.client.post('/api/evaluations', headers=self.auth('shared', 2),
            json={'lotId': 'SHARED', 'pieceId': 'FORBIDDEN'}).status_code, 403)

    def test_todas_las_rutas_operativas_exigen_contexto_o_estan_bloqueadas(self):
        protected = 0
        for path, methods in app.openapi()['paths'].items():
            if path in ('/api/auth/login', '/api/health', '/api/auth/google/config', '/api/auth/google/challenge',
                        '/api/auth/google/login', '/api/auth/google/accept-invitation',
                        '/api/auth/invitations/preview', '/api/auth/invitations/register'):
                continue
            url = (path.replace('{evaluation_id}', 'E-000001').replace('{image_id}', 'I-000001')
                   .replace('{lot_id}', '1').replace('{user_id}', '1')
                   .replace('{lot_code}', 'SHARED').replace('{piece_code}', 'PIECE-1'))
            for method in methods:
                if method.upper() not in ('GET', 'POST', 'PATCH', 'PUT', 'DELETE'):
                    continue
                with self.subTest(path=path, method=method):
                    response = self.client.request(method, url, json={})
                    expected = 503 if path.startswith('/api/admin/backups') else 401
                    self.assertEqual(response.status_code, expected, response.text)
                    protected += 1
        self.assertGreater(protected, 50)

    def test_ids_ajenos_bloqueados_en_todas_las_subrutas_antes_del_cuerpo(self):
        checked = 0
        for path, methods in app.openapi()['paths'].items():
            if not any(token in path for token in ('{evaluation_id}', '{image_id}', '{lot_id}')):
                continue
            url = path.replace('{evaluation_id}', 'E-000002').replace('{image_id}', 'I-000002').replace('{lot_id}', '2')
            for method in methods:
                if method.upper() not in ('GET', 'POST', 'PATCH', 'PUT', 'DELETE'):
                    continue
                with self.subTest(path=path, method=method):
                    response = self.client.request(method, url, headers=self.auth(), json={})
                    self.assertEqual(response.status_code, 404, response.text)
                    checked += 1
        self.assertGreater(checked, 30)

    def test_consultas_historial_reportes_y_resultados_solo_de_la_empresa(self):
        for name, org in (('adminA', 1), ('adminB', 2)):
            headers = self.auth(name)
            evaluations = self.client.get('/api/evaluations', headers=headers)
            self.assertEqual(evaluations.status_code, 200, evaluations.text)
            self.assertEqual([row['id'] for row in evaluations.json()], [f'E-{org:06d}'])
            history = self.client.get('/api/piece-history?lot=SHARED', headers=headers)
            self.assertEqual(history.status_code, 200, history.text)
            self.assertEqual(history.json()['attemptCount'], 1)
            self.assertEqual(history.json()['pieces'][0]['pieceCode'], f'PIECE-{org}')
            for endpoint in ('traceability', 'vision/assessments', 'vision/quality/proposals', 'vision/geometry',
                             f'vision/physical/I-{org:06d}', f'vision/board/I-{org:06d}',
                             f'vision/board/I-{org:06d}/comparisons'):
                reply = self.client.get(f'/api/evaluations/E-{org:06d}/{endpoint}', headers=headers)
                self.assertEqual(reply.status_code, 200, reply.text)
                self.assertNotIn(f'model-{3-org}', reply.text)
            report = self.client.get('/api/piece-history/report?lot=SHARED', headers=headers)
            self.assertEqual(report.status_code, 200, report.text)
            self.assertNotIn(f'PIECE-{3-org}', report.text)
            queue = self.client.get('/api/reviews/queue', headers=headers)
            self.assertEqual(queue.status_code, 200, queue.text)
            self.assertNotIn(f'E-{3-org:06d}', queue.text)
            board = self.client.get('/api/evaluations/vision/board-validation/report', headers=headers)
            self.assertEqual(board.status_code, 200, board.text)
            self.assertEqual(board.json()['products']['mango']['sampleCount'], 1)
            self.assertEqual(board.json()['products']['mango']['meanAbsoluteErrorMajorCm'], org)
        self.assertEqual(self.client.get('/api/piece-history?lot=B-ONLY', headers=self.auth()).status_code, 404)
        self.assertEqual(self.client.get('/api/piece-history/SHARED/PIECE-2', headers=self.auth()).status_code, 404)

    def test_fotografias_y_relaciones_indirectas(self):
        for name, own, foreign in (('adminA', 1, 2), ('adminB', 2, 1)):
            reply = self.client.get(f'/api/images/I-{own:06d}', headers=self.auth(name))
            self.assertEqual(reply.status_code, 200)
            self.assertEqual(reply.content, self.photo_bytes[own])
            self.assertEqual(self.client.get(f'/api/images/I-{foreign:06d}', headers=self.auth(name)).status_code, 404)
            body = {'action': 'initial_label', 'imageId': f'I-{foreign:06d}', 'newValue': 'E1',
                'reason': 'Revisión sintética con imagen de otra empresa', 'expectedReviewId': None, 'requestId': str(uuid4())}
            reply = self.client.post(f'/api/evaluations/E-{own:06d}/review-decisions', headers=self.auth(name), json=body)
            self.assertEqual(reply.status_code, 404, reply.text)
            body['imageId'] = f'I-{own:06d}'
            reply = self.client.post(f'/api/evaluations/E-{own:06d}/review-decisions', headers=self.auth(name), json=body)
            self.assertEqual(reply.status_code, 201, reply.text)

    def test_identificadores_en_cuerpos_no_permiten_referencias_ajenas(self):
        reply = self.client.post('/api/evaluations/auto', headers=self.auth(),
            json={'lotId': 'SHARED', 'detectionToken': '2'*64})
        self.assertEqual(reply.status_code, 404, reply.text)
        with self.Session() as db:
            self.assertEqual(db.get(VisionPrecheck, '2'*64).registration_claims, 0)
        own = self.client.post('/api/evaluations/auto', headers=self.auth(),
            json={'lotId': 'SHARED', 'detectionToken': '1'*64})
        self.assertEqual(own.status_code, 201, own.text)
        self.assertEqual(own.json()['id'], 'E-000001')
        comparison = self.client.post('/api/evaluations/E-000001/vision/board/I-000001/comparisons',
            headers=self.auth(), json={'boardCalibrationId': 2, 'referenceMajorCm': 10,
                                      'referenceMinorCm': 5, 'instrumentId': 'synthetic'})
        self.assertEqual(comparison.status_code, 409, comparison.text)
        missing = self.client.post('/api/evaluations/E-000001/vision/board/I-000001/comparisons',
            headers=self.auth(), json={'boardCalibrationId': 999999, 'referenceMajorCm': 10,
                                      'referenceMinorCm': 5, 'instrumentId': 'synthetic'})
        self.assertEqual(comparison.json(), missing.json())
        review = self.client.post('/api/evaluations/E-000001/vision/quality/reviews', headers=self.auth(),
            json={'imageId': 'I-000001', 'predictionId': 2, 'grade': 'E1', 'roi': [0,0,10,10],
                  'roiConfirmed': True, 'humanConfirmed': True, 'rubricVersion': 'test',
                  'evidence': 'Prueba sintética de aislamiento de predicciones', 'expectedLastEventId': None})
        self.assertEqual(review.status_code, 404, review.text)

    def test_escrituras_y_codigos_por_organizacion(self):
        payload = {'code': 'shared', 'product': 'mango', 'responsible': 'Test'}
        self.assertEqual(self.client.post('/api/lots', headers=self.auth(), json=payload).status_code, 409)
        payload.update(code='B-ONLY', organization_id=2)
        reply = self.client.post('/api/lots', headers=self.auth(), json=payload)
        self.assertEqual(reply.status_code, 201, reply.text)
        with self.Session() as db:
            self.assertEqual(db.get(Lot, reply.json()['id']).organization_id, 1)
        reply = self.client.post('/api/evaluations', headers=self.auth(),
            json={'lotId': 'B-ONLY', 'pieceId': 'NEW-A', 'organization_id': 2})
        self.assertEqual(reply.status_code, 201, reply.text)
        with self.Session() as db:
            row = db.scalar(select(Evaluation).where(Evaluation.piece_id == 'NEW-A'))
            self.assertEqual(row.organization_id, 1)
            self.assertNotEqual(row.lot_id, 3)

    def test_sqlite_rechaza_cruces_incluso_sin_filtros_orm(self):
        with self.Session() as db:
            db.add(Lot(id=4, organization_id=1, code='A-OTHER', product='mango'))
            db.add(Evaluation(id=4, organization_id=1, lot_id=1, piece_ref_id=1,
                              piece_id='ANOTHER', product='mango'))
            db.commit()
        attempts = [
            insert(Image).values(organization_id=1, evaluation_id=2, view='bad', relative_path='images/bad', content_type='image/png', size_bytes=1),
            insert(Evaluation).values(organization_id=1, lot_id=1, piece_ref_id=2, piece_id='bad', product='mango'),
            insert(Evaluation).values(organization_id=1, lot_id=1, piece_ref_id=1, piece_id='bad', product='mango', weight_pre_measurement_id=2),
            insert(Evaluation).values(organization_id=1, lot_id=4, piece_ref_id=1, piece_id='bad', product='mango'),
            insert(VisionAssessment).values(organization_id=1, evaluation_id=1, image_id=2, image_sha256='a'*64,
                model_version='bad', rules_version='bad', inference_size=1, inference_confidence=.1,
                acceptance_threshold=.1, outcome='bad', reason='bad', candidate_count=1, detections_json='[]'),
            insert(VisionAssessment).values(organization_id=1, evaluation_id=4, image_id=1, image_sha256='c'*64,
                model_version='bad', rules_version='bad', inference_size=1, inference_confidence=.1,
                acceptance_threshold=.1, outcome='bad', reason='bad', candidate_count=1, detections_json='[]'),
        ]
        for statement in attempts:
            with self.subTest(statement=str(statement)), self.assertRaises(IntegrityError):
                with self.engine.begin() as connection:
                    connection.execute(statement)
        with self.Session() as db:
            self.assertEqual(db.connection().exec_driver_sql('PRAGMA foreign_key_check').all(), [])

    def test_actualizaciones_masivas_y_sesion_sin_contexto_fallan_cerrado(self):
        with self.Session(info={'organization_id': 1, 'organization_required': True}) as db:
            self.assertIsNone(db.get(Evaluation, 2))
            changed = db.execute(update(Evaluation).where(Evaluation.id == 2).values(status='cancelled'))
            self.assertEqual(changed.rowcount, 0)
            db.commit()
        with self.Session(info={'organization_required': True}) as db:
            with self.assertRaisesRegex(Exception, 'contexto empresarial'):
                db.scalars(select(Lot)).all()

    def test_administracion_limitada_a_membresias_sin_afectar_otras_empresas(self):
        reply = self.client.get('/api/users', headers=self.auth())
        self.assertEqual({user['username'] for user in reply.json()}, {'adminA', 'operatorA', 'shared'})
        self.assertEqual(self.client.patch(f'/api/users/{self.users["adminB"]}/role',
            headers=self.auth(), json={'role': 'operador'}).status_code, 404)
        reply = self.client.patch(f'/api/users/{self.users["shared"]}/status',
            headers=self.auth('adminB'), json={'isActive': False})
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(self.client.get('/api/lots', headers=self.auth('shared', 1)).status_code, 200)
        self.assertEqual(self.client.get('/api/lots', headers=self.auth('shared', 2)).status_code, 403)
        with self.Session() as db:
            self.assertTrue(db.get(User, self.users['shared']).is_active)

    def test_iot_exige_identidad_y_respaldos_globales_siguen_bloqueados(self):
        for name in ('adminA', 'adminB', 'operatorA', 'shared'):
            for method, path in (('GET', '/api/iot/status'), ('POST', '/api/iot/measurements'),
                                 ('POST', '/api/admin/backups'), ('POST', '/api/admin/backups/restore')):
                with self.subTest(name=name, path=path):
                    expected = (409 if name == 'shared' else 200) if path == '/api/iot/status' else 401 if path == '/api/iot/measurements' else 503
                    self.assertEqual(self.client.request(method, path, headers=self.auth(name), json={}).status_code, expected)

    def test_solicitudes_simultaneas_no_comparten_contexto(self):
        def read(name):
            reply = self.client.get('/api/evaluations', headers=self.auth(name))
            self.assertEqual(reply.status_code, 200, reply.text)
            return name, [row['id'] for row in reply.json()]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(read, ['adminA', 'adminB'] * 4))
        for name, ids in results:
            self.assertEqual(ids, ['E-000001'] if name == 'adminA' else ['E-000002'])

    def test_cambios_de_rol_y_organizacion_revocan_tokens_ya_emitidos(self):
        shared_a = self.auth('shared', 1)
        shared_b = self.auth('shared', 2)
        response = self.client.patch(f'/api/users/{self.users["shared"]}/role',
            headers=self.auth(), json={'role': 'administrador'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get('/api/users', headers=shared_a).status_code, 200)
        self.assertEqual(self.client.get('/api/users', headers=shared_b).status_code, 403)
        self.assertEqual(self.client.get('/api/auth/me', headers=shared_b).json()['roles'], ['revisor'])
        issued = self.auth('adminB')
        with self.Session() as db:
            db.get(Organization, 2).is_active = False
            db.commit()
        self.assertEqual(self.client.get('/api/lots', headers=issued).status_code, 403)
        self.assertEqual(self.client.get('/api/lots', headers=self.auth()).status_code, 200)


if __name__ == '__main__':
    unittest.main()
