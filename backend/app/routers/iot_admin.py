"""Aprovisionamiento exclusivamente por el administrador de la empresa activa."""
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin
from ..iot_models import IotDevice, IotStation
from ..services.device_auth import credential_hash, begin_device_write, require_iot_schema

def serialize_writes(request: Request, db: Session = Depends(get_db)):
    if request.method in ('POST', 'PATCH', 'DELETE'):
        begin_device_write(db)


router = APIRouter(prefix='/api/iot', tags=['dispositivos'],
                   dependencies=[Depends(require_admin), Depends(require_iot_schema), Depends(serialize_writes)])


class StationCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    code: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    name: str = Field(min_length=1, max_length=120)


class StationState(BaseModel):
    model_config = ConfigDict(extra='forbid')
    isActive: bool


class DeviceCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    stationId: int = Field(gt=0)
    deviceId: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')


def station_out(row):
    return {'id': row.id, 'code': row.code, 'name': row.name, 'isActive': row.is_active}


def device_out(row):
    return {'id': row.id, 'stationId': row.station_id, 'deviceId': row.device_id,
            'isActive': row.is_active, 'provisioned': row.credential_hash is not None}


def resource(db, model, pk):
    row = db.get(model, pk)
    if row is None:
        raise HTTPException(404, 'Recurso no encontrado.')
    return row


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'El identificador ya existe en esta empresa.') from None


@router.get('/stations')
def stations(db: Session = Depends(get_db)):
    return [station_out(row) for row in db.scalars(select(IotStation).order_by(IotStation.id))]


@router.post('/stations', status_code=201)
def create_station(body: StationCreate, db: Session = Depends(get_db)):
    row = IotStation(code=body.code, name=body.name)
    db.add(row)
    commit(db)
    return station_out(row)


@router.patch('/stations/{station_id}')
def station_state(station_id: int, body: StationState, db: Session = Depends(get_db)):
    row = resource(db, IotStation, station_id)
    row.is_active = body.isActive
    # Suspender no conserva credenciales que puedan revivir al reactivar estación.
    if not body.isActive:
        db.execute(update(IotDevice).where(IotDevice.station_id == row.id).values(
            is_active=False, credential_hash=None))
    db.commit()
    return station_out(row)


@router.get('/devices')
def devices(db: Session = Depends(get_db)):
    return [device_out(row) for row in db.scalars(select(IotDevice).order_by(IotDevice.id))]


def provision(db, row, response):
    station = resource(db, IotStation, row.station_id)
    if not station.is_active:
        raise HTTPException(409, 'La estación está suspendida.')
    secret = 'agd_' + secrets.token_urlsafe(32)
    row.credential_hash = credential_hash(secret)
    row.is_active = True
    commit(db)
    response.headers['Cache-Control'] = 'no-store'
    return {**device_out(row), 'credential': secret}


@router.post('/devices', status_code=201)
def create_device(body: DeviceCreate, response: Response, db: Session = Depends(get_db)):
    resource(db, IotStation, body.stationId)
    row = IotDevice(station_id=body.stationId, device_id=body.deviceId)
    db.add(row)
    return provision(db, row, response)


@router.post('/devices/{device_pk}/credentials')
def rotate_device(device_pk: int, response: Response, db: Session = Depends(get_db)):
    return provision(db, resource(db, IotDevice, device_pk), response)


@router.delete('/devices/{device_pk}/credentials', status_code=204)
def revoke_device(device_pk: int, db: Session = Depends(get_db)):
    row = resource(db, IotDevice, device_pk)
    row.is_active = False
    row.credential_hash = None
    db.commit()
