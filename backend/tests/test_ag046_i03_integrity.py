"""AG-046 I03: integridad y restauracion con SQLite/archivos descartables.

No usa backend/data/agroscan.db, fotografias reales, ESP32 ni base operativa.
Cada test crea y destruye su propia instancia aislada.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.organization_models import Organization, OrganizationMembership
from app.database import Base, enable_sqlite_foreign_keys, get_db
from app.decision_models import ReviewDecisionEvidence
from app.main import app
from app.models import Evaluation, Image, Lot, Piece, Review, Role, User
from app.routers import images as image_router, review_decisions
from app.security import create_access_token
from app.services import backup_service
from app.vision_assessment_models import VisionAssessment


# PNG pequeno de prueba (no es fotografia de una fruta).
PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAFElEQVR4nGM8ISfHAANMDEgANwcANHYBDK9qubUAAAAASUVORK5CYII='
)


class AG046I03IntegrityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='ag046-i03-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.data = self.root / 'data'
        self.data.mkdir()
        self.images = self.data / 'images'
        self.images.mkdir()
        self.backups = self.data / 'backups'
        self.backups.mkdir()
        self.db_file = self.data / 'agroscan.db'

        self.engine = create_engine(
            f'sqlite:///{self.db_file.as_posix()}',
            connect_args={'check_same_thread': False, 'timeout': 5},
        )
        event.listen(self.engine, 'connect', enable_sqlite_foreign_keys)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(Organization.__table__.insert().values(id=1, name="AgroScan Inicial", is_active=True))
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, info={"organization_id": 1})

        for module, attr, value in (
            (backup_service, 'DATA_DIR', self.data),
            (backup_service, 'DB_PATH', self.db_file),
            (backup_service, 'IMAGES_DIR', self.images),
            (backup_service, 'BACKUP_DIR', self.backups),
            (backup_service, 'engine', self.engine),
            (image_router, 'DATA_DIR', self.data),
            (image_router, 'IMAGES_DIR', self.images),
            (review_decisions, 'DATA_DIR', self.data),
        ):
            mocked = patch.object(module, attr, value)
            mocked.start()
            self.addCleanup(mocked.stop)

        self.users = {}
        with self.Session() as db:
            for role in ('administrador', 'operador', 'revisor'):
                user = User(
                    username=f'i03_{role}', full_name=f'Test {role}',
                    password_hash='TEST_TOKEN_ONLY_NO_LOGIN', is_active=True,
                    roles=[Role(name=role)],
                )
                db.add(user)
                db.flush()
                db.add(OrganizationMembership(organization_id=1, user_id=user.id, role_id=user.roles[0].id))
                self.users[role] = user.id

            lot = Lot(code='AG046-I03-MANGO', product='mango', status='open')
            db.add(lot)
            db.flush()
            piece = Piece(lot_id=lot.id, code='PIEZA-I03', status='registered')
            db.add(piece)
            db.flush()
            evaluation = Evaluation(
                lot_id=lot.id, piece_ref_id=piece.id, piece_id=piece.code,
                product='mango', status='pending_review', image_count=2,
            )
            db.add(evaluation)
            db.flush()
            self.lot_id, self.piece_id, self.evaluation_id = lot.id, piece.id, evaluation.id
            self.photos = []
            for index in (1, 2):
                relative = f'images/E-{evaluation.id:06d}/vista-{index}.png'
                path = self.data / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(PNG)
                photo = Image(
                    evaluation_id=evaluation.id, view=f'vista-{index}',
                    relative_path=relative, content_type='image/png',
                    size_bytes=len(PNG), idempotency_key=str(index) * 64,
                )
                db.add(photo)
                db.flush()
                self.photos.append((photo.id, path, relative))
            acquisition = Evaluation(
                lot_id=lot.id, piece_ref_id=piece.id, piece_id=piece.code,
                product='mango', status='processing', image_count=0,
                weight_pre_g=150.0,
            )
            db.add(acquisition)
            db.flush()
            self.acquisition_id = acquisition.id
            db.commit()

        def isolated_db():
            with self.Session() as session:
                yield session

        app.dependency_overrides[get_db] = isolated_db
        self.addCleanup(lambda: app.dependency_overrides.pop(get_db, None))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.review_path = f'/api/evaluations/E-{self.evaluation_id:06d}/review-decisions'

    def auth(self, role='revisor'):
        return {'Authorization': 'Bearer ' + create_access_token(self.users[role])}

    def upload(self, content=PNG, mime='image/png', key='f' * 64):
        return self.client.post(
            f'/api/evaluations/E-{self.acquisition_id:06d}/images',
            headers={**self.auth('operador'), 'Idempotency-Key': key},
            data={'view': 'vista-prueba'},
            files={'file': ('prueba.png', content, mime)},
        )

    def decision(self, image_id, *, action='initial_label', value='E1', revision=None):
        return self.client.post(self.review_path, headers=self.auth(), json={
            'action': action, 'imageId': f'I-{image_id:06d}',
            'newValue': value, 'reason': 'Revision del archivo sintetico verificable',
            'expectedReviewId': revision, 'requestId': str(uuid4()),
        })

    def register_snapshot(self, image_id, sha):
        with self.Session() as db:
            db.add(VisionAssessment(
                evaluation_id=self.evaluation_id, image_id=image_id,
                image_sha256=sha, model_version='AG046-TEST',
                rules_version='AG046-TEST-R1', inference_size=512,
                inference_confidence=0.25, acceptance_threshold=0.4,
                outcome='ready_to_capture', reason='fixture',
                confidence=0.99, candidate_count=1, detections_json='[]',
            ))
            db.commit()

    def test_int01_llaves_foraneas_activas_por_conexion(self):
        with self.engine.connect() as first, self.engine.connect() as second:
            self.assertIsNot(first.connection.driver_connection, second.connection.driver_connection)
            for db in (first, second):
                self.assertEqual(db.exec_driver_sql('PRAGMA foreign_keys').scalar(), 1)

    def test_int02_integrity_check_sqlite_ok(self):
        with closing(sqlite3.connect(self.db_file)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(backup_service.validate_database(self.db_file)['evaluationImageCount'], 2)

    def test_int03_sin_fks_huerfanas_y_rechaza_una_nueva(self):
        with closing(sqlite3.connect(self.db_file)) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        with self.assertRaisesRegex(IntegrityError, 'FOREIGN KEY constraint failed'):
            with self.engine.begin() as db:
                db.execute(text("INSERT INTO pieces(organization_id,lot_id,code,status,created_at) "
                                "VALUES (1,999999,'ORPHAN','registered','2026-01-01')"))
        with closing(sqlite3.connect(self.db_file)) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_int04_imagenes_y_evaluacion_con_ruta_bytes_y_conteo(self):
        with self.Session() as db:
            ev = db.get(Evaluation, self.evaluation_id)
            saved = list(db.scalars(select(Image).where(Image.evaluation_id == ev.id)).all())
            self.assertEqual(ev.image_count, len(saved))
            self.assertEqual(len(saved), 2)
            self.assertEqual(db.get(Piece, ev.piece_ref_id).lot_id, ev.lot_id)
            for item in saved:
                image_file = self.data / item.relative_path
                self.assertTrue(image_file.is_file())
                self.assertEqual(image_file.stat().st_size, item.size_bytes)
                self.assertEqual(hashlib.sha256(image_file.read_bytes()).hexdigest(), hashlib.sha256(PNG).hexdigest())

    def test_int04_respaldo_rechaza_imagen_referenciada_ausente(self):
        self.photos[0][1].unlink()
        with self.assertRaises(backup_service.BackupError):
            backup_service.create_backup()
        self.assertEqual(list(self.backups.glob('*.zip')), [])

    def test_int05_api_rechaza_archivo_vacio_mime_y_bytes_incorrectos(self):
        for content, mime in (
            (b'', 'image/png'),
            (b'contenido-no-es-png', 'image/png'),
            (PNG, 'text/plain'),
            (b'X' * (5 * 1024 * 1024 + 1), 'image/png'),
        ):
            with self.subTest(mime=mime, length=len(content)):
                response = self.upload(content=content, mime=mime, key=uuid4().hex * 2)
                self.assertEqual(response.status_code, 422, response.text)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(Image).where(Image.evaluation_id == self.acquisition_id)).all()), 0)
            self.assertEqual(db.get(Evaluation, self.acquisition_id).image_count, 0)

    def test_int06_fallo_de_publicacion_rollback_y_sin_huerfanos(self):
        with patch.object(image_router.os, 'replace', side_effect=OSError('DISCO_TEST')):
            result = self.upload()
        self.assertEqual(result.status_code, 500, result.text)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(Image).where(Image.evaluation_id == self.acquisition_id)).all()), 0)
            self.assertEqual(db.get(Evaluation, self.acquisition_id).image_count, 0)
        self.assertEqual(list(self.images.rglob('*.tmp')), [])
        result = self.upload()
        self.assertEqual(result.status_code, 201, result.text)

    def test_int07_idempotency_key_no_duplica_original(self):
        key = 'e' * 64
        first = self.upload(key=key)
        second = self.upload(key=key)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(first.json()['id'], second.json()['id'])
        with self.Session() as db:
            saved = list(db.scalars(select(Image).where(Image.evaluation_id == self.acquisition_id)).all())
            self.assertEqual(len(saved), 1)
            self.assertEqual(db.get(Evaluation, self.acquisition_id).image_count, 1)
            self.assertEqual((self.data / saved[0].relative_path).read_bytes(), PNG)

    def test_int08_sha_original_tamper_impide_decision_formal(self):
        image_id, path, _ = self.photos[0]
        self.register_snapshot(image_id, hashlib.sha256(PNG).hexdigest())
        path.write_bytes(b'Z' * len(PNG))  # mismo tamano, diferente SHA
        response = self.decision(image_id)
        self.assertEqual(response.status_code, 409, response.text)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(Review)).all()), 0)

    def test_int09_dos_imagenes_requieren_dos_decisiones(self):
        first = self.decision(self.photos[0][0])
        self.assertEqual(first.status_code, 201, first.text)
        with self.Session() as db:
            self.assertEqual(db.get(Evaluation, self.evaluation_id).status, 'pending_review')
        second = self.decision(self.photos[1][0], action='confirm', revision=first.json()['id'])
        self.assertEqual(second.status_code, 201, second.text)
        with self.Session() as db:
            self.assertEqual(db.get(Evaluation, self.evaluation_id).status, 'completed')
            self.assertEqual(len(db.scalars(select(ReviewDecisionEvidence)).all()), 2)
        self.assertEqual(self.photos[0][1].read_bytes(), PNG)
        self.assertEqual(self.photos[1][1].read_bytes(), PNG)

    def test_int10_reporte_csv_sha256_estable_y_conteos(self):
        for id_, _, _ in self.photos:
            self.register_snapshot(id_, hashlib.sha256(PNG).hexdigest())
        url = '/api/piece-history/report?lot=AG046-I03-MANGO'
        first = self.client.get(url, headers=self.auth('revisor'))
        second = self.client.get(url, headers=self.auth('revisor'))
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()['csv'], second.json()['csv'])
        self.assertEqual(first.json()['csvSha256'], second.json()['csvSha256'])
        self.assertEqual(first.json()['csvSha256'], hashlib.sha256(first.json()['csv'].encode('utf-8')).hexdigest())
        self.assertEqual(first.json()['counts']['pieceCount'], 1)
        self.assertEqual(first.json()['counts']['captureCount'], 2)
        self.assertEqual(first.json()['counts']['attemptCount'], 2)

    def test_bkp01_zip_manifest_sqlite_imagenes_y_hashes(self):
        result = backup_service.create_backup()
        self.assertEqual(result['imageFiles'], 2)
        self.assertEqual(result['evaluationImages'], 2)
        with zipfile.ZipFile(result['path']) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['evaluationImageCount'], 2)
            self.assertEqual(hashlib.sha256(archive.read('database/agroscan.db')).hexdigest(), manifest['database']['sha256'])
            for item in manifest['images']:
                body = archive.read('payload/' + item['path'])
                self.assertEqual(hashlib.sha256(body).hexdigest(), item['sha256'])
                self.assertEqual(len(body), item['size'])
        prepared = backup_service.prepare_restore(Path(result['path']), self.root / 'staging-bkp01')
        self.assertTrue(prepared['verified'])

    def test_bkp02_sha_alterado_se_rechaza_sin_tocar_origen(self):
        original = Path(backup_service.create_backup()['path'])
        corrupted = self.root / 'alterado.zip'
        before_db = hashlib.sha256(self.db_file.read_bytes()).hexdigest()
        before_image = self.photos[0][1].read_bytes()
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(corrupted, 'w') as target:
            for name in source.namelist():
                body = source.read(name)
                if name == 'payload/' + self.photos[0][2]:
                    body = b'Z' * len(body)
                target.writestr(name, body)
        with self.assertRaises(backup_service.BackupError):
            backup_service.restore_backup(corrupted)
        self.assertEqual(hashlib.sha256(self.db_file.read_bytes()).hexdigest(), before_db)
        self.assertEqual(self.photos[0][1].read_bytes(), before_image)

    def test_bkp02_zip_traversal_se_rechaza(self):
        original = Path(backup_service.create_backup()['path'])
        malicious = self.root / 'traversal.zip'
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(malicious, 'w') as target:
            for name in source.namelist():
                target.writestr(name, source.read(name))
            target.writestr('../infiltrado.txt', b'MALICIOUS_TEST_ONLY')
        with self.assertRaises(backup_service.BackupError):
            backup_service.prepare_restore(malicious, self.root / 'staging-traversal')
        self.assertFalse((self.root / 'infiltrado.txt').exists())

    def test_bkp03_restaura_ids_relaciones_revisiones_y_bytes(self):
        decision = self.decision(self.photos[0][0])
        self.assertEqual(decision.status_code, 201, decision.text)
        with self.Session() as db:
            original_review_id = db.scalar(select(Review.id))
            self.assertIsNotNone(original_review_id)
        original = Path(backup_service.create_backup()['path'])
        with self.Session() as db:
            meta = db.get(ReviewDecisionEvidence, original_review_id)
            db.delete(meta)
            db.delete(db.get(Review, original_review_id))
            db.get(Evaluation, self.evaluation_id).status = 'error'
            db.add(Lot(code='POST-BACKUP', product='tomate', status='open'))
            db.commit()
        self.photos[0][1].unlink()
        result = backup_service.restore_backup(original)
        self.assertTrue(result['restored'])
        with self.Session() as db:
            self.assertIsNotNone(db.get(Lot, self.lot_id))
            self.assertIsNotNone(db.get(Piece, self.piece_id))
            self.assertIsNotNone(db.get(Image, self.photos[0][0]))
            self.assertEqual(db.get(Evaluation, self.evaluation_id).piece_ref_id, self.piece_id)
            self.assertEqual(db.get(Evaluation, self.evaluation_id).status, 'pending_review')
            self.assertIsNotNone(db.get(Review, original_review_id))
            self.assertIsNotNone(db.get(ReviewDecisionEvidence, original_review_id))
            self.assertIsNone(db.scalar(select(Lot).where(Lot.code == 'POST-BACKUP')))
        self.assertEqual(self.photos[0][1].read_bytes(), PNG)
        self.assertEqual(self.photos[1][1].read_bytes(), PNG)

    def test_bkp04_rollback_si_falla_sustitucion_final_de_imagenes(self):
        old_backup = Path(backup_service.create_backup()['path'])
        with self.Session() as db:
            db.add(Lot(code='POST-CAPTURE', product='tomate', status='open'))
            db.commit()
        self.photos[0][1].write_bytes(b'MODIFIED_TEST_IMAGE')
        expected = self.photos[0][1].read_bytes()
        real_replace = backup_service.os.replace

        def fail_image_install(source, destination):
            source = Path(source)
            destination = Path(destination)
            if (source.name == 'images' and destination == self.images
                    and source.parent.name.startswith('agroscan-restore-')):
                raise OSError('FALLO_INYECTADO_POST_SQLITE')
            return real_replace(source, destination)

        with patch.object(backup_service.os, 'replace', side_effect=fail_image_install):
            with self.assertRaises(OSError):
                backup_service.restore_backup(old_backup)
        with self.Session() as db:
            self.assertIsNotNone(db.scalar(select(Lot).where(Lot.code == 'POST-CAPTURE')))
        self.assertEqual(self.photos[0][1].read_bytes(), expected)
        self.assertEqual(backup_service.validate_database(self.db_file)['evaluationImageCount'], 2)


if __name__ == '__main__':
    unittest.main()
