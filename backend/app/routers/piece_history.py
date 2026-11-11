"""AG-040 / AGROP-48: expediente de lectura por pieza y lote.

Una pieza = un (lote, codigo de pieza), no una evaluación ni una fotografía.
No se modifican evaluaciones, snapshots, decisiones o archivos originales.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_authenticated
from ..models import Evaluation, Image, Lot, Piece, Review, User
from ..vision_assessment_models import VisionAssessment
from ..decision_models import ReviewDecisionEvidence

router = APIRouter(prefix="/api/piece-history", tags=["historial-por-pieza"])


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _lot(db: Session, code: str) -> Lot:
    code = code.strip()
    if not code or len(code) > 32:
        raise HTTPException(status_code=422, detail="Codigo de lote invalido")
    matches = db.scalars(select(Lot).where(func.lower(Lot.code) == code.lower())).all()
    if not matches:
        raise HTTPException(status_code=404, detail="Lote inexistente")
    if len(matches) > 1:
        raise HTTPException(status_code=409, detail="Codigo de lote ambiguo")
    return matches[0]


def _counts(db: Session, model: type, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    return dict(db.execute(
        select(model.evaluation_id, func.count(model.id))
        .where(model.evaluation_id.in_(ids))
        .group_by(model.evaluation_id)
    ).all())


def _group_lot(db: Session, lot: Lot) -> list[dict]:
    registered = db.scalars(select(Piece).where(Piece.lot_id == lot.id)).all()
    by_code = {piece.code: piece for piece in registered}
    by_id = {piece.id: piece for piece in registered}
    evaluations = db.scalars(
        select(Evaluation).where(Evaluation.lot_id == lot.id)
        .order_by(Evaluation.id.asc())
    ).all()
    ids = [ev.id for ev in evaluations]
    captures = _counts(db, Image, ids)
    reviews = _counts(db, Review, ids)
    assessments = _counts(db, VisionAssessment, ids)
    grouped: dict[str, list[Evaluation]] = defaultdict(list)

    for ev in evaluations:
        # No inferir identidad cuando la FK contradice el codigo persistido.
        if ev.piece_ref_id is not None:
            related = by_id.get(ev.piece_ref_id)
            if related is None or related.code != ev.piece_id:
                raise HTTPException(
                    status_code=409,
                    detail="Inconsistencia de identidad de pieza: verificar referencia normalizada",
                )
        grouped[ev.piece_id].append(ev)

    # Se incluyen piezas registradas sin intentos, con conteos cero.
    result = []
    for code in sorted(set(by_code) | set(grouped)):
        attempts = grouped.get(code, [])
        item = by_code.get(code)
        last = attempts[-1] if attempts else None
        result.append({
            "lotCode": lot.code,
            "pieceCode": code,
            "pieceId": item.id if item is not None else None,
            "identitySource": "registered" if item is not None else "legacy_inferred",
            "attemptCount": len(attempts),
            "captureCount": sum(captures.get(ev.id, 0) for ev in attempts),
            "automaticAssessmentCount": sum(assessments.get(ev.id, 0) for ev in attempts),
            "reviewEventCount": sum(reviews.get(ev.id, 0) for ev in attempts),
            "latestEvaluationId": f"E-{last.id:06d}" if last else None,
            "latestStatus": last.status if last else None,
        })
    return result


def _read_detail(db: Session, lot: Lot, summary: dict) -> dict:
    code = summary["pieceCode"]
    evals = db.scalars(
        select(Evaluation).where(
            Evaluation.lot_id == lot.id,
            Evaluation.piece_id == code,
        ).order_by(Evaluation.id.asc())
    ).all()
    ids = [ev.id for ev in evals]
    image_by_eval: dict[int, list[Image]] = defaultdict(list)
    review_by_eval: dict[int, list[Review]] = defaultdict(list)
    model_by_eval: dict[int, list[VisionAssessment]] = defaultdict(list)
    metadata_by_review: dict[int, ReviewDecisionEvidence] = {}

    if ids:
        for row in db.scalars(select(Image).where(Image.evaluation_id.in_(ids)).order_by(Image.id)):
            image_by_eval[row.evaluation_id].append(row)
        all_reviews = db.scalars(select(Review).where(Review.evaluation_id.in_(ids)).order_by(Review.id)).all()
        for row in all_reviews:
            review_by_eval[row.evaluation_id].append(row)
        for row in db.scalars(select(VisionAssessment).where(VisionAssessment.evaluation_id.in_(ids)).order_by(VisionAssessment.id)):
            model_by_eval[row.evaluation_id].append(row)
        review_ids = [row.id for row in all_reviews]
        if review_ids:
            for row in db.scalars(select(ReviewDecisionEvidence).where(ReviewDecisionEvidence.review_id.in_(review_ids))):
                metadata_by_review[row.review_id] = row

    attempts = []
    for attempt_index, ev in enumerate(evals, start=1):
        views = image_by_eval[ev.id]
        snapshots = model_by_eval[ev.id]
        reviews = review_by_eval[ev.id]
        known_hashes: dict[int, set[str]] = defaultdict(set)
        for snapshot in snapshots:
            known_hashes[snapshot.image_id].add(snapshot.image_sha256)
        for record in reviews:
            meta = metadata_by_review.get(record.id)
            if meta:
                known_hashes[meta.image_id].add(meta.image_sha256)
        notes = []
        captures = []
        for photo in views:
            hashes = sorted(known_hashes.get(photo.id, set()))
            if len(hashes) > 1:
                notes.append(f"Inconsistencia de SHA256 para I-{photo.id:06d}")
            captures.append({
                "id": f"I-{photo.id:06d}",
                "view": photo.view,
                "createdAt": _iso(photo.created_at),
                "imageUrl": f"/api/images/I-{photo.id:06d}",
                "imageSha256": hashes[0] if len(hashes) == 1 else None,
                "hashConflict": len(hashes) > 1,
            })
        detections = []
        for snapshot in snapshots:
            try:
                original_detections = json.loads(snapshot.detections_json)
            except (TypeError, json.JSONDecodeError):
                original_detections = None
                notes.append(f"Predicciones ilegibles en snapshot {snapshot.id}")
            detections.append({
                "assessmentId": snapshot.id,
                "imageId": f"I-{snapshot.image_id:06d}",
                "imageSha256": snapshot.image_sha256,
                "createdAt": _iso(snapshot.created_at),
                "modelVersion": snapshot.model_version,
                "rulesVersion": snapshot.rules_version,
                "inferenceSize": snapshot.inference_size,
                "threshold": snapshot.acceptance_threshold,
                "confidence": snapshot.confidence,
                "candidateCount": snapshot.candidate_count,
                "outcome": snapshot.outcome,
                "reason": snapshot.reason,
                "detections": original_detections,
            })
        review_events = []
        for event in reviews:
            meta = metadata_by_review.get(event.id)
            review_events.append({
                "id": f"R-{event.id:06d}",
                "createdAt": _iso(event.performed_at),
                "type": event.type,
                "actorId": event.actor_id,
                "reason": event.reason,
                "previousValue": event.previous_value,
                "updatedValue": event.updated_value,
                "action": meta.action if meta else None,
                "imageId": f"I-{meta.image_id:06d}" if meta else None,
                "imageSha256": meta.image_sha256 if meta else None,
                "requestId": meta.request_id if meta else None,
            })
        attempts.append({
            "id": f"E-{ev.id:06d}",
            "attemptNumber": attempt_index,
            "createdAt": _iso(ev.created_at),
            "status": ev.status,
            "product": ev.product,
            "weightGrams": ev.weight_grams,
            "weightPreGrams": ev.weight_pre_g,
            "weightPostGrams": ev.weight_post_g,
            "deviceId": ev.device_id,
            "calibrationReference": ev.calibration_reference,
            "declaredModelVersion": ev.model_version,
            "declaredRulesVersion": ev.rules_version,
            "originalVisualCategory": ev.visual_category,
            "failureReason": ev.failure_reason,
            "captures": captures,
            "automaticAssessments": detections,
            "reviews": review_events,
            "dataQualityNotes": notes,
        })
    return {"lotCode": lot.code, "piece": summary, "attempts": attempts,
            "identityWarning": (
                "Agrupacion historica por codigo de pieza: identidad fisica no acreditada"
                if summary["identitySource"] == "legacy_inferred" else None
            )}


@router.get("")
def list_piece_history(
    lot: str = Query(min_length=1, max_length=32),
    db: Session = Depends(get_db),
    _user: User = Depends(require_authenticated),
):
    current_lot = _lot(db, lot)
    pieces = _group_lot(db, current_lot)
    return {
        "lotCode": current_lot.code,
        "product": current_lot.product,
        "pieceCount": len(pieces),
        "attemptCount": sum(p["attemptCount"] for p in pieces),
        "captureCount": sum(p["captureCount"] for p in pieces),
        "pieces": pieces,
    }


@router.get("/{lot_code}/{piece_code}")
def detail_piece_history(
    lot_code: str, piece_code: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_authenticated),
):
    if not piece_code or len(piece_code) > 64:
        raise HTTPException(422, "Codigo de pieza invalido")
    current_lot = _lot(db, lot_code)
    summaries = _group_lot(db, current_lot)
    match = next((p for p in summaries if p["pieceCode"] == piece_code), None)
    if match is None:
        raise HTTPException(404, "Pieza no registrada en el lote")
    return _read_detail(db, current_lot, match)
