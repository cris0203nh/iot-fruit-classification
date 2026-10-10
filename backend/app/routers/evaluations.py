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
from ..models import Evaluation, Lot

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
        "evidence": [],  # se llenará cuando se guarden las imágenes
        "visualCategory": ev.visual_category,
        "reviewNote": ev.review_note,
    }


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
    pk = parse_id(evaluation_id)
    ev = db.get(Evaluation, pk) if pk is not None else None
    if ev is None:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada.")
    return detail(ev)