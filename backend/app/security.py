import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv
from pwdlib import PasswordHash


# Cargar variables del archivo .env del backend.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

JWT_SECRET = os.getenv("AGROSCAN_JWT_SECRET")
JWT_ALGORITHM = os.getenv("AGROSCAN_JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_MINUTES = int(
    os.getenv("AGROSCAN_ACCESS_TOKEN_MINUTES", "30")
)

if not JWT_SECRET or len(JWT_SECRET) < 32:
    raise RuntimeError("La clave JWT no está configurada correctamente.")

if JWT_ALGORITHM != "HS256":
    raise RuntimeError("El algoritmo JWT configurado no está permitido.")

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Generar hash seguro de contraseña mediante Argon2."""
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verificar una contraseña contra su hash."""
    return password_hash.verify(password, hashed_password)


def create_access_token(user_id: int) -> str:
    """Generar token JWT para un usuario autenticado."""
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
    }

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> int:
    """Validar JWT y recuperar el identificador del usuario."""
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat"]},
        )

        user_id = int(payload["sub"])

        if user_id <= 0:
            raise ValueError("Identificador inválido.")

        return user_id

    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
