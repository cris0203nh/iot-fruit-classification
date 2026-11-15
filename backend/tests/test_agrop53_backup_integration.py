
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Lot, Piece, Evaluation, Image
from app.services import backup_service


class AGROP53RealIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

        self.data_dir = self.root / "data"
        self.db_path = self.data_dir / "agroscan.db"
        self.images_dir = self.data_dir / "images"
        self.backup_dir = self.data_dir / "backups"

        self.images_dir.mkdir(parents=True)
        self.backup_dir.mkdir(parents=True)

        # Base de datos temporal con los modelos reales de AgroScan.
        self.engine = create_engine(
            f"sqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)

        self.SessionLocal = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )

        # Redirigir el servicio a los archivos temporales.
        self.patches = [
            patch.object(
                backup_service,
                "DATA_DIR",
                self.data_dir,
            ),
            patch.object(
                backup_service,
                "DB_PATH",
                self.db_path,
            ),
            patch.object(
                backup_service,
                "IMAGES_DIR",
                self.images_dir,
            ),
            patch.object(
                backup_service,
                "BACKUP_DIR",
                self.backup_dir,
            ),
            patch.object(
                backup_service,
                "engine",
                self.engine,
            ),
        ]

        for item in self.patches:
            item.start()

    def tearDown(self):
        self.engine.dispose()

        for item in reversed(self.patches):
            item.stop()

        self.tmp.cleanup()

    def test_simulacion_integral_respaldo_y_restauracion(self):

        # -------------------------------------------------
        # 1. CREAR LOTE, PIEZA, EVALUACION E IMAGEN
        # -------------------------------------------------

        relative_path = (
            "images/AG045/evidencia-01.png"
        )

        image_path = self.data_dir / relative_path
        image_path.parent.mkdir(parents=True)

        image_content = b"IMAGEN-REAL-DE-PRUEBA-AG045"
        image_path.write_bytes(image_content)

        with self.SessionLocal() as db:

            lot = Lot(
                code="LOTE-AG045",
                product="mango",
                status="open",
                responsible="Operador de prueba",
            )

            piece = Piece(
                code="PIEZA-AG045-001",
                status="registered",
                lot=lot,
            )

            evaluation = Evaluation(
                lot=lot,
                piece=piece,
                piece_id="PIEZA-AG045-001",
                product="mango",
                status="processing",
                image_count=1,
                visual_category="primera",
            )

            evidence = Image(
                evaluation=evaluation,
                view="frontal",
                relative_path=relative_path,
                content_type="image/png",
                size_bytes=len(image_content),
                idempotency_key="ag045-prueba-integral",
            )

            db.add(lot)
            db.add(piece)
            db.add(evaluation)
            db.add(evidence)

            db.commit()

            lot_id = lot.id
            piece_id = piece.id
            evaluation_id = evaluation.id
            image_id = evidence.id

        # -------------------------------------------------
        # 2. COMPROBAR INFORMACION ORIGINAL
        # -------------------------------------------------

        with self.SessionLocal() as db:

            original_evaluation = db.get(
                Evaluation,
                evaluation_id,
            )

            self.assertIsNotNone(original_evaluation)
            self.assertEqual(
                original_evaluation.image_count,
                1,
            )
            self.assertEqual(
                len(original_evaluation.images),
                1,
            )

            self.assertEqual(
                original_evaluation.images[0].id,
                image_id,
            )

        # -------------------------------------------------
        # 3. CREAR RESPALDO COMPLETO
        # -------------------------------------------------

        backup_result = backup_service.create_backup()

        backup_path = Path(backup_result["path"])

        self.assertTrue(backup_path.is_file())
        self.assertGreater(
            backup_path.stat().st_size,
            0,
        )

        self.assertEqual(
            backup_result["evaluationImages"],
            1,
        )

        self.assertEqual(
            backup_result["imageFiles"],
            1,
        )

        # -------------------------------------------------
        # 4. SIMULAR PERDIDA DE INFORMACION
        # -------------------------------------------------

        with self.SessionLocal() as db:

            db.delete(db.get(Image, image_id))
            db.flush()

            db.delete(
                db.get(Evaluation, evaluation_id)
            )
            db.flush()

            db.delete(db.get(Piece, piece_id))
            db.flush()

            db.delete(db.get(Lot, lot_id))

            db.commit()

        image_path.unlink()

        # Confirmar que los datos desaparecieron.
        with self.SessionLocal() as db:

            self.assertIsNone(
                db.get(Evaluation, evaluation_id)
            )

            self.assertIsNone(
                db.get(Image, image_id)
            )

            self.assertIsNone(
                db.get(Lot, lot_id)
            )

        self.assertFalse(image_path.exists())

        # -------------------------------------------------
        # 5. RESTAURAR RESPALDO
        # -------------------------------------------------

        restore_result = backup_service.restore_backup(
            backup_path
        )

        self.assertTrue(restore_result["restored"])
        self.assertTrue(restore_result["verified"])

        self.assertEqual(
            restore_result["evaluationImages"],
            1,
        )

        # -------------------------------------------------
        # 6. VERIFICAR RECUPERACION DE MODELOS REALES
        # -------------------------------------------------

        with self.SessionLocal() as db:

            restored_lot = db.get(
                Lot,
                lot_id,
            )

            restored_piece = db.get(
                Piece,
                piece_id,
            )

            restored_evaluation = db.get(
                Evaluation,
                evaluation_id,
            )

            restored_image = db.get(
                Image,
                image_id,
            )

            self.assertIsNotNone(restored_lot)
            self.assertIsNotNone(restored_piece)
            self.assertIsNotNone(restored_evaluation)
            self.assertIsNotNone(restored_image)

            # Comprobar lote y pieza.
            self.assertEqual(
                restored_lot.code,
                "LOTE-AG045",
            )

            self.assertEqual(
                restored_piece.code,
                "PIEZA-AG045-001",
            )

            # Comprobar evaluación.
            self.assertEqual(
                restored_evaluation.lot_id,
                lot_id,
            )

            self.assertEqual(
                restored_evaluation.piece_ref_id,
                piece_id,
            )

            self.assertEqual(
                restored_evaluation.status,
                "processing",
            )

            # Comprobar vínculo imagen-evaluación.
            self.assertEqual(
                restored_image.evaluation_id,
                evaluation_id,
            )

            self.assertEqual(
                restored_image.relative_path,
                relative_path,
            )

            self.assertEqual(
                len(restored_evaluation.images),
                1,
            )

            self.assertEqual(
                restored_evaluation.images[0].id,
                image_id,
            )

        # -------------------------------------------------
        # 7. VERIFICAR RECUPERACION DEL ARCHIVO FISICO
        # -------------------------------------------------

        self.assertTrue(image_path.is_file())

        self.assertEqual(
            image_path.read_bytes(),
            image_content,
        )

        # -------------------------------------------------
        # 8. VERIFICAR INTEGRIDAD DE SQLITE
        # -------------------------------------------------

        validation = backup_service.validate_database(
            self.db_path
        )

        self.assertEqual(
            validation["evaluationImageCount"],
            1,
        )

        self.assertEqual(
            validation["imagePaths"],
            [relative_path],
        )


if __name__ == "__main__":
    unittest.main()
