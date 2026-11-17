import re

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import select

from .database import get_db
from .models import User, Role, Evaluation, Image, Lot
from .organization_models import Organization, OrganizationMembership
from .platform_models import PlatformOwner
from .security import decode_access_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
BUSINESS_ROLES = ('administrador', 'operador', 'revisor')


def get_authenticated_identity(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:

    user_id = decode_access_token(token)
    user = db.get(User, user_id)

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inexistente o inactivo.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_current_user(
    user: User = Depends(get_authenticated_identity),
    db: Session = Depends(get_db),
    organization_header: str | None = Header(default=None, alias='X-Organization-ID'),
) -> User:
    memberships = db.execute(
        select(OrganizationMembership.organization_id, Role.name, Organization.name.label('organization_name'))
        .join(Role, OrganizationMembership.role_id == Role.id)
        .join(Organization, OrganizationMembership.organization_id == Organization.id)
        .where(OrganizationMembership.user_id == user.id,
               OrganizationMembership.is_active.is_(True), Organization.is_active.is_(True),
               Role.name.in_(BUSINESS_ROLES))
    ).all()
    allowed = {row.organization_id for row in memberships}
    if organization_header is None:
        if len(allowed) != 1:
            raise HTTPException(403 if not allowed else 409,
                                'Selecciona una organización con membresía activa.')
        organization_id = next(iter(allowed))
    else:
        try:
            organization_id = int(organization_header)
        except ValueError:
            raise HTTPException(400, 'Organización inválida.') from None
        if organization_id not in allowed:
            raise HTTPException(403, 'No tienes acceso a esa organización.')
    previous = db.info.get('organization_id')
    if previous is not None and previous != organization_id:
        raise HTTPException(403, 'No se permite cambiar organización en una solicitud.')
    db.info['organization_id'] = organization_id
    db.info['organization_roles'] = {row.name for row in memberships if row.organization_id == organization_id}
    organizations = {}
    for row in memberships:
        organizations.setdefault(row.organization_id, {
            'id': row.organization_id, 'name': row.organization_name, 'roles': []})['roles'].append(row.name)
    db.info['organizations'] = [organizations[key] for key in sorted(organizations)]
    return user


def require_superadmin(user: User = Depends(get_authenticated_identity), db: Session = Depends(get_db)) -> User:
    # El JWT y las membresías nunca conceden autoridad global.
    owner = db.get(PlatformOwner, 1, populate_existing=True)
    if owner is None or owner.user_id != user.id:
        raise HTTPException(403, 'Se requiere el propietario de la plataforma.')
    return user


def require_roles(*allowed_roles: str):

    def role_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:

        user_roles = db.info['organization_roles']

        if not user_roles.intersection(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para realizar esta operación.",
            )

        return current_user

    return role_checker


require_admin = require_roles("administrador")
require_reviewer = require_roles("administrador", "revisor")
require_operator = require_roles("administrador", "operador")

require_authenticated = require_roles(
    "administrador",
    "revisor",
    "operador",
)


def block_global_operations():
    raise HTTPException(503, 'Respaldo/restauración global HTTP deshabilitados. Usa mantenimiento privado o exportación empresarial autorizada.')


def require_operational_context(request: Request,
        current_user: User = Depends(require_authenticated), db: Session = Depends(get_db)):
    """Autoriza IDs de ruta antes de validar cuerpos o ejecutar inferencias."""
    resources = {}
    for parameter, model, pattern in (
        ('lot_id', Lot, r'(\d+)'),
        ('evaluation_id', Evaluation, r'E-(\d{1,9})'),
        ('image_id', Image, r'I-(\d{1,9})'),
    ):
        value = request.path_params.get(parameter)
        if value is None:
            continue
        match = re.fullmatch(pattern, str(value))
        item = db.get(model, int(match.group(1))) if match else None
        if item is None:
            raise HTTPException(404, 'Recurso no encontrado.')
        resources[parameter] = item
    if 'image_id' in resources and 'evaluation_id' in resources:
        if resources['image_id'].evaluation_id != resources['evaluation_id'].id:
            raise HTTPException(404, 'Recurso no encontrado.')
    return current_user
