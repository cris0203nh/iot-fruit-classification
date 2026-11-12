"""AG-054 I03: pruebas controladas; NO se acredita webcam ni precision 3D."""
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
from app.board_calibration_models import BoardCalibration, DimensionalComparison
from app.fruit_geometry_models import FruitGeometry
from app.models import Evaluation, Image, Lot, Piece, Role, User
from app.routers import fruit_geometry
from app.security import create_access_token, hash_password
from app.services.board_calibration import (
    BOARD_VERSION, MARKER_LAYOUT_MM, MARKER_SIDE_MM, CalibrationRejected,
    measure_board_projection, compare_with_caliper,
)


def sample(visible_ids=(0, 1, 2, 3)):
    """Patron REAL de ArUco sintetico y fruta geometrica; sin fotos de campo."""
    frame = np.full((750, 1000, 3), 245, dtype=np.uint8)
    aruco = cv2.aruco
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    scale = 2.0  # pixeles por mm solo para el generador de TEST
    dx, dy = 95, 75
    for marker_id, (x, y) in MARKER_LAYOUT_MM.items():
        if marker_id not in visible_ids:
            continue
        pixels = int(MARKER_SIDE_MM * scale)
        img = aruco.generateImageMarker(dictionary, marker_id, pixels)
        px, py = int(dx + x * scale), int(dy + y * scale)
        frame[py:py+pixels, px:px+pixels] = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    center = (int(dx + 195 * scale), int(dy + 137.5 * scale))
    points = []
    for theta in np.linspace(0, 2*np.pi, 80, endpoint=False):
        points.append([float(center[0] + 100*np.cos(theta)),
                       float(center[1] + 84*np.sin(theta))])
    cv2.fillPoly(frame, [np.asarray(points, dtype=np.int32)], (40, 100, 205))
    ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 96])
    assert ok
    return encoded.tobytes(), points


class BoardMath(unittest.TestCase):
    def test_four_markers_calculates_reference_plane_only(self):
        raw, polygon = sample()
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        measured = measure_board_projection(frame, polygon)
        self.assertEqual(measured['boardVersion'], BOARD_VERSION)
        self.assertEqual(measured['markerIds'], [0, 1, 2, 3])
        self.assertLess(measured['rmsReprojectionMm'], 1.5)
        self.assertAlmostEqual(measured['measurements']['majorAxisCm'], 10.0, delta=.25)
        self.assertAlmostEqual(measured['measurements']['minorAxisCm'], 8.4, delta=.25)

    def test_three_separate_markers_work(self):
        raw, polygon = sample((0, 1, 2))
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(len(measure_board_projection(frame, polygon)['markerIds']), 3)

    def test_two_markers_do_not_emit_centimeters(self):
        raw, polygon = sample((0, 1))
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        with self.assertRaises(CalibrationRejected) as exc:
            measure_board_projection(frame, polygon)
        self.assertEqual(exc.exception.reason, 'board_markers_insufficient')

    def test_no_markers_does_not_emit_centimeters(self):
        raw, polygon = sample(())
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        with self.assertRaises(CalibrationRejected) as exc:
            measure_board_projection(frame, polygon)
        self.assertEqual(exc.exception.reason, 'board_markers_insufficient')

    def test_crop_does_not_emit_centimeters(self):
        raw, _ = sample()
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        with self.assertRaises(CalibrationRejected) as exc:
            measure_board_projection(frame, [[0, 200], [700, 200], [700, 500], [0, 500]])
        self.assertEqual(exc.exception.reason, 'fruit_partially_out_of_frame')

    def test_manual_comparison_is_not_automatic_certification(self):
        outcome = compare_with_caliper({'majorAxisCm': 10.0, 'minorAxisCm': 8.4}, 9.0, 8.0)
        self.assertEqual(outcome['status'], 'comparison_only')
        self.assertFalse(outcome['physicalDimensionsValidated'])
        self.assertAlmostEqual(outcome['major']['absoluteErrorCm'], 1.0)
        self.assertAlmostEqual(outcome['minor']['relativeAbsoluteErrorPct'], 5.0)
        with self.assertRaises(ValueError):
            compare_with_caliper({'majorAxisCm': 10.0, 'minorAxisCm': 8.4}, 7, 9)


class BoardApi(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='ag054-i03-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root/'images').mkdir()
        self.engine = create_engine(f"sqlite:///{(self.root/'isolated.db').as_posix()}",
                                    connect_args={'check_same_thread': False})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.raw, self.polygon = sample()
        self.photo = self.root/'images'/'original.jpg'
        self.photo.write_bytes(self.raw)
        frame = cv2.imdecode(np.frombuffer(self.raw,dtype=np.uint8),cv2.IMREAD_COLOR)
        with self.Session() as db:
            users = {}
            for role in ('operador','revisor'):
                user = User(username='ag054_i03_'+role,full_name='Test '+role,
                            password_hash=hash_password('TestPassword123!'),
                            is_active=True,roles=[Role(name=role)])
                db.add(user)
                db.flush()
                users[role] = user.id
            lot = Lot(code='AG054-I03-LOTE', product='mango', status='open', responsible='test')
            db.add(lot); db.flush()
            piece = Piece(lot_id=lot.id, code='P-000001'); db.add(piece); db.flush()
            evaluation = Evaluation(lot_id=lot.id,piece_id=piece.code,piece_ref_id=piece.id,product='mango')
            db.add(evaluation); db.flush()
            image = Image(evaluation_id=evaluation.id,view='vista-1',relative_path='images/original.jpg',
                          content_type='image/jpeg',size_bytes=len(self.raw))
            db.add(image); db.flush()
            geometry = FruitGeometry(evaluation_id=evaluation.id,image_id=image.id,
                image_sha256=hashlib.sha256(self.raw).hexdigest(),model_version='yoloe-26n-seg',
                rules_version='ag054-pixel-geometry-v1',status='measured',reason='deteccion_unica',
                product='mango',confidence=.9,candidate_count=1,
                frame_width=int(frame.shape[1]),frame_height=int(frame.shape[0]),
                box_json=json.dumps([200,200,700,550]),polygon_json=json.dumps(self.polygon),
                measurements_json=json.dumps({'widthPx':200}))
            db.add(geometry); db.commit()
            self.users = users
            self.eid, self.iid = f'E-{evaluation.id:06d}',f'I-{image.id:06d}'
        def isolated_db():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = isolated_db
        self.addCleanup(lambda: app.dependency_overrides.pop(get_db,None))
        mocked = patch.object(fruit_geometry,'DATA_DIR',self.root)
        mocked.start(); self.addCleanup(mocked.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def headers(self,role='operador'):
        return {'Authorization':'Bearer '+create_access_token(self.users[role])}

    def endpoint(self):
        return f'/api/evaluations/{self.eid}/vision/board/{self.iid}'

    def body(self):
        return {'boardVersion': BOARD_VERSION,'markerAtPlatformLevel':True,
                'independentSupport':True,'printedDimensionsVerified':True,'fixedCamera':True}

    def test_permission_and_mount_conditions(self):
        self.assertEqual(self.client.post(self.endpoint(),json=self.body()).status_code,401)
        self.assertEqual(self.client.post(self.endpoint(),json=self.body(),headers=self.headers('revisor')).status_code,403)
        body = self.body();body['independentSupport']=False
        self.assertEqual(self.client.post(self.endpoint(),json=body,headers=self.headers()).status_code,422)
        body = self.body();body['boardVersion']='arbitrary-layout'
        self.assertEqual(self.client.post(self.endpoint(),json=body,headers=self.headers()).status_code,422)

    def test_estimation_stored_same_id_retry_and_compare(self):
        original=self.photo.read_bytes()
        first=self.client.post(self.endpoint(),json=self.body(),headers=self.headers())
        self.assertEqual(first.status_code,201,first.text)
        result=first.json()
        self.assertEqual(result['status'],'reference_plane_estimate')
        self.assertFalse(result['physicalDimensionsValidated'])
        self.assertEqual(result['markerIds'],[0,1,2,3])
        repeated=self.client.post(self.endpoint(),json=self.body(),headers=self.headers())
        self.assertEqual(repeated.status_code,201)
        self.assertEqual(repeated.json()['id'],result['id'])
        self.assertEqual(len(self.client.get(self.endpoint(),headers=self.headers('revisor')).json()),1)
        comparison_body={'referenceMajorCm':9.0,'referenceMinorCm':8.0,'instrumentId':'Pie de rey - ensayo'}
        first_compare=self.client.post(self.endpoint()+'/comparisons',json=comparison_body,headers=self.headers())
        self.assertEqual(first_compare.status_code,201,first_compare.text)
        self.assertEqual(first_compare.json()['comparison']['status'],'comparison_only')
        self.assertEqual(self.client.post(self.endpoint()+'/comparisons',json=comparison_body,
                headers=self.headers()).json()['id'],first_compare.json()['id'])
        self.assertEqual(len(self.client.get(self.endpoint()+'/comparisons',headers=self.headers('revisor')).json()),1)
        report=self.client.get('/api/evaluations/vision/board-validation/report',headers=self.headers('revisor'))
        self.assertEqual(report.status_code,200,report.text)
        self.assertEqual(report.json()['products']['mango']['sampleCount'],1)
        self.assertEqual(report.json()['products']['tomate']['sampleCount'],0)
        self.assertFalse(report.json()['physicalDimensionsValidated'])
        self.assertEqual(self.photo.read_bytes(),original)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(BoardCalibration)).all()),1)
            self.assertEqual(len(db.scalars(select(DimensionalComparison)).all()),1)

    def test_no_reference_rejects_manual_comparison(self):
        comparison={'referenceMajorCm':9,'referenceMinorCm':8,'instrumentId':'caliper'}
        response=self.client.post(self.endpoint()+'/comparisons',json=comparison,headers=self.headers())
        self.assertEqual(response.status_code,409)

    def test_hash_mismatch_rejected(self):
        with self.Session() as db:
            geom=db.scalar(select(FruitGeometry))
            geom.image_sha256='f'*64
            db.commit()
        res=self.client.post(self.endpoint(),json=self.body(),headers=self.headers())
        self.assertEqual(res.status_code,409)

    def test_foreign_photo_rejected(self):
        result=self.client.get(self.endpoint().replace(self.iid,'I-999999'),headers=self.headers('revisor'))
        self.assertEqual(result.status_code,404)


if __name__=='__main__':
    unittest.main()
