"""V2 API authorization, persistence, no-evaluable and immutable review contracts."""
import os
import unittest
from unittest.mock import patch

from app.models import Evaluation, Image
from app.quality_prediction_models import QualityPrediction
from app.routers import quality_prediction as router
from vision.tests.test_ag055_v2 import artifact
import test_ag055_i04 as previous


class V2APITests(unittest.TestCase):
    def setUp(self):
        previous.I04Tests.setUp(self)
        detector=patch.object(router,'_infer_products',return_value=[{'product':'tomate','confidence':.95,
            'polygon':[[20,20],[120,20],[120,120]],'box':[20,20,120,120]}])
        detector.start();self.addCleanup(detector.stop)
    auth=previous.I04Tests.auth

    def test_detection_gate_distinguishes_absence_ambiguity_product_and_missing_mask(self):
        raw=(self.dir/'images/1.jpg').read_bytes()
        valid={'product':'tomate','confidence':.95,'polygon':[[20,20],[120,20],[120,120]],'box':[20,20,120,120]}
        for candidates,reason in (([],'fruit_not_detected'),([valid,valid],'ambiguous_fruit_detection'),
                ([{**valid,'product':'mango'}],'incompatible_or_uncertain_detection'),
                ([{**valid,'confidence':.2}],'incompatible_or_uncertain_detection'),
                ([{**valid,'polygon':[]}],'detector_mask_unavailable')):
            with patch.object(router,'_infer_products',return_value=candidates),patch.object(router,'predict_v2') as classify:
                result=router._predict_v2_view(artifact(),raw)
                self.assertEqual(result['reason'],reason);self.assertIsNone(result['label']);classify.assert_not_called()

    def test_detector_outage_is_retryable_and_never_cached_as_a_grade(self):
        path=f'/api/evaluations/{self.eid}/vision/quality/v2/analyze'
        with patch.object(router,'_v2_models',return_value=[(artifact(),'a'*64)]):
            with patch.object(router,'_infer_products',side_effect=RuntimeError('synthetic detector unavailable')):
                self.assertEqual(self.client.post(path,headers=self.auth()).status_code,503)
            with self.Session() as db:self.assertEqual(db.query(QualityPrediction).count(),0)
            self.assertEqual(self.client.post(path,headers=self.auth()).status_code,200)

    def test_invalid_view_does_not_discard_other_view_or_write_human_grade(self):
        (self.dir/'images/2.jpg').write_bytes(b'invalid synthetic photo')
        with self.Session() as db:
            db.get(Image,2).size_bytes=len(b'invalid synthetic photo')
            db.commit()
        path=f'/api/evaluations/{self.eid}/vision/quality/v2/analyze'
        with patch.object(router,'_v2_models',return_value=[(artifact(),'a'*64)]):
            result=self.client.post(path,headers=self.auth())
        self.assertEqual(result.status_code,200,result.text)
        views=result.json()[0]['details']['perView']
        self.assertEqual(len(views),2);self.assertEqual(views[1]['reason'],'image_decode_failed')
        self.assertIsNone(result.json()[0]['proposedGrade'])
        with self.Session() as db:self.assertIsNone(db.query(Evaluation).first().visual_category)

    def test_new_policy_appends_snapshot_and_keeps_old_prediction_immutable(self):
        path=f'/api/evaluations/{self.eid}/vision/quality/v2/analyze'
        with patch.object(router,'_v2_models',return_value=[(artifact(),'a'*64)]):
            with patch.object(router,'V2_POLICY_VERSION','previous-test-policy'):
                previous_row=self.client.post(path,headers=self.auth()).json()[0]
            current=self.client.post(path,headers=self.auth()).json()[0]
            repeated=self.client.post(path,headers=self.auth()).json()[0]
        self.assertNotEqual(previous_row['id'],current['id']);self.assertEqual(current['id'],repeated['id'])
        stored=self.client.get(f'/api/evaluations/{self.eid}/vision/quality/proposals',headers=self.auth()).json()
        self.assertEqual(stored[0],previous_row)

    def test_installed_model_directory_and_explicit_override(self):
        with patch.dict(os.environ, {'AGROSCAN_V2_MODELS_PATH': ''}), \
             patch.object(router, 'load_v2_models', return_value=[]) as load:
            router._v2_models('tomate')
            load.assert_called_once_with(str(router.DATA_DIR / 'ag055_v2' / 'models'), 'tomate')
        with patch.dict(os.environ, {'AGROSCAN_V2_MODELS_PATH': str(self.dir / 'explicit')}), \
             patch.object(router, 'load_v2_models', return_value=[]) as load:
            router._v2_models('mango')
            load.assert_called_once_with(str(self.dir / 'explicit'), 'mango')

    def test_v2_permissions_idempotence_and_human_review_even_no_evaluable(self):
        with patch.object(router,'_v2_models',return_value=[(artifact(),'a'*64)]), \
             patch.dict(os.environ,{'AGROSCAN_REVIEW_RUN':str(self.dir),'AGROSCAN_TEST_INSTANCE':'1'}):
            base=f'/api/evaluations/{self.eid}/vision/quality'
            self.assertEqual(self.client.get(base+'/v2/status').status_code,401)
            self.assertEqual(self.client.post(base+'/v2/analyze',headers=self.auth('revisor')).status_code,403)
            first=self.client.post(base+'/v2/analyze',headers=self.auth())
            self.assertEqual(first.status_code,200,first.text);r=first.json()[0]
            self.assertEqual(r['status'],'experimental_e0e1e2_v2');self.assertIsNone(r['proposedGrade'])
            self.assertEqual(self.client.post(base+'/v2/analyze',headers=self.auth()).json()[0]['id'],r['id'])
            body={'imageId':'I-000001','predictionId':r['id'],'grade':'no_evaluable','roi':[0,0,160,160],
                  'roiConfirmed':True,'humanConfirmed':True,'rubricVersion':'tomato-ext-test',
                  'evidence':'Automated software check only; NOT real human annotation','expectedLastEventId':None}
            saved=self.client.post(base+'/reviews',json=body,headers=self.auth())
            self.assertEqual(saved.status_code,201,saved.text)
            self.assertEqual(saved.json()['annotationPurpose'],'automated_test_not_human_ground_truth')
            with self.Session() as db:self.assertIsNone(db.query(Evaluation).first().visual_category)

    def test_missing_or_invalid_model_fail_closed(self):
        base=f'/api/evaluations/{self.eid}/vision/quality'
        with patch.object(router,'load_v2_models',side_effect=ValueError('invalid')):
            self.assertEqual(self.client.get(base+'/v2/status',headers=self.auth()).status_code,503)
        with patch.object(router,'_v2_models',return_value=[]):
            self.assertEqual(self.client.post(base+'/v2/analyze',headers=self.auth()).status_code,409)
