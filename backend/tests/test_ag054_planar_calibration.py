"""AG-054 I02: tests in isolated SQLite; NO physical hardware or claims of 3D accuracy."""
import hashlib
import json
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
from app.main import app
from app.models import Evaluation, Image, Lot, Piece, Role, User
from app.fruit_geometry_models import FruitGeometry
from app.planar_calibration_models import PlanarCalibration
from app.routers import planar_calibration
from app.security import create_access_token, hash_password
from app.services.planar_calibration import CalibrationRejected, measure_plane_projection


def sample(include_marker=True):
    frame = np.full((800, 900, 3), 255, np.uint8)
    if include_marker:
        aruco = cv2.aruco
        marker = aruco.generateImageMarker(aruco.getPredefinedDictionary(aruco.DICT_4X4_50), 0, 180)
        frame[80:260, 650:830] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    polygon = [[220., 290.], [390., 290.], [390., 460.], [220., 460.]]
    ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 96])
    assert ok
    return encoded.tobytes(), polygon


class CalibrationMath(unittest.TestCase):
    def test_aruco_real_50mm_proyeccion_no_3d(self):
        raw, polygon = sample()
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        result = measure_plane_projection(frame, polygon, marker_id=0, marker_side_mm=50)
        self.assertEqual(len(result['markerCornersPx']), 4)
        self.assertAlmostEqual(result['measurements']['widthCm'], 4.7, delta=.20)
        self.assertAlmostEqual(result['measurements']['heightCm'], 4.7, delta=.20)

    def test_sin_marker_no_fabrica_cm(self):
        raw, polygon = sample(include_marker=False)
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        with self.assertRaises(CalibrationRejected) as exc:
            measure_plane_projection(frame, polygon, 0, 50)
        self.assertEqual(exc.exception.reason, 'marker_not_found')

    def test_fruta_cortada_rechazada(self):
        raw, _ = sample()
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        with self.assertRaises(CalibrationRejected) as exc:
            measure_plane_projection(frame, [[0, 150], [300, 150], [300, 320], [0, 320]], 0, 50)
        self.assertEqual(exc.exception.reason, 'fruit_partially_out_of_frame')

    def test_escala_fuera_de_intervalo(self):
        raw, poly = sample()
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        for value in (0, 151, float('inf')):
            with self.subTest(value=value), self.assertRaises(CalibrationRejected):
                measure_plane_projection(frame, poly, 0, value)


class PlanarHttp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ag054-i02-')
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        (self.path / 'images').mkdir()
        self.engine = create_engine(f"sqlite:///{(self.path/'test.db').as_posix()}", connect_args={'check_same_thread':False})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        raw, poly = sample()
        self.raw = raw
        self.photo = self.path / 'images' / 'original.jpg'
        self.photo.write_bytes(raw)
        with self.Session() as db:
            roles = {v: Role(name=v) for v in ('operador','revisor')}
            users = {v: User(username='ag054_'+v, full_name='AG054 '+v,
                             password_hash=hash_password('TestPassword123!'), is_active=True,
                             roles=[roles[v]]) for v in roles}
            db.add_all(users.values())
            lot = Lot(code='I02-REAL', product='mango', status='open', responsible='prueba')
            db.add(lot)
            db.flush()
            piece = Piece(lot_id=lot.id, code='P-000001')
            db.add(piece)
            db.flush()
            ev = Evaluation(lot_id=lot.id, piece_id=piece.code, piece_ref_id=piece.id, product='mango')
            db.add(ev)
            db.flush()
            img = Image(evaluation_id=ev.id, view='vista-1', relative_path='images/original.jpg',
                        content_type='image/jpeg', size_bytes=len(raw))
            db.add(img)
            db.flush()
            geom = FruitGeometry(evaluation_id=ev.id, image_id=img.id,
                 image_sha256=hashlib.sha256(raw).hexdigest(), model_version='yoloe-26n-seg',
                 rules_version='ag054-pixel-geometry-v1', status='measured', reason='deteccion_unica',
                 product='mango', confidence=.93, candidate_count=1, frame_width=900, frame_height=800,
                 box_json=json.dumps([220,290,390,460]),polygon_json=json.dumps(poly),
                 measurements_json=json.dumps({'widthPx':170}))
            db.add(geom)
            db.commit()
            self.uid = {v: u.id for v,u in users.items()}
            self.eid, self.iid = f'E-{ev.id:06d}', f'I-{img.id:06d}'
        def isolated():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = isolated
        self.addCleanup(lambda: app.dependency_overrides.pop(get_db, None))
        p = patch.object(planar_calibration, 'DATA_DIR', self.path, create=True)
        # _original_image uses DATA_DIR in fruit_geometry module (patch source instead).
        from app.routers import fruit_geometry
        p = patch.object(fruit_geometry, 'DATA_DIR', self.path)
        p.start(); self.addCleanup(p.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def headers(self, role='operador'):
        return {'Authorization':'Bearer '+create_access_token(self.uid[role])}

    def endpoint(self):
        return f'/api/evaluations/{self.eid}/vision/physical/{self.iid}'

    def test_inferir_guardar_y_reintentar_no_duplica(self):
        data={'markerId':0,'markerSideMm':50.0,'markerAtPlatformLevel':True}
        first=self.client.post(self.endpoint(), json=data, headers=self.headers())
        self.assertEqual(first.status_code,201,first.text)
        value=first.json()
        self.assertEqual(value['status'],'reference_plane_estimate')
        self.assertEqual(value['unit'],'cm_reference_plane')
        self.assertFalse(value['physicalDimensionsValidated'])
        self.assertFalse(value['fruitHeightCorrected'])
        self.assertGreater(value['measurements']['majorAxisCm'], 0)
        second=self.client.post(self.endpoint(),json=data,headers=self.headers())
        self.assertEqual(second.status_code,201)
        self.assertEqual(second.json()['id'],value['id'])
        rows=self.client.get(self.endpoint(),headers=self.headers('revisor'))
        self.assertEqual(len(rows.json()),1)
        self.assertEqual(self.photo.read_bytes(),self.raw)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(PlanarCalibration)).all()),1)

    def test_permiso_y_declaracion_obligatoria(self):
        data={'markerId':0,'markerSideMm':50,'markerAtPlatformLevel':True}
        self.assertEqual(self.client.post(self.endpoint(),json=data).status_code,401)
        self.assertEqual(self.client.post(self.endpoint(),json=data,headers=self.headers('revisor')).status_code,403)
        data['markerAtPlatformLevel']=False
        self.assertEqual(self.client.post(self.endpoint(),json=data,headers=self.headers()).status_code,422)

    def test_referencia_inexistente_no_produce_medida(self):
        self.photo.write_bytes(sample(False)[0])
        with self.Session() as db:
            img=db.scalar(select(Image))
            geom=db.scalar(select(FruitGeometry))
            img.size_bytes=self.photo.stat().st_size
            geom.image_sha256=hashlib.sha256(self.photo.read_bytes()).hexdigest()
            db.commit()
        result=self.client.post(self.endpoint(),json={'markerId':0,'markerSideMm':50,'markerAtPlatformLevel':True},headers=self.headers())
        self.assertEqual(result.status_code,201,result.text)
        self.assertEqual(result.json()['status'],'needs_review')
        self.assertIsNone(result.json()['measurements'])

    def test_otra_fotografia_y_hash_no_concordante(self):
        invalid=self.endpoint().replace(self.iid,'I-999999')
        self.assertEqual(self.client.get(invalid,headers=self.headers()).status_code,404)
        self.photo.write_bytes(self.raw+b'altered')
        with self.Session() as db:
            db.scalar(select(Image)).size_bytes=self.photo.stat().st_size
            db.commit()
        self.assertEqual(self.client.post(self.endpoint(),json={'markerId':0,'markerSideMm':50,'markerAtPlatformLevel':True},headers=self.headers()).status_code,409)


if __name__=='__main__':
    unittest.main()
