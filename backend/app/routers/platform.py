"""Administración global, exclusiva del propietario de la plataforma."""
from fastapi import APIRouter, Depends, HTTPException
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import BUSINESS_ROLES, require_superadmin
from ..models import Evaluation, Role, User
from ..organization_models import Organization, OrganizationMembership
from ..user_schemas import UserCreate, UserStatusUpdate
from ..security import hash_password


def platform_context(user: User = Depends(require_superadmin), db: Session = Depends(get_db)):
    # Este permiso solo se establece después de validar al propietario vigente.
    if db.info.get('organization_id') is not None:
        raise HTTPException(403, 'La administración de plataforma requiere un contexto independiente.')
    db.info['platform_authorized'] = True
    return user


router = APIRouter(prefix='/api/platform', tags=['administracion-saas'],
                   dependencies=[Depends(platform_context)])


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=2, max_length=120)

    @field_validator('name')
    @classmethod
    def normalize_name(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError('Indica el nombre de la empresa.')
        return value


class AdministratorCreate(UserCreate):
    role: Literal['administrador'] = 'administrador'


def administrator_role(db):
    roles = {role.name: role for role in db.scalars(select(Role).where(Role.name.in_(BUSINESS_ROLES)))}
    for name in BUSINESS_ROLES:
        if name not in roles:
            roles[name] = Role(name=name)
            db.add(roles[name])
    db.flush()
    return roles['administrador']


def organization_or_404(db, organization_id):
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(404, 'Empresa no encontrada.')
    return organization


def organization_output(organization, users=0, evaluations=0):
    return {'id': organization.id, 'name': organization.name, 'isActive': organization.is_active,
            'userCount': users, 'evaluationCount': evaluations}


@router.get('/me')
def platform_me(user: User = Depends(require_superadmin)):
    return {'id': user.id, 'username': user.username, 'fullName': user.full_name, 'isSuperadmin': True}


@router.get('/metrics')
def platform_metrics(db: Session = Depends(get_db)):
    return {
        'organizations': db.scalar(select(func.count(Organization.id))),
        'activeOrganizations': db.scalar(select(func.count(Organization.id)).where(Organization.is_active.is_(True))),
        'users': db.scalar(select(func.count(User.id))),
        'activeUsers': db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))),
        'evaluations': db.scalar(select(func.count(Evaluation.id))),
    }


@router.get('/organizations')
def list_organizations(db: Session = Depends(get_db)):
    members = select(OrganizationMembership.organization_id,
        func.count(func.distinct(OrganizationMembership.user_id)).label('users')).group_by(
            OrganizationMembership.organization_id).subquery()
    evaluations = select(Evaluation.organization_id, func.count(Evaluation.id).label('evaluations')).group_by(
        Evaluation.organization_id).subquery()
    rows = db.execute(select(Organization, func.coalesce(members.c.users, 0),
        func.coalesce(evaluations.c.evaluations, 0))
        .outerjoin(members, members.c.organization_id == Organization.id)
        .outerjoin(evaluations, evaluations.c.organization_id == Organization.id).order_by(Organization.id)).all()
    return [organization_output(organization, users, count) for organization, users, count in rows]


@router.post('/organizations', status_code=201)
def create_organization(body: OrganizationCreate, db: Session = Depends(get_db)):
    # Serializa la comprobación de nombres y el alta sin cambiar el esquema histórico.
    db.connection().exec_driver_sql('BEGIN IMMEDIATE')
    if db.scalar(select(Organization.id).where(func.lower(Organization.name) == func.lower(body.name))) is not None:
        raise HTTPException(409, 'Ya existe una empresa con ese nombre.')
    organization = Organization(name=body.name)
    db.add(organization)
    db.commit()
    return organization_output(organization)


@router.patch('/organizations/{organization_id}/status')
def update_organization_status(organization_id: int, body: UserStatusUpdate, db: Session = Depends(get_db)):
    organization = organization_or_404(db, organization_id)
    organization.is_active = body.isActive
    db.commit()
    return {'id': organization.id, 'name': organization.name, 'isActive': organization.is_active}


@router.get('/users')
def platform_users(db: Session = Depends(get_db)):
    return [{'id': user.id, 'username': user.username, 'fullName': user.full_name, 'isActive': user.is_active}
            for user in db.scalars(select(User).order_by(User.id))]


@router.get('/organizations/{organization_id}/administrators')
def list_administrators(organization_id: int, db: Session = Depends(get_db)):
    organization_or_404(db, organization_id)
    rows = db.execute(select(User, OrganizationMembership.is_active)
        .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
        .join(Role, OrganizationMembership.role_id == Role.id)
        .where(OrganizationMembership.organization_id == organization_id, Role.name == 'administrador')
        .order_by(User.id)).all()
    return [{'id': user.id, 'username': user.username, 'fullName': user.full_name,
             'isActive': user.is_active and active} for user, active in rows]


@router.put('/organizations/{organization_id}/administrators/{user_id}')
def designate_administrator(organization_id: int, user_id: int, db: Session = Depends(get_db)):
    # Una única transacción evita altas duplicadas y carreras con suspensiones.
    db.connection().exec_driver_sql('BEGIN IMMEDIATE')
    organization = organization_or_404(db, organization_id)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, 'Usuario no encontrado.')
    if not organization.is_active or not user.is_active:
        raise HTTPException(409, 'La empresa y el usuario deben estar activos.')
    role_id = administrator_role(db).id
    membership = db.get(OrganizationMembership, (organization_id, user_id, role_id))
    if membership is None:
        db.add(OrganizationMembership(organization_id=organization_id, user_id=user_id, role_id=role_id))
    else:
        membership.is_active = True
    db.commit()
    return {'organizationId': organization_id, 'userId': user_id, 'role': 'administrador', 'isActive': True}


@router.post('/organizations/{organization_id}/administrators', status_code=201)
def create_administrator(organization_id: int, body: AdministratorCreate, db: Session = Depends(get_db)):
    hashed = hash_password(body.password)
    db.connection().exec_driver_sql('BEGIN IMMEDIATE')
    organization = organization_or_404(db, organization_id)
    if not organization.is_active:
        raise HTTPException(409, 'Activa la empresa antes de registrar su administrador.')
    if db.scalar(select(User.id).where(User.username == body.username)) is not None:
        raise HTTPException(409, 'Ese usuario ya existe. Selecciónalo como usuario registrado.')
    role = administrator_role(db)
    user = User(username=body.username, full_name=body.fullName, password_hash=hashed,
                is_active=True, roles=[role])
    db.add(user)
    db.flush()
    db.add(OrganizationMembership(organization_id=organization.id, user_id=user.id, role_id=role.id))
    db.commit()
    return {'id': user.id, 'username': user.username, 'fullName': user.full_name, 'isActive': user.is_active}


@router.delete('/organizations/{organization_id}/administrators/{user_id}', status_code=204)
def remove_administrator(organization_id: int, user_id: int, db: Session = Depends(get_db)):
    organization_or_404(db, organization_id)
    role_id = db.scalar(select(Role.id).where(Role.name == 'administrador'))
    result = db.execute(delete(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.user_id == user_id, OrganizationMembership.role_id == role_id))
    if not result.rowcount:
        raise HTTPException(404, 'Asignación administrativa no encontrada.')
    db.commit()
