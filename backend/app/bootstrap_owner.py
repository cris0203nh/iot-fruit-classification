"""Inicialización local explícita del primer propietario; sin registro HTTP."""
import argparse
import sqlite3
from contextlib import closing
from getpass import GetPassWarning, getpass
import warnings
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .database import SessionLocal
from .models import User
from .platform_models import PlatformOwner
from .security import hash_password


def ready_for_initialization(db):
    """Comprueba la base existente sin crear archivos ni ejecutar migraciones."""
    path = Path(db.get_bind().url.database).resolve()
    if not path.is_file():
        print('No existe la base configurada. Inicialización cancelada.')
        return False
    try:
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'users', 'platform_owner'}.issubset(tables):
                print('Faltan migraciones de SaaS-04. Inicialización cancelada; no se modificó la base.')
                return False
            if connection.execute('SELECT 1 FROM platform_owner LIMIT 1').fetchone():
                print('El propietario ya fue inicializado; no se reemplazará.')
                return False
    except sqlite3.Error:
        print('No fue posible verificar la base. Inicialización cancelada.')
        return False
    return True


def assign_first_owner(db, user_id: int):
    # Serializa inicializaciones simultáneas y nunca reemplaza al propietario.
    db.connection().exec_driver_sql('BEGIN IMMEDIATE')
    if db.get(PlatformOwner, 1) is not None:
        raise ValueError('El propietario ya fue inicializado; no se reemplazará.')
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise ValueError('Selecciona explícitamente un usuario existente y activo.')
    db.add(PlatformOwner(id=1, user_id=user.id))
    db.commit()
    return user.id, user.username


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--user-id', type=int, help='ID del propietario seleccionado explícitamente')
    modes.add_argument('--create-user', action='store_true', help='Crear cuenta privada sin rol empresarial')
    modes.add_argument('--check', action='store_true', help='Comprobar requisitos en modo de solo lectura')
    args = parser.parse_args(argv)
    with SessionLocal() as db:
        if not ready_for_initialization(db):
            return 1
        if args.check:
            print('Esquema listo; asignación inicial del propietario pendiente.')
            return 0
        try:
            if args.create_user:
                if db.get(PlatformOwner, 1) is not None:
                    raise ValueError('El propietario ya fue inicializado.')
                # No mantener un bloqueo de escritura mientras se ingresan credenciales.
                db.rollback()
                username = input('Usuario del propietario: ').strip().lower()
                full_name = input('Nombre completo: ').strip()
                with warnings.catch_warnings():
                    # Cancelar antes de que getpass recurra a entrada visible.
                    warnings.simplefilter('error', GetPassWarning)
                    password = getpass('Contraseña (12 a 128 caracteres): ')
                    confirmation = getpass('Confirmar contraseña: ')
                if not 3 <= len(username) <= 64 or not 2 <= len(full_name) <= 120:
                    raise ValueError('Usuario o nombre inválido.')
                if not 12 <= len(password) <= 128 or password != confirmation:
                    raise ValueError('Contraseña inválida o confirmación diferente.')
                hashed = hash_password(password)
                db.connection().exec_driver_sql('BEGIN IMMEDIATE')
                if db.get(PlatformOwner, 1) is not None:
                    raise ValueError('El propietario ya fue inicializado.')
                if db.scalar(select(User.id).where(User.username == username)) is not None:
                    raise ValueError('El usuario ya existe; elige un nombre nuevo y exclusivo para el propietario.')
                user = User(username=username, full_name=full_name, password_hash=hashed, is_active=True)
                db.add(user)
                db.flush()
                db.add(PlatformOwner(id=1, user_id=user.id))
                db.commit()
                owner_id, owner_name = user.id, user.username
            else:
                owner_id, owner_name = assign_first_owner(db, args.user_id)
            print(f'Propietario inicializado: ID {owner_id}, usuario {owner_name}.')
            return 0
        except GetPassWarning:
            db.rollback()
            print('Usa una consola interactiva que permita ocultar la contraseña. No se creó la cuenta.')
            return 1
        except (ValueError, IntegrityError) as exc:
            db.rollback()
            message = str(exc) if isinstance(exc, ValueError) else 'Conflicto de inicialización; no se asignó el propietario.'
            print(message)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
