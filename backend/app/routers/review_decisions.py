"""AG-038/AGROP-46 — explicit, append-only human decisions with evidence.

YOLOE detects a fruit but never determines visual grade E0/E1/E2. A first
human grade must be labeled 'initial_label', not a fictitious correction.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, IntegrityError
from sqlalchemy.orm import Session

from ..database import DATA_DIR, get_db
from ..decision_models import ReviewDecisionEvidence
from ..dependencies import require_authenticated, require_reviewer
from ..models import Evaluation, Image, Review, User
from ..review_completion import assert_quality_source_unchanged, reconcile_review_status
from ..vision_assessment_models import VisionAssessment

router = APIRouter(prefix='/api/evaluations', tags=['auditoria-revisiones'])
EVAL_RE = re.compile(r'E-(\d{1,9})\Z')
IMAGE_RE = re.compile(r'I-(\d{1,9})\Z')
REVIEW_RE = re.compile(r'R-(\d{1,9})\Z')
GRADE_VISUAL = frozenset({'E0', 'E1', 'E2'})
GRADE_COMERCIAL = frozenset({'primera', 'segunda'})
CHOICES = GRADE_VISUAL | GRADE_COMERCIAL | {'no_evaluable'}
MAX_BYTES = 5 * 1024 * 1024


class DecisionCreate(BaseModel):
    action: Literal['confirm', 'correct', 'initial_label', 'no_evaluable']
    imageId: str
    newValue: str | None = None
    reason: str
    expectedReviewId: str | None
    requestId: str

    @field_validator('imageId')
    @classmethod
    def image_id(cls, value: str) -> str:
        if IMAGE_RE.fullmatch(value) is None:
            raise ValueError('Imagen con identificador incorrecto')
        return value

    @field_validator('newValue')
    @classmethod
    def grade(cls, value: str | None) -> str | None:
        if value is not None and value not in CHOICES:
            raise ValueError('Resultado no admitido')
        return value

    @field_validator('reason')
    @classmethod
    def justification(cls, value: str) -> str:
        value = value.strip()
        if not 10 <= len(value) <= 500:
            raise ValueError('Motivo obligatorio de 10 a 500 caracteres')
        return value

    @field_validator('expectedReviewId')
    @classmethod
    def expected_revision(cls, value: str | None) -> str | None:
        if value is not None and REVIEW_RE.fullmatch(value) is None:
            raise ValueError('Revisión esperada incorrecta')
        return value

    @field_validator('requestId')
    @classmethod
    def request_key(cls, value: str) -> str:
        try:
            parsed = UUID(value)
            if str(parsed) != value or parsed.version != 4:
                raise ValueError()
        except (ValueError, AttributeError):
            raise ValueError('requestId debe ser UUID v4 canónico') from None
        return value


def _evaluation(db: Session, public_id: str) -> Evaluation:
    match = EVAL_RE.fullmatch(public_id)
    evaluation = db.get(Evaluation, int(match.group(1))) if match else None
    if evaluation is None:
        raise HTTPException(404, 'Evaluación inexistente')
    return evaluation


def _current_value(ev: Evaluation, reviews: list[Review]) -> str | None:
    for item in reversed(reviews):
        if item.type == 'review':
            return item.updated_value
    return ev.visual_category


def _validate_change(action: str, previous: str | None, new: str | None) -> str:
    if action == 'no_evaluable':
        if new not in (None, 'no_evaluable'):
            raise HTTPException(422, 'No evaluable no puede recibir otra categoría')
        return 'no_evaluable'
    if action == 'confirm':
        if previous is None or previous != new:
            raise HTTPException(422, 'Confirmar no puede modificar el resultado')
        return new
    if new is None or new == 'no_evaluable':
        raise HTTPException(422, 'Seleccione un grado o use la acción no_evaluable')
    if action == 'initial_label':
        if previous is not None or new not in GRADE_VISUAL:
            raise HTTPException(409 if previous is not None else 422,
                                'El etiquetado inicial requiere ausencia de grado y rúbrica E0/E1/E2')
        return new
    if previous is None or previous not in CHOICES:
        raise HTTPException(409, 'No existe un resultado anterior comparable; registre etiqueta inicial')
    if action == 'correct':
        if previous == new:
            raise HTTPException(422, 'Corregir requiere un valor distinto')
        if previous in GRADE_VISUAL and new not in GRADE_VISUAL:
            raise HTTPException(422, 'No convertir grados E0/E1/E2 a categoría comercial')
        if previous in GRADE_COMERCIAL and new not in GRADE_COMERCIAL:
            raise HTTPException(422, 'No convertir categorías comerciales en grados E0/E1/E2')
        if previous == 'no_evaluable' and new not in GRADE_VISUAL:
            raise HTTPException(422, 'Un resultado no evaluable solo puede reclasificarse con evidencia E0/E1/E2')
        return new
    raise HTTPException(422, 'Acción desconocida')


def _source_sha(image: Image) -> str:
    root = DATA_DIR.resolve(strict=True)
    rel = image.relative_path
    if not rel or '\\' in rel or ':' in rel:
        raise HTTPException(409, 'Referencia de evidencia inválida')
    relative = PurePosixPath(rel)
    if relative.is_absolute() or '..' in relative.parts:
        raise HTTPException(409, 'Ruta de evidencia insegura')
    source = root.joinpath(*relative.parts)
    if not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(root):
        raise HTTPException(409, 'Evidencia original no disponible')
    if not 0 < image.size_bytes <= MAX_BYTES or source.stat().st_size != image.size_bytes:
        raise HTTPException(409, 'Evidencia original inconsistente')
    digest = hashlib.sha256()
    with source.open('rb') as handle:
        while block := handle.read(65536):
            digest.update(block)
    return digest.hexdigest()


def _serialize(item: Review, meta: ReviewDecisionEvidence) -> dict:
    return {
        'id': f'R-{item.id:06d}', 'evaluationId': f'E-{item.evaluation_id:06d}',
        'action': meta.action, 'previousValue': item.previous_value,
        'newValue': item.updated_value, 'actorId': item.actor_id,
        'performedAt': item.performed_at.isoformat(), 'reason': item.reason,
        'imageId': f'I-{meta.image_id:06d}', 'imageSha256': meta.image_sha256,
        'requestId': meta.request_id,
    }


def _request_digest(payload: DecisionCreate) -> str:
    raw = json.dumps(payload.model_dump(), ensure_ascii=False, sort_keys=True,
                     separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _read_reviews(db: Session, pk: int) -> list[Review]:
    return list(db.scalars(select(Review).where(Review.evaluation_id == pk)
                           .order_by(Review.id.asc())).all())


@router.get('/{evaluation_id}/review-decisions')
def list_review_decisions(evaluation_id: str, db: Session = Depends(get_db),
                          user: User = Depends(require_authenticated)):
    ev = _evaluation(db, evaluation_id)
    reviews = _read_reviews(db, ev.id)
    rows = db.execute(select(Review, ReviewDecisionEvidence)
        .join(ReviewDecisionEvidence, Review.id == ReviewDecisionEvidence.review_id)
        .where(ReviewDecisionEvidence.evaluation_id == ev.id)
        .order_by(Review.id.asc())).all()
    return {
        'evaluationId': evaluation_id,
        'originalValue': ev.visual_category,
        'currentValue': _current_value(ev, reviews),
        'revisionId': f'R-{reviews[-1].id:06d}' if reviews else None,
        'decisions': [_serialize(item, meta) for item, meta in rows],
    }


@router.post('/{evaluation_id}/review-decisions', status_code=201)
def record_review_decision(evaluation_id: str, payload: DecisionCreate,
        db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    # The lock must precede the revision read, serializing competing decisions
    # in SQLite. Authentication may already have performed SELECT queries.
    try:
        if db.get_bind().dialect.name == 'sqlite':
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
    except OperationalError as exc:
        db.rollback()
        raise HTTPException(409, 'Revisión ocupada; actualice la bitácora') from exc

    try:
        ev = _evaluation(db, evaluation_id)
        if ev.status not in ('pending_review', 'completed'):
            raise HTTPException(409, 'Solo se revisan evaluaciones completas o pendientes')
        digest = _request_digest(payload)
        replay = db.scalar(select(ReviewDecisionEvidence).where(
            ReviewDecisionEvidence.evaluation_id == ev.id,
            ReviewDecisionEvidence.request_id == payload.requestId))
        if replay is not None:
            if replay.payload_sha256 != digest:
                raise HTTPException(409, 'requestId reutilizado para una decisión distinta')
            old = db.get(Review, replay.review_id)
            result = _serialize(old, replay)
            db.rollback()
            return result

        reviews = _read_reviews(db, ev.id)
        revision = f'R-{reviews[-1].id:06d}' if reviews else None
        if payload.expectedReviewId != revision:
            raise HTTPException(409, 'Revisión desactualizada: consulte de nuevo el historial')
        image = db.get(Image, int(IMAGE_RE.fullmatch(payload.imageId).group(1)))
        if image is None or image.evaluation_id != ev.id:
            raise HTTPException(404, 'Imagen no asociada a esta evaluación')
        sha = _source_sha(image)
        # An earlier detector snapshot is an immutable reference for this photo.
        prior_hashes = db.scalars(select(VisionAssessment.image_sha256).where(
            VisionAssessment.image_id == image.id)).all()
        if any(saved != sha for saved in prior_hashes):
            raise HTTPException(409, 'El SHA256 de la imagen difiere del snapshot original')
        assert_quality_source_unchanged(db, ev, image.id, sha)
        previous = _current_value(ev, reviews)
        next_value = _validate_change(payload.action, previous, payload.newValue)
        item = Review(evaluation_id=ev.id, type='review', actor_id=user.username,
                      previous_value=previous, updated_value=next_value,
                      reason=payload.reason)
        db.add(item)
        db.flush()
        meta = ReviewDecisionEvidence(review_id=item.id, evaluation_id=ev.id,
            image_id=image.id, image_sha256=sha, action=payload.action,
            request_id=payload.requestId, payload_sha256=digest)
        db.add(meta)
        db.flush()  # AG-038: source-bound decision must exist before AG-056 routing.
        reconcile_review_status(db, ev, DATA_DIR)
        ev.review_note = payload.reason
        db.commit()
        db.refresh(item)
        return _serialize(item, meta)
    except HTTPException:
        db.rollback()
        raise
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise HTTPException(409, 'Conflicto de revisión; consulte el historial') from exc
