"""AG-038: decisions leave a reproducible audit trail on isolated SQLite.

No ESP32, real fruit photo or actual professional diagnosis is used in tests.
"""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Evaluation, Image, Lot, Review, Role, User
from app.decision_models import ReviewDecisionEvidence
from app.vision_assessment_models import VisionAssessment
from app.security import create_access_token, hash_password
from app.routers import review_decisions as review_router


class ReviewDecisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.engine = create_engine('sqlite:///' + str(self.root / 'db.sqlite'),
                                    connect_args={'check_same_thread': False, 'timeout': 5})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.users = {}
        self.original = b'\xff\xd8\xffAG038-TEST-ORIGINAL\xff\xd9'
        (self.root / 'evidence.jpg').write_bytes(self.original)
        self.sha = hashlib.sha256(self.original).hexdigest()
        with self.Session() as db:
            for role in ('revisor', 'operador'):
                user = User(username='ag038_' + role, full_name='Prueba ' + role,
                            password_hash=hash_password('ClaveFicticiaSoloTest123'),
                            is_active=True, roles=[Role(name=role)])
                db.add(user)
                db.flush()
                self.users[role] = user.id
            lot = Lot(code='AG038-SIM', product='mango', status='open')
            db.add(lot)
            db.flush()
            ev = Evaluation(lot_id=lot.id, piece_id='PIEZA-AG038',
                            product='mango', status='pending_review')
            db.add(ev)
            db.flush()
            img = Image(evaluation_id=ev.id, view='vista-1',
                        relative_path='evidence.jpg', content_type='image/jpeg',
                        size_bytes=len(self.original))
            db.add(img)
            db.flush()
            self.eval_pk, self.image_pk = ev.id, img.id
            db.commit()
        def override_db():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = override_db
        self.addCleanup(lambda: app.dependency_overrides.pop(get_db, None))
        p = patch.object(review_router, 'DATA_DIR', self.root)
        p.start()
        self.addCleanup(p.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.evaluation_id = f'E-{self.eval_pk:06d}'
        self.image_id = f'I-{self.image_pk:06d}'
        self.path = f'/api/evaluations/{self.evaluation_id}/review-decisions'

    def auth(self, role='revisor'):
        return {'Authorization': 'Bearer ' + create_access_token(self.users[role])}

    def create(self, action='initial_label', value='E1', expected=None, *,
               reason='Inspección de la evidencia visual de prueba', request_id=None,
               role='revisor', image_id=None):
        return self.client.post(self.path, headers=self.auth(role), json={
            'action': action, 'imageId': image_id or self.image_id,
            'newValue': value, 'expectedReviewId': expected, 'reason': reason,
            'requestId': request_id or str(uuid4()),
        })

    def test_first_label_then_confirm_then_correct(self):
        first = self.create()
        self.assertEqual(first.status_code, 201, first.text)
        a = first.json()
        self.assertIsNone(a['previousValue'])
        self.assertEqual(a['newValue'], 'E1')
        self.assertEqual(a['actorId'], 'ag038_revisor')
        self.assertEqual(a['imageSha256'], self.sha)
        confirm = self.create('confirm', 'E1', a['id'])
        self.assertEqual(confirm.status_code, 201, confirm.text)
        self.assertEqual(confirm.json()['previousValue'], 'E1')
        corrected = self.create('correct', 'E2', confirm.json()['id'])
        self.assertEqual(corrected.status_code, 201, corrected.text)
        self.assertEqual(corrected.json()['previousValue'], 'E1')
        self.assertEqual(corrected.json()['newValue'], 'E2')
        log = self.client.get(self.path, headers=self.auth())
        self.assertEqual(log.status_code, 200, log.text)
        self.assertEqual(log.json()['currentValue'], 'E2')
        self.assertEqual(len(log.json()['decisions']), 3)
        self.assertIsNone(log.json()['originalValue'])
        self.assertEqual((self.root/'evidence.jpg').read_bytes(), self.original)
        # Read-back from a distinct SQLite connection, not a cached Session.
        independent_engine = create_engine('sqlite:///' + str(self.root/'db.sqlite'))
        try:
            with Session(independent_engine) as db:
                ev = db.get(Evaluation, self.eval_pk)
                self.assertIsNone(ev.visual_category)
                self.assertEqual(len(db.scalars(select(Review)).all()), 3)
                self.assertEqual(len(db.scalars(select(ReviewDecisionEvidence)).all()), 3)
                self.assertEqual(db.get(Review, int(a['id'][2:])).updated_value, 'E1')
        finally:
            independent_engine.dispose()

    def test_confirm_requires_same_value(self):
        first = self.create().json()
        self.assertEqual(self.create('confirm', 'E2', first['id']).status_code, 422)

    def test_correct_requires_different_value(self):
        first = self.create().json()
        self.assertEqual(self.create('correct', 'E1', first['id']).status_code, 422)

    def test_stale_revision_is_rejected(self):
        self.assertEqual(self.create().status_code, 201)
        self.assertEqual(self.create('initial_label', 'E2', None).status_code, 409)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(ReviewDecisionEvidence)).all()), 1)

    def test_exact_replay_is_idempotent(self):
        request_id = str(uuid4())
        a = self.create(request_id=request_id)
        b = self.create(request_id=request_id)
        self.assertEqual(a.status_code, 201, a.text)
        self.assertEqual(b.status_code, 201, b.text)
        self.assertEqual(a.json()['id'], b.json()['id'])
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(Review)).all()), 1)

    def test_replay_with_modified_payload_is_conflict(self):
        rid = str(uuid4())
        self.assertEqual(self.create(request_id=rid).status_code, 201)
        self.assertEqual(self.create(value='E2', request_id=rid).status_code, 409)

    def test_operator_is_denied(self):
        self.assertEqual(self.create(role='operador').status_code, 403)

    def test_reason_required(self):
        self.assertEqual(self.create(reason='vago').status_code, 422)
        self.assertEqual(self.create(reason='  ').status_code, 422)

    def test_wrong_image_id(self):
        self.assertEqual(self.create(image_id='I-999999').status_code, 404)

    def test_missing_image_blocks_decision(self):
        (self.root / 'evidence.jpg').unlink()
        self.assertEqual(self.create().status_code, 409)

    def test_no_evaluable_does_not_invent_grade(self):
        result = self.create('no_evaluable', 'no_evaluable')
        self.assertEqual(result.status_code, 201, result.text)
        self.assertIsNone(result.json()['previousValue'])
        with self.Session() as db:
            self.assertIsNone(db.get(Evaluation, self.eval_pk).visual_category)

    def test_no_evaluable_can_be_confirmed_and_corrected_later(self):
        initial = self.create('no_evaluable', 'no_evaluable')
        self.assertEqual(initial.status_code, 201, initial.text)
        confirmed = self.create('confirm', 'no_evaluable', initial.json()['id'])
        self.assertEqual(confirmed.status_code, 201, confirmed.text)
        corrected = self.create('correct', 'E0', confirmed.json()['id'])
        self.assertEqual(corrected.status_code, 201, corrected.text)
        self.assertEqual(corrected.json()['previousValue'], 'no_evaluable')

    def test_initial_label_not_allowed_when_value_exists(self):
        first = self.create().json()
        self.assertEqual(self.create('initial_label', 'E2', first['id']).status_code, 409)

    def test_visual_and_commercial_must_not_mix(self):
        first = self.create().json()
        self.assertEqual(self.create('correct', 'segunda', first['id']).status_code, 422)

    def test_legacy_commercial_category_can_be_confirmed_without_conversion(self):
        with self.Session() as db:
            ev = db.get(Evaluation, self.eval_pk)
            ev.visual_category = 'primera'
            db.commit()
        self.assertEqual(self.create('confirm', 'primera').status_code, 201)
        first = self.client.get(self.path, headers=self.auth()).json()['revisionId']
        self.assertEqual(self.create('correct', 'segunda', first).status_code, 201)
        latest = self.client.get(self.path, headers=self.auth()).json()
        self.assertEqual(latest['originalValue'], 'primera')
        self.assertEqual(latest['currentValue'], 'segunda')

    def test_original_snapshot_conflict_detected(self):
        with self.Session() as db:
            db.add(VisionAssessment(
                evaluation_id=self.eval_pk, image_id=self.image_pk,
                image_sha256='0' * 64, model_version='sim-model', rules_version='sim-rules',
                inference_size=512, inference_confidence=.25, acceptance_threshold=.4,
                outcome='pending_review', reason='confianza_insuficiente', confidence=.35,
                candidate_count=1, detections_json='[]',
            ))
            db.commit()
        self.assertEqual(self.create().status_code, 409)

    def test_processing_evaluation_is_rejected(self):
        with self.Session() as db:
            db.get(Evaluation, self.eval_pk).status = 'processing'
            db.commit()
        self.assertEqual(self.create().status_code, 409)

    def test_existing_review_is_observed_by_revision_control(self):
        with self.Session() as db:
            db.add(Review(evaluation_id=self.eval_pk, type='uncertainty',
                          actor_id='ag037', reason='Revisión solicitada',
                          previous_value='processing', updated_value='pending_review'))
            db.commit()
        self.assertEqual(self.create().status_code, 409)
        revision = self.client.get(self.path, headers=self.auth()).json()['revisionId']
        self.assertTrue(revision.startswith('R-'))
        self.assertEqual(self.create(expected=revision).status_code, 201)


if __name__ == '__main__':
    unittest.main()
