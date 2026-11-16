"""I03: regression de ajuste ArUco A4 sin relajar la geometria.

Ejecutar desde raiz:
  .\\backend\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_agroscan_i03_a4_fit.py" -v
"""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.services import board_calibration as board
from app.services.planar_calibration import CalibrationRejected

# Coordenadas observadas en la captura suministrada, en pixeles de pantalla.
# Sirven como fixture de geometria; NO acreditan medidas fisicas del fruto.
POINTS = {
    0: [[68, 592], [101, 592], [101, 625], [69, 625]],
    1: [[302, 592], [335, 592], [335, 624], [303, 625]],
    2: [[302, 749], [336, 749], [335, 783], [302, 782]],
    3: [[68, 749], [101, 749], [101, 782], [68, 782]],
}
FRUIT = [[155, 640], [235, 634], [258, 660], [259, 700], [230, 731], [170, 717]]


def detected(points):
    ids = np.array([[k] for k in points], dtype=np.int32)
    corners = [np.array(points[k], dtype=np.float32).reshape(1, 4, 2) for k in points]
    return corners, ids


class A4GlobalFitTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.full((868, 647, 3), 255, dtype=np.uint8)

    def test_regression_16_corners_consistent_are_accepted(self):
        with patch.object(board, '_marker_candidates', return_value=detected(POINTS)):
            result = board.measure_board_projection(self.frame, FRUIT, board.A4_BOARD_VERSION)
        self.assertEqual(result['markerIds'], [0, 1, 2, 3])
        self.assertLessEqual(result['rmsReprojectionMm'], board.MAX_RMS_MM)
        self.assertGreater(result['measurements']['majorAxisCm'], 0)
        self.assertEqual(result['boardVersion'], board.A4_BOARD_VERSION)

    def test_real_geometry_mismatch_still_rejected(self):
        corrupted = {key: [pair[:] for pair in corners] for key, corners in POINTS.items()}
        corrupted[2] = [[x + 18, y + 8] for x, y in corrupted[2]]
        with patch.object(board, '_marker_candidates', return_value=detected(corrupted)):
            with self.assertRaises(CalibrationRejected) as exc:
                board.measure_board_projection(self.frame, FRUIT, board.A4_BOARD_VERSION)
        self.assertIn(exc.exception.reason, ('board_inconsistent_markers', 'board_reprojection_error'))

    def test_missing_markers_still_rejected(self):
        with patch.object(board, '_marker_candidates', return_value=detected({0: POINTS[0], 1: POINTS[1]})):
            with self.assertRaises(CalibrationRejected) as exc:
                board.measure_board_projection(self.frame, FRUIT, board.A4_BOARD_VERSION)
        self.assertEqual(exc.exception.reason, 'board_markers_insufficient')

    def test_reference_a3_is_not_changed(self):
        self.assertEqual(board.BOARD_VERSION, 'ag054-board-a3-v1')
        self.assertEqual(board.MAX_RMS_MM, 1.5)
        self.assertEqual(board.BOARD_LAYOUTS[board.A4_BOARD_VERSION]['marker_side_mm'], 30.0)


if __name__ == '__main__':
    unittest.main()
