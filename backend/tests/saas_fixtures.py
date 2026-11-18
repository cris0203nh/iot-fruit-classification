"""Datos empresariales sintéticos explícitos para fixtures históricas, sin overrides de permisos."""
import hashlib

from sqlalchemy import select

from app.iot_models import IotDevice, IotStation
from app.models import Role, User
from app.organization_models import Organization, OrganizationMembership


def seed_company(db, organization_id=1):
    previous = db.info.get('organization_id')
    if previous is not None and previous != organization_id:
        raise ValueError('La fixture no puede cambiar de empresa dentro de la sesión.')
    db.info['organization_id'] = organization_id
    organization = Organization(id=organization_id, name='Synthetic fixture company')
    db.add(organization)
    db.flush()
    return organization


def seed_memberships(db, *users):
    """Conservar exactamente los roles declarados por cada prueba."""
    db.flush()
    for user in users:
        for role in user.roles:
            db.add(OrganizationMembership(organization_id=db.info['organization_id'],
                                          user_id=user.id, role_id=role.id))
    db.flush()


def seed_actor(db, role='operador'):
    business_role = Role(name=role)
    user = User(username='synthetic_'+role, full_name='Synthetic '+role,
                password_hash='SYNTHETIC-NO-PASSWORD-LOGIN', is_active=True, roles=[business_role])
    db.add(user)
    seed_memberships(db, user)
    return user


def seed_scale(db, device_id):
    """Registro para mediciones sintéticas insertadas en ORM, no un bypass de autenticación HTTP."""
    station = db.scalar(select(IotStation).where(IotStation.code == 'synthetic-station'))
    if station is None:
        station = IotStation(code='synthetic-station', name='Synthetic station')
        db.add(station)
        db.flush()
    device = IotDevice(station_id=station.id, device_id=device_id, is_active=True,
                       credential_hash=hashlib.sha256(('synthetic-credential:'+device_id).encode()).hexdigest())
    db.add(device)
    db.flush()
    return device
