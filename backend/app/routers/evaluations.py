import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import DATA_DIR, get_db
from ..dependencies import (
    require_admin,
    require_reviewer,
    require_operator,
    require_authenticated,
)
from ..evaluation_schemas import (
    EvaluationCreate,
    EvaluationDetailOut,
    EvaluationSummaryOut,
    WeightStepOut,
)
from ..models import Evaluation, Image, Lot, Measurement, Piece, Review, User

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
        "evidence": [
            {"id": f"I-{i.id:06d}", "view": i.view, "imageUrl": f"/api/images/I-{i.id:06d}"}
            for i in ev.images
        ],
        "visualCategory": ev.visual_category,
        "reviewNote": ev.review_note,
        "failureReason": ev.failure_reason,
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
        raise HTTPException(status_code=404, detail="EvaluaciÃ³n no encontrada.")
    return ev


def effective_value(ev: Evaluation) -> str | None:
    """Valor vigente: el de la Ãºltima revisiÃ³n, o el original si no hay."""
    for r in reversed(ev.reviews):
        if r.type == "review":
            return r.updated_value
    return ev.visual_category


@router.get(
    "",
    response_model=list[EvaluationSummaryOut],
    dependencies=[Depends(require_authenticated)],
)
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
def create_evaluation(
    payload: EvaluationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    # 1. Buscar el lote correspondiente.
    lot = db.scalar(
        select(Lot).where(
            func.lower(Lot.code) == payload.lotId.lower()
        )
    )

    if lot is None:
        raise HTTPException(
            status_code=404,
            detail="El lote indicado no existe."
        )

    if lot.status != "open":
        raise HTTPException(
            status_code=409,
            detail="El lote estÃ¡ cerrado."
        )

    # 2. Buscar si la pieza ya estÃ¡ registrada dentro del lote.
    piece = db.scalar(
        select(Piece).where(
            Piece.lot_id == lot.id,
            Piece.code == payload.pieceId
        )
    )

    # 3. Registrar la pieza solamente si todavÃ­a no existe.
    if piece is None:
        piece = Piece(
            lot_id=lot.id,
            code=payload.pieceId
        )
        db.add(piece)
        db.flush()

    # 4. Crear la evaluaciÃ³n vinculada a la pieza.
    ev = Evaluation(
        lot_id=lot.id,
        piece_id=payload.pieceId,
        piece_ref_id=piece.id,
        product=lot.product
    )
    db.add(ev)
    try:
        db.commit()
        db.refresh(ev)
    except Exception:
        db.rollback()
        raise
    return detail(ev)



@router.get(
    "/{evaluation_id}",
    response_model=EvaluationDetailOut,
    dependencies=[Depends(require_authenticated)],
)
def get_evaluation(evaluation_id: str, db: Session = Depends(get_db)):
    return detail(get_or_404(db, evaluation_id))


@router.get(
    "/{evaluation_id}/traceability",
    response_model=TraceabilityOut,
    dependencies=[Depends(require_authenticated)],
)
def get_traceability(evaluation_id: str, db: Session = Depends(get_db)):
    ev = get_or_404(db, evaluation_id)
    return {
        "evaluation": detail(ev),
        "calibrationReference": ev.calibration_reference,
        "modelVersion": ev.model_version,
        "rulesVersion": ev.rules_version,
        "reviews": [review_out(r) for r in ev.reviews],
    }


@router.post(
    "/{evaluation_id}/reviews",
    response_model=ReviewEventOut,
    status_code=201,
)
def add_review(
    evaluation_id: str,
    payload: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer),
):
    ev = get_or_404(db, evaluation_id)

    if ev.status not in ("pending_review", "completed"):
        raise HTTPException(
            status_code=409,
            detail="Solo se puede revisar una evaluaciÃ³n completada o por revisar.",
        )

    review = Review(
        evaluation_id=ev.id,
        type="review",
        actor_id=current_user.username,
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


@router.post(
    "/{evaluation_id}/cancel",
    response_model=ReviewEventOut,
    status_code=201,
)
def cancel_evaluation(
    evaluation_id: str,
    payload: CancelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ev = get_or_404(db, evaluation_id)

    if ev.status == "cancelled":
        raise HTTPException(
            status_code=409,
            detail="La evaluaciÃ³n ya estÃ¡ anulada.",
        )

    event = Review(
        evaluation_id=ev.id,
        type="cancellation",
        actor_id=current_user.username,
        reason=payload.reason,
        previous_value=ev.status,
        updated_value="cancelled",
    )

    db.add(event)
    ev.status = "cancelled"

    db.commit()
    db.refresh(event)

    return review_out(event)

FRESH_SECONDS = 10       # una lectura es vigente si llegÃ³ hace menos de esto
TOLERANCE_G = 5.0        # diferencia mÃ¡xima entre peso inicial y de confirmaciÃ³n
TIMEOUT_SECONDS = 180    # tiempo mÃ¡ximo de una evaluaciÃ³n en proceso


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def fail(db: Session, ev: Evaluation, reason: str):
    ev.status = "error"
    ev.failure_reason = reason
    db.commit()
    raise HTTPException(status_code=409, detail=reason)


def ensure_active(db: Session, ev: Evaluation) -> None:
    if ev.status != "processing":
        raise HTTPException(status_code=409, detail="La evaluaciÃ³n ya no estÃ¡ en proceso.")
    age = (datetime.now(timezone.utc) - aware(ev.created_at)).total_seconds()
    if age > TIMEOUT_SECONDS:
        fail(db, ev, "Tiempo de espera agotado sin completar la mediciÃ³n de peso.")




def latest_ready(db: Session, after: datetime) -> Measurement:
    """Obtiene la Ãºltima adquisiciÃ³n y valida su vigencia y trazabilidad."""

    last = db.scalar(
        select(Measurement).order_by(Measurement.id.desc()).limit(1)
    )

    if last is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SENSOR_DISCONNECTED",
                "message": "No se recibiÃ³ ninguna lectura del sensor.",
                "action": "Revise la conexiÃ³n del ESP32."
            }
        )

    now = datetime.now(timezone.utc)

    # 1. Exigir timestamp de adquisiciÃ³n.
    if last.observed_at is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TIMESTAMP_MISSING",
                "message": "La adquisiciÃ³n no tiene timestamp.",
                "action": "Verifique el puente serial y espere una nueva lectura."
            }
        )

    observed = aware(last.observed_at)
    received = aware(last.received_at)

    # 2. Rechazar timestamps futuros.
    if (observed - now).total_seconds() > 2:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TIMESTAMP_INVALID",
                "message": "El timestamp de adquisiciÃ³n estÃ¡ en el futuro.",
                "action": "Verifique la sincronizaciÃ³n del reloj."
            }
        )

    # 3. Evitar timestamps posteriores a la recepciÃ³n.
    if (observed - received).total_seconds() > 2:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TIMESTAMP_INVALID",
                "message": "La fecha de adquisiciÃ³n es posterior a su recepciÃ³n.",
                "action": "Verifique el timestamp enviado por el puente serial."
            }
        )

    # 4. Validar antigÃ¼edad de la adquisiciÃ³n, no solo recepciÃ³n.
    age = (now - observed).total_seconds()

    if age > FRESH_SECONDS:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SENSOR_DISCONNECTED",
                "message": "La adquisiciÃ³n del peso estÃ¡ vencida.",
                "action": "Espere una nueva lectura del ESP32."
            }
        )

    # 5. Exigir versiÃ³n compatible con el firmware real.
    if not re.fullmatch(
        r"cal-[0-9a-fA-F]{32}-[1-9][0-9]*",
        last.calibration_version
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CALIBRATION_INVALID",
                "message": "La versiÃ³n de calibraciÃ³n no es vÃ¡lida.",
                "action": "Realice y verifique la calibraciÃ³n de la balanza."
            }
        )

    # 6. Validar estabilidad.
    if not last.stable:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "WEIGHT_UNSTABLE",
                "message": "El peso registrado no estÃ¡ estable.",
                "action": "Mantenga la pieza quieta."
            }
        )

    # 7. Validar puesta a cero.
    if not last.zero_confirmed:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ZERO_NOT_CONFIRMED",
                "message": "No se confirmÃ³ el cero de la balanza.",
                "action": "Retire la carga y realice TARE."
            }
        )

    # 8. Exigir una adquisiciÃ³n posterior a la etapa anterior.
    if observed <= aware(after):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "WAITING_FOR_NEW_READING",
                "message": "La adquisiciÃ³n no es posterior al inicio de esta etapa.",
                "action": "Espere una nueva lectura del sensor."
            }
        )

    return last



def weight_step(stage: str, m: Measurement) -> dict:
    return {
        "stage": stage,
        "weightG": m.weight_g,
        "deviceId": m.device_id,
        "receivedAt": iso(m.received_at),
    }



@router.post("/{evaluation_id}/weight/pre", response_model=WeightStepOut)
def weight_pre(
    evaluation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    ev = get_or_404(db, evaluation_id)
    ensure_active(db, ev)

    if ev.weight_pre_g is not None:
        raise HTTPException(
            status_code=409,
            detail="El peso inicial ya fue registrado."
        )

    m = latest_ready(db, after=aware(ev.created_at))

    # Registrar el peso y vincular la mediciÃ³n original.
    ev.weight_pre_g = m.weight_g
    ev.weight_pre_at = m.received_at
    ev.weight_pre_measurement_id = m.id

    ev.device_id = m.device_id
    ev.boot_id = m.boot_id
    ev.calibration_reference = m.calibration_version

    db.commit()

    return weight_step("pre", m)


@router.post("/{evaluation_id}/weight/post", response_model=WeightStepOut)
def weight_post(
    evaluation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    ev = get_or_404(db, evaluation_id)
    ensure_active(db, ev)

    if ev.weight_pre_g is None:
        raise HTTPException(
            status_code=409,
            detail="Falta registrar el peso inicial."
        )

    if ev.weight_post_g is not None:
        raise HTTPException(
            status_code=409,
            detail="El peso de confirmaciÃ³n ya fue registrado."
        )

    m = latest_ready(db, after=aware(ev.weight_pre_at))

    # Verificar que continÃºa siendo el mismo dispositivo y sesiÃ³n.
    if m.device_id != ev.device_id or m.boot_id != ev.boot_id:
        fail(db, ev, "El sensor se reiniciÃ³ o cambiÃ³ durante la evaluaciÃ³n.")

    # Verificar que el peso no haya cambiado significativamente.
    if abs(m.weight_g - ev.weight_pre_g) > TOLERANCE_G:
        fail(
            db,
            ev,
            "El peso cambiÃ³ durante la captura: posible movimiento o cambio de pieza."
        )

    # Registrar el peso final y vincular la mediciÃ³n original.
    ev.weight_post_g = m.weight_g
    ev.weight_post_at = aware(m.observed_at)
    ev.weight_post_measurement_id = m.id
    ev.weight_grams = m.weight_g

    db.commit()

    return weight_step("post", m)
@router.post("/{evaluation_id}/acquisition/confirm")
def confirm_acquisition(
    evaluation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    ev = get_or_404(db, evaluation_id)

    if ev.status != "processing":
        raise HTTPException(
            status_code=409,
            detail="La evaluaciÃ³n ya no estÃ¡ en proceso."
        )

    # Verificar los dos registros de peso.
    if (
        ev.weight_pre_g is None
        or ev.weight_post_g is None
        or ev.weight_pre_measurement_id is None
        or ev.weight_post_measurement_id is None
        or ev.weight_grams is None
    ):
        raise HTTPException(
            status_code=409,
            detail="Falta completar la captura y confirmaciÃ³n del peso."
        )

    # Recuperar las mediciones originales.
    pre = db.get(Measurement, ev.weight_pre_measurement_id)
    post = db.get(Measurement, ev.weight_post_measurement_id)

    if pre is None or post is None:
        raise HTTPException(
            status_code=409,
            detail="No se encontraron las mediciones originales."
        )

    # Verificar que ambas mediciones sean del mismo dispositivo y sesiÃ³n.
    if (
        pre.device_id != post.device_id
        or pre.boot_id != post.boot_id
        or pre.device_id != ev.device_id
        or pre.boot_id != ev.boot_id
    ):
        raise HTTPException(
            status_code=409,
            detail="Las mediciones no corresponden al mismo dispositivo y sesiÃ³n."
        )

    # Comprobar que existen fotografÃ­as asociadas a esta evaluaciÃ³n.
    images = db.scalars(
        select(Image).where(Image.evaluation_id == ev.id)
    ).all()

    if not images:
        raise HTTPException(
            status_code=409,
            detail="Debe guardar al menos una fotografÃ­a de la pieza."
        )

    # Verificar que los archivos asociados continÃºen disponibles.
    for image in images:
        image_path = DATA_DIR / image.relative_path

        if not image_path.is_file() or image.size_bytes <= 0:
            raise HTTPException(
                status_code=409,
                detail="Existe una fotografÃ­a no disponible o invÃ¡lida."
            )

    return {
        "confirmed": True,
        "evaluationId": public_id(ev.id),
        "pieceId": ev.piece_id,
        "product": ev.product,
        "weightGrams": ev.weight_grams,
        "imageCount": len(images),
        "deviceId": ev.device_id,
    }
