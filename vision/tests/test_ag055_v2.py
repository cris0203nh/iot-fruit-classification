"""Synthetic V2 contracts; no external evaluation photographs used."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image, ImageDraw

from vision.ag055.v2 import features,predict,validate,segment,load_models,VERSION,FEATURE_VERSION,DIMENSIONS


def artifact():
    return {'version':VERSION,'featureVersion':FEATURE_VERSION,'product':'tomate','labels':['E0','E1','E2'],
            'labelSpace':'pilot_declared_e0e1e2_v2','deploymentAuthorized':False,'humanReviewRequired':True,
            'kentAccredited':False,'independentTestMetrics':None,'trainingImageHashes':['a'*64],
            'dataVersion':'synthetic','limitations':['software fixture only'],
            'model':{'mean':[0]*DIMENSIONS,'scale':[.05]*DIMENSIONS,'gamma':.01,
                     'supportCounts':[1,1,1],'supportVectors':[[0]*DIMENSIONS]*3,
                     'dualCoef':[[0]*3]*2,'intercept':[1,1,1]}}


def photo(color=(220,40,20)):
    im=Image.new('RGB',(160,160),'white');ImageDraw.Draw(im).ellipse((35,30,125,130),fill=color)
    stream=io.BytesIO();im.save(stream,format='PNG');return stream.getvalue()


class V2Tests(unittest.TestCase):
    def test_deterministic_fruit_only_descriptor(self):
        a,info=features(photo());b,_=features(photo())
        self.assertIsNotNone(a);np.testing.assert_array_equal(a,b)
        self.assertEqual(len(a),DIMENSIONS);self.assertFalse(info['roiHumanVerified'])
        self.assertGreater(info['foregroundFraction'],.1)
        x,y,w,h=info['roi']
        self.assertLessEqual(x+w,160);self.assertLessEqual(y+h,160)
        self.assertGreater(w,0);self.assertGreater(h,0)
        # Saturated fruit hue has one occupied bin; paper is not counted.
        self.assertEqual(np.count_nonzero(a[48:64]),1)

    def test_uniform_image_and_low_saturation_never_force_grade(self):
        for raw in (photo((160,160,160)),):
            result=predict(artifact(),raw)
            self.assertFalse(result['evaluable']);self.assertIsNone(result['label'])
            self.assertIsNone(result['confidence']);self.assertEqual(result['scoresUncalibrated'],{})
            self.assertIsNone(result['proposedGrade'])

    def test_mask_failure_preserves_review_path_and_original_roi(self):
        with patch('vision.ag055.v2.features',return_value=(None,{'roi':[0,0,160,160],'reason':'uncertain'})):
            r=predict(artifact(),photo());self.assertEqual(r['status'],'no_evaluable')
            self.assertEqual(r['roi'],[0,0,160,160]);self.assertTrue(r['uncertainty']['humanReviewRequired'])

    def test_enclosed_dark_defect_is_retained_by_contour_fill(self):
        im=Image.open(io.BytesIO(photo()));ImageDraw.Draw(im).ellipse((65,65,95,95),fill='black')
        buf=io.BytesIO();im.save(buf,format='PNG')
        _,mask,_=segment(buf.getvalue())
        self.assertIsNotNone(mask);self.assertTrue(mask[80,80])
        x,_=features(buf.getvalue());self.assertGreater(x[0],.02)

    def test_opencv_failure_returns_no_evaluable(self):
        with patch('vision.ag055.v2.cv2.grabCut',side_effect=cv2.error('software failure')):
            r=predict(artifact(),photo());self.assertFalse(r['evaluable'])
            self.assertEqual(r['reason'],'segmentation_failed');self.assertIsNone(r['label'])

    def test_changed_model_hash_is_rejected_before_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);(base/'models').mkdir()
            (base/'models/ag055_v2_tomate.json').write_text(json.dumps(artifact()))
            (base/'SHA256SUMS.json').write_text(json.dumps({'models/ag055_v2_tomate.json':'0'*64}))
            with self.assertRaisesRegex(ValueError,'SHA-256 mismatch'):
                load_models(base/'models','tomate')

    def test_runtime_rejects_old_descriptor_nan_and_tiny_scales(self):
        a=artifact();validate(a)
        for changes in ({'version':'v1'},{'featureVersion':'old'},{'kentAccredited':True}):
            with self.assertRaises(ValueError):validate({**a,**changes})
        for scale in ([1e-8]*DIMENSIONS,[float('nan')]*DIMENSIONS):
            with self.assertRaises(ValueError):validate({**a,'model':{**a['model'],'scale':scale}})

    def test_safe_proposal_always_experimental(self):
        r=predict(artifact(),photo());self.assertTrue(r['evaluable'])
        self.assertIsNone(r['proposedGrade']);self.assertFalse(r['confidenceCalibrated'])
        self.assertFalse(r['independentPerformanceEvaluated']);self.assertFalse(r['kentVerified'])

    def test_training_scaler_and_transitive_grouping(self):
        try:
            from vision.ag055.train_v2 import robust_fit,transform,grouping
        except ImportError:
            self.skipTest('Optional development sklearn dependency required')
        center,scale=robust_fit(np.array([[.1,0],[.1,1]],np.float32))
        self.assertAlmostEqual(center[1],.5);self.assertGreaterEqual(scale.min(),.05)
        self.assertTrue(np.isfinite(transform([[.1,1000]],center,scale)).all())
        rows=[{'product':'mango','group':'A','relative':'a','sha256':'x'},
              {'product':'mango','group':'B','relative':'b','sha256':'x'},
              {'product':'mango','group':'B','relative':'c','sha256':'z'}]
        self.assertEqual(len(set(grouping(rows,{'newHeuristicPairs':[]}))),1)
