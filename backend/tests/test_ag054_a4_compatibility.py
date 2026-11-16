"""AG-054 A4: geometry and version isolation; synthetic markers, not field metrology."""
import hashlib
import json
import unittest

import cv2
import numpy as np
from sqlalchemy import select

from app.fruit_geometry_models import FruitGeometry
from app.models import Image
from app.board_calibration_models import BoardCalibration
from app.services.board_calibration import (
    A4_BOARD_VERSION, BOARD_VERSION, BOARD_LAYOUTS, CalibrationRejected,
    measure_board_projection,
)
from test_ag054_board_calibration import BoardApi


def synthetic_a4(visible=(0, 1, 2, 3)):
    frame = np.full((690, 900, 3), 246, dtype=np.uint8)
    dic = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    layout = BOARD_LAYOUTS[A4_BOARD_VERSION]
    scale = 2.5
    dx, dy = 85, 90
    for mid, (x, y) in layout['markers_mm'].items():
        if mid not in visible:
            continue
        pixels = int(round(layout['marker_side_mm'] * scale))
        marker = cv2.aruco.generateImageMarker(dic, mid, pixels)
        ix, iy = int(dx + x * scale), int(dy + y * scale)
        frame[iy:iy+pixels, ix:ix+pixels] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    center = (dx + 138.5*scale, dy + 95*scale)
    polygon = [[center[0]+100*np.cos(theta), center[1]+75*np.sin(theta)]
               for theta in np.linspace(0, 2*np.pi, 96, endpoint=False)]
    cv2.fillPoly(frame, [np.asarray(polygon, dtype=np.int32)], (36, 91, 192))
    ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 96])
    assert ok
    return encoded.tobytes(), polygon


class A4GeometryTests(unittest.TestCase):
    def test_four_markers_match_a4_scale(self):
        raw, contour = synthetic_a4()
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        value = measure_board_projection(frame, contour, A4_BOARD_VERSION)
        self.assertEqual(value['markerIds'], [0, 1, 2, 3])
        self.assertEqual(value['boardVersion'], A4_BOARD_VERSION)
        self.assertAlmostEqual(value['measurements']['majorAxisCm'], 8.0, delta=.3)
        self.assertAlmostEqual(value['measurements']['minorAxisCm'], 6.0, delta=.3)
        self.assertLess(value['rmsReprojectionMm'], 1.5)

    def test_three_markers_work_and_two_fail(self):
        for visible in ((0, 1, 2), (0, 2, 3)):
            raw, contour = synthetic_a4(visible)
            frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
            self.assertEqual(len(measure_board_projection(frame, contour, A4_BOARD_VERSION)['markerIds']), 3)
        raw, contour = synthetic_a4((0, 1))
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        with self.assertRaises(CalibrationRejected) as err:
            measure_board_projection(frame, contour, A4_BOARD_VERSION)
        self.assertEqual(err.exception.reason, 'board_markers_insufficient')

    def test_a4_is_not_a3_and_unsupported_is_rejected(self):
        raw, contour = synthetic_a4()
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        with self.assertRaises(CalibrationRejected):
            measure_board_projection(frame, contour, BOARD_VERSION)
        with self.assertRaises(CalibrationRejected) as err:
            measure_board_projection(frame, contour, 'ag054-board-a4-shrunk-a3')
        self.assertEqual(err.exception.reason, 'board_version_unsupported')


class A4ApiTests(unittest.TestCase):
    endpoint = BoardApi.endpoint
    headers = BoardApi.headers

    def setUp(self):
        BoardApi.setUp(self)
        raw, contour = synthetic_a4()
        self.raw = raw
        self.polygon = contour
        self.photo.write_bytes(raw)
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        with self.Session() as db:
            geom = db.scalar(select(FruitGeometry))
            geom.image_sha256 = hashlib.sha256(raw).hexdigest()
            geom.frame_width = int(frame.shape[1])
            geom.frame_height = int(frame.shape[0])
            geom.polygon_json = json.dumps(contour)
            image = db.scalar(select(Image))
            image.size_bytes = len(raw)
            db.commit()

    def body(self, version=A4_BOARD_VERSION):
        return {'boardVersion': version, 'markerAtPlatformLevel': True,
                'independentSupport': True, 'printedDimensionsVerified': True, 'fixedCamera': True}

    def test_a4_snapshot_and_original_unchanged(self):
        original = self.photo.read_bytes()
        first = self.client.post(self.endpoint(), json=self.body(), headers=self.headers())
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(first.json()['boardVersion'], A4_BOARD_VERSION)
        self.assertEqual(first.json()['status'], 'reference_plane_estimate')
        self.assertFalse(first.json()['physicalDimensionsValidated'])
        again = self.client.post(self.endpoint(), json=self.body(), headers=self.headers())
        self.assertEqual(again.json()['id'], first.json()['id'])
        self.assertEqual(self.photo.read_bytes(), original)

    def test_same_image_different_layout_has_distinct_snapshot(self):
        first = self.client.post(self.endpoint(), json=self.body(), headers=self.headers()).json()
        second = self.client.post(self.endpoint(), json=self.body(BOARD_VERSION), headers=self.headers()).json()
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(first['boardVersion'], A4_BOARD_VERSION)
        self.assertEqual(second['boardVersion'], BOARD_VERSION)
        self.assertEqual(second['status'], 'needs_review')
        self.assertIsNone(second['measurements'])
        rows = self.client.get(self.endpoint(), headers=self.headers('revisor')).json()
        self.assertEqual(len(rows), 2)

    def test_comparison_links_to_correct_a4_snapshot(self):
        a4 = self.client.post(self.endpoint(), json=self.body(), headers=self.headers()).json()
        self.client.post(self.endpoint(), json=self.body(BOARD_VERSION), headers=self.headers())
        cmp = self.client.post(self.endpoint()+'/comparisons', headers=self.headers(),json={
            'boardCalibrationId': a4['id'], 'referenceMajorCm': 8.0,
            'referenceMinorCm': 6.0, 'instrumentId': 'Pie de rey contrastado'
        })
        self.assertEqual(cmp.status_code, 201, cmp.text)
        self.assertEqual(cmp.json()['boardCalibrationId'], a4['id'])
        bad = self.client.post(self.endpoint()+'/comparisons', headers=self.headers(),json={
            'boardCalibrationId': 99999, 'referenceMajorCm': 8.0,
            'referenceMinorCm': 6.0, 'instrumentId': 'Pie de rey contrastado'
        })
        self.assertEqual(bad.status_code, 409)


if __name__ == '__main__':
    unittest.main()
