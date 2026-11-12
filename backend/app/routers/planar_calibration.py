"""AG-054 I02: calibrar la proyeccion de una mascara YOLOE al plano ArUco.

Nunca declara largo/diametro REAL validado del fruto tridimensional.
La fotografia, la inferencia AG054 I01 y las revisiones son inmutables.
"""
from __future__ import annotations
import hashlib
import json
import re

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_authenticated, require_operator
from ..fruit_geometry_models import FruitGeometry
from ..models import User
from ..planar_calibration_models import PlanarCalibration
from ..services.planar_calibration import CalibrationRejected, measure_plane_projection
from .fruit_geometry import _evaluation, _evidence, _original_image

router = APIRouter(prefix='/api/evaluations', tags=['AG-054 · escala de referencia'])
RULES_VERSION = 'ag054-aruco-plane-v1'


class PlanarCalibrationInput(BaseModel):
    markerId: int = Field(default=0, ge=0, le=49)
    markerSideMm: float = Field(ge=15.0, le=150.0, allow_inf_nan=False)
    # Declaración del operador, no verificación automática de montaje.
    markerAtPlatformLevel: bool


def _out(record: PlanarCalibration) -> dict:
    return {
        'id': record.id,
        'evaluationId': f'E-{record.evaluation_id:06d}',
        'imageId': f'I-{record.image_id:06d}',
        'geometryId': record.geometry_id,
        'imageSha256': record.image_sha256,
        'modelVersion': record.model_version,
        'rulesVersion': record.rules_version,
        'markerId': record.marker_id,
        'markerSideMm': record.marker_side_mm,
        'markerAtPlatformLevelDeclared': record.platform_plane_declared,
        'status': record.status,
        'reason': record.reason,
        'markerCornersPx': json.loads(record.marker_corners_json),
        'measurements': json.loads(record.measurements_json),
        'unit': 'cm_reference_plane',
        'physicalDimensionsValidated': False,
        'cameraIntrinsicsCalibrated': False,
        'fruitHeightCorrected': False,
        'classificationE0E1E2Produced': False,
        'createdAt': record.created_at.isoformat(),
    }


@router.get('/{evaluation_id}/vision/physical/{image_id}')
def list_planar_calibration(evaluation_id: str, image_id: str,
                            db: Session = Depends(get_db),
                            _user: User = Depends(require_authenticated)):
    ev = _evaluation(db, evaluation_id)
    img = _evidence(db, ev, image_id)
    records = db.scalars(select(PlanarCalibration).where(
        PlanarCalibration.evaluation_id == ev.id,
        PlanarCalibration.image_id == img.id,
    ).order_by(PlanarCalibration.id)).all()
    return [_out(item) for item in records]


@router.post('/{evaluation_id}/vision/physical/{image_id}', status_code=201)
def measure_reference_plane(evaluation_id: str, image_id: str, payload: PlanarCalibrationInput,
                            db: Session = Depends(get_db),
                            operator: User = Depends(require_operator)):
    ev = _evaluation(db, evaluation_id)
    if ev.status in ('cancelled', 'error'):
        raise HTTPException(409, 'Esta evaluación no admite nuevas mediciones.')
    img = _evidence(db, ev, image_id)
    geometry = db.scalar(select(FruitGeometry).where(
        FruitGeometry.evaluation_id == ev.id,
        FruitGeometry.image_id == img.id,
    ).order_by(FruitGeometry.id.desc()))
    if geometry is None or geometry.status != 'measured':
        raise HTTPException(409, 'Primero debe existir una geometría YOLOE válida de esta fotografía.')
    raw = _original_image(img)
    sha = hashlib.sha256(raw).hexdigest()
    if sha != geometry.image_sha256:
        raise HTTPException(409, 'La imagen original no coincide con la geometría guardada.')
    previous = db.scalar(select(PlanarCalibration).where(
        PlanarCalibration.image_id == img.id,
        PlanarCalibration.geometry_id == geometry.id,
        PlanarCalibration.image_sha256 == sha,
        PlanarCalibration.marker_id == payload.markerId,
        PlanarCalibration.marker_side_mm == payload.markerSideMm,
        PlanarCalibration.rules_version == RULES_VERSION,
    ))
    if previous:
        return _out(previous)

    if not payload.markerAtPlatformLevel:
        raise HTTPException(422, 'Debes confirmar que el marcador está a la altura del plano de la plataforma; no basta colocarlo sobre la mesa.')
    frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None or frame.shape[:2] != (geometry.frame_height, geometry.frame_width):
        raise HTTPException(409, 'Fotografía original incompatible con la geometría guardada.')
    result = None
    try:
        result = measure_plane_projection(frame, json.loads(geometry.polygon_json),
                                          payload.markerId, payload.markerSideMm)
        status, reason = 'reference_plane_estimate', 'projection_only_not_3d'
    except CalibrationRejected as exc:
        status, reason = 'needs_review', exc.reason
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc

    record = PlanarCalibration(
        evaluation_id=ev.id, image_id=img.id, geometry_id=geometry.id,
        operator_id=operator.id, image_sha256=sha,
        model_version=geometry.model_version, rules_version=RULES_VERSION,
        marker_id=payload.markerId, marker_side_mm=payload.markerSideMm,
        platform_plane_declared=True, status=status, reason=reason,
        marker_corners_json=json.dumps(result['markerCornersPx'] if result else [], allow_nan=False),
        measurements_json=json.dumps(result['measurements'] if result else None, allow_nan=False),
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(PlanarCalibration).where(
            PlanarCalibration.image_id == img.id,
            PlanarCalibration.geometry_id == geometry.id,
            PlanarCalibration.image_sha256 == sha,
            PlanarCalibration.marker_id == payload.markerId,
            PlanarCalibration.marker_side_mm == payload.markerSideMm,
            PlanarCalibration.rules_version == RULES_VERSION,
        ))
        if existing:
            return _out(existing)
        raise HTTPException(409, 'Conflicto al guardar la escala de referencia.')
    return _out(record)
