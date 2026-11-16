"""Pruebas unitarias I03B: escala de pixels ArUco A4, sin 3D."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services import board_calibration as b
from app.services.planar_calibration import CalibrationRejected

MARKERS = {
  0: [[25,25],[55,25],[55,55],[25,55]],
  1: [[325,25],[355,25],[355,55],[325,55]],
  2: [[325,245],[355,245],[355,275],[325,275]],
  3: [[25,245],[55,245],[55,275],[25,275]],
}
FRUIT = [[180,115],[240,115],[240,155],[180,155]]
FRAME = np.full((310,390,3),255,dtype=np.uint8)
def detected(data):
    return ([np.array(data[k],dtype=np.float32).reshape(1,4,2) for k in data],
            np.array([[k] for k in data],dtype=np.int32))

class PixelScaleTests(unittest.TestCase):
    def test_3_cm_per_30_px(self):
        with patch.object(b,'_marker_candidates',return_value=detected(MARKERS)):
            out=b.measure_a4_marker_pixel_scale(FRAME,FRUIT)
        self.assertEqual(out['markerIds'],[0,1,2,3])
        self.assertAlmostEqual(out['measurements']['majorAxisCm'],6.0,places=2)
        self.assertAlmostEqual(out['measurements']['minorAxisCm'],4.0,places=2)
        self.assertEqual(out['rmsReprojectionMm'],None)
    def test_changes_scale_with_actual_resolution(self):
        twice={k: [[x*2,y*2] for x,y in pts] for k,pts in MARKERS.items()}
        twice_fruit=[[x*2,y*2] for x,y in FRUIT]
        with patch.object(b,'_marker_candidates',return_value=detected(twice)):
            out=b.measure_a4_marker_pixel_scale(np.full((620,780,3),255,dtype=np.uint8),twice_fruit)
        self.assertAlmostEqual(out['measurements']['majorAxisCm'],6.0,places=2)
    def test_missing_markers_rejected(self):
        with patch.object(b,'_marker_candidates',return_value=detected({0:MARKERS[0],1:MARKERS[1]})):
            with self.assertRaises(CalibrationRejected):b.measure_a4_marker_pixel_scale(FRAME,FRUIT)
    def test_extreme_scale_rejected(self):
        data={k:[p[:] for p in pts] for k,pts in MARKERS.items()}
        data[2] = [[325,220],[405,220],[405,300],[325,300]]
        with patch.object(b,'_marker_candidates',return_value=detected(data)):
            with self.assertRaises(CalibrationRejected):b.measure_a4_marker_pixel_scale(np.full((350,450,3),255,dtype=np.uint8),FRUIT)
    def test_original_a4_homography_preserved(self):
        self.assertEqual(b.A4_BOARD_VERSION,'ag054-board-a4-v1')
        self.assertEqual(b.MAX_RMS_MM,1.5)
if __name__=='__main__':unittest.main()
