import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Evaluation, Lot, Role, User
from app.security import create_access_token, hash_password


class AGROP47PermissionTests(unittest.TestCase):

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

        for role_name in ["administrador", "revisor", "operador"]:
            role = Role(name=role_name)

            user = User(
                username=f"test_{role_name}",
                full_name=f"Usuario {role_name}",
                password_hash=hash_password("PruebaSegura123"),
                is_active=True,
            )

            user.roles.append(role)
            self.db.add(user)
            self.users[role_name] = user

        lot = Lot(
            code="LOTE-AGROP47",
            product="mango",
            status="open",
        )

        self.db.add(lot)
        self.db.commit()

        self.lot = lot

        self.db.refresh(lot)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def create_evaluation(self):
        evaluation = Evaluation(
            lot_id=self.lot.id,
            piece_id="PIEZA-AGROP47",
            product="mango",
            status="pending_review",
            visual_category="primera",
        )

        self.db.add(evaluation)
        self.db.commit()
        self.db.refresh(evaluation)

        return f"E-{evaluation.id:06d}"

    def headers(self, role_name):
        user = self.users[role_name]
        token = create_access_token(user.id)

        return {
            "Authorization": f"Bearer {token}"
        }

    def review(self, evaluation_id, role_name):
        return self.client.post(
            f"/api/evaluations/{evaluation_id}/reviews",
            headers=self.headers(role_name),
            json={
                "actorId": "usuario",
                "reason": "Correccion de prueba AGROP-47",
                "newValue": "segunda",
            },
        )

    def cancel(self, evaluation_id, role_name):
        return self.client.post(
            f"/api/evaluations/{evaluation_id}/cancel",
            headers=self.headers(role_name),
            json={
                "actorId": "usuario",
                "reason": "Cancelacion de prueba AGROP-47",
            },
        )

    def test_operador_no_puede_corregir(self):
        evaluation_id = self.create_evaluation()

        response = self.review(evaluation_id, "operador")

        self.assertEqual(response.status_code, 403)

    def test_operador_no_puede_cancelar(self):
        evaluation_id = self.create_evaluation()

        response = self.cancel(evaluation_id, "operador")

        self.assertEqual(response.status_code, 403)

    def test_revisor_puede_corregir(self):
        evaluation_id = self.create_evaluation()

        response = self.review(evaluation_id, "revisor")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["actorId"], "test_revisor")

    def test_revisor_no_puede_cancelar(self):
        evaluation_id = self.create_evaluation()

        response = self.cancel(evaluation_id, "revisor")

        self.assertEqual(response.status_code, 403)

    def test_administrador_puede_corregir(self):
        evaluation_id = self.create_evaluation()

        response = self.review(evaluation_id, "administrador")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["actorId"],
            "test_administrador",
        )

    def test_administrador_puede_cancelar(self):
        evaluation_id = self.create_evaluation()

        response = self.cancel(evaluation_id, "administrador")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["type"], "cancellation")

    def test_usuario_sin_token_no_puede_corregir(self):
        evaluation_id = self.create_evaluation()

        response = self.client.post(
            f"/api/evaluations/{evaluation_id}/reviews",
            json={
                "actorId": "desconocido",
                "reason": "Prueba sin autenticacion",
                "newValue": "segunda",
            },
        )

        self.assertEqual(response.status_code, 401)

    def test_usuario_sin_token_no_puede_cancelar(self):
        evaluation_id = self.create_evaluation()

        response = self.client.post(
            f"/api/evaluations/{evaluation_id}/cancel",
            json={
                "actorId": "desconocido",
                "reason": "Prueba sin autenticacion",
            },
        )

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
