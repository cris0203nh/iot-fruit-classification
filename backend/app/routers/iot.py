from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..iot_schemas import IotStatusOut, MeasurementCreate, MeasurementOut
from ..models import Measurement

router = APIRouter(prefix="/api/iot", tags=["iot"])

# Una lectura se considera vigente si llegó hace menos de este tiempo.
FRESH_SECONDS = 10


def iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


@router.post("/measurements", response_model=MeasurementOut)
def receive_measurement(payload: MeasurementCreate, db: Session = Depends(get_db)):
    if payload.schema_version != 1:
        raise HTTPException(status_code=422, detail="schema_version no soportada.")

    existing = db.scalar(
        select(Measurement).where(
            Measurement.device_id == payload.device_id,
            Measurement.boot_id == payload.boot_id,
            Measurement.seq == payload.seq,
        )
    )
    if existing:
        # Duplicado: no se guarda otra vez ni se refresca received_at.
        return {"received": True, "duplicate": True, "receivedAt": iso(existing.received_at)}

    m = Measurement(
        device_id=payload.device_id,
        boot_id=payload.boot_id,
        seq=payload.seq,
        weight_g=payload.weight_g,
        stable=payload.stable,
        calibration_version=payload.calibration_version,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"received": True, "duplicate": False, "receivedAt": iso(m.received_at)}


@router.get("/status", response_model=IotStatusOut)
def iot_status(db: Session = Depends(get_db)):
    last = db.scalar(select(Measurement).order_by(Measurement.id.desc()).limit(1))
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