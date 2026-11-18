
"""AGROP-52: recuperación de cámara y almacenamiento."""
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from saas_fixtures import seed_company, seed_actor
from app.security import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models import Evaluation, Image, Lot
from app.routers import images, evaluations


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAFElEQVR4nGM8ISfHAANMDEgANwcANHYBDK9qubUAAAAASUVORK5CYII="
)


class AGROP52ImageRecoveryTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="agrop52-")
        self.addCleanup(self.tmp.cleanup)

        self.root = Path(self.tmp.name)

        self.engine = create_engine(
            f"sqlite:///{(self.root / 'test.db').as_posix()}"
        )
        self.addCleanup(self.engine.dispose)

        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, info={"organization_id": 1})

        with self.Session() as db:
            seed_company(db)
            actor = seed_actor(db)
            self.auth_headers = {"Authorization": "Bearer "+create_access_token(actor.id)}
            lot = Lot(
                code="LOTE-AGROP52-IMG",
                product="mango",
                status="open",
                responsible="AGROP52",
            )
            db.add(lot)
            db.flush()

            evaluation = Evaluation(
                lot_id=lot.id,
                piece_id="PIEZA-AGROP52-001",
                product="mango",
                status="processing",
            )
            db.add(evaluation)
            db.commit()
            db.refresh(evaluation)

            self.evaluation_pk = evaluation.id
            self.eval_id = f"E-{evaluation.id:06d}"

        def isolated_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = isolated_db
        self.addCleanup(
            lambda: app.dependency_overrides.pop(get_db, None)
        )

        self.data_patch = patch.object(
            images, "DATA_DIR", self.root
        )
        self.images_patch = patch.object(
            images, "IMAGES_DIR", self.root / "images"
        )

        self.data_patch.start()
        self.images_patch.start()

        self.addCleanup(self.images_patch.stop)
        self.addCleanup(self.data_patch.stop)

        (self.root / "images").mkdir()

        self.client = TestClient(app, headers=self.auth_headers)
        self.addCleanup(self.client.close)

        self.idempotency_key = "c" * 64

    def upload(self, content=PNG, filename="captura.png"):
        return self.client.post(
            f"/api/evaluations/{self.eval_id}/images",
            data={"view": "vista-1"},
            files={
                "file": (filename, content, "image/png")
            },
            headers={
                "Idempotency-Key": self.idempotency_key
            },
        )

    def state(self):
        with self.Session() as db:
            evaluation = db.get(Evaluation, self.evaluation_pk)

            images_saved = db.scalars(
                select(Image).where(
                    Image.evaluation_id == self.evaluation_pk
                )
            ).all()

            return {
                "evaluation_id": evaluation.id,
                "image_count": evaluation.image_count,
                "images": images_saved,
            }

    def test_captura_invalida_y_reintento_conserva_evaluacion(self):
        original_id = self.evaluation_pk

        failed = self.upload(
            content=b"captura invalida",
            filename="captura.png",
        )

        self.assertEqual(failed.status_code, 422)

        after_failure = self.state()

        self.assertEqual(after_failure["evaluation_id"], original_id)
        self.assertEqual(after_failure["image_count"], 0)
        self.assertEqual(len(after_failure["images"]), 0)

        successful = self.upload()

        self.assertEqual(successful.status_code, 201, successful.text)

        body = successful.json()

        after_retry = self.state()

        self.assertEqual(after_retry["evaluation_id"], original_id)
        self.assertEqual(after_retry["image_count"], 1)
        self.assertEqual(len(after_retry["images"]), 1)

        self.assertEqual(
            after_retry["images"][0].evaluation_id,
            original_id,
        )

        downloaded = self.client.get(body["imageUrl"])

        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, PNG)

    def test_fallo_disco_y_reintento_guarda_en_misma_evaluacion(self):
        original_id = self.evaluation_pk

        with patch(
            "app.routers.images.os.replace",
            side_effect=OSError("Fallo simulado de almacenamiento"),
        ):
            failed = self.upload()

        self.assertEqual(failed.status_code, 500)

        after_failure = self.state()

        self.assertEqual(after_failure["evaluation_id"], original_id)
        self.assertEqual(after_failure["image_count"], 0)
        self.assertEqual(len(after_failure["images"]), 0)

        remaining_files = [
            path
            for path in (self.root / "images").rglob("*")
            if path.is_file()
        ]

        self.assertEqual(remaining_files, [])

        successful = self.upload()

        self.assertEqual(successful.status_code, 201, successful.text)

        body = successful.json()

        after_retry = self.state()

        self.assertEqual(after_retry["evaluation_id"], original_id)
        self.assertEqual(after_retry["image_count"], 1)
        self.assertEqual(len(after_retry["images"]), 1)

        self.assertEqual(
            after_retry["images"][0].evaluation_id,
            original_id,
        )

        downloaded = self.client.get(body["imageUrl"])

        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, PNG)


if __name__ == "__main__":
    unittest.main()
