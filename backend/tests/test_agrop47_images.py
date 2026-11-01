import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Role, User
from app.security import create_access_token, hash_password


class AGROP47ImagePermissionTests(unittest.TestCase):

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
                username=f"image_{name}",
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

    def upload(self, headers=None):
        return self.client.post(
            "/api/evaluations/E-000001/images",
            headers=headers,
            files={
                "file": (
                    "foto.jpg",
                    b"contenido de prueba",
                    "image/jpeg",
                )
            },
        )

    def test_revisor_no_puede_subir_imagen(self):
        response = self.upload(self.headers("revisor"))
        self.assertEqual(response.status_code, 403)

    def test_usuario_sin_token_no_puede_subir_imagen(self):
        response = self.upload()
        self.assertEqual(response.status_code, 401)

    def test_operador_supera_autorizacion_de_subida(self):
        response = self.upload(self.headers("operador"))
        self.assertEqual(response.status_code, 404)

    def test_administrador_supera_autorizacion_de_subida(self):
        response = self.upload(self.headers("administrador"))
        self.assertEqual(response.status_code, 404)

    def test_usuario_sin_token_no_puede_consultar_imagen(self):
        response = self.client.get("/api/images/I-000001")
        self.assertEqual(response.status_code, 401)

    def test_roles_autenticados_pueden_consultar_imagen(self):
        for role in ["administrador", "revisor", "operador"]:
            response = self.client.get(
                "/api/images/I-000001",
                headers=self.headers(role),
            )
            self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()