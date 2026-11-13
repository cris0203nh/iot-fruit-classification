"""V2 API authorization, persistence, no-evaluable and immutable review contracts."""
import os
import unittest
from unittest.mock import patch

from app.models import Evaluation
from app.routers import quality_prediction as router
from vision.tests.test_ag055_v2 import artifact
import test_ag055_i04 as previous


class V2APITests(unittest.TestCase):
    setUp=previous.I04Tests.setUp
    auth=previous.I04Tests.auth

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
