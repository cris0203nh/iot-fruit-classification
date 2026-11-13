"""API contracts use synthetic fixtures; optional REAL run evidence is explicit."""
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select

from app.models import Evaluation, Image
from app.quality_prediction_models import QualityPrediction
from app.routers import quality_prediction as router
import test_ag055_quality as quality_tests
from vision.ag055.experimental import FEATURE_COUNT, FEATURE_VERSION, VERSION


class ExploratoryAPITests(unittest.TestCase):
    setUp=quality_tests.AG055QualityTests.setUp
    auth=quality_tests.AG055QualityTests.auth

    def artifact(self):
        return {'version':VERSION,'featureVersion':FEATURE_VERSION,'task':'TQ','product':'tomate',
            'labelSpace':'original_source_labels','labels':['Fresh','Rotten'],
            'deploymentAuthorized':False,'humanReviewRequired':True,'dataVersion':'test-only',
            'limitations':['SYNTHETIC software fixture'], 'model':{'algorithm':'softmax_l2',
            'mean':[0]*FEATURE_COUNT,'scale':[1]*FEATURE_COUNT,'weights':[[0,0]]*FEATURE_COUNT,'bias':[1,0]}}

    def test_authenticated_status_and_blocked_no_model(self):
        with patch.object(router,'_exploratory_models',return_value=[]):
            path=f'/api/evaluations/{self.eid}/vision/quality/exploratory'
            self.assertEqual(self.client.get(path+'/status').status_code,401)
            self.assertEqual(self.client.get(path+'/status',headers=self.auth('revisor')).json()['models'],[])
            self.assertEqual(self.client.post(path+'/analyze',headers=self.auth('revisor')).status_code,403)
            self.assertEqual(self.client.post(path+'/analyze',headers=self.auth()).status_code,409)

    def test_persisted_images_audited_and_never_publish_grade(self):
        with patch.object(router,'_exploratory_models',return_value=[(self.artifact(),'b'*64)]):
            path=f'/api/evaluations/{self.eid}/vision/quality/exploratory/analyze'
            first=self.client.post(path,headers=self.auth())
            self.assertEqual(first.status_code,200,first.text)
            row=first.json()[0]
            self.assertEqual(row['status'],'exploratory_original_labels')
            self.assertIsNone(row['proposedGrade'])
            self.assertEqual(row['details']['perView'][0]['label'],'Fresh')
            self.assertFalse(row['details']['perView'][0]['roiHumanVerified'])
            self.assertEqual(self.client.post(path,headers=self.auth()).json()[0]['id'],row['id'])
        with self.Session() as db:
            ev=db.scalar(select(Evaluation)); self.assertIsNone(ev.visual_category)
            self.assertEqual(ev.status,'processing')
            self.assertEqual(db.query(QualityPrediction).count(),1)

    def test_invalid_artifact_and_corrupt_evidence_are_explicit(self):
        with patch.dict(os.environ,{'AGROSCAN_EXPLORATORY_MODELS_PATH':str(self.dir)}):
            p=self.dir/'ag055_exploratory_TQ.json'
            m=self.artifact(); m['labels']=['E0','E2']; p.write_text(json.dumps(m))
            response=self.client.get(f'/api/evaluations/{self.eid}/vision/quality/exploratory/status',headers=self.auth())
            self.assertEqual(response.status_code,503)
        with patch.object(router,'_exploratory_models',return_value=[(self.artifact(),'c'*64)]):
            (self.dir/'images/1.jpg').write_bytes(b'corrupted')
            response=self.client.post(f'/api/evaluations/{self.eid}/vision/quality/exploratory/analyze',headers=self.auth())
            self.assertEqual(response.status_code,409)

    @unittest.skipUnless(os.getenv('AG055_REAL_RUN'),'Set AG055_REAL_RUN to verify real photographs and trained artifacts')
    def test_real_photographs_through_authenticated_fastapi(self):
        run=Path(os.environ['AG055_REAL_RUN'])
        manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
        samples=[r for r in manifest if r['source']=='TQ' and r.get('split')=='test'][:2]
        with self.Session() as db:
            for img,sample in zip(db.scalars(select(Image).order_by(Image.id)).all(),samples):
                raw=(Path(sample['root'])/sample['relative']).read_bytes()
                (self.dir/img.relative_path).write_bytes(raw); img.size_bytes=len(raw)
            db.commit()
        with patch.dict(os.environ,{'AGROSCAN_EXPLORATORY_MODELS_PATH':str(run/'models')}):
            response=self.client.post(f'/api/evaluations/{self.eid}/vision/quality/exploratory/analyze',headers=self.auth())
            self.assertEqual(response.status_code,200,response.text)
            rows=response.json()
            self.assertEqual({r['details']['task'] for r in rows},{'TQ','FG'})
            self.assertTrue(all(r['proposedGrade'] is None for r in rows))
            # Reproducible, reviewable evidence; photographs never copied into Git.
            evidence=run/'fastapi_real_evidence.json'
            if not evidence.exists():
                evidence.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    unittest.main()
