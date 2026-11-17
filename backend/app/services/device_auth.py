"""Credenciales opacas de dispositivo, separadas de JWT y membresías humanas."""
import hashlib
import re

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ..database import get_db
from ..iot_models import IotDevice, IotStation
from ..organization_models import Organization


def credential_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode('ascii')).hexdigest()


def require_iot_schema(db: Session = Depends(get_db)):
    # El código puede desplegarse antes del mantenimiento: seguir cerrado con
    # 503 hasta que estén disponibles las nuevas relaciones empresariales.
    try:
        db.connection().exec_driver_sql('SELECT id, organization_id, station_id, device_id, credential_hash, is_active FROM iot_devices LIMIT 0')
        db.connection().exec_driver_sql('SELECT id, organization_id, is_active FROM iot_stations LIMIT 0')
    except OperationalError:
        raise HTTPException(503, 'IoT no disponible; verifica la migración s007iot y el acceso a SQLite.') from None


def begin_device_write(db):
    try:
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
    except OperationalError:
        raise HTTPException(503, 'SQLite ocupado; reintenta la misma operación.') from None


def authenticated_device(authorization: str | None = Header(default=None),
                         organization_header: str | None = Header(default=None, alias='X-Organization-ID'),
                         db: Session = Depends(get_db)) -> IotDevice:
    if not authorization or not re.fullmatch(r'Bearer agd_[A-Za-z0-9_-]{43}', authorization):
        raise HTTPException(401, 'Se requiere una credencial individual de dispositivo.')
    if organization_header is not None:
        raise HTTPException(400, 'La empresa se obtiene de la identidad del dispositivo.')
    # Serializa autenticación/escritura con revocación, incluso entre procesos.
    begin_device_write(db)
    devices, stations, organizations = IotDevice.__table__, IotStation.__table__, Organization.__table__
    # Única consulta de capacidad previa al contexto; secreto aleatorio de 256 bits.
    row = db.execute(select(devices.c.id, devices.c.organization_id).select_from(
        devices.join(stations, (devices.c.station_id == stations.c.id) &
                     (devices.c.organization_id == stations.c.organization_id))
        .join(organizations, organizations.c.id == devices.c.organization_id)).where(
            devices.c.credential_hash == credential_hash(authorization[7:]), devices.c.is_active.is_(True),
            stations.c.is_active.is_(True), organizations.c.is_active.is_(True))).first()
    if row is None:
        raise HTTPException(401, 'Dispositivo no autorizado o revocado.')
    db.info['organization_id'] = row.organization_id
    return db.get(IotDevice, row.id)


def active_measurements(query):
    """No reutilizar lecturas recientes de dispositivos o estaciones suspendidos."""
    from ..models import Measurement
    return query.join(IotDevice, (IotDevice.organization_id == Measurement.organization_id) &
                      (IotDevice.device_id == Measurement.device_id)).join(IotStation,
                      (IotStation.id == IotDevice.station_id) &
                      (IotStation.organization_id == IotDevice.organization_id)).where(
                          IotDevice.is_active.is_(True), IotStation.is_active.is_(True))
