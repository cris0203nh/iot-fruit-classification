from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from ..dependencies import require_authenticated
from ..iot_models import IotDevice
from ..services.device_auth import authenticated_device, active_measurements, require_iot_schema
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..iot_schemas import IotStatusOut, MeasurementCreate, MeasurementOut
from ..models import Measurement

router = APIRouter(prefix="/api/iot", tags=["iot"], dependencies=[Depends(require_iot_schema)])

# Una lectura se considera vigente si llegó hace menos de este tiempo.
FRESH_SECONDS = 10


def iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


@router.post("/measurements", response_model=MeasurementOut)
def receive_measurement(payload: MeasurementCreate, db: Session = Depends(get_db),
                        device: IotDevice = Depends(authenticated_device)):
    if payload.device_id != device.device_id:
        raise HTTPException(403, 'La medición no corresponde al dispositivo autenticado.')
    if payload.schema_version != 1:
        raise HTTPException(status_code=422, detail="schema_version no soportada.")

    measurement_query = select(Measurement).where(
        Measurement.device_id == payload.device_id,
        Measurement.boot_id == payload.boot_id,
        Measurement.seq == payload.seq,
    )
    existing = db.scalar(measurement_query)
    if existing:
        # Duplicado: no se guarda otra vez ni se refresca received_at.
        return {"received": True, "duplicate": True, "receivedAt": iso(existing.received_at)}

    m = Measurement(
        device_id=payload.device_id,
        boot_id=payload.boot_id,
        seq=payload.seq,
        weight_g=payload.weight_g,
        stable=payload.stable,
        zero_confirmed=payload.zero_confirmed,
        calibration_version=payload.calibration_version,
        observed_at=payload.observed_at,
    )
    db.add(m)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Otro reenvío pudo confirmar la misma secuencia después del SELECT.
        existing = db.scalar(measurement_query)
        if existing is None:
            raise
        return {"received": True, "duplicate": True, "receivedAt": iso(existing.received_at)}
    db.refresh(m)
    return {"received": True, "duplicate": False, "receivedAt": iso(m.received_at)}


@router.get("/status", response_model=IotStatusOut)
def iot_status(db: Session = Depends(get_db), user=Depends(require_authenticated)):
    last = db.scalar(active_measurements(select(Measurement)).order_by(Measurement.id.desc()).limit(1))
    if last is None:
        return {"online": False, "deviceId": None, "weightG": None,
                "stable": None, "receivedAt": None, "ageSeconds": None}

    received = last.received_at
    if received.tzinfo is None:
        received = received.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - received).total_seconds()
    fresh = age <= FRESH_SECONDS
    return {
        "online": fresh,
        "deviceId": last.device_id,
        # Si la lectura es vieja, no se muestra como peso actual.
        "weightG": last.weight_g if fresh else None,
        "stable": last.stable if fresh else None,
        "receivedAt": iso(received),
        "ageSeconds": round(age, 1),
    }
