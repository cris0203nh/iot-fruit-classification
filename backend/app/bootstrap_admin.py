from getpass import getpass

from sqlalchemy import select, func

from .database import SessionLocal
from .models import User, Role
from .security import hash_password


ROLES = ["administrador", "revisor", "operador"]


def main():
    db = SessionLocal()

    try:
        if db.scalar(select(func.count()).select_from(User)) > 0:
            print("Ya existen usuarios. Inicialización cancelada.")
            return

        # Registrar los tres roles.
        roles = {}

        for name in ROLES:
            role = db.scalar(
                select(Role).where(Role.name == name)
            )

            if role is None:
                role = Role(name=name)
                db.add(role)

            roles[name] = role

        db.flush()

        print("\n===== ADMINISTRADOR INICIAL =====")

        username = input("Usuario: ").strip().lower()
        full_name = input("Nombre completo: ").strip()

        if not username or not full_name:
            raise ValueError("Los datos del administrador son obligatorios.")

        password = getpass("Contraseña (mínimo 12 caracteres): ")
        confirmation = getpass("Confirmar contraseña: ")

        if len(password) < 12:
            raise ValueError("La contraseña debe tener al menos 12 caracteres.")

        if password != confirmation:
            raise ValueError("Las contraseñas no coinciden.")

        admin = User(
            username=username,
            full_name=full_name,
            password_hash=hash_password(password),
            is_active=True,
            roles=[roles["administrador"]],
        )

        db.add(admin)
        db.commit()

        print("\nAdministrador creado correctamente.")
        print("Usuario:", username)
        print("Roles disponibles:", ", ".join(ROLES))

    except Exception as error:
        db.rollback()
        print("\nNo se pudo completar la inicialización:", error)

    finally:
        db.close()


if __name__ == "__main__":
    main()
