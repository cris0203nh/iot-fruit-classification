
import unittest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Evaluation, Lot, Measurement
from app.routers.evaluations import weight_pre


class AGROP24WeightValidationTests(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        lot = Lot(
            code="LOTE-AGROP24",
            product="tomate",
            status="open",
        )
        self.db.add(lot)
        self.db.commit()

        self.evaluation = Evaluation(
            lot_id=lot.id,
            piece_id="PIEZA-001",
            product="tomate",
            status="processing",
            created_at=datetime.now(timezone.utc) - timedelta(seconds=2),
        )
        self.db.add(self.evaluation)
        self.db.commit()
        self.db.refresh(self.evaluation)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_measurement(self, stable=True, zero_confirmed=True):
        measurement = Measurement(
            device_id="station-001",
            boot_id="boot-agrop24",
            seq=1,
            weight_g=250.0,
            stable=stable,
            zero_confirmed=zero_confirmed,
            calibration_version="test-1",
            received_at=datetime.now(timezone.utc),
        )
        self.db.add(measurement)
        self.db.commit()

    def test_sensor_desconectado_bloquea_pesaje(self):
        with self.assertRaises(HTTPException) as error:
            weight_pre(f"E-{self.evaluation.id:06d}", self.db)

        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(
            error.exception.detail["code"],
            "SENSOR_DISCONNECTED",
        )

    def test_peso_inestable_bloquea_pesaje(self):
        self.add_measurement(stable=False)

        with self.assertRaises(HTTPException) as error:
            weight_pre(f"E-{self.evaluation.id:06d}", self.db)

        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(
            error.exception.detail["code"],
            "WEIGHT_UNSTABLE",
        )

    def test_cero_no_confirmado_bloquea_pesaje(self):
        self.add_measurement(stable=True, zero_confirmed=False)

        with self.assertRaises(HTTPException) as error:
            weight_pre(f"E-{self.evaluation.id:06d}", self.db)

        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(
            error.exception.detail["code"],
            "ZERO_NOT_CONFIRMED",
        )

    def test_pesaje_valido_permite_registro(self):
        self.add_measurement(stable=True, zero_confirmed=True)

        result = weight_pre(
            f"E-{self.evaluation.id:06d}",
            self.db,
        )

        self.assertEqual(result["stage"], "pre")
        self.assertEqual(result["weightG"], 250.0)
        self.assertEqual(self.evaluation.weight_pre_g, 250.0)


    
    def preparar_peso_previo(self):
        now = datetime.now(timezone.utc)
        self.evaluation.weight_pre_g = 250.0
        self.evaluation.weight_pre_at = now - timedelta(seconds=2)
        self.evaluation.device_id = "station-001"
        self.evaluation.boot_id = "boot-agrop24"
        self.db.commit()

    def test_weight_post_sensor_desconectado_bloquea(self):
        from app.routers.evaluations import weight_post

        self.preparar_peso_previo()

        with self.assertRaises(HTTPException) as error:
            weight_post(f"E-{self.evaluation.id:06d}", self.db)

        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(
            error.exception.detail["code"],
            "SENSOR_DISCONNECTED",
        )

    def test_weight_post_peso_inestable_bloquea(self):
        from app.routers.evaluations import weight_post

        self.preparar_peso_previo()
        self.add_measurement(stable=False)

        with self.assertRaises(HTTPException) as error:
            weight_post(f"E-{self.evaluation.id:06d}", self.db)

        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(
            error.exception.detail["code"],
            "WEIGHT_UNSTABLE",
        )

    def test_weight_post_cero_no_confirmado_bloquea(self):
        from app.routers.evaluations import weight_post

        self.preparar_peso_previo()
        self.add_measurement(stable=True, zero_confirmed=False)

        with self.assertRaises(HTTPException) as error:
            weight_post(f"E-{self.evaluation.id:06d}", self.db)

        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(
            error.exception.detail["code"],
            "ZERO_NOT_CONFIRMED",
        )

    def test_weight_post_valido_permite_confirmacion(self):
        from app.routers.evaluations import weight_post

        self.preparar_peso_previo()
        self.add_measurement(stable=True, zero_confirmed=True)

        result = weight_post(
            f"E-{self.evaluation.id:06d}",
            self.db,
        )

        self.assertEqual(result["stage"], "post")
        self.assertEqual(result["weightG"], 250.0)
        self.assertEqual(self.evaluation.weight_post_g, 250.0)
        self.assertEqual(self.evaluation.weight_grams, 250.0)



if __name__ == "__main__":
    unittest.main()
