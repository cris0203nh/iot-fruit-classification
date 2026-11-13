"""Pilot integration contracts; real artifacts are read-only when explicitly provided."""
import json
import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from app.models import Evaluation
from app.routers import quality_prediction as router
import test_ag055_i04 as previous
from vision.ag055.pilot117 import VERSION,FEATURE_VERSION,predict,validate
from vision.ag055.review import _publish_json,review_history


class PilotTests(unittest.TestCase):
    setUp=previous.I04Tests.setUp
    auth=previous.I04Tests.auth

    def fixture(self):
        artifact={'version':VERSION,'featureVersion':FEATURE_VERSION,'product':'tomate',
            'labels':['E0','E1','E2'],'labelSpace':'pilot_declared_e0e1e2','deploymentAuthorized':False,
            'humanReviewRequired':True,'independentTestMetrics':None,'kentAccredited':False,
            'trainingImageHashes':['test']*56,'dataVersion':'synthetic-contract-only','limitations':['synthetic fixture'],
            'model':{'mean':[0]*676,'scale':[1]*676,'gamma':.01,'supportVectors':[[0]*676]*3,
                'dualCoef':[[0]*3]*2,'intercept':[1,1,1],'supportCounts':[1,1,1]}}
        return artifact

    def test_json_runtime_rejects_contract_drift_and_returns_only_unaccredited_proposal(self):
        model=self.fixture();validate(model)
        raw=(self.dir/'images/1.jpg').read_bytes();prediction=predict(model,raw)
        self.assertIn(prediction['label'],['E0','E1','E2'])
        self.assertFalse(prediction['confidenceCalibrated']);self.assertIsNone(prediction['proposedGrade'])
        self.assertFalse(prediction['independentPerformanceEvaluated'])
        with self.assertRaises(ValueError):validate({**model,'kentAccredited':True})
        with self.assertRaises(ValueError):validate({**model,'labelSpace':'original_source_labels'})

    def test_pilot_permissions_idempotence_and_reuse_human_review(self):
        with patch.object(router,'_pilot_models',return_value=[(self.fixture(),'f'*64)]), \
             patch.dict(os.environ,{'AGROSCAN_REVIEW_RUN':str(self.dir),'AGROSCAN_TEST_INSTANCE':'1'}):
            base=f'/api/evaluations/{self.eid}/vision/quality'
            self.assertEqual(self.client.get(base+'/pilot/status').status_code,401)
            self.assertEqual(self.client.post(base+'/pilot/analyze',headers=self.auth('revisor')).status_code,403)
            first=self.client.post(base+'/pilot/analyze',headers=self.auth())
            self.assertEqual(first.status_code,200,first.text);row=first.json()[0]
            self.assertIsNone(row['proposedGrade']);self.assertEqual(row['details']['labelSpace'],'pilot_declared_e0e1e2')
            self.assertEqual(self.client.post(base+'/pilot/analyze',headers=self.auth()).json()[0]['id'],row['id'])
            body={'imageId':'I-000001','predictionId':row['id'],'grade':'no_evaluable','roi':[0,0,160,160],
                'roiConfirmed':True,'humanConfirmed':True,'rubricVersion':'tomato-ext-test',
                'evidence':'Software-only review; no agronomic annotation','expectedLastEventId':None}
            event=self.client.post(base+'/reviews',json=body,headers=self.auth())
            self.assertEqual(event.status_code,201,event.text)
            with self.Session() as db:self.assertIsNone(db.query(Evaluation).first().visual_category)

    def test_imported_declaration_null_metadata_and_correction_chain(self):
        body_model=self.fixture()
        raw=(self.dir/'images/1.jpg').read_bytes();sample=None
        with self.Session() as db:
            ev=db.query(Evaluation).first();sample=router._sample(ev,ev.images[0],raw)
        (self.dir/'reviews').mkdir()
        declaration={'id':'pilot117_declared','eventId':'declared-event','grade':'E1','reviewer':None,
            'reviewedAt':None,'rubricVersion':None,'evidence':None,'imageSha256':sample['sha256'],
            'importedAt':'2026-01-01T12:00:00+00:00','annotationPurpose':'human_label_declaration_import',
            'roiHumanVerified':False,'accreditationVerified':False,'supersedesEventId':None}
        _publish_json(self.dir/'reviews/declared.json',declaration)
        with patch.object(router,'_pilot_models',return_value=[(body_model,'d'*64)]), \
             patch.dict(os.environ,{'AGROSCAN_REVIEW_RUN':str(self.dir),'AGROSCAN_TEST_INSTANCE':'1'}):
            base=f'/api/evaluations/{self.eid}/vision/quality'
            queue=self.client.get(base+'/reviews',headers=self.auth()).json()
            self.assertEqual(queue['images'][0]['status'],'declared_pending_metadata')
            self.assertIsNone(queue['images'][0]['history'][0]['reviewer'])
            row=self.client.post(base+'/pilot/analyze',headers=self.auth()).json()[0]
            body={'imageId':'I-000001','predictionId':row['id'],'grade':'E2','roi':[0,0,160,160],
                'roiConfirmed':True,'humanConfirmed':True,'rubricVersion':'tomato-ext-test',
                'evidence':'R03 software test evidence in central ROI','expectedLastEventId':'declared-event'}
            event=self.client.post(base+'/reviews',json=body,headers=self.auth())
            self.assertEqual(event.status_code,201,event.text)
            self.assertEqual(event.json()['supersedesEventId'],'declared-event')
            self.assertEqual(json.loads((self.dir/'reviews/declared.json').read_text()),declaration)

    @unittest.skipUnless(os.getenv('AG055_PILOT117_RUN'),'Provide the audited real pilot workspace')
    def test_real_photo_with_real_pilot_json_and_117_declared_records(self):
        run=Path(os.environ['AG055_PILOT117_RUN']);records=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(len(records),117)
        sample=next(r for r in records if r['product']=='tomate');raw=(Path(sample['root'])/sample['relative']).read_bytes()
        with self.Session() as db:
            img=db.query(Evaluation).first().images[0];(self.dir/img.relative_path).write_bytes(raw);img.size_bytes=len(raw);db.commit()
        with patch.dict(os.environ,{'AGROSCAN_PILOT117_MODELS_PATH':str(run/'models')}):
            response=self.client.post(f'/api/evaluations/{self.eid}/vision/quality/pilot/analyze',headers=self.auth())
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()[0]['details']['perView'][0]['sampleUse'],'training_photo')
