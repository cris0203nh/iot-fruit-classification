from getpass import getpass
from sqlalchemy import select
from backend.app.database import SessionLocal
from backend.app.models import User, Role
from backend.app.security import hash_password

db = SessionLocal()

try:
    print("\n=== CREAR USUARIO REVISOR AGROSCAN ===")

    username = input("Nombre de usuario: ").strip().lower()
    full_name = input("Nombre completo: ").strip()
    password = getpass("Contraseña (mínimo 12 caracteres): ")
    confirmation = getpass("Confirmar contraseña: ")

    if len(username) < 3 or not full_name:
        raise ValueError("Datos incompletos.")

    if len(password) < 12:
        raise ValueError("La contraseña debe tener mínimo 12 caracteres.")

    if password != confirmation:
        raise ValueError("Las contraseñas no coinciden.")

    if db.scalar(select(User).where(User.username == username)):
        raise ValueError("El usuario ya existe.")

    role = db.scalar(select(Role).where(Role.name == "revisor"))

    if role is None:
        raise ValueError("El rol revisor no está registrado.")

    user = User(
        username=username,
        full_name=full_name,
        password_hash=hash_password(password),
        is_active=True,
        roles=[role],
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    print("\n=== USUARIO CREADO CORRECTAMENTE ===")
    print("ID:", user.id)
    print("Usuario:", user.username)
    print("Nombre:", user.full_name)
    print("Rol: revisor")
    print("Estado: activo")

except Exception as error:
    db.rollback()
    print("\nERROR:", error)

finally:
    db.close()
