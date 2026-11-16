import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Evaluation, Image, Lot, Role, User
from app.routers import evaluations as evaluations_router
from app.security import create_access_token, hash_password


class AGROP47PermissionTests(unittest.TestCase):

    def setUp(self):
        # Fixture actualizada: una revision generica exige evidencia persistida.
        # Los bytes y la ruta son sinteticos y aislados del directorio operativo.
        self.temp = tempfile.TemporaryDirectory(prefix="agrop47-permissions-")
        self.addCleanup(self.temp.cleanup)
        self.data_dir = Path(self.temp.name)
        evidence_root_patch = patch.object(evaluations_router, "DATA_DIR", self.data_dir)
        evidence_root_patch.start()
        self.addCleanup(evidence_root_patch.stop)

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
            image_count=1,
        )

        self.db.add(evaluation)
        self.db.flush()
        # No son fotografias reales ni datos tomados en campo.
        relative = f"images/agrop47-evidence-{evaluation.id}.jpg"
        evidence = self.data_dir / relative
        evidence.parent.mkdir(parents=True, exist_ok=True)
        content = b"\xff\xd8\xffAGROP47-EVIDENCIA-SINTETICA\xff\xd9"
        evidence.write_bytes(content)
        self.db.add(Image(
            evaluation_id=evaluation.id,
            view="vista-1",
            relative_path=relative,
            content_type="image/jpeg",
            size_bytes=len(content),
        ))
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

    def test_revisor_no_puede_corregir_sin_fotografia(self):
        evaluation_id = self.create_evaluation()
        # La autorizacion por rol sigue vigente, pero falta una precondicion
        # de integridad: el backend debe denegar la revision, no fingir 201.
        pk = int(evaluation_id.split("-")[1])
        (self.data_dir / f"images/agrop47-evidence-{pk}.jpg").unlink()
        response = self.review(evaluation_id, "revisor")
        self.assertEqual(response.status_code, 409)

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
