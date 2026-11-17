from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import BUSINESS_ROLES, get_authenticated_identity, get_current_user
from ..platform_models import PlatformOwner
from ..models import User, Role
from ..organization_models import Organization, OrganizationMembership
from ..security import (
    create_access_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["autenticacion"])


@router.post("/login")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(User.username == form.username)
    )

    if (
        user is None
        or not user.is_active
        or not verify_password(form.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user.id)
    owner = db.get(PlatformOwner, 1)

    return {
        "access_token": token,
        "token_type": "bearer",
        "is_superadmin": owner is not None and owner.user_id == user.id,
    }


@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    owner = db.get(PlatformOwner, 1)
    return {
        "id": current_user.id,
        "username": current_user.username,
        "fullName": current_user.full_name,
        "roles": sorted(db.info['organization_roles']),
        "organizationId": db.info['organization_id'],
        "organizations": db.info['organizations'],
        "isSuperadmin": owner is not None and owner.user_id == current_user.id,
    }


@router.get('/organizations')
def my_organizations(user: User = Depends(get_authenticated_identity), db: Session = Depends(get_db)):
    rows = db.execute(select(Organization.id, Organization.name, Role.name.label('role'))
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .join(Role, OrganizationMembership.role_id == Role.id)
        .where(OrganizationMembership.user_id == user.id,
               OrganizationMembership.is_active.is_(True), Organization.is_active.is_(True),
               Role.name.in_(BUSINESS_ROLES))
        .order_by(Organization.id, Role.name)).all()
    result = {}
    for row in rows:
        result.setdefault(row.id, {'id': row.id, 'name': row.name, 'roles': []})['roles'].append(row.role)
    return list(result.values())
