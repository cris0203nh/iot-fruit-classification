"""AG-056 I04: reconcile status after a human event with the *same* queue engine.

Only a caller that has acquired the existing AG-038 SQLite write lock and
flushed its human event should call this function. It does not commit a session
or synthesize a human grade. If evidence is absent/inconsistent, fail closed.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Evaluation, Image, Review
from .decision_models import ReviewDecisionEvidence
from .quality_prediction_models import QualityPrediction
from .review_selection import QUALITY_STATUSES
from .review_queue import _image_sha, _projection


def _unresolved_reasons(db: Session, evaluation: Evaluation, data_dir: Path) -> tuple[dict, ...]:
    """Route the new state as *completed* to suppress the generic pending fallback.

    The completion decision must not be circular: pending_review by itself is
    not a new outstanding incident after a valid human decision. AG-037 and
    AG-055 evidence, however, must still be checked per image/source/time.
    """
    previous = evaluation.status
    with db.no_autoflush:
        try:
            evaluation.status = 'completed'
            result = next(_projection(db, [(evaluation, '')], data_dir), None)
            return tuple(result['reasons']) if result else ()
        finally:
            evaluation.status = previous


def unresolved_evidence(db: Session, evaluation: Evaluation, data_dir: Path) -> tuple[dict, ...]:
    """Return still-open incidents. Never trust missing or changed source bytes."""
    photos = db.scalars(select(Image).where(Image.evaluation_id == evaluation.id)
                        .order_by(Image.id.asc())).all()
    if not photos:
        return ({'code': 'acquisition_evidence_missing', 'imageId': None},)
    if evaluation.image_count is not None and evaluation.image_count > len(photos):
        return ({'code': 'acquisition_image_count_mismatch', 'imageId': None},)
    hashes = {}
    for photo in photos:
        hashes[photo.id] = _image_sha(photo, data_dir)
        if hashes[photo.id] is None:
            return ({'code': 'evidence_unavailable', 'imageId': f'I-{photo.id:06d}'},)

    # Acquisition completion commonly sets pending_review without any AG-055
    # proposal. AG-038 cannot complete such a TWO-VIEW evaluation on the first
    # photo alone. Older one-photo AG-037 legacy resolutions remain compatible.
    if evaluation.status == 'pending_review' and len(photos) > 1:
        decision_rows = db.execute(select(ReviewDecisionEvidence, Review).join(
            Review, ReviewDecisionEvidence.review_id == Review.id
        ).where(ReviewDecisionEvidence.evaluation_id == evaluation.id)).all()
        covered = {meta.image_id for meta, review in decision_rows
                   if review.type == 'review' and review.evaluation_id == evaluation.id
                   and hashes.get(meta.image_id) == meta.image_sha256}
        missing = [photo for photo in photos if photo.id not in covered]
        if missing:
            return tuple({'code': 'acquisition_image_unreviewed',
                          'imageId': f'I-{photo.id:06d}'} for photo in missing)
    return _unresolved_reasons(db, evaluation, data_dir)


def reconcile_review_status(db: Session, evaluation: Evaluation, data_dir: Path) -> bool:
    """Set pending_review only while work remains; return whether work remains.

    Caller must flush new Review + ReviewDecisionEvidence first and must own
    transaction/commit. No model inference or new persisted columns are used.
    """
    pending = bool(unresolved_evidence(db, evaluation, data_dir))
    evaluation.status = 'pending_review' if pending else 'completed'
    return pending


def pending_ag037_images(db: Session, evaluation: Evaluation, data_dir: Path) -> frozenset[str]:
    """Identify unresolved AG-037 photo IDs before a legacy global resolution.

    The old /vision/resolve API cannot identify individual photos. If two or
    more photos have outstanding flags, it must not silently clear all of them.
    """
    ag037_codes = frozenset({'manual_or_uncertain_detection', 'uncertain_detection',
                             'unknown_detection_outcome'})
    reasons = _unresolved_reasons(db, evaluation, data_dir)
    return frozenset(reason['imageId'] for reason in reasons
                     if reason.get('code') in ag037_codes and reason.get('imageId'))


def assert_quality_source_unchanged(db: Session, evaluation: Evaluation,
                                    image_id: int, actual_sha: str) -> None:
    """AG-038 must not attest a photo that differs from an AG-055 snapshot.

    Source integrity is a precondition of a human decision. Stale or malformed
    quality provenance cannot be treated as human verification.
    """
    evidence_id = f'I-{image_id:06d}'
    statement = select(QualityPrediction).where(
        QualityPrediction.evaluation_id == evaluation.id,
        QualityPrediction.status.in_(QUALITY_STATUSES),
    )
    for prediction in db.scalars(statement):
        try:
            details = json.loads(prediction.details_json)
        except (TypeError, ValueError) as exc:
            raise HTTPException(409, 'Snapshot AG-055 con procedencia ilegible') from exc
        if not isinstance(details, dict) or not isinstance(details.get('sources'), list):
            raise HTTPException(409, 'Snapshot AG-055 sin procedencia verificable')
        for source in details['sources']:
            if not isinstance(source, dict) or not isinstance(source.get('imageId'), str):
                raise HTTPException(409, 'Snapshot AG-055 con referencias inválidas')
            if source['imageId'] != evidence_id:
                continue
            sha = source.get('sha256')
            if not isinstance(sha, str) or sha.lower() != actual_sha:
                raise HTTPException(409, 'La fotografía difiere de la fuente AG-055 original')
