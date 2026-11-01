import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Role, User
from app.security import create_access_token, hash_password


class AGROP47UserManagementTests(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.client = TestClient(app)

        def override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = override_get_db

        self.users = {}

        for name in ["administrador", "revisor", "operador"]:
            role = Role(name=name)
            user = User(
                username=f"test_{name}",
                full_name=f"Usuario {name}",
                password_hash=hash_password("PruebaSegura123"),
                is_active=True,
                roles=[role],
            )
            self.db.add(user)
            self.users[name] = user

        self.db.commit()

        for user in self.users.values():
            self.db.refresh(user)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def headers(self, role):
        token = create_access_token(self.users[role].id)
        return {"Authorization": f"Bearer {token}"}

    def test_administrador_puede_listar_usuarios(self):
        response = self.client.get(
            "/api/users",
            headers=self.headers("administrador"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 3)

    def test_administrador_puede_crear_usuario(self):
        response = self.client.post(
            "/api/users",
            headers=self.headers("administrador"),
            json={
                "username": "nuevo_usuario",
                "fullName": "Nuevo Usuario",
                "password": "ClaveSegura12345",
                "role": "operador",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["roles"], ["operador"])

    def test_administrador_puede_cambiar_rol(self):
        user_id = self.users["operador"].id

        response = self.client.patch(
            f"/api/users/{user_id}/role",
            headers=self.headers("administrador"),
            json={"role": "revisor"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["roles"], ["revisor"])

    def test_administrador_puede_desactivar_usuario(self):
        user_id = self.users["operador"].id

        response = self.client.patch(
            f"/api/users/{user_id}/status",
            headers=self.headers("administrador"),
            json={"isActive": False},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["isActive"])

    def test_operador_y_revisor_no_pueden_administrar_usuarios(self):
        user_id = self.users["operador"].id

        for role in ["operador", "revisor"]:
            headers = self.headers(role)

            responses = [
                self.client.get("/api/users", headers=headers),
                self.client.post(
                    "/api/users",
                    headers=headers,
                    json={
                        "username": "otro_usuario",
                        "fullName": "Otro Usuario",
                        "password": "ClaveSegura12345",
                        "role": "operador",
                    },
                ),
                self.client.patch(
                    f"/api/users/{user_id}/role",
                    headers=headers,
                    json={"role": "revisor"},
                ),
                self.client.patch(
                    f"/api/users/{user_id}/status",
                    headers=headers,
                    json={"isActive": False},
                ),
            ]

            for response in responses:
                self.assertEqual(response.status_code, 403)

    def test_usuario_sin_token_no_puede_administrar_usuarios(self):
        user_id = self.users["operador"].id

        responses = [
            self.client.get("/api/users"),
            self.client.post(
                "/api/users",
                json={
                    "username": "sin_token",
                    "fullName": "Sin Token",
                    "password": "ClaveSegura12345",
                    "role": "operador",
                },
            ),
            self.client.patch(
                f"/api/users/{user_id}/role",
                json={"role": "revisor"},
            ),
            self.client.patch(
                f"/api/users/{user_id}/status",
                json={"isActive": False},
            ),
        ]

        for response in responses:
            self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
