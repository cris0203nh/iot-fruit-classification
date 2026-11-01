from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin
from ..models import User, Role
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


def user_output(user: User):
    return {
        "id": user.id,
        "username": user.username,
        "fullName": user.full_name,
        "isActive": user.is_active,
        "roles": [role.name for role in user.roles],
    }


@router.get("")
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    users = db.scalars(
        select(User).order_by(User.id)
    ).all()

    return [user_output(user) for user in users]


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
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No se pudo registrar el usuario.",
        )

    return user_output(user)


@router.patch("/{user_id}/role")
def update_user_role(
    user_id: int,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.get(User, user_id)

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

    user.roles = [role]
    db.commit()
    db.refresh(user)

    return user_output(user)


@router.patch("/{user_id}/status")
def update_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    if user.id == current_user.id and not payload.isActive:
        raise HTTPException(
            status_code=409,
            detail="No puedes desactivar tu propia cuenta.",
        )

    user.is_active = payload.isActive
    db.commit()
    db.refresh(user)

    return user_output(user)
