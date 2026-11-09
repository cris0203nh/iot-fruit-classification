"""AG-037 / AGROP-45: no evaluable queda pendiente, evidencia y categoria originales intactas."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Evaluation, Image, Lot, Review, Role, User
from app.vision_assessment_models import VisionAssessment
from app.security import create_access_token, hash_password
from app.uncertainty import GateResult, classify_detection
import app.routers.uncertainty as gate_router


class DecisionGateTests(unittest.TestCase):
    def test_no_detection(self):
        self.assertEqual(classify_detection('mango', []).reason, 'sin_deteccion')

    def test_wrong_class(self):
        self.assertEqual(classify_detection('mango', [dict(label='tomato fruit', confidence=.99, mask=True)]).reason,
                         'clase_no_esperada')

    def test_low_confidence(self):
        r = classify_detection('tomate', [dict(label='tomato fruit', confidence=.399, mask=True)])
        self.assertTrue(r.pending)
        self.assertEqual(r.reason, 'confianza_insuficiente')

    def test_threshold_inclusive(self):
        self.assertFalse(classify_detection('mango', [dict(label='mango fruit', confidence=.40, mask=True)]).pending)

    def test_no_mask(self):
        self.assertEqual(classify_detection('mango', [dict(label='mango fruit', confidence=.80, mask=False)]).reason,
                         'segmentacion_no_evaluable')

    def test_multiple(self):
        r = classify_detection('mango', [dict(label='mango fruit', confidence=.9, mask=True),
                                         dict(label='mango fruit', confidence=.8, mask=True)])
        self.assertEqual(r.reason, 'multiples_candidatos')

    def test_invalid_confidence_rejected(self):
        for bad in (float('nan'), float('inf'), -0.01, 1.1):
            with self.subTest(confidence=bad), self.assertRaises(ValueError):
                classify_detection('mango', [dict(label='mango fruit', confidence=bad, mask=True)])


class APIGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = Path(self.tmp.name)
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.users = {}
        with Session(self.engine) as db:
            for role_name in ('administrador', 'revisor', 'operador'):
                user = User(username=f'ag037_{role_name}', full_name=role_name,
                            password_hash=hash_password('PruebaSegura123'), is_active=True,
                            roles=[Role(name=role_name)])
                db.add(user)
                db.flush()
                self.users[role_name] = user.id
            lot = Lot(code='AG037-LOTE', product='mango', status='open')
            db.add(lot)
            db.flush()
            ev = Evaluation(lot_id=lot.id, piece_id='PIEZA-1', product='mango',status='processing')
            db.add(ev)
            db.flush()
            self.ev_id = ev.id
            self.image_bytes = b'\xff\xd8\xffEVIDENCIA ORIGINAL AG037\xff\xd9'
            (self.data_dir / 'original.jpg').write_bytes(self.image_bytes)
            img = Image(evaluation_id=ev.id, view='vista-1', relative_path='original.jpg',
                        content_type='image/jpeg', size_bytes=len(self.image_bytes))
            db.add(img)
            db.flush()
            self.image_id = img.id
            db.commit()
        def override_db():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.addCleanup(app.dependency_overrides.clear)
        self.original_data_dir = gate_router.DATA_DIR
        gate_router.DATA_DIR = self.data_dir
        self.addCleanup(setattr, gate_router, 'DATA_DIR', self.original_data_dir)

    def tearDown(self):
        self.engine.dispose()

    def auth(self, role):
        return {'Authorization': f'Bearer {create_access_token(self.users[role])}'}

    def run_gate(self, role='revisor', **kwargs):
        body = {'imageId':f'I-{self.image_id:06d}', **kwargs}
        return self.client.post(f'/api/evaluations/E-{self.ev_id:06d}/vision/review-gate',
                                headers=self.auth(role), json=body)

    def test_low_confidence_sets_pending_keeps_original(self):
        old_sha = hashlib.sha256(self.image_bytes).hexdigest()
        with patch.object(gate_router, '_infer',return_value=(GateResult(True,'confianza_insuficiente',.35,1),[{'label':'mango fruit','confidence':.35,'box':[1,2,3,4],'mask':True}])):
            result = self.run_gate('operador')
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['status'],'pending_review')
        self.assertEqual(result.json()['imageSha256'],old_sha)
        self.assertEqual((self.data_dir/'original.jpg').read_bytes(),self.image_bytes)
        with Session(self.engine) as db:
            ev = db.get(Evaluation,self.ev_id)
            self.assertIsNone(ev.visual_category)
            self.assertEqual(ev.status,'pending_review')
            row = db.scalar(select(Review))
            self.assertEqual(row.type,'uncertainty')
            self.assertIn(old_sha,row.reason)
            snapshot=db.scalar(select(VisionAssessment))
            self.assertEqual(snapshot.image_sha256,old_sha)
            self.assertEqual(snapshot.reason,'confianza_insuficiente')
        trace = self.client.get(f'/api/evaluations/E-{self.ev_id:06d}/traceability',headers=self.auth('revisor'))
        self.assertEqual(trace.status_code,200,trace.text)
        self.assertEqual(trace.json()['reviews'][0]['type'],'uncertainty')

    def test_manual_flag_preserves_original_category_after_completed(self):
        with Session(self.engine) as db:
            ev = db.get(Evaluation,self.ev_id)
            ev.status='completed';ev.visual_category='primera'
            db.commit()
        result = self.run_gate(forceReview=True,note='La fruta está fuera del encuadre')
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['reason'],'solicitud_manual')
        with Session(self.engine) as db:
            ev = db.get(Evaluation,self.ev_id)
            self.assertEqual(ev.status,'pending_review')
            self.assertEqual(ev.visual_category,'primera')
            self.assertEqual(ev.images[0].relative_path,'original.jpg')

    def test_idempotent_manual_review(self):
        self.assertEqual(self.run_gate(forceReview=True,note='Fotografía muy borrosa').status_code,200)
        repeat = self.run_gate(forceReview=True,note='Fotografía muy borrosa')
        self.assertEqual(repeat.status_code,200)
        self.assertTrue(repeat.json()['eventAlreadyRecorded'])
        with Session(self.engine) as db:
            self.assertEqual(len(db.scalars(select(Review)).all()),1)

    def test_ready_does_not_auto_accept_quality(self):
        with patch.object(gate_router, '_infer',return_value=(GateResult(False,'deteccion_apta_para_captura',.9,1),[{'label':'mango fruit','confidence':.9,'box':[1,2,3,4],'mask':True}])):
            response=self.run_gate('operador')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['decision'],'ready_to_capture')
        with Session(self.engine) as db:
            self.assertEqual(db.get(Evaluation,self.ev_id).status,'processing')
            self.assertIsNone(db.get(Evaluation,self.ev_id).visual_category)
            self.assertEqual(len(db.scalars(select(Review)).all()),0)
            self.assertEqual(len(db.scalars(select(VisionAssessment)).all()),1)

    def test_detector_unavailable_fails_closed(self):
        with patch.object(gate_router,'_infer',side_effect=RuntimeError('model failed')):
            r=self.run_gate('operador')
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['reason'],'detector_no_disponible')
        self.assertEqual(r.json()['status'],'pending_review')

    def test_operator_cannot_force_manual_review(self):
        self.assertEqual(self.run_gate('operador',forceReview=True,note='Fotografía no evaluable').status_code,403)

    def test_manual_review_requires_justification(self):
        self.assertEqual(self.run_gate(forceReview=True,note='borrosa').status_code,422)

    def test_missing_image_and_mismatched_reference(self):
        r=self.client.post(f'/api/evaluations/E-{self.ev_id:06d}/vision/review-gate',
                          headers=self.auth('revisor'),json={'imageId':'I-999999'})
        self.assertEqual(r.status_code,404)
        (self.data_dir/'original.jpg').unlink()
        self.assertEqual(self.run_gate(forceReview=True,note='Fotografía no evaluable').status_code,409)

    def test_block_cancelled_evaluation(self):
        with Session(self.engine) as db:
            db.get(Evaluation,self.ev_id).status='cancelled';db.commit()
        self.assertEqual(self.run_gate(forceReview=True,note='Fotografía no evaluable').status_code,409)

    def test_reviewer_can_resolve_without_overwriting_original(self):
        with Session(self.engine) as db:
            db.get(Evaluation,self.ev_id).visual_category='primera';db.commit()
        self.assertEqual(self.run_gate(forceReview=True,note='Fotografía no evaluable').status_code,200)
        response=self.client.post(f'/api/evaluations/E-{self.ev_id:06d}/vision/resolve',
                                  headers=self.auth('revisor'),json={
                                      'reason':'Inspección visual de evidencia original',
                                      'outcome':'E1'})
        self.assertEqual(response.status_code,200,response.text)
        with Session(self.engine) as db:
            ev=db.get(Evaluation,self.ev_id)
            self.assertEqual(ev.status,'completed')
            self.assertEqual(ev.visual_category,'primera')
            self.assertEqual(len(db.scalars(select(Review)).all()),2)


    def test_no_evaluable_closes_without_grade_and_preserves_image(self):
        self.assertEqual(self.run_gate(forceReview=True,note='La foto no permite evaluar').status_code,200)
        result=self.client.post(f'/api/evaluations/E-{self.ev_id:06d}/vision/resolve',
                    headers=self.auth('revisor'),
                    json={'outcome':'no_evaluable','reason':'No se distinguen los defectos externos'})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['reviewOutcome'],'no_evaluable')
        with Session(self.engine) as db:
            ev=db.get(Evaluation,self.ev_id)
            self.assertEqual(ev.status,'completed')
            self.assertIsNone(ev.visual_category)
            self.assertEqual(len(db.scalars(select(Review)).all()),2)
        self.assertEqual((self.data_dir/'original.jpg').read_bytes(),self.image_bytes)

    def test_operator_cannot_resolve(self):
        self.run_gate(forceReview=True,note='La foto no permite evaluar')
        result=self.client.post(f'/api/evaluations/E-{self.ev_id:06d}/vision/resolve',
                    headers=self.auth('operador'),
                    json={'outcome':'E0','reason':'Revision de grado de prueba'})
        self.assertEqual(result.status_code,403)

    def test_unverified_result_is_not_accepted(self):
        self.run_gate(forceReview=True,note='La foto no permite evaluar')
        result=self.client.post(f'/api/evaluations/E-{self.ev_id:06d}/vision/resolve',
                    headers=self.auth('revisor'),json={'outcome':'primera','reason':'Texto suficientemente largo'})
        self.assertEqual(result.status_code,422)

    def test_readback_automatic_detections_and_idempotency(self):
        predicted=(GateResult(False,'deteccion_apta_para_captura',.80,1),
                   [{'label':'mango fruit','confidence':.8,'box':[1,2,3,4],'mask':True}])
        with patch.object(gate_router,'_infer',return_value=predicted) as model:
            self.assertEqual(self.run_gate('operador').status_code,200)
            self.assertEqual(self.run_gate('operador').status_code,200)
            self.assertEqual(model.call_count,1)
        assessment=self.client.get(f'/api/evaluations/E-{self.ev_id:06d}/vision/assessments',
                                   headers=self.auth('revisor'))
        self.assertEqual(assessment.status_code,200,assessment.text)
        self.assertEqual(len(assessment.json()),1)
        self.assertEqual(assessment.json()[0]['detections'][0]['box'],[1,2,3,4])
        self.assertEqual(assessment.json()[0]['outcome'],'ready_to_capture')

    def test_processed_auto_result_keeps_original_after_manual_objection(self):
        predicted=(GateResult(False,'deteccion_apta_para_captura',.80,1),
                   [{'label':'mango fruit','confidence':.8,'box':[1,2,3,4],'mask':True}])
        with patch.object(gate_router,'_infer',return_value=predicted):
            self.assertEqual(self.run_gate('operador').status_code,200)
        self.assertEqual(self.run_gate('revisor',forceReview=True,note='Observacion de la fruta').status_code,200)
        result=self.client.get(f'/api/evaluations/E-{self.ev_id:06d}/vision/assessments',
                               headers=self.auth('revisor'))
        self.assertEqual(len(result.json()),1)
        self.assertEqual(result.json()[0]['outcome'],'ready_to_capture')



if __name__=='__main__':
    unittest.main()
