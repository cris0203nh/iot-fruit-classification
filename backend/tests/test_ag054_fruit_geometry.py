"""AGROP-66 / AG-054: pruebas aisladas con evidencias y detecciones controladas.

NO evalua la precision real de YOLOE ni confirma centimetros.
"""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.fruit_geometry_models import FruitGeometry
from app.main import app
from app.models import Evaluation, Image, Lot, Role, User
from app.routers import fruit_geometry
from app.security import create_access_token, hash_password
from app.services.fruit_geometry import InvalidGeometry, measure_polygon


RECTANGLE = [[20, 30], [100, 30], [100, 90], [20, 90]]


class AG054GeometryMathTests(unittest.TestCase):
    def test_medidas_2d_en_pixeles_sin_cm(self):
        measured = measure_polygon(RECTANGLE, 160, 128)
        self.assertAlmostEqual(measured['widthPx'], 80)
        self.assertAlmostEqual(measured['heightPx'], 60)
        self.assertAlmostEqual(measured['areaPx2'], 4800)
        self.assertAlmostEqual(measured['perimeterPx'], 280)
        self.assertAlmostEqual(measured['majorAxisPx'], 80)
        self.assertAlmostEqual(measured['minorAxisPx'], 60)
        self.assertNotIn('centimeters', measured)
        self.assertNotIn('quality', measured)

    def test_mascaras_invalidas_no_producen_medidas(self):
        for bad in ([], [[0, 0], [4, 4]], [[-1, 5], [10, 10], [5, 10]],
                    [[1, 1], [1, 1], [1, 1]], [[1, 2], [float('nan'), 10], [3, 4]]):
            with self.subTest(bad=bad):
                with self.assertRaises(InvalidGeometry):
                    measure_polygon(bad, 160, 128)


class AG054ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ag054-test-')
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.engine = create_engine(f'sqlite:///{(root / "test.sqlite").as_posix()}',
                                    connect_args={'check_same_thread': False})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.Session() as db:
            self.roles = {}
            for name in ('operador', 'revisor'):
                user = User(username='ag054_'+name, full_name='AG054 '+name,
                            password_hash=hash_password('TestValid123!'), is_active=True,
                            roles=[Role(name=name)])
                db.add(user)
                db.flush()
                self.roles[name] = user.id
            lot = Lot(code='AG054-MANGO', product='mango', status='open', responsible='Prueba')
            db.add(lot)
            db.flush()
            ev = Evaluation(lot_id=lot.id, piece_id='P-000001', product='mango',
                            status='processing', visual_category=None)
            db.add(ev)
            db.flush()
            frame = np.full((128, 160, 3), (12, 160, 220), dtype=np.uint8)
            valid, jpg = cv2.imencode('.jpg', frame)
            self.assertTrue(valid)
            raw = jpg.tobytes()
            source = root / 'images' / 'original.jpg'
            source.parent.mkdir(parents=True)
            source.write_bytes(raw)
            img = Image(evaluation_id=ev.id, view='vista-1', relative_path='images/original.jpg',
                        content_type='image/jpeg', size_bytes=len(raw),
                        idempotency_key='a'*64)
            db.add(img)
            db.flush()
            self.eid = f'E-{ev.id:06d}'
            self.iid = f'I-{img.id:06d}'
            self.source = source
            self.original = raw
            db.commit()
        self.patch_dir = patch.object(fruit_geometry, 'DATA_DIR', root)
        self.patch_dir.start()
        self.addCleanup(self.patch_dir.stop)

        def isolated_db():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = isolated_db
        self.addCleanup(lambda: app.dependency_overrides.pop(get_db, None))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.url = f'/api/evaluations/{self.eid}/vision/geometry/{self.iid}'

    def auth(self, role='operador'):
        return {'Authorization': 'Bearer ' + create_access_token(self.roles[role])}

    def detection(self):
        return [{'product':'mango', 'confidence':0.95, 'box':[20, 30, 100, 90],
                 'polygon':RECTANGLE}]

    def test_guarda_medicion_consulta_autenticada_y_reintento_no_infiere(self):
        with patch.object(fruit_geometry, '_infer_products', return_value=self.detection()) as infer:
            first = self.client.post(self.url, headers=self.auth())
            self.assertEqual(first.status_code, 201, first.text)
            second = self.client.post(self.url, headers=self.auth())
            self.assertEqual(second.status_code, 201, second.text)
            self.assertEqual(infer.call_count, 1)
        record = first.json()
        self.assertEqual(first.json(), second.json())
        self.assertEqual(record['measurements']['areaPx2'], 4800)
        self.assertEqual(record['unit'], 'px')
        self.assertFalse(record['calibrated'])
        self.assertFalse(record['classificationE0E1E2Produced'])
        self.assertEqual(record['imageSha256'], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(self.source.read_bytes(), self.original)
        result = self.client.get(f'/api/evaluations/{self.eid}/vision/geometry', headers=self.auth('revisor'))
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json(), [record])
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(FruitGeometry)).all()), 1)
            self.assertIsNone(db.get(Evaluation, int(self.eid[2:])).visual_category)

    def test_rechaza_usuario_anonimo_y_revisor_escritura(self):
        self.assertEqual(self.client.post(self.url).status_code, 401)
        self.assertEqual(self.client.post(self.url, headers=self.auth('revisor')).status_code, 403)
        self.assertEqual(self.client.get(f'/api/evaluations/{self.eid}/vision/geometry').status_code, 401)

    def test_no_acepta_imagen_de_otra_evaluacion(self):
        self.assertEqual(self.client.post(f'/api/evaluations/E-999999/vision/geometry/{self.iid}',
                                          headers=self.auth()).status_code, 404)
        self.assertEqual(self.client.post(f'/api/evaluations/{self.eid}/vision/geometry/I-999999',
                                          headers=self.auth()).status_code, 404)

    def test_deteccion_incierta_no_publica_medidas(self):
        with patch.object(fruit_geometry, '_infer_products', return_value=[
            *self.detection(), {'product':'tomate','confidence':0.90, 'box':[1,1,11,11], 'polygon':RECTANGLE},
        ]):
            response = self.client.post(self.url, headers=self.auth())
        self.assertEqual(response.status_code, 201, response.text)
        result=response.json()
        self.assertEqual(result['status'], 'needs_review')
        self.assertEqual(result['reason'], 'varias_frutas')
        self.assertIsNone(result['measurements'])
        self.assertEqual(result['polygon'], [])

    def test_producto_distinto_no_publica_medidas(self):
        with patch.object(fruit_geometry, '_infer_products', return_value=[
            {'product':'tomate', 'confidence':0.96, 'box':[20,30,100,90], 'polygon':RECTANGLE}
        ]):
            response = self.client.post(self.url, headers=self.auth())
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['reason'], 'producto_distinto_al_lote')
        self.assertIsNone(response.json()['measurements'])

    def test_fallo_detector_no_crea_medidas(self):
        with patch.object(fruit_geometry, '_infer_products', side_effect=RuntimeError('modelo ausente')):
            response = self.client.post(self.url, headers=self.auth())
        self.assertEqual(response.status_code, 503)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(FruitGeometry)).all()), 0)

    def test_evidencia_invalida_no_se_sobrescribe(self):
        self.source.write_bytes(b'alterada')
        with patch.object(fruit_geometry, '_infer_products') as infer:
            response = self.client.post(self.url, headers=self.auth())
        self.assertEqual(response.status_code, 409)
        infer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
