"""I03C: no se afirma calibración manual en cálculo automático."""
import hashlib
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.routers import board_calibration as module
from app.services.planar_calibration import CalibrationRejected

RAW = cv2.imencode('.png', np.full((256, 256, 3), 255, dtype=np.uint8))[1].tobytes()
SHA = hashlib.sha256(RAW).hexdigest()
EVALUATION = SimpleNamespace(id=20, status='processing')
IMAGE = SimpleNamespace(id=17)
GEOMETRY = SimpleNamespace(id=5, evaluation_id=20, image_id=17, status='measured',
                           image_sha256=SHA, frame_height=256, frame_width=256,
                           model_version='yoloe-test', polygon_json='[[40,40],[80,40],[80,80],[40,80]]')
SAMPLE = {
    'markerIds':[0,1,2,3], 'markerCornersPx':{},
    'measurements':{'widthCm':7., 'heightCm':6., 'majorAxisCm':7., 'minorAxisCm':6.,
                    'projectedAreaCm2':40., 'projectedPerimeterCm':25.,
                    'markerSidePxMedian':100., 'markerScaleVariationPct':2.},
    'rmsReprojectionMm':None,
}
class MemoryDb:
    def __init__(self):self.calls=0;self.record=None
    def scalar(self, statement):
        self.calls+=1
        return GEOMETRY if self.calls==1 else None
    def add(self,record):self.record=record
    def commit(self):pass
    def refresh(self,record):
        record.id=101
        record.created_at=datetime.now(timezone.utc)

class AutoNominalTests(unittest.TestCase):
    def execute(self, verified, fail=False):
        db=MemoryDb()
        with patch.object(module,'_evaluation',return_value=EVALUATION), \
             patch.object(module,'_evidence',return_value=IMAGE), \
             patch.object(module,'_original_image',return_value=RAW), \
             patch.object(module,'measure_a4_marker_pixel_scale',side_effect=(CalibrationRejected('board_markers_insufficient') if fail else None),return_value=SAMPLE):
            result=module.approximate_a4('E-000020','I-000017',
                module.ApproxInput(printedDimensionsVerified=verified),db,SimpleNamespace(id=1))
        return db.record, result
    def test_automatic_without_manual_declaration(self):
        row, out=self.execute(False)
        self.assertFalse(row.printed_scale_verified_declared)
        self.assertEqual(row.reason,'approximate_nominal_30mm_unverified_no_3d')
        self.assertEqual(out['status'],'pixel_scale_estimate')
        self.assertFalse(out['physicalDimensionsValidated'])
    def test_explicit_verification_remains_auditable(self):
        row, out=self.execute(True)
        self.assertTrue(row.printed_scale_verified_declared)
        self.assertEqual(row.reason,'approximate_marker_pixel_scale_no_3d')
        self.assertFalse(out['physicalDimensionsValidated'])
    def test_marker_error_yields_no_centimeters(self):
        row, out=self.execute(False,fail=True)
        self.assertEqual(out['status'],'needs_review')
        self.assertIsNone(out['measurements'])
        self.assertFalse(row.printed_scale_verified_declared)
if __name__=='__main__':unittest.main()
