"""I04 authorization, immutable inference and append-only reviews in isolated fixtures."""
import json
import os
import unittest
from unittest.mock import patch

from app.models import Evaluation, Image
from app.quality_prediction_models import QualityPrediction
from app.routers import quality_prediction as router
import test_ag055_exploratory as exploratory_tests


class I04Tests(unittest.TestCase):
    setUp=exploratory_tests.ExploratoryAPITests.setUp
    auth=exploratory_tests.ExploratoryAPITests.auth
    artifact=exploratory_tests.ExploratoryAPITests.artifact

    def setup_review(self):
        env=patch.dict(os.environ,{'AGROSCAN_REVIEW_RUN':str(self.dir),'AGROSCAN_TEST_INSTANCE':'1'})
        env.start();self.addCleanup(env.stop)
        models=patch.object(router,'_exploratory_models',return_value=[(self.artifact(),'e'*64)])
        models.start();self.addCleanup(models.stop)
        self.base=f'/api/evaluations/{self.eid}/vision/quality'
        response=self.client.post(self.base+'/exploratory/analyze',headers=self.auth())
        self.assertEqual(response.status_code,200,response.text)
        self.prediction=response.json()[0]
        return {'imageId':'I-000001','predictionId':self.prediction['id'],'grade':'E1','roi':[0,0,160,160],
            'roiConfirmed':True,'humanConfirmed':True,'rubricVersion':'tomato-ext-test',
            'evidence':'R03 software test only; visible evidence in central ROI','expectedLastEventId':None}

    def test_auth_no_impersonation_and_explicit_human_declaration(self):
        body=self.setup_review()
        self.assertEqual(self.client.get(self.base+'/reviews').status_code,401)
        self.assertEqual(self.client.post(self.base+'/reviews',json=body,headers=self.auth('revisor')).status_code,403)
        self.assertEqual(self.client.post(self.base+'/reviews',json={**body,'reviewer':'another_person'},headers=self.auth()).status_code,422)
        self.assertEqual(self.client.post(self.base+'/reviews',json={**body,'humanConfirmed':False},headers=self.auth()).status_code,409)
        self.assertEqual(self.client.post(self.base+'/reviews',json={**body,'predictionId':9999},headers=self.auth()).status_code,404)

    def test_corrections_preserve_inference_and_original_grades(self):
        body=self.setup_review()
        before=self.client.get(self.base+'/proposals',headers=self.auth()).json()
        self.assertEqual(self.client.get(self.base+'/reviews',headers=self.auth()).json()['images'][0]['status'],'pending')
        first=self.client.post(self.base+'/reviews',json=body,headers=self.auth())
        self.assertEqual(first.status_code,201,first.text)
        event=first.json(); self.assertEqual(event['reviewer'],'ag055_operador')
        self.assertFalse(event['accreditationVerified'])
        self.assertFalse(event['roiHumanVerified'])
        self.assertEqual(event['annotationPurpose'],'automated_test_not_human_ground_truth')
        stale=self.client.post(self.base+'/reviews',json=body,headers=self.auth())
        self.assertEqual(stale.status_code,409)
        correction=self.client.post(self.base+'/reviews',json={**body,'expectedLastEventId':event['eventId'],'grade':'no_evaluable'},headers=self.auth())
        self.assertEqual(correction.status_code,201,correction.text)
        self.assertEqual(correction.json()['supersedesEventId'],event['eventId'])
        history=self.client.get(self.base+'/reviews',headers=self.auth('revisor')).json()['images'][0]['history']
        self.assertEqual([e['grade'] for e in history],['E1','no_evaluable'])
        self.assertEqual(self.client.get(self.base+'/proposals',headers=self.auth()).json(),before)
        with self.Session() as db:
            self.assertIsNone(db.query(Evaluation).first().visual_category)
            self.assertEqual(db.query(QualityPrediction).count(),1)

    def test_tampered_evidence_and_missing_photograph_and_inference_failure(self):
        body=self.setup_review()
        path=self.dir/'images/1.jpg'; raw=path.read_bytes()
        path.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
        self.assertEqual(self.client.post(self.base+'/reviews',json=body,headers=self.auth()).status_code,409)
        path.write_bytes(raw)
        with patch.object(router,'predict_exploratory',side_effect=ValueError('failed')):
            # A new image fingerprint avoids replaying the existing immutable snapshot.
            with self.Session() as db:
                img=db.query(Image).filter(Image.id==2).first(); db.delete(img); db.commit()
            self.assertEqual(self.client.post(self.base+'/exploratory/analyze',headers=self.auth()).status_code,409)
        with self.Session() as db:
            db.query(Image).delete(); db.commit()
        self.assertEqual(self.client.post(self.base+'/exploratory/analyze',headers=self.auth()).status_code,409)

    def test_unconfigured_review_storage_is_explicit(self):
        self.base=f'/api/evaluations/{self.eid}/vision/quality'
        with patch.dict(os.environ,{'AGROSCAN_REVIEW_RUN':''}):
            self.assertEqual(self.client.get(self.base+'/reviews',headers=self.auth()).status_code,409)
