"""AG-056 I02: API, SQLite and evidence integrity integration, no hardware/model."""
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Evaluation, Image, Lot, Review, Role, User
from app.quality_prediction_models import QualityPrediction
from app.decision_models import ReviewDecisionEvidence
from app.vision_assessment_models import VisionAssessment
from app.security import create_access_token

T0 = datetime(2026, 11, 10, 14, 30, tzinfo=timezone.utc)


class QueueApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = create_engine('sqlite:///' + str(self.root / 'queue.db'),
                                    connect_args={'check_same_thread': False})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.users = {}
        with self.Session() as db:
            for role in ('operador', 'revisor', 'administrador'):
                user = User(username='ag056_' + role, full_name='Prueba AG056 ' + role,
                            password_hash='TEST_NO_LOGIN', roles=[Role(name=role)], is_active=True)
                db.add(user)
                db.flush()
                self.users[role] = user.id
            db.commit()
        def use_test_db():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = use_test_db
        self.addCleanup(lambda: app.dependency_overrides.pop(get_db, None))
        p = patch('app.review_queue.DATA_DIR', self.root)
        p.start()
        self.addCleanup(p.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def auth(self, role='revisor'):
        return {'Authorization': 'Bearer ' + create_access_token(self.users[role])}

    def request(self, role='revisor', **filters):
        return self.client.get('/api/reviews/queue', params=filters, headers=self.auth(role))

    def evaluation(self, *, code='LOTE-AG056', piece='PZ-1', product='mango',
                   status='completed', views=2, date=T0):
        with self.Session() as db:
            lot = db.scalar(select(Lot).where(Lot.code == code))
            if lot is None:
                lot = Lot(code=code, product=product, status='open')
                db.add(lot)
                db.flush()
            ev = Evaluation(lot_id=lot.id, piece_id=piece, product=product,
                            status=status, created_at=date, image_count=views)
            db.add(ev)
            db.flush()
            image_info = []
            for i in range(views):
                raw = f'AG056 original {code} {piece} view {i}'.encode()
                relative_path = f'E{ev.id}_photo{i}.jpg'
                (self.root / relative_path).write_bytes(raw)
                img = Image(evaluation_id=ev.id, view=f'vista-{i+1}',
                            relative_path=relative_path, content_type='image/jpeg',
                            size_bytes=len(raw))
                db.add(img)
                db.flush()
                image_info.append((img.id, hashlib.sha256(raw).hexdigest(), relative_path))
            db.commit()
            return ev.id, image_info

    def proposal(self, ev, images, *, grades=('E0', 'E0'), status='experimental_e0e1e2_v2', at=T0,
                 payload=None):
        sources = [{'imageId': f'I-{i:06d}', 'sha256': sha} for i, sha, _ in images]
        details = payload if payload is not None else {'sources': sources, 'perView': [
            {'imageId': f'I-{item[0]:06d}', 'label': grade, 'evaluable': True}
            for item, grade in zip(images, grades)
        ]}
        with self.Session() as db:
            db.add(QualityPrediction(evaluation_id=ev, product='mango', status=status,
                source_fingerprint=hashlib.sha256(str(at).encode()).hexdigest(),
                model_sha256='a'*64, model_version='ag055-v2-test',
                proposed_grade=None, reason='experimental_only',
                created_at=at, details_json=json.dumps(details)))
            db.commit()

    def detection(self, ev, image, *, outcome='pending_review'):
        img_id, sha, _ = image
        with self.Session() as db:
            db.add(VisionAssessment(evaluation_id=ev, image_id=img_id,
                image_sha256=sha, model_version='yoloe-test', rules_version='test-v1',
                inference_size=512, inference_confidence=.2, acceptance_threshold=.4,
                outcome=outcome, reason='confianza_insuficiente', confidence=.2,
                candidate_count=1, detections_json='[]', created_at=T0))
            db.commit()

    def human(self, ev, image, *, at=T0+timedelta(minutes=1)):
        image_id, sha, _ = image
        with self.Session() as db:
            review = Review(evaluation_id=ev, type='review', actor_id='ag056_revisor',
                reason='Inspección registrada AG038', updated_value='E0', performed_at=at)
            db.add(review)
            db.flush()
            db.add(ReviewDecisionEvidence(review_id=review.id, evaluation_id=ev,
                image_id=image_id, image_sha256=sha, action='initial_label',
                request_id=f'00000000-0000-4000-8000-{review.id:012d}', payload_sha256='b'*64))
            db.commit()

    def test_empty_queue(self):
        response = self.request()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['items'], [])
        self.assertEqual(response.json()['total'], 0)
        self.assertEqual(response.json()['counts']['all'], 0)

    def test_reviewer_and_admin_only(self):
        self.evaluation(status='pending_review')
        self.assertEqual(self.client.get('/api/reviews/queue').status_code, 401)
        self.assertEqual(self.request('operador').status_code, 403)
        self.assertEqual(self.request('revisor').status_code, 200)
        self.assertEqual(self.request('administrador').status_code, 200)

    def test_pending_without_model_is_selected(self):
        ev, _ = self.evaluation(status='pending_review')
        obj = self.request().json()
        self.assertEqual((obj['total'], obj['items'][0]['priority']), (1, 'normal'))
        self.assertEqual(obj['items'][0]['evaluationId'], f'E-{ev:06d}')
        self.assertEqual(obj['items'][0]['reasons'][0]['code'], 'acquisition_pending_review')

    def test_high_priority_detection(self):
        ev, images = self.evaluation()
        self.detection(ev, images[0])
        obj = self.request().json()
        self.assertEqual(obj['counts'], {'high': 1, 'normal': 0, 'all': 1})
        self.assertEqual(obj['items'][0]['imageIds'], [f'I-{images[0][0]:06d}'])
        self.assertIn('uncertain_detection', {r['code'] for r in obj['items'][0]['reasons']})

    def test_detection_ready_alone_does_not_enter_queue(self):
        ev, images = self.evaluation()
        self.detection(ev, images[0], outcome='ready_to_capture')
        self.assertEqual(self.request().json()['total'], 0)

    def test_quality_two_views_only_partially_reviewed(self):
        ev, images = self.evaluation()
        self.proposal(ev, images)
        self.assertEqual(self.request().json()['items'][0]['imageCount'], 2)
        self.human(ev, images[0])
        self.assertEqual(self.request().json()['items'][0]['imageIds'], [f'I-{images[1][0]:06d}'])
        self.human(ev, images[1])
        self.assertEqual(self.request().json()['total'], 0)

    def test_newer_model_snapshot_reopens_after_decision(self):
        ev, images = self.evaluation()
        self.proposal(ev, images, at=T0)
        for img in images:
            self.human(ev, img)
        self.assertEqual(self.request().json()['total'], 0)
        self.proposal(ev, images, at=T0 + timedelta(hours=1))
        self.assertEqual(self.request().json()['total'], 1)

    def test_priority_filters_stable_order_and_counts(self):
        old, ims = self.evaluation(code='L1', piece='OLD', status='pending_review', date=T0)
        urgent, photos = self.evaluation(code='L1', piece='URGENT', date=T0+timedelta(days=1))
        self.detection(urgent, photos[0])
        self.evaluation(code='L2', piece='TOMATO', product='tomate',
                        status='pending_review', date=T0+timedelta(days=2))
        obj = self.request(limit=1, offset=0).json()
        self.assertEqual((obj['total'], obj['counts']), (3, {'high': 1, 'normal': 2, 'all': 3}))
        self.assertEqual(obj['items'][0]['evaluationId'], f'E-{urgent:06d}')
        self.assertTrue(obj['hasMore'])
        self.assertEqual(self.request(limit=1, offset=1).json()['items'][0]['evaluationId'], f'E-{old:06d}')
        self.assertEqual(self.request(priority='normal').json()['total'], 2)
        self.assertEqual(self.request(priority='high').json()['total'], 1)
        self.assertEqual(self.request(product='tomate').json()['total'], 1)
        self.assertEqual(self.request(lot='l1').json()['total'], 2)
        self.assertEqual(self.request(lot='unknown').json()['total'], 0)
        self.assertEqual(self.request(offset=5).json()['items'], [])

    def test_multiple_sql_batches_preserve_total_and_order(self):
        with self.Session() as db:
            lot = Lot(code='BATCH-AG056', product='mango', status='open')
            db.add(lot)
            db.flush()
            for ix in range(105):
                db.add(Evaluation(lot_id=lot.id, piece_id=f'B-{ix}',
                    product='mango', status='pending_review', image_count=0,
                    created_at=T0 + timedelta(seconds=ix)))
            db.commit()
        first = self.request(lot='BATCH-AG056', limit=2).json()
        self.assertEqual((first['total'], first['counts']['high']), (105, 105))
        last = self.request(lot='BATCH-AG056', limit=10, offset=100).json()
        self.assertEqual(len(last['items']), 5)
        self.assertFalse(last['hasMore'])
        self.assertNotEqual(first['items'][0]['evaluationId'], last['items'][0]['evaluationId'])

    def test_bad_query_is_422(self):
        for params in ({'limit': 0}, {'limit': 101}, {'offset': -1},
                       {'priority': 'critical'}, {'product': 'pear'}):
            self.assertEqual(self.request(**params).status_code, 422, params)

    def test_cancelled_error_and_processing_are_excluded(self):
        for ix, status in enumerate(('cancelled', 'error', 'processing')):
            self.evaluation(code=f'L{ix}', piece='excluded', status=status)
        self.assertEqual(self.request().json()['total'], 0)

    def test_pending_capture_missing_image_is_high_priority_without_ai(self):
        _ev, images = self.evaluation(status='pending_review')
        (self.root / images[0][2]).unlink()
        obj = self.request().json()['items'][0]
        self.assertEqual(obj['priority'], 'high')
        self.assertIn('evidence_unavailable', {x['code'] for x in obj['reasons']})

    def test_windows_path_canonicalization_does_not_invalidate_sha(self):
        """An ordinary file stays verifiable if absolute() differs from resolve()."""
        from app.review_queue import _image_sha

        _ev, photos = self.evaluation(status='pending_review', views=1)
        with self.Session() as db:
            image = db.get(Image, photos[0][0])
            # Windows absolute() and resolve() may differ in normalization.
            # The verifier must validate the actual source, not their equality.
            with patch.object(Path, 'absolute', side_effect=RuntimeError('nonportable path test')):
                self.assertEqual(_image_sha(image, self.root), photos[0][1])
        self.assertEqual(self.request().json()['counts'], {'high': 0, 'normal': 1, 'all': 1})

    def test_tampered_image_requires_high_priority(self):
        ev, images = self.evaluation()
        self.proposal(ev, images)
        file_path = self.root / images[0][2]
        file_path.write_bytes(b'changed original evidence')
        obj = self.request().json()['items'][0]
        self.assertEqual(obj['priority'], 'high')
        self.assertIn('source_hash_unverified', {x['code'] for x in obj['reasons']})
        self.assertEqual(file_path.read_bytes(), b'changed original evidence')

    def test_invalid_relative_path_fails_closed(self):
        ev, images = self.evaluation()
        self.proposal(ev, images)
        with self.Session() as db:
            img = db.get(Image, images[0][0])
            img.relative_path = '../outside.jpg'
            db.commit()
        obj = self.request().json()['items'][0]
        self.assertEqual(obj['priority'], 'high')
        self.assertIn('source_hash_unverified', {x['code'] for x in obj['reasons']})

    def test_malformed_snapshot_is_escalated(self):
        ev, images = self.evaluation()
        self.proposal(ev, images)
        with self.Session() as db:
            row = db.scalar(select(QualityPrediction))
            row.details_json = '{oops'
            db.commit()
        obj = self.request().json()['items'][0]
        self.assertEqual(obj['priority'], 'high')
        self.assertEqual(obj['reasons'][0]['code'], 'quality_source_missing')

    def test_pending_evidence_missing_is_high(self):
        self.evaluation(status='pending_review', views=0)
        obj = self.request().json()['items'][0]
        self.assertEqual(obj['priority'], 'high')
        self.assertEqual(obj['reasons'][0]['code'], 'acquisition_evidence_missing')

    def test_does_not_modify_database(self):
        ev, images = self.evaluation()
        self.proposal(ev, images)
        with self.Session() as db:
            before = (db.scalar(select(func.count(Review.id))),
                      db.get(Evaluation, ev).status,
                      db.get(Evaluation, ev).visual_category)
        self.assertEqual(self.request().status_code, 200)
        with self.Session() as db:
            after = (db.scalar(select(func.count(Review.id))),
                     db.get(Evaluation, ev).status,
                     db.get(Evaluation, ev).visual_category)
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
