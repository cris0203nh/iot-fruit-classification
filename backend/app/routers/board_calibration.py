"""AG-054 I03: tablero multimarcas externo y comparación manual auditable.

No modifica los pesos, la clasificación, las imágenes ni el dictamen humano.
"""
from __future__ import annotations

import hashlib
import json
import math

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..board_calibration_models import BoardCalibration, DimensionalComparison
from ..database import get_db
from ..dependencies import require_authenticated, require_operator, require_reviewer
from ..fruit_geometry_models import FruitGeometry
from ..models import Evaluation, User
from ..services.board_calibration import (
    BOARD_VERSION, A4_BOARD_VERSION, BOARD_LAYOUTS, CalibrationRejected, compare_with_caliper, measure_board_projection,
)
from .fruit_geometry import _evaluation, _evidence, _original_image

router = APIRouter(prefix='/api/evaluations', tags=['AG-054 · tablero multimarcas'])
RULES_VERSION = 'ag054-board-plane-v1'
COMPARISON_RULES_VERSION = 'ag054-caliper-comparison-v1'


class BoardInput(BaseModel):
    boardVersion: Literal['ag054-board-a3-v1', 'ag054-board-a4-v1']
    markerAtPlatformLevel: bool
    independentSupport: bool
    printedDimensionsVerified: bool
    fixedCamera: bool


class ComparisonInput(BaseModel):
    boardCalibrationId: int | None = Field(default=None, ge=1)
    referenceMajorCm: float = Field(ge=0.1, le=60.0, allow_inf_nan=False)
    referenceMinorCm: float = Field(ge=0.1, le=60.0, allow_inf_nan=False)
    instrumentId: str = Field(min_length=2, max_length=120)


def _board_out(row: BoardCalibration) -> dict:
    return {
        'id': row.id, 'evaluationId': f'E-{row.evaluation_id:06d}',
        'imageId': f'I-{row.image_id:06d}', 'geometryId': row.geometry_id,
        'imageSha256': row.image_sha256, 'modelVersion': row.model_version,
        'rulesVersion': row.rules_version, 'boardVersion': row.board_version,
        'status': row.status, 'reason': row.reason,
        'markerIds': json.loads(row.marker_ids_json),
        'markerCornersPx': json.loads(row.corners_json),
        'measurements': json.loads(row.measurements_json),
        'rmsReprojectionMm': row.rms_reprojection_mm,
        'unit': 'cm_reference_plane', 'physicalDimensionsValidated': False,
        'fruitHeightCorrected': False, 'cameraIntrinsicsCalibrated': False,
        'classificationE0E1E2Produced': False,
        'createdAt': row.created_at.isoformat(),
    }


def _comparison_out(row: DimensionalComparison) -> dict:
    return {
        'id': row.id, 'boardCalibrationId': row.board_calibration_id,
        'referenceMajorCm': row.major_manual_cm, 'referenceMinorCm': row.minor_manual_cm,
        'instrumentId': row.instrument_id,
        'comparison': json.loads(row.comparison_json),
        'physicalDimensionsValidated': False, 'createdAt': row.created_at.isoformat(),
    }


@router.get('/{evaluation_id}/vision/board/{image_id}')
def list_board(evaluation_id: str, image_id: str,
               db: Session = Depends(get_db), _user: User = Depends(require_authenticated)):
    ev = _evaluation(db, evaluation_id)
    img = _evidence(db, ev, image_id)
    return [_board_out(row) for row in db.scalars(select(BoardCalibration).where(
        BoardCalibration.evaluation_id == ev.id, BoardCalibration.image_id == img.id,
    ).order_by(BoardCalibration.id)).all()]


@router.post('/{evaluation_id}/vision/board/{image_id}', status_code=201)
def create_board(evaluation_id: str, image_id: str, payload: BoardInput,
                 db: Session = Depends(get_db), operator: User = Depends(require_operator)):
    ev = _evaluation(db, evaluation_id)
    if ev.status in ('error','cancelled'):
        raise HTTPException(409, 'No se puede analizar una evaluación anulada o fallida.')
    img = _evidence(db, ev, image_id)
    geometry = db.scalar(select(FruitGeometry).where(
        FruitGeometry.evaluation_id == ev.id, FruitGeometry.image_id == img.id,
    ).order_by(FruitGeometry.id.desc()))
    if geometry is None or geometry.status != 'measured':
        raise HTTPException(409, 'Se requiere geometría YOLOE válida de la fotografía guardada.')
    # Decisiones declaradas sobre el montaje; nunca inferidas del contenido RGB.
    if not all((payload.markerAtPlatformLevel, payload.independentSupport,
                payload.printedDimensionsVerified, payload.fixedCamera)):
        raise HTTPException(422, 'Confirma plano, soporte independiente, impresión medida y cámara fija.')
    raw = _original_image(img)
    sha = hashlib.sha256(raw).hexdigest()
    if geometry.image_sha256 != sha:
        raise HTTPException(409, 'El original y su geometría no tienen el mismo SHA-256.')
    rules_version = RULES_VERSION if payload.boardVersion == BOARD_VERSION else 'ag054-board-plane-v2-a4'
    prior = db.scalar(select(BoardCalibration).where(
        BoardCalibration.image_id == img.id, BoardCalibration.geometry_id == geometry.id,
        BoardCalibration.image_sha256 == sha, BoardCalibration.rules_version == rules_version,
    ))
    if prior:
        return _board_out(prior)
    frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None or frame.shape[:2] != (geometry.frame_height, geometry.frame_width):
        raise HTTPException(409, 'El original no corresponde a las dimensiones YOLOE guardadas.')
    try:
        result = measure_board_projection(frame, json.loads(geometry.polygon_json), payload.boardVersion)
        status, reason = 'reference_plane_estimate', 'projection_only_not_3d'
    except CalibrationRejected as exc:
        result = None
        status, reason = 'needs_review', exc.reason
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    item = BoardCalibration(
        evaluation_id=ev.id, image_id=img.id, geometry_id=geometry.id,
        operator_id=operator.id, image_sha256=sha,
        model_version=geometry.model_version, rules_version=rules_version,
        board_version=payload.boardVersion, status=status, reason=reason,
        marker_ids_json=json.dumps(result['markerIds'] if result else [], allow_nan=False),
        corners_json=json.dumps(result['markerCornersPx'] if result else {}, allow_nan=False),
        measurements_json=json.dumps(result['measurements'] if result else None, allow_nan=False),
        rms_reprojection_mm=result['rmsReprojectionMm'] if result else None,
        platform_level_declared=True, independent_support_declared=True,
        printed_scale_verified_declared=True, fixed_camera_declared=True,
    )
    try:
        db.add(item)
        db.commit()
        db.refresh(item)
    except IntegrityError:
        db.rollback()
        prior = db.scalar(select(BoardCalibration).where(
            BoardCalibration.image_id == img.id, BoardCalibration.geometry_id == geometry.id,
            BoardCalibration.image_sha256 == sha, BoardCalibration.rules_version == rules_version,
        ))
        if prior:
            return _board_out(prior)
        raise HTTPException(409, 'Conflicto guardando tablero; reintenta.')
    return _board_out(item)


@router.get('/{evaluation_id}/vision/board/{image_id}/comparisons')
def list_comparisons(evaluation_id: str, image_id: str,
                     db: Session = Depends(get_db), _user: User = Depends(require_authenticated)):
    ev = _evaluation(db, evaluation_id)
    img = _evidence(db, ev, image_id)
    rows = db.scalars(select(DimensionalComparison).join(BoardCalibration).where(
        BoardCalibration.evaluation_id == ev.id, BoardCalibration.image_id == img.id,
    ).order_by(DimensionalComparison.id)).all()
    return [_comparison_out(row) for row in rows]


@router.post('/{evaluation_id}/vision/board/{image_id}/comparisons', status_code=201)
def create_comparison(evaluation_id: str, image_id: str, payload: ComparisonInput,
                      db: Session = Depends(get_db), operator: User = Depends(require_operator)):
    ev = _evaluation(db, evaluation_id)
    img = _evidence(db, ev, image_id)
    if not payload.instrumentId.strip():
        raise HTTPException(422, 'Identifica el instrumento físico utilizado.')
    constraints = [
        BoardCalibration.evaluation_id == ev.id,
        BoardCalibration.image_id == img.id,
        BoardCalibration.status == 'reference_plane_estimate',
    ]
    if payload.boardCalibrationId is not None:
        constraints.append(BoardCalibration.id == payload.boardCalibrationId)
    board = db.scalar(select(BoardCalibration).where(*constraints).order_by(BoardCalibration.id.desc()))
    if board is None:
        raise HTTPException(409, 'No existe estimación válida del tablero para comparar.')
    if payload.referenceMajorCm < payload.referenceMinorCm:
        raise HTTPException(422, 'El eje mayor manual debe ser mayor o igual al menor.')
    if hashlib.sha256(_original_image(img)).hexdigest() != board.image_sha256:
        raise HTTPException(409, 'El archivo original ha cambiado; comparación no autorizada.')
    instrument = payload.instrumentId.strip()
    previous = db.scalar(select(DimensionalComparison).where(
        DimensionalComparison.board_calibration_id == board.id,
        DimensionalComparison.major_manual_cm == payload.referenceMajorCm,
        DimensionalComparison.minor_manual_cm == payload.referenceMinorCm,
        DimensionalComparison.instrument_id == instrument,
        DimensionalComparison.rules_version == COMPARISON_RULES_VERSION,
    ))
    if previous:
        return _comparison_out(previous)
    try:
        result = compare_with_caliper(json.loads(board.measurements_json),
                                      payload.referenceMajorCm, payload.referenceMinorCm)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    row = DimensionalComparison(
        board_calibration_id=board.id, operator_id=operator.id,
        rules_version=COMPARISON_RULES_VERSION,
        major_manual_cm=payload.referenceMajorCm,
        minor_manual_cm=payload.referenceMinorCm,
        instrument_id=instrument,
        comparison_json=json.dumps(result, ensure_ascii=False, allow_nan=False),
    )
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except IntegrityError:
        db.rollback()
        prior = db.scalar(select(DimensionalComparison).where(
            DimensionalComparison.board_calibration_id == board.id,
            DimensionalComparison.major_manual_cm == payload.referenceMajorCm,
            DimensionalComparison.minor_manual_cm == payload.referenceMinorCm,
            DimensionalComparison.instrument_id == instrument,
            DimensionalComparison.rules_version == COMPARISON_RULES_VERSION,
        ))
        if prior:
            return _comparison_out(prior)
        raise HTTPException(409, 'Conflicto guardando comparación.')
    return _comparison_out(row)


@router.get('/vision/board-validation/report')
def report(db: Session = Depends(get_db), _user: User = Depends(require_reviewer)):
    """Informe agregado de comparaciones reales; sin inventar umbrales aprobatorios."""
    rows = db.execute(select(DimensionalComparison, BoardCalibration, Evaluation).join(
        BoardCalibration, DimensionalComparison.board_calibration_id == BoardCalibration.id
    ).join(Evaluation, BoardCalibration.evaluation_id == Evaluation.id)).all()
    per_product: dict[str, list[dict]] = {'mango': [], 'tomate': []}
    for comparison, board, evaluation in rows:
        if evaluation.product in per_product:
            per_product[evaluation.product].append(json.loads(comparison.comparison_json))
    summary = {}
    for product, records in per_product.items():
        if not records:
            summary[product] = {'sampleCount': 0, 'meanAbsoluteErrorMajorCm': None,
                                'meanAbsoluteErrorMinorCm': None, 'meanAbsolutePercentageErrorMajor': None,
                                'physicalDimensionsValidated': False}
        else:
            n = len(records)
            summary[product] = {
                'sampleCount': n,
                'meanAbsoluteErrorMajorCm': round(sum(r['major']['absoluteErrorCm'] for r in records)/n, 3),
                'meanAbsoluteErrorMinorCm': round(sum(r['minor']['absoluteErrorCm'] for r in records)/n, 3),
                'meanAbsolutePercentageErrorMajor': round(sum(r['major']['relativeAbsoluteErrorPct'] for r in records)/n, 2),
                'physicalDimensionsValidated': False,
            }
    return {'boardVersion': 'multiple', 'supportedBoardVersions': sorted(BOARD_LAYOUTS),
            'method': 'comparison_only',
            'sampleDefinition': 'registros_de_comparacion_no_necesariamente_piezas_unicas',
            'products': summary, 'physicalDimensionsValidated': False}
