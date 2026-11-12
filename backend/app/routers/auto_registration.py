"""AG-053: detección YOLOE antes del registro e identificación segura de pieza.

No crea etiquetas de calidad ni valida dimensiones físicas. No usa datos
simulados en la API: un detector ausente retorna 503 explícito.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from ..auto_registration_models import VisionPrecheck
from ..database import get_db
from ..dependencies import require_operator
from ..models import Evaluation, Lot, Piece, User
from .evaluations import detail
from .images import _VISION_INFERENCE_LOCK, get_vision_model

router = APIRouter(prefix='/api', tags=['AG-053 · identificación automática'])

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MIN_CONFIDENCE = 0.40
TOKEN_TTL = timedelta(minutes=15)
MODEL_VERSION = 'yoloe-26n-seg'


class AutoRegisterInput(BaseModel):
    lotId: str = Field(min_length=1, max_length=32)
    detectionToken: str = Field(pattern=r'^[0-9a-f]{64}$')


def _product_from_label(label: str) -> str | None:
    text = label.lower()
    if 'mango' in text:
        return 'mango'
    if 'tomato' in text or 'tomate' in text:
        return 'tomate'
    return None


def _infer_products(frame: np.ndarray) -> list[dict]:
    """Invoca los pesos/prompts usados por la detección existente de AgroScan."""
    model = get_vision_model()
    with _VISION_INFERENCE_LOCK:
        result = model.predict(
            source=frame, imgsz=512, conf=0.25, iou=0.50,
            max_det=10, device='cpu', verbose=False,
        )[0]

    names = result.names
    polygons = result.masks.xy if result.masks is not None else []
    candidates = []
    if result.boxes is None:
        return candidates

    for index, box in enumerate(result.boxes):
        class_id = int(box.cls[0].item())
        label = names.get(class_id, '') if isinstance(names, dict) else names[class_id]
        product = _product_from_label(str(label))
        if product is None:
            continue
        confidence = float(box.conf[0].item())
        coordinates = [float(value) for value in box.xyxy[0].tolist()]
        if not np.isfinite(confidence) or not np.isfinite(coordinates).all():
            continue
        points = polygons[index] if index < len(polygons) else []
        stride = max(1, len(points) // 120)
        polygon = [[round(float(p[0]), 1), round(float(p[1]), 1)] for p in points[::stride]]
        if not all(np.isfinite(p).all() for p in polygon):
            polygon = []
        candidates.append({
            'product': product,
            'confidence': confidence,
            'box': [round(value, 1) for value in coordinates],
            'polygon': polygon,
        })
    return sorted(candidates, key=lambda item: item['confidence'], reverse=True)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@router.post('/vision/precheck')
def precheck_fruit(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    operator: User = Depends(require_operator),
):
    """Una fotografía temporal identifica la fruta, sin crear lote ni pieza."""
    if file.content_type not in ('image/jpeg', 'image/png'):
        raise HTTPException(422, 'Envía una fotografía JPG o PNG.')
    content = file.file.read(MAX_IMAGE_BYTES + 1)
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(422, 'Fotografía vacía o de más de 2 MiB.')
    frame = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None or min(frame.shape[:2]) < 128:
        raise HTTPException(422, 'Fotografía inválida o resolución menor de 128 px.')

    try:
        candidates = _infer_products(frame)
    except Exception as exc:
        raise HTTPException(503, f'YOLOE no disponible: {type(exc).__name__}') from exc

    chosen = candidates[0] if candidates else None
    ready = bool(
        len(candidates) == 1 and chosen is not None
        and chosen['confidence'] >= MIN_CONFIDENCE
        and len(chosen['polygon']) >= 3
    )
    reason = (
        'deteccion_unica' if ready else
        'varias_frutas' if len(candidates) > 1 else
        'sin_deteccion' if not candidates else
        'confianza_insuficiente' if chosen and chosen['confidence'] < MIN_CONFIDENCE
        else 'segmentacion_no_disponible'
    )
    token = None
    if ready:
        token = secrets.token_hex(32)
        db.add(VisionPrecheck(
            token=token, operator_id=operator.id, product=chosen['product'],
            confidence=chosen['confidence'], image_sha256=hashlib.sha256(content).hexdigest(),
        ))
        db.commit()

    return {
        'detected': chosen is not None,
        'readyToRegister': ready,
        'product': chosen['product'] if ready else None,
        'confidence': chosen['confidence'] if chosen else None,
        'candidateCount': len(candidates),
        'box': chosen['box'] if chosen else None,
        'polygon': chosen['polygon'] if chosen else [],
        'frameWidth': int(frame.shape[1]), 'frameHeight': int(frame.shape[0]),
        'reason': reason, 'detectionToken': token,
        'modelVersion': MODEL_VERSION,
        'classificationE0E1E2Produced': False,
    }


def _next_piece_code(db: Session, lot_id: int) -> str:
    """Contador por lote; se invoca después de tomar bloqueo de escritura."""
    codes = db.scalars(select(Piece.code).where(Piece.lot_id == lot_id)).all()
    values = []
    for code in codes:
        match = re.fullmatch(r'P-(\d+)', code)
        if match:
            values.append(int(match.group(1)))
    next_number = max(values, default=0) + 1
    if next_number > 999_999_999:
        raise HTTPException(409, 'Límite de referencias automáticas alcanzado.')
    return f'P-{next_number:06d}'


@router.post('/evaluations/auto', status_code=201)
def register_detected_piece(
    payload: AutoRegisterInput,
    db: Session = Depends(get_db),
    operator: User = Depends(require_operator),
):
    """Consume token una sola vez; repetirlo devuelve la misma evaluación."""
    try:
        # Primera escritura: serializa las transacciones SQLite, también si
        # dos operarios usan tokens distintos sobre el mismo lote.
        affected = db.execute(
            update(VisionPrecheck)
            .where(VisionPrecheck.token == payload.detectionToken)
            .values(registration_claims=VisionPrecheck.registration_claims + 1)
        )
        if affected.rowcount != 1:
            db.rollback()
            raise HTTPException(404, 'Detección no encontrada. Vuelve a analizar la fotografía.')

        detection = db.get(VisionPrecheck, payload.detectionToken, populate_existing=True)
        if detection.operator_id != operator.id:
            db.rollback()
            raise HTTPException(403, 'La detección pertenece a otra sesión de operador.')

        # Idempotencia: procesar el mismo token no puede duplicar piezas.
        if detection.evaluation_id is not None:
            old = db.get(Evaluation, detection.evaluation_id)
            if old is None or old.lot.code.lower() != payload.lotId.strip().lower():
                db.rollback()
                raise HTTPException(409, 'La detección ya se usó para otro lote.')
            response = detail(old)
            db.commit()
            return response

        if datetime.now(timezone.utc) - _utc(detection.created_at) > TOKEN_TTL:
            db.rollback()
            raise HTTPException(409, 'La detección expiró; analiza nuevamente la fruta.')

        lot = db.scalar(select(Lot).where(func.lower(Lot.code) == payload.lotId.strip().lower()))
        if lot is None:
            db.rollback()
            raise HTTPException(404, 'El lote seleccionado no existe.')
        if lot.status != 'open':
            db.rollback()
            raise HTTPException(409, 'El lote ya no está abierto.')
        if lot.product != detection.product:
            db.rollback()
            raise HTTPException(409, 'El producto detectado no coincide con el lote seleccionado.')

        # Fila bloqueada en motores SQL con SELECT FOR UPDATE;
        # SQLite serializa desde UPDATE VisionPrecheck anterior.
        db.execute(select(Lot.id).where(Lot.id == lot.id).with_for_update()).scalar_one()
        piece = Piece(lot_id=lot.id, code=_next_piece_code(db, lot.id))
        db.add(piece)
        db.flush()
        evaluation = Evaluation(
            lot_id=lot.id, piece_id=piece.code, piece_ref_id=piece.id,
            product=lot.product,
        )
        db.add(evaluation)
        db.flush()
        detection.evaluation_id = evaluation.id
        detection.registered_lot_id = lot.id
        db.commit()
        db.refresh(evaluation)
        return detail(evaluation)
    except HTTPException:
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'Conflicto de numeración; vuelve a intentar el registro.') from exc
    except OperationalError as exc:
        db.rollback()
        raise HTTPException(503, 'La base de datos está ocupada; reintenta con la misma detección.') from exc
