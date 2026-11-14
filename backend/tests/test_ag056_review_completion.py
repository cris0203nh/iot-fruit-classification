"""AG-056 I04: persisted two-photo completion, source integrity, and no new queue table.

All samples are generated synthetic bytes; no physical fruit, model validation,
or actual human observations are claimed.
"""
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Evaluation, Image, Lot, Review
from app.decision_models import ReviewDecisionEvidence
from app.quality_prediction_models import QualityPrediction
from app.vision_assessment_models import VisionAssessment
from app.review_completion import reconcile_review_status, pending_ag037_images
from app.review_queue import get_review_queue

T0 = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)


class ReviewCompletionPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ag056-i04-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.engine = create_engine('sqlite:///' + str(self.root / 'db.sqlite'),
                                    connect_args={'check_same_thread': False})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        with self.Session() as db:
            lot = Lot(code='AG056-I04', product='mango', status='open')
            db.add(lot)
            db.flush()
            ev = Evaluation(lot_id=lot.id, piece_id='M-01', product='mango',
                            status='pending_review', image_count=2, created_at=T0)
            db.add(ev)
            db.flush()
            self.eval_id = ev.id
            self.images = []
            for ix in range(2):
                raw = f'AG056 synthetic view {ix}'.encode()
                path = f'view-{ix}.jpg'
                (self.root / path).write_bytes(raw)
                photo = Image(evaluation_id=ev.id, view=f'vista-{ix+1}',
                              relative_path=path, content_type='image/jpeg', size_bytes=len(raw))
                db.add(photo)
                db.flush()
                self.images.append((photo.id, hashlib.sha256(raw).hexdigest(), path))
            sources = [{'imageId': f'I-{x[0]:06d}', 'sha256': x[1]} for x in self.images]
            prediction = QualityPrediction(evaluation_id=ev.id, product='mango',
                status='experimental_e0e1e2_v2', reason='experimental_only',
                source_fingerprint='1'*64, model_sha256='2'*64, model_version='test-v2',
                proposed_grade=None, created_at=T0, details_json=json.dumps({
                    'sources': sources, 'perView': [
                        {'imageId': s['imageId'], 'label': 'E0', 'evaluable': True}
                        for s in sources]}))
            db.add(prediction)
            db.commit()

    def _decide(self, index, at):
        photo_id, sha, _ = self.images[index]
        with self.Session() as db:
            ev = db.get(Evaluation, self.eval_id)
            record = Review(evaluation_id=ev.id, type='review', actor_id='revisor-test',
                            reason='Vista sintética inspeccionada, solo prueba',
                            updated_value='E0', performed_at=at)
            db.add(record)
            db.flush()
            db.add(ReviewDecisionEvidence(review_id=record.id, evaluation_id=ev.id,
                image_id=photo_id, image_sha256=sha, action='confirm',
                request_id=f'00000000-0000-4000-8000-{record.id:012d}',
                payload_sha256='a'*64))
            db.flush()
            still_pending = reconcile_review_status(db, ev, self.root)
            db.commit()
            return still_pending

    def _status(self):
        with self.Session() as db:
            return db.get(Evaluation, self.eval_id).status

    def _queue(self):
        with self.Session() as db:
            return get_review_queue(db, data_dir=self.root)

    def test_first_view_does_not_mark_completed(self):
        self.assertTrue(self._decide(0, T0 + timedelta(minutes=1)))
        self.assertEqual(self._status(), 'pending_review')
        queue = self._queue()
        self.assertEqual(queue['total'], 1)
        self.assertEqual(queue['items'][0]['imageIds'], [f'I-{self.images[1][0]:06d}'])

    def test_second_view_completes_and_clears_queue(self):
        self._decide(0, T0 + timedelta(minutes=1))
        self.assertFalse(self._decide(1, T0 + timedelta(minutes=2)))
        self.assertEqual(self._status(), 'completed')
        self.assertEqual(self._queue()['total'], 0)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(ReviewDecisionEvidence)).all()), 2)
            self.assertEqual(len(db.scalars(select(Review)).all()), 2)
            self.assertIsNone(db.get(Evaluation, self.eval_id).visual_category)

    def test_new_snapshot_after_review_reopens_queue(self):
        self._decide(0, T0 + timedelta(minutes=1))
        self._decide(1, T0 + timedelta(minutes=2))
        with self.Session() as db:
            old = db.scalars(select(QualityPrediction)).first()
            db.add(QualityPrediction(evaluation_id=self.eval_id, product='mango',
                status='experimental_e0e1e2_v2', reason='experimental_only',
                source_fingerprint='3'*64, model_sha256='2'*64, model_version='test-v2',
                proposed_grade=None, created_at=T0 + timedelta(minutes=3),
                details_json=old.details_json))
            db.commit()
        self.assertEqual(self._queue()['total'], 1)
        self.assertTrue(self._decide(0, T0 + timedelta(minutes=4)))
        self.assertEqual(self._status(), 'pending_review')
        self.assertFalse(self._decide(1, T0 + timedelta(minutes=5)))
        self.assertEqual(self._status(), 'completed')

    def test_tampered_second_photo_blocks_completion(self):
        self._decide(0, T0 + timedelta(minutes=1))
        (self.root / self.images[1][2]).write_bytes(b'tampered bytes changed')
        self.assertTrue(self._decide(1, T0 + timedelta(minutes=2)))
        self.assertEqual(self._status(), 'pending_review')

    def test_missing_second_photo_blocks_completion(self):
        (self.root / self.images[1][2]).unlink()
        self.assertTrue(self._decide(0, T0 + timedelta(minutes=1)))
        self.assertEqual(self._status(), 'pending_review')

    def test_missing_count_blocks_completion(self):
        with self.Session() as db:
            ev = db.get(Evaluation, self.eval_id)
            ev.image_count = 3
            db.commit()
        self._decide(0, T0 + timedelta(minutes=1))
        self.assertTrue(self._decide(1, T0 + timedelta(minutes=2)))
        self.assertEqual(self._status(), 'pending_review')

    def test_two_views_without_model_still_require_both_decisions(self):
        with self.Session() as db:
            for item in db.scalars(select(QualityPrediction)).all():
                db.delete(item)
            db.commit()
        self.assertTrue(self._decide(0, T0 + timedelta(minutes=1)))
        self.assertEqual(self._status(), 'pending_review')
        self.assertFalse(self._decide(1, T0 + timedelta(minutes=2)))
        self.assertEqual(self._status(), 'completed')

    def test_two_ag037_flags_cannot_be_resolved_globally(self):
        with self.Session() as db:
            db.add_all([VisionAssessment(evaluation_id=self.eval_id,
                image_id=pk, image_sha256=sha, model_version='yoloe-test',
                rules_version='test-v1', inference_size=512,
                inference_confidence=.25, acceptance_threshold=.4,
                outcome='pending_review', reason='confianza_insuficiente',
                confidence=.2, candidate_count=1, detections_json='[]', created_at=T0)
                for pk, sha, _ in self.images])
            db.commit()
        with self.Session() as db:
            ids = pending_ag037_images(db, db.get(Evaluation, self.eval_id), self.root)
            self.assertEqual(ids, {f'I-{x[0]:06d}' for x in self.images})

    def test_reconcile_does_not_commit_on_its_own(self):
        with self.Session() as db:
            ev = db.get(Evaluation, self.eval_id)
            self.assertTrue(reconcile_review_status(db, ev, self.root))
            db.rollback()
        self.assertEqual(self._status(), 'pending_review')

if __name__ == '__main__':
    unittest.main()
