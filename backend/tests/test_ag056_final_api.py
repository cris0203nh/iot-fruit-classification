"""AG-056 I04: real FastAPI/SQLite workflow, synthetic source bytes only.

No hardware, real fruit data, production DB or calibrated model is involved.
"""
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Evaluation, Image, Lot, Review, Role, User
from app.quality_prediction_models import QualityPrediction
from app.decision_models import ReviewDecisionEvidence
from app.security import create_access_token
from app.routers import review_decisions, evaluations, uncertainty

T0 = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)


class FinalApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ag056-i04-api-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = create_engine('sqlite:///' + str(self.root / 'api.sqlite'),
                                    connect_args={'check_same_thread': False, 'timeout': 5})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        self.users = {}
        with self.Session() as db:
            for role in ('operador', 'revisor', 'administrador'):
                user = User(username='ag056_i04_' + role,
                    full_name='Prueba AG056 ' + role, password_hash='TEST_NO_LOGIN',
                    roles=[Role(name=role)], is_active=True)
                db.add(user)
                db.flush()
                self.users[role] = user.id
            lot = Lot(code='AG056-FINAL', product='tomate', status='open')
            db.add(lot)
            db.flush()
            ev = Evaluation(lot_id=lot.id, piece_id='PZ-FINAL', product='tomate',
                            status='pending_review', image_count=2, created_at=T0)
            db.add(ev)
            db.flush()
            self.pk = ev.id
            self.photos = []
            for ix in range(2):
                raw = f'AG056 simulated photograph {ix}'.encode()
                path = self.root / f'photo-{ix}.jpg'
                path.write_bytes(raw)
                im = Image(evaluation_id=ev.id, view=f'vista-{ix+1}',
                           relative_path=path.name, content_type='image/jpeg',
                           size_bytes=len(raw))
                db.add(im)
                db.flush()
                self.photos.append((im.id, hashlib.sha256(raw).hexdigest(), path))
            sources = [{'imageId': f'I-{i:06d}', 'sha256': sha} for i, sha, _ in self.photos]
            db.add(QualityPrediction(evaluation_id=ev.id, product='tomate',
                status='experimental_e0e1e2_v2', reason='experimental_only',
                source_fingerprint='1'*64, model_sha256='2'*64, model_version='test-v2',
                proposed_grade=None, created_at=T0,
                details_json=json.dumps({'sources': sources, 'perView': [
                    {'imageId': s['imageId'], 'label': 'E1', 'evaluable': True}
                    for s in sources]})))
            db.commit()
        def db_override():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = db_override
        self.addCleanup(lambda: app.dependency_overrides.pop(get_db, None))
        for module in (review_decisions, evaluations, uncertainty):
            p = patch.object(module, 'DATA_DIR', self.root)
            p.start()
            self.addCleanup(p.stop)
        p = patch('app.review_queue.DATA_DIR', self.root)
        p.start()
        self.addCleanup(p.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.evaluation_id = f'E-{self.pk:06d}'
        self.route = f'/api/evaluations/{self.evaluation_id}/review-decisions'

    def auth(self, role='revisor'):
        return {'Authorization': 'Bearer ' + create_access_token(self.users[role])}

    def decision(self, ix, *, action='initial_label', new_value='E1',
                 revision=None, request_id=None, role='revisor'):
        return self.client.post(self.route, headers=self.auth(role), json={
            'action': action, 'imageId': f'I-{self.photos[ix][0]:06d}',
            'newValue': new_value, 'reason': 'Revisión visual de evidencia sintética AG-056',
            'expectedReviewId': revision, 'requestId': request_id or str(uuid4())})

    def status(self):
        with self.Session() as db:
            return db.get(Evaluation, self.pk).status

    def queue(self, role='revisor'):
        return self.client.get('/api/reviews/queue', headers=self.auth(role))

    def test_two_image_api_write_and_queue_close_only_after_second(self):
        first = self.decision(0)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(self.status(), 'pending_review')
        pending = self.queue().json()
        self.assertEqual(pending['total'], 1)
        self.assertEqual(pending['items'][0]['imageIds'], [f'I-{self.photos[1][0]:06d}'])
        second = self.decision(1, action='confirm', new_value='E1', revision=first.json()['id'])
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(self.status(), 'completed')
        self.assertEqual(self.queue().json()['total'], 0)
        with self.Session() as db:
            self.assertEqual(db.scalar(select(func.count(ReviewDecisionEvidence.review_id))), 2)
            self.assertIsNone(db.get(Evaluation, self.pk).visual_category)

    def test_pending_without_model_cannot_close_after_one_photo(self):
        with self.Session() as db:
            for item in db.scalars(select(QualityPrediction)).all():
                db.delete(item)
            db.commit()
        first = self.decision(0)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(self.status(), 'pending_review')
        last = self.decision(1, action='confirm', new_value='E1', revision=first.json()['id'])
        self.assertEqual(last.status_code, 201, last.text)
        self.assertEqual(self.status(), 'completed')

    def test_exact_idempotent_replay_never_duplicates(self):
        key = str(uuid4())
        a = self.decision(0, request_id=key)
        b = self.decision(0, request_id=key)
        self.assertEqual(a.status_code, 201, a.text)
        self.assertEqual(b.status_code, 201, b.text)
        self.assertEqual(a.json()['id'], b.json()['id'])
        self.assertEqual(self.status(), 'pending_review')
        with self.Session() as db:
            self.assertEqual(db.scalar(select(func.count(ReviewDecisionEvidence.review_id))), 1)

    def test_second_reviewer_stale_revision_is_rejected(self):
        first = self.decision(0)
        self.assertEqual(first.status_code, 201)
        stale = self.decision(1, role='administrador', revision=None)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.status(), 'pending_review')
        with self.Session() as db:
            self.assertEqual(db.scalar(select(func.count(ReviewDecisionEvidence.review_id))), 1)

    def test_operator_cannot_write_or_read_queue(self):
        self.assertEqual(self.decision(0, role='operador').status_code, 403)
        self.assertEqual(self.queue('operador').status_code, 403)
        self.assertEqual(self.queue('administrador').status_code, 200)
        self.assertEqual(self.client.get('/api/reviews/queue').status_code, 401)

    def test_quality_sha_conflict_does_not_add_human_decision(self):
        pk, _, path = self.photos[0]
        old = path.read_bytes()
        path.write_bytes(b'Z' * len(old))  # same size: provenance, not just length, must fail.
        self.assertEqual(self.decision(0).status_code, 409)
        with self.Session() as db:
            self.assertEqual(db.scalar(select(func.count(ReviewDecisionEvidence.review_id))), 0)
            self.assertEqual(db.get(Evaluation, self.pk).status, 'pending_review')

    def test_generic_legacy_review_cannot_close_ag055_incident(self):
        r = self.client.post(f'/api/evaluations/{self.evaluation_id}/reviews',
            headers=self.auth(), json={'actorId': 'ag056_i04_revisor',
            'reason': 'Intento legacy de revisión sin fotografía identificada',
            'newValue': 'E1'})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(self.status(), 'pending_review')
        with self.Session() as db:
            self.assertEqual(db.scalar(select(func.count(Review.id))), 0)

    def test_ag037_global_legacy_resolution_cannot_hide_other_quality_views(self):
        with self.Session() as db:
            db.add(Review(evaluation_id=self.pk, type='uncertainty', actor_id='test',
                reason=f'AG037|image=I-{self.photos[0][0]:06d}|sha256={self.photos[0][1]}|cause=sin_deteccion|note=prueba',
                previous_value='processing', updated_value='pending_review', performed_at=T0))
            db.commit()
        r = self.client.post(f'/api/evaluations/{self.evaluation_id}/vision/resolve',
            headers=self.auth(), json={'outcome': 'E1',
            'reason': 'Resolución legacy de prueba sin referencia por imagen'})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(self.status(), 'pending_review')
        with self.Session() as db:
            self.assertEqual(db.scalar(select(func.count(Review.id))), 1)

    def test_ag037_legacy_cannot_resolve_two_uncertain_photos(self):
        with self.Session() as db:
            for photo_id, sha, _ in self.photos:
                db.add(Review(evaluation_id=self.pk, type='uncertainty', actor_id='test',
                    reason=f'AG037|image=I-{photo_id:06d}|sha256={sha}|cause=sin_deteccion|note=prueba',
                    previous_value='processing', updated_value='pending_review', performed_at=T0))
            db.commit()
        r = self.client.post(f'/api/evaluations/{self.evaluation_id}/vision/resolve',
            headers=self.auth(), json={'outcome': 'E1',
            'reason': 'Revisión de ambas fotografías requiere vínculo individual'})
        self.assertEqual(r.status_code, 409, r.text)
        with self.Session() as db:
            self.assertEqual(db.scalar(select(func.count(Review.id))), 2)

if __name__ == '__main__':
    unittest.main()
