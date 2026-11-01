"""AGROP-26: imágenes de muestra vinculadas a evaluación, SQLite aislado."""
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Evaluation, Lot
from app.routers import images

# PNG 1x1 válido para demostrar transporte y vinculación (no legibilidad).
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAFElEQVR4nGM8ISfHAANMDEgANwcANHYBDK9qubUAAAAASUVORK5CYII="
)


class CaptureAGROP26Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = create_engine(f"sqlite:///{(self.root / 'test.db').as_posix()}")
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        with Session() as db:
            lot = Lot(code="DEMO-AGROP26", product="tomate", status="open", responsible="")
            db.add(lot)
            db.flush()
            ev = Evaluation(lot_id=lot.id, piece_id="DEMO-P-01", product="tomate", status="processing")
            db.add(ev)
            db.commit()
            db.refresh(ev)
            self.eval_id = f"E-{ev.id:06d}"

        def test_session():
            with Session() as db:
                yield db

        app.dependency_overrides[get_db] = test_session
        self.data_dir = patch.object(images, "DATA_DIR", self.root)
        self.image_dir = patch.object(images, "IMAGES_DIR", self.root / "images")
        self.data_dir.start()
        self.image_dir.start()
        (self.root / "images").mkdir()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.image_dir.stop()
        self.data_dir.stop()
        self.engine.dispose()
        self.tmp.cleanup()

    def upload(self, filename="toma.png", content=PNG, mime="image/png"):
        return self.client.post(
            f"/api/evaluations/{self.eval_id}/images",
            data={"view": "vista-1"},
            files={"file": (filename, content, mime)},
        )

    def test_subida_sin_peso_previo_se_vincula_a_la_evaluacion(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertTrue(body["id"].startswith("I-"))
        self.assertEqual(body["view"], "vista-1")
        self.assertEqual(body["imageUrl"], f'/api/images/{body["id"]}')
        image = self.client.get(body["imageUrl"])
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.content, PNG)
        detail = self.client.get(f"/api/evaluations/{self.eval_id}").json()
        self.assertEqual(detail["id"], self.eval_id)
        self.assertEqual(detail["imageCount"], 1)
        self.assertEqual(detail["evidence"], [body])
        self.assertEqual(detail["status"], "processing")
        self.assertIsNone(detail["weightGrams"])

    def test_rechazo_de_evaluacion_ajena_o_inexistente(self):
        response = self.client.post(
            "/api/evaluations/E-999999/images",
            files={"file": ("toma.png", PNG, "image/png")},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(list(self.root.rglob('*.png')), [])

    def test_rechaza_contenido_disfrazado_y_archivo_vacio(self):
        for name, content, mime in [
            ("falsa.png", b"texto plano", "image/png"),
            ("falsa.jpg", b"texto plano", "image/jpeg"),
            ("vacia.png", b"", "image/png"),
            ("doc.pdf", b"%PDF", "application/pdf"),
        ]:
            with self.subTest(name=name):
                response = self.upload(name, content, mime)
                self.assertEqual(response.status_code, 422)
        detail = self.client.get(f"/api/evaluations/{self.eval_id}").json()
        self.assertEqual(detail["imageCount"], 0)

    def test_rechaza_archivo_mayor_a_cinco_megas(self):
        response = self.upload("grande.png", PNG + b"X" * (5 * 1024 * 1024), "image/png")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get(f"/api/evaluations/{self.eval_id}").json()["imageCount"], 0)

    def test_evaluacion_cerrada_no_admite_imagen(self):
        Session = sessionmaker(bind=self.engine)
        with Session() as db:
            ev = db.get(Evaluation, int(self.eval_id[2:]))
            ev.status = "cancelled"
            db.commit()
        self.assertEqual(self.upload().status_code, 409)


if __name__ == "__main__":
    unittest.main()
