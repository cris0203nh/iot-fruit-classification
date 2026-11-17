from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin
from ..models import User, Role
from ..organization_models import OrganizationMembership
from ..security import hash_password
from ..user_schemas import (
    UserCreate,
    UserRoleUpdate,
    UserStatusUpdate,
)

router = APIRouter(
    prefix="/api/users",
    tags=["gestion de usuarios"],
)


def member_roles(db: Session, user_id: int):
    return db.execute(select(Role.name, OrganizationMembership.is_active)
        .join(OrganizationMembership, OrganizationMembership.role_id == Role.id)
        .where(OrganizationMembership.organization_id == db.info["organization_id"],
               OrganizationMembership.user_id == user_id)).all()


def scoped_user(db: Session, user_id: int):
    return db.scalar(select(User).where(User.id == user_id, User.id.in_(
        select(OrganizationMembership.user_id).where(
            OrganizationMembership.organization_id == db.info["organization_id"]))))


def user_output(db: Session, user: User):
    memberships = member_roles(db, user.id)
    return {
        "id": user.id,
        "username": user.username,
        "fullName": user.full_name,
        "isActive": user.is_active and any(item.is_active for item in memberships),
        "roles": sorted(item.name for item in memberships),
    }


@router.get("")
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    users = db.scalars(
        select(User).where(User.id.in_(select(OrganizationMembership.user_id).where(
            OrganizationMembership.organization_id == db.info["organization_id"]))).order_by(User.id)
    ).all()

    return [user_output(db, user) for user in users]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    existing = db.scalar(
        select(User).where(User.username == payload.username)
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="El nombre de usuario ya existe.",
        )

    role = db.scalar(
        select(Role).where(Role.name == payload.role)
    )

    if role is None:
        raise HTTPException(
            status_code=409,
            detail="El rol solicitado no está registrado.",
        )

    user = User(
        username=payload.username,
        full_name=payload.fullName,
        password_hash=hash_password(payload.password),
        is_active=True,
        roles=[role],
    )

    db.add(user)

    try:
        db.flush()
        db.add(OrganizationMembership(organization_id=db.info["organization_id"], user_id=user.id, role_id=role.id))
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No se pudo registrar el usuario.",
        )

    return user_output(db, user)


@router.patch("/{user_id}/role")
def update_user_role(
    user_id: int,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = scoped_user(db, user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    if user.id == current_user.id and payload.role != "administrador":
        raise HTTPException(
            status_code=409,
            detail="No puedes retirar tu propio rol de administrador.",
        )

    role = db.scalar(
        select(Role).where(Role.name == payload.role)
    )

    if role is None:
        raise HTTPException(status_code=404, detail="Rol no encontrado.")

    active = any(item.is_active for item in member_roles(db, user.id))
    db.execute(delete(OrganizationMembership).where(
        OrganizationMembership.organization_id == db.info["organization_id"],
        OrganizationMembership.user_id == user.id))
    db.add(OrganizationMembership(organization_id=db.info["organization_id"],
        user_id=user.id, role_id=role.id, is_active=active))
    db.commit()
    db.refresh(user)

    return user_output(db, user)


@router.patch("/{user_id}/status")
def update_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = scoped_user(db, user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    if user.id == current_user.id and not payload.isActive:
        raise HTTPException(
            status_code=409,
            detail="No puedes desactivar tu propia cuenta.",
        )

    memberships = db.scalars(select(OrganizationMembership).where(
        OrganizationMembership.organization_id == db.info["organization_id"],
        OrganizationMembership.user_id == user.id)).all()
    for membership in memberships:
        membership.is_active = payload.isActive
    db.commit()
    db.refresh(user)

    return user_output(db, user)


@router.delete('/{user_id}/membership', status_code=204)
def revoke_membership(user_id: int, db: Session = Depends(get_db),
                      current_user: User = Depends(require_admin)):
    user = scoped_user(db, user_id)
    if user is None:
        raise HTTPException(404, 'Usuario no encontrado.')
    if user.id == current_user.id:
        raise HTTPException(409, 'No puedes revocar tu propia membresía administrativa.')
    db.execute(delete(OrganizationMembership).where(
        OrganizationMembership.organization_id == db.info['organization_id'],
        OrganizationMembership.user_id == user.id))
    db.commit()
