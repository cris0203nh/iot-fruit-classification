import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..evaluation_schemas import (
    EvaluationCreate,
    EvaluationDetailOut,
    EvaluationSummaryOut,
)
from ..models import Evaluation, Lot, Review
from ..review_schemas import (
    CancelCreate,
    ReviewCreate,
    ReviewEventOut,
    TraceabilityOut,
)

router = APIRouter(prefix="/api/evaluations", tags=["evaluaciones"])


def public_id(evaluation_id: int) -> str:
    return f"E-{evaluation_id:06d}"


def parse_id(value: str) -> int | None:
    match = re.fullmatch(r"E-(\d{1,9})", value)
    return int(match.group(1)) if match else None


def iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def summary(ev: Evaluation) -> dict:
    return {
        "id": public_id(ev.id),
        "lotId": ev.lot.code,
        "pieceId": ev.piece_id,
        "product": ev.product,
        "registeredAt": iso(ev.created_at),
        "status": ev.status,
        "weightGrams": ev.weight_grams,
        "imageCount": ev.image_count,
    }


def detail(ev: Evaluation) -> dict:
    return {
        **summary(ev),
        "evidence": [],
        "visualCategory": ev.visual_category,
        "reviewNote": ev.review_note,
    }


def review_out(r: Review) -> dict:
    return {
        "id": f"R-{r.id:06d}",
        "performedAt": iso(r.performed_at),
        "actorId": r.actor_id,
        "type": r.type,
        "reason": r.reason,
        "previousValue": r.previous_value,
        "updatedValue": r.updated_value,
    }


def get_or_404(db: Session, evaluation_id: str) -> Evaluation:
    pk = parse_id(evaluation_id)
    ev = db.get(Evaluation, pk) if pk is not None else None
    if ev is None:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada.")
    return ev


def effective_value(ev: Evaluation) -> str | None:
    """Valor vigente: el de la última revisión, o el original si no hay."""
    for r in reversed(ev.reviews):
        if r.type == "review":
            return r.updated_value
    return ev.visual_category


@router.get("", response_model=list[EvaluationSummaryOut])
def list_evaluations(
    lot: str | None = None,
    product: Literal["mango", "tomate"] | None = None,
    status: Literal["processing", "completed", "pending_review", "error", "cancelled"] | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Evaluation).join(Lot).order_by(Evaluation.id.desc())
    if lot:
        stmt = stmt.where(func.lower(Lot.code) == lot.strip().lower())
    if product:
        stmt = stmt.where(Evaluation.product == product)
    if status:
        stmt = stmt.where(Evaluation.status == status)
    return [summary(ev) for ev in db.scalars(stmt).all()]


@router.post("", response_model=EvaluationDetailOut, status_code=201)
def create_evaluation(payload: EvaluationCreate, db: Session = Depends(get_db)):
    lot = db.scalar(select(Lot).where(func.lower(Lot.code) == payload.lotId.lower()))
    if lot is None:
        raise HTTPException(status_code=404, detail="El lote indicado no existe.")
    if lot.status != "open":
        raise HTTPException(status_code=409, detail="El lote está cerrado.")

    ev = Evaluation(lot_id=lot.id, piece_id=payload.pieceId, product=lot.product)
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return detail(ev)


@router.get("/{evaluation_id}", response_model=EvaluationDetailOut)
def get_evaluation(evaluation_id: str, db: Session = Depends(get_db)):
    return detail(get_or_404(db, evaluation_id))


@router.get("/{evaluation_id}/traceability", response_model=TraceabilityOut)
def get_traceability(evaluation_id: str, db: Session = Depends(get_db)):
    ev = get_or_404(db, evaluation_id)
    return {
        "evaluation": detail(ev),
        "calibrationReference": ev.calibration_reference,
        "modelVersion": ev.model_version,
        "rulesVersion": ev.rules_version,
        "reviews": [review_out(r) for r in ev.reviews],
    }


@router.post("/{evaluation_id}/reviews", response_model=ReviewEventOut, status_code=201)
def add_review(evaluation_id: str, payload: ReviewCreate, db: Session = Depends(get_db)):
    ev = get_or_404(db, evaluation_id)
    if ev.status not in ("pending_review", "completed"):
        raise HTTPException(
            status_code=409,
            detail="Solo se puede revisar una evaluación completada o por revisar.",
        )

    review = Review(
        evaluation_id=ev.id,
        type="review",
        actor_id=payload.actorId,
        reason=payload.reason,
        previous_value=effective_value(ev),
        updated_value=payload.newValue,
    )
    db.add(review)
    ev.status = "completed"
    ev.review_note = payload.reason
    db.commit()
    db.refresh(review)
    return review_out(review)


@router.post("/{evaluation_id}/cancel", response_model=ReviewEventOut, status_code=201)
def cancel_evaluation(evaluation_id: str, payload: CancelCreate, db: Session = Depends(get_db)):
    ev = get_or_404(db, evaluation_id)
    if ev.status == "cancelled":
        raise HTTPException(status_code=409, detail="La evaluación ya está anulada.")

    event = Review(
        evaluation_id=ev.id,
        type="cancellation",
        actor_id=payload.actorId,
        reason=payload.reason,
        previous_value=ev.status,
        updated_value="cancelled",
    )
    db.add(event)
    ev.status = "cancelled"
    db.commit()
    db.refresh(event)
    return review_out(event)