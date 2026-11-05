import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import User
from ..login_throttle import login_throttle
from ..security import (
    create_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["autenticacion"])
# Evita distinguir usuarios existentes por la ausencia de verificación Argon2.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


@router.post("/login")
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else "unknown"
    username = form.username.strip()
    login_throttle.check(ip, username)
    user = db.scalar(
        select(User).where(User.username == username)
    )

    eligible = user is not None and user.is_active
    credential_hash = user.password_hash if eligible else _DUMMY_HASH
    valid_password = verify_password(form.password, credential_hash)
    if not eligible or not valid_password:
        login_throttle.failure(ip, username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    login_throttle.success(ip, username)
    token = create_access_token(user.id)

    return {
        "access_token": token,
        "token_type": "bearer",
    }


@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user),
):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "fullName": current_user.full_name,
        "roles": [role.name for role in current_user.roles],
    }
