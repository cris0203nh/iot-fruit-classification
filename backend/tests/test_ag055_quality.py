"""AG-055: ensayos controlados, sin etiquetado real ni base de usuario."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image as PILImage
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Evaluation, Image, Lot, Role, User
from app.security import create_access_token, hash_password
from app.routers import quality_prediction
from app.quality_prediction_models import QualityPrediction
from vision.ag055.quality_model import VERSION, probabilities, predict_artifact
from vision.evaluation.agrop42.comparar_calidad_ag034 import FEATURES, LABELS


class AG055QualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ag055-test-')
        self.addCleanup(self.tmp.cleanup)
        self.dir=Path(self.tmp.name)
        self.engine=create_engine(f'sqlite:///{self.dir / "test.sqlite"}',connect_args={'check_same_thread':False})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session=sessionmaker(bind=self.engine,expire_on_commit=False)
        with self.Session() as db:
            self.tokens={}
            for role in ('operador','revisor'):
                user=User(username='ag055_'+role,full_name='AG055 '+role,
                    password_hash=hash_password('TestSeguro12345!'),
                    is_active=True,roles=[Role(name=role)])
                db.add(user);db.flush()
                self.tokens[role]=create_access_token(user.id)
            lot=Lot(code='AG055-TOM',product='tomate',status='open',responsible='TEST')
            db.add(lot);db.flush()
            ev=Evaluation(lot_id=lot.id,piece_id='P-001',product='tomate')
            db.add(ev);db.flush()
            self.eid=f'E-{ev.id:06d}'
            (self.dir/'images').mkdir()
            for number in (1,2):
                output=io.BytesIO()
                PILImage.new('RGB',(160,160),(160,45,25)).save(output,format='JPEG')
                raw=output.getvalue()
                fn=f'images/{number}.jpg'
                (self.dir/fn).write_bytes(raw)
                db.add(Image(evaluation_id=ev.id,view=f'vista-{number}',
                             relative_path=fn,content_type='image/jpeg',size_bytes=len(raw),
                             idempotency_key=f'{number:064x}'))
            db.commit()

        def isolated_db():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db]=isolated_db
        self.addCleanup(lambda:app.dependency_overrides.pop(get_db,None))
        patchdir=patch.object(quality_prediction,'DATA_DIR',self.dir)
        patchdir.start();self.addCleanup(patchdir.stop)
        self.client=TestClient(app)
        self.addCleanup(self.client.close)

    def auth(self,role='operador'):
        return {'Authorization':'Bearer '+self.tokens[role]}

    def model(self):
        return {'version':VERSION,'product':'tomate','features':list(FEATURES),
            'deploymentAuthorized':False,'humanReviewRequired':True,
            'rubricVersion':'tomato-ext-v0.1',
            'model':{'algoritmo':'softmax_l2_python','clases':list(LABELS),
                     'pesos':[[0.0]*(len(FEATURES)+1) for _ in LABELS],
                     'medias_train':[0.0]*len(FEATURES),'escalas_train':[1.0]*len(FEATURES)}}

    def fake_detection(self, frame):
        return [{'product':'tomate','confidence':0.95,
                'polygon':[[20,20],[120,20],[120,120],[20,120]],
                'box':[20,20,120,120]}]

    def test_without_model_never_creates_grade_or_snapshots(self):
        with patch.object(quality_prediction,'_load_model',return_value=(None,None)):
            status=self.client.get(f'/api/evaluations/{self.eid}/vision/quality/status',headers=self.auth('revisor'))
            self.assertEqual(status.status_code,200,status.text)
            self.assertFalse(status.json()['modelAvailable'])
            result=self.client.post(f'/api/evaluations/{self.eid}/vision/quality/analyze',headers=self.auth())
            self.assertEqual(result.status_code,200,result.text)
            self.assertIsNone(result.json()['proposedGrade'])
        with self.Session() as db:
            self.assertIsNone(db.query(QualityPrediction).first())
            ev=db.query(Evaluation).first()
            self.assertIsNone(ev.visual_category)

    def test_reviewer_cannot_generate_proposal(self):
        response=self.client.post(f'/api/evaluations/{self.eid}/vision/quality/analyze',headers=self.auth('revisor'))
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.client.post(f'/api/evaluations/{self.eid}/vision/quality/analyze').status_code,401)

    def test_experimental_proposal_is_immutable_and_idempotent(self):
        with patch.object(quality_prediction,'_load_model',return_value=(self.model(),'a'*64)), \
             patch.object(quality_prediction,'_infer_products',side_effect=self.fake_detection):
            first=self.client.post(f'/api/evaluations/{self.eid}/vision/quality/analyze',headers=self.auth())
            self.assertEqual(first.status_code,200,first.text)
            self.assertEqual(first.json()['status'],'experimental_proposal')
            self.assertEqual(first.json()['proposedGrade'],'E0')
            self.assertTrue(first.json()['humanReviewRequired'])
            self.assertFalse(first.json()['automaticallyFinalized'])
            second=self.client.post(f'/api/evaluations/{self.eid}/vision/quality/analyze',headers=self.auth())
            self.assertEqual(second.status_code,200,second.text)
            self.assertEqual(first.json()['id'],second.json()['id'])
            listing=self.client.get(f'/api/evaluations/{self.eid}/vision/quality/proposals',headers=self.auth('revisor'))
            self.assertEqual(len(listing.json()),1)
        with self.Session() as db:
            ev=db.query(Evaluation).first()
            self.assertIsNone(ev.visual_category)
            self.assertEqual(ev.status,'processing')
            self.assertEqual(db.query(QualityPrediction).count(),1)

    def test_disagreement_does_not_publish_proposed_grade(self):
        n=[0]
        def disagree(artifact,raw,roi):
            n[0]+=1
            return {'proposedGrade':'E1' if n[0]==1 else 'E2','scoresUncalibrated':None}
        with patch.object(quality_prediction,'_load_model',return_value=(self.model(),'b'*64)), \
             patch.object(quality_prediction,'_infer_products',side_effect=self.fake_detection), \
             patch.object(quality_prediction,'predict_artifact',side_effect=disagree):
            response=self.client.post(f'/api/evaluations/{self.eid}/vision/quality/analyze',headers=self.auth())
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['status'],'needs_review')
            self.assertIsNone(response.json()['proposedGrade'])

    def test_numeric_scores_are_explicitly_uncalibrated(self):
        model=self.model()
        out=probabilities(model['model'],[0.0]*len(FEATURES))
        self.assertAlmostEqual(sum(out.values()),1,places=6)
        self.assertFalse(predict_artifact(model,(self.dir/'images/1.jpg').read_bytes(),[20,20,100,100])['confidenceCalibrated'])


if __name__=='__main__':
    unittest.main()
