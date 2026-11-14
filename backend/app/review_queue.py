"""AG-056 I02: read-only, bounded SQL adapter for the persisted review queue.

The queue is derived from AG-037/AG-038/AG-055 source-of-truth records.
No duplicated workflow status, model inference or database write is performed.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from .database import DATA_DIR
from .decision_models import ReviewDecisionEvidence
from .models import Evaluation, Image, Lot, Review
from .quality_prediction_models import QualityPrediction
from .review_selection import (
    QUALITY_STATUSES, RULE_VERSION, DetectionEvidence, EvaluationFacts,
    HumanDecision, ImageEvidence, parse_ag037_uncertainty, parse_ag055_quality,
    select_for_human_review,
)
from .vision_assessment_models import VisionAssessment

MAX_IMAGE_BYTES = 5 * 1024 * 1024
SQL_BATCH_SIZE = 100


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _image_sha(image: Image, root: Path) -> str | None:
    """Verify on-disk evidence, including on Windows and junction-aware paths.

    ``Path.resolve() == Path.absolute()`` is not a portable way to reject
    symlinks: those methods may produce differently canonicalized Windows paths
    for an ordinary file. Instead reject reparse links component-by-component,
    require containment, and verify the open handle against pre/post metadata.
    """
    rel = image.relative_path
    if not isinstance(rel, str) or not rel or "\\" in rel or ":" in rel:
        return None
    part = PurePosixPath(rel)
    if part.is_absolute() or ".." in part.parts or not part.parts:
        return None
    if not 0 < image.size_bytes <= MAX_IMAGE_BYTES:
        return None
    try:
        root = root.resolve(strict=True)
        target = root
        for segment in part.parts:
            target = target / segment
            # Do not follow a source-controlled symlink or Windows junction.
            if target.is_symlink() or (hasattr(target, "is_junction") and target.is_junction()):
                return None
        if not target.resolve(strict=True).is_relative_to(root):
            return None

        # A metadata change while reading is not proof of tampering, but it
        # prevents trusting this read. Allow one fresh, fully validated retry.
        for _ in range(2):
            before = target.stat()
            if not stat.S_ISREG(before.st_mode) or before.st_size != image.size_bytes:
                return None
            digest = hashlib.sha256()
            with target.open("rb") as reader:
                opened = os.fstat(reader.fileno())
                if (opened.st_dev, opened.st_ino, opened.st_size) != (
                    before.st_dev, before.st_ino, before.st_size
                ):
                    continue
                while chunk := reader.read(65536):
                    digest.update(chunk)
                ending = os.fstat(reader.fileno())
            after = target.stat()
            # ctime may differ across Windows stat interfaces; the verified
            # content digest and dev/inode/size/mtime checks are authoritative.
            identity = lambda info: (
                info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
            )
            if identity(before) == identity(opened) == identity(ending) == identity(after):
                if any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction())
                       for p in (root.joinpath(*part.parts[:i]) for i in range(1, len(part.parts)+1))):
                    return None
                return digest.hexdigest()
        return None
    except (OSError, ValueError, RuntimeError):
        return None


def _candidate_stmt(lot: str | None, product: str | None):
    """SQL prefilter: keep explicit signals, not entire historical evaluation list."""
    flag = exists(select(Review.id).where(and_(
        Review.evaluation_id == Evaluation.id, Review.type == 'uncertainty')))
    detector = exists(select(VisionAssessment.id).where(and_(
        VisionAssessment.evaluation_id == Evaluation.id,
        VisionAssessment.outcome != 'ready_to_capture')))
    proposal = exists(select(QualityPrediction.id).where(and_(
        QualityPrediction.evaluation_id == Evaluation.id,
        QualityPrediction.status.in_(QUALITY_STATUSES))))
    stmt = select(Evaluation, Lot.code).join(Lot, Evaluation.lot_id == Lot.id).where(or_(
        Evaluation.status == 'pending_review',
        and_(Evaluation.status.in_(('processing', 'completed')), or_(flag, detector, proposal)),
    ))
    if lot is not None:
        stmt = stmt.where(func.lower(Lot.code) == lot.strip().lower())
    if product is not None:
        stmt = stmt.where(Evaluation.product == product)
    return stmt


def _group(db: Session, klass: type, evaluation_ids: list[int]) -> dict[int, list[Any]]:
    grouped: dict[int, list[Any]] = defaultdict(list)
    if evaluation_ids:
        rows = db.scalars(select(klass).where(klass.evaluation_id.in_(evaluation_ids))
                          .order_by(klass.id.asc())).all()
        for row in rows:
            grouped[row.evaluation_id].append(row)
    return grouped


def _decisions(db: Session, evaluation_ids: list[int]) -> dict[int, list[tuple[ReviewDecisionEvidence, Review]]]:
    grouped: dict[int, list[tuple[ReviewDecisionEvidence, Review]]] = defaultdict(list)
    if evaluation_ids:
        rows = db.execute(select(ReviewDecisionEvidence, Review).join(
            Review, ReviewDecisionEvidence.review_id == Review.id
        ).where(ReviewDecisionEvidence.evaluation_id.in_(evaluation_ids))
            .order_by(ReviewDecisionEvidence.review_id.asc())).all()
        for evidence, review in rows:
            if (review.type == 'review' and review.evaluation_id == evidence.evaluation_id):
                grouped[evidence.evaluation_id].append((evidence, review))
    return grouped


def _projection(db: Session, batch: list[tuple[Evaluation, str]], root: Path):
    ids = [ev.id for ev, _ in batch]
    photos = _group(db, Image, ids)
    reviews = _group(db, Review, ids)
    detectors = _group(db, VisionAssessment, ids)
    proposals = _group(db, QualityPrediction, ids)
    decisions = _decisions(db, ids)
    for evaluation, lot_code in batch:
        imgs = photos[evaluation.id]
        hashes = {img.id: _image_sha(img, root) for img in imgs}
        image_keys = set(hashes)
        human = tuple(HumanDecision(
            row.review_id, f'I-{row.image_id:06d}', row.image_sha256.lower(), review.performed_at
        ) for row, review in decisions[evaluation.id]
            if row.image_id in image_keys and len(row.image_sha256) == 64)
        quality = []
        for row in proposals[evaluation.id]:
            try:
                details = json.loads(row.details_json)
                if not isinstance(details, dict):
                    details = {}
            except (ValueError, TypeError):
                details = {}  # Broken snapshot must not disappear silently.
            quality.append(parse_ag055_quality(row.id, row.status, row.reason, row.created_at, details))
        facts = EvaluationFacts(
            evaluation_id=f'E-{evaluation.id:06d}', status=evaluation.status,
            images=tuple(ImageEvidence(f'I-{img.id:06d}', hashes[img.id]) for img in imgs),
            detections=tuple(DetectionEvidence(
                item.id, f'I-{item.image_id:06d}', item.image_sha256,
                item.outcome, item.reason, item.created_at
            ) for item in detectors[evaluation.id]),
            quality_predictions=tuple(quality),
            uncertainty_flags=tuple(parse_ag037_uncertainty(r.id, r.reason, r.performed_at)
                                    for r in reviews[evaluation.id] if r.type == 'uncertainty'),
            human_decisions=human,
            legacy_ag037_resolutions=tuple(r.performed_at for r in reviews[evaluation.id]
                if r.type == 'review' and r.reason.startswith('AG037|revision_humana|')),
        )
        decision = select_for_human_review(facts)
        if not decision.requires_review:
            continue
        yield {
            'evaluationId': facts.evaluation_id,
            'lotId': lot_code,
            'pieceId': evaluation.piece_id,
            'product': evaluation.product,
            'status': evaluation.status,
            'registeredAt': _utc(evaluation.created_at).isoformat(),
            'imageCount': len(imgs),
            'imageIds': list(decision.image_ids),
            'priority': decision.priority,
            'reasons': [dict(code=r.code, priority=r.priority,
                             imageId=r.image_id, source=r.source) for r in decision.reasons],
            'ruleVersion': decision.rule_version,
        }


def get_review_queue(db: Session, *, lot: str | None = None,
                     product: str | None = None, priority: str | None = None,
                     limit: int = 20, offset: int = 0, data_dir: Path | None = None) -> dict:
    """Accurate filtered counts and stable pagination. Never writes to the DB.

    SQL prefilters old records; image hashing and I01 rules are performed in
    bounded batches. Full selection is necessary for truthful count+priority
    pagination: do not paginate before routing eligible evidence.
    """
    root = data_dir if data_dir is not None else DATA_DIR
    stmt = _candidate_stmt(lot, product)
    cursor = 0
    items = []
    high = normal = 0
    while True:
        batch = db.execute(stmt.where(Evaluation.id > cursor)
                           .order_by(Evaluation.id.asc()).limit(SQL_BATCH_SIZE)).all()
        if not batch:
            break
        cursor = batch[-1][0].id
        for item in _projection(db, batch, root):
            if item['priority'] == 'high':
                high += 1
            else:
                normal += 1
            if priority is None or priority == item['priority']:
                items.append(item)
    items.sort(key=lambda x: (0 if x['priority'] == 'high' else 1,
                              x['registeredAt'], x['evaluationId']))
    total = len(items)
    return {
        'items': items[offset:offset + limit], 'total': total,
        'limit': limit, 'offset': offset, 'hasMore': offset + limit < total,
        'counts': {'high': high, 'normal': normal, 'all': high + normal},
        'ruleVersion': RULE_VERSION,
    }
