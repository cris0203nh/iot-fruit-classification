
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Evaluation, Lot, Role, User
from app.security import create_access_token, hash_password
import app.routers.images as images_router


class AGROP27MultipleViewsTests(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.client = TestClient(app)

        self.original_images_dir = images_router.IMAGES_DIR
        self.temp_dir = tempfile.TemporaryDirectory(
            dir=str(images_router.DATA_DIR)
        )
        images_router.IMAGES_DIR = Path(self.temp_dir.name)

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

        self.db.add(
            Lot(
                code="LOTE-AGROP27",
                product="mango",
                status="open",
                responsible="Operador de prueba",
            )
        )

        self.db.commit()

        for user in self.users.values():
            self.db.refresh(user)

        self.lot = self.db.scalar(
            select(Lot).where(Lot.code == "LOTE-AGROP27")
        )

        self.evaluation_id = self.create_evaluation("PIEZA-001")

    def tearDown(self):
        app.dependency_overrides.clear()

        self.db.close()
        self.engine.dispose()

        images_router.IMAGES_DIR = self.original_images_dir
        self.temp_dir.cleanup()

    def headers(self, role):
        token = create_access_token(self.users[role].id)
        return {"Authorization": f"Bearer {token}"}

    def create_evaluation(self, piece_id):
        response = self.client.post(
            "/api/evaluations",
            headers=self.headers("operador"),
            json={
                "lotId": "LOTE-AGROP27",
                "pieceId": piece_id,
            },
        )

        self.assertEqual(response.status_code, 201)

        evaluation_id = response.json()["id"]
        numeric_id = int(evaluation_id.split("-")[1])

        evaluation = self.db.get(Evaluation, numeric_id)

        # El endpoint de imágenes exige peso inicial registrado.
        evaluation.weight_pre_g = 150.0
        self.db.commit()

        return evaluation_id

    def upload(self, evaluation_id, view, headers=None):
        return self.client.post(
            f"/api/evaluations/{evaluation_id}/images",
            headers=headers,
            data={"view": view},
            files={
                "file": (
                    f"{view}.jpg",
                    b"contenido de prueba de imagen",
                    "image/jpeg",
                )
            },
        )

    def get_evaluation(self, evaluation_id):
        return self.client.get(
            f"/api/evaluations/{evaluation_id}",
            headers=self.headers("operador"),
        )

    # AGROP-27: dos vistas de una misma pieza.

    def test_dos_vistas_se_asocian_a_una_misma_evaluacion(self):
        first = self.upload(
            self.evaluation_id,
            "vista-1",
            self.headers("operador"),
        )

        second = self.upload(
            self.evaluation_id,
            "vista-2",
            self.headers("operador"),
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)

        detail = self.get_evaluation(self.evaluation_id)

        self.assertEqual(detail.status_code, 200)

        data = detail.json()

        self.assertEqual(data["id"], self.evaluation_id)
        self.assertEqual(data["pieceId"], "PIEZA-001")
        self.assertEqual(data["imageCount"], 2)

        self.assertEqual(
            [item["view"] for item in data["evidence"]],
            ["vista-1", "vista-2"],
        )

        self.assertEqual(len(data["evidence"]), 2)

    # AGROP-27: evitar mezcla entre piezas.

    def test_imagenes_de_diferentes_piezas_no_se_mezclan(self):
        second_evaluation = self.create_evaluation("PIEZA-002")

        first_upload = self.upload(
            self.evaluation_id,
            "vista-1",
            self.headers("operador"),
        )

        second_upload = self.upload(
            second_evaluation,
            "vista-1",
            self.headers("operador"),
        )

        self.assertEqual(first_upload.status_code, 201)
        self.assertEqual(second_upload.status_code, 201)

        first_detail = self.get_evaluation(self.evaluation_id)
        second_detail = self.get_evaluation(second_evaluation)

        self.assertEqual(first_detail.status_code, 200)
        self.assertEqual(second_detail.status_code, 200)

        first_data = first_detail.json()
        second_data = second_detail.json()

        self.assertEqual(first_data["pieceId"], "PIEZA-001")
        self.assertEqual(second_data["pieceId"], "PIEZA-002")

        self.assertEqual(first_data["imageCount"], 1)
        self.assertEqual(second_data["imageCount"], 1)

        self.assertNotEqual(
            first_data["evidence"][0]["id"],
            second_data["evidence"][0]["id"],
        )

        self.assertNotEqual(
            first_data["id"],
            second_data["id"],
        )

    # AGROP-27: consulta de todas las vistas.

    def test_historial_devuelve_todas_las_vistas(self):
        self.upload(
            self.evaluation_id,
            "vista-1",
            self.headers("operador"),
        )

        self.upload(
            self.evaluation_id,
            "vista-2",
            self.headers("operador"),
        )

        response = self.get_evaluation(self.evaluation_id)

        self.assertEqual(response.status_code, 200)

        evidence = response.json()["evidence"]

        self.assertEqual(len(evidence), 2)
        self.assertTrue(all(item["imageUrl"] for item in evidence))

    # AGROP-47: conservar las pruebas de permisos existentes.

    def test_revisor_no_puede_subir_imagen(self):
        response = self.upload(
            self.evaluation_id,
            "vista-1",
            self.headers("revisor"),
        )
        self.assertEqual(response.status_code, 403)

    def test_usuario_sin_token_no_puede_subir_imagen(self):
        response = self.upload(self.evaluation_id, "vista-1")
        self.assertEqual(response.status_code, 401)

    def test_operador_puede_subir_imagen(self):
        response = self.upload(
            self.evaluation_id,
            "vista-1",
            self.headers("operador"),
        )
        self.assertEqual(response.status_code, 201)

    def test_administrador_puede_subir_imagen(self):
        response = self.upload(
            self.evaluation_id,
            "vista-1",
            self.headers("administrador"),
        )
        self.assertEqual(response.status_code, 201)

    def test_usuario_sin_token_no_puede_consultar_imagen(self):
        self.upload(
            self.evaluation_id,
            "vista-1",
            self.headers("operador"),
        )

        response = self.client.get("/api/images/I-000001")
        self.assertEqual(response.status_code, 401)

    def test_roles_autenticados_pueden_consultar_imagen(self):
        uploaded = self.upload(
            self.evaluation_id,
            "vista-1",
            self.headers("operador"),
        )

        self.assertEqual(uploaded.status_code, 201)

        image_id = uploaded.json()["id"]

        for role in ["administrador", "revisor", "operador"]:
            response = self.client.get(
                f"/api/images/{image_id}",
                headers=self.headers(role),
            )

            self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
