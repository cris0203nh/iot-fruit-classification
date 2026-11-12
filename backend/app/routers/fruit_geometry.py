"""AG-054: analisis geometrico auditable de fotos ORIGINALES persistidas.

GET es solo lectura. POST ejecuta inferencia real YOLOE sobre una evidencia
ya guardada; los resultados son instantaneas versionadas e idempotentes.
No modifica la clasificacion E0/E1/E2, el estado ni la imagen original.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import DATA_DIR, get_db
from ..dependencies import require_authenticated, require_operator
from ..fruit_geometry_models import FruitGeometry
from ..models import Evaluation, Image, User
from ..services.fruit_geometry import InvalidGeometry, measure_polygon
from .auto_registration import MIN_CONFIDENCE, MODEL_VERSION, _infer_products

router = APIRouter(prefix='/api/evaluations', tags=['AG-054 · geometria RGB'])
RULES_VERSION = 'ag054-pixel-geometry-v1'
MAX_ORIGINAL_BYTES = 5 * 1024 * 1024


def _pk(reference: str, prefix: str) -> int | None:
    match = re.fullmatch(rf'{prefix}-(\d{{1,9}})', reference)
    return int(match.group(1)) if match else None


def _evaluation(db: Session, evaluation_id: str) -> Evaluation:
    pk = _pk(evaluation_id, 'E')
    ev = db.get(Evaluation, pk) if pk is not None else None
    if ev is None:
        raise HTTPException(404, 'Evaluación no encontrada.')
    return ev


def _evidence(db: Session, ev: Evaluation, image_id: str) -> Image:
    pk = _pk(image_id, 'I')
    img = db.get(Image, pk) if pk is not None else None
    if img is None or img.evaluation_id != ev.id:
        raise HTTPException(404, 'La fotografía no pertenece a esta evaluación.')
    return img


def _original_image(img: Image) -> bytes:
    base = DATA_DIR.resolve()
    target = (base / img.relative_path).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise HTTPException(409, 'La fotografía original no está disponible.')
    if img.size_bytes < 1 or img.size_bytes > MAX_ORIGINAL_BYTES:
        raise HTTPException(409, 'El tamaño registrado de la evidencia no es válido.')
    content = target.read_bytes()
    if len(content) != img.size_bytes:
        raise HTTPException(409, 'La evidencia no coincide con el tamaño registrado.')
    return content


def _out(row: FruitGeometry) -> dict:
    return {
        'id': row.id,
        'evaluationId': f'E-{row.evaluation_id:06d}',
        'imageId': f'I-{row.image_id:06d}',
        'imageSha256': row.image_sha256,
        'modelVersion': row.model_version,
        'rulesVersion': row.rules_version,
        'status': row.status,
        'reason': row.reason,
        'product': row.product,
        'confidence': row.confidence,
        'candidateCount': row.candidate_count,
        'frameWidth': row.frame_width,
        'frameHeight': row.frame_height,
        'box': json.loads(row.box_json),
        'polygon': json.loads(row.polygon_json),
        'measurements': json.loads(row.measurements_json),
        'unit': 'px',
        'calibrated': False,
        'classificationE0E1E2Produced': False,
        'createdAt': row.created_at.isoformat(),
    }


def _existing(db: Session, img: Image, image_sha256: str) -> FruitGeometry | None:
    return db.scalar(select(FruitGeometry).where(
        FruitGeometry.image_id == img.id,
        FruitGeometry.image_sha256 == image_sha256,
        FruitGeometry.model_version == MODEL_VERSION,
        FruitGeometry.rules_version == RULES_VERSION,
    ))


@router.get('/{evaluation_id}/vision/geometry')
def list_geometry(
    evaluation_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_authenticated),
):
    ev = _evaluation(db, evaluation_id)
    rows = db.scalars(select(FruitGeometry).where(
        FruitGeometry.evaluation_id == ev.id,
    ).order_by(FruitGeometry.id)).all()
    return [_out(row) for row in rows]


@router.post('/{evaluation_id}/vision/geometry/{image_id}', status_code=201)
def analyze_geometry(
    evaluation_id: str,
    image_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_operator),
):
    ev = _evaluation(db, evaluation_id)
    if ev.status in ('cancelled', 'error'):
        raise HTTPException(409, 'Esta evaluación no permite un nuevo análisis.')
    img = _evidence(db, ev, image_id)
    raw = _original_image(img)
    sha = hashlib.sha256(raw).hexdigest()
    previous = _existing(db, img, sha)
    if previous is not None:
        return _out(previous)

    frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None or min(frame.shape[:2]) < 128:
        raise HTTPException(422, 'El original no se pudo decodificar o tiene baja resolución.')
    height, width = frame.shape[:2]
    try:
        # Reutiliza exactamente los pesos/prompts y el bloqueo YOLOE de AG-053.
        candidates = _infer_products(frame)
    except Exception as exc:
        raise HTTPException(503, f'Detector YOLOE no disponible: {type(exc).__name__}') from exc

    selected = candidates[0] if len(candidates) == 1 else None
    reason = 'deteccion_unica'
    if not candidates:
        reason = 'sin_deteccion'
    elif len(candidates) > 1:
        reason = 'varias_frutas'
    elif selected['product'] != ev.product:
        reason = 'producto_distinto_al_lote'
    elif selected['confidence'] < MIN_CONFIDENCE:
        reason = 'confianza_insuficiente'
    elif len(selected['polygon']) < 3:
        reason = 'segmentacion_no_disponible'

    measured = None
    if reason == 'deteccion_unica' and selected is not None:
        try:
            measured = measure_polygon(selected['polygon'], width, height)
        except InvalidGeometry:
            reason = 'segmentacion_invalida'

    # Solo una pieza, clase compatible, umbral aceptado y máscara válida
    # permiten publicar métricas; NO equivalen a un dictamen de calidad.
    valid = measured is not None and reason == 'deteccion_unica'
    record = FruitGeometry(
        evaluation_id=ev.id, image_id=img.id, image_sha256=sha,
        model_version=MODEL_VERSION, rules_version=RULES_VERSION,
        status='measured' if valid else 'needs_review', reason=reason,
        product=selected['product'] if selected is not None else None,
        confidence=selected['confidence'] if selected is not None else None,
        candidate_count=len(candidates), frame_width=int(width), frame_height=int(height),
        box_json=json.dumps(selected['box'] if valid else None, allow_nan=False),
        polygon_json=json.dumps(selected['polygon'] if valid else [], allow_nan=False),
        measurements_json=json.dumps(measured if valid else None, allow_nan=False),
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except IntegrityError:
        db.rollback()
        current = _existing(db, img, sha)
        if current is not None:
            return _out(current)
        raise HTTPException(409, 'Conflicto al registrar la geometría; reintenta.')
    return _out(record)
