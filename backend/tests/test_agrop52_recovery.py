
import unittest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Evaluation, Lot, Measurement
from app.routers.evaluations import weight_pre, weight_post


class AGROP52RecoveryTests(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

        lot = Lot(
            code="LOTE-AGROP52",
            product="mango",
            status="open",
        )
        self.db.add(lot)
        self.db.commit()

        self.evaluation = Evaluation(
            lot_id=lot.id,
            piece_id="PIEZA-001",
            product="mango",
            status="processing",
            created_at=datetime.now(timezone.utc) - timedelta(seconds=2),
        )
        self.db.add(self.evaluation)
        self.db.commit()
        self.db.refresh(self.evaluation)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_measurement(
        self,
        seq,
        weight,
        stable=True,
        zero_confirmed=True,
    ):
        now = datetime.now(timezone.utc)

        measurement = Measurement(
            device_id="station-agrop52",
            boot_id="boot-agrop52",
            seq=seq,
            weight_g=weight,
            stable=stable,
            zero_confirmed=zero_confirmed,
            calibration_version="cal-1e8bb75b2be1879349addaa4c4861e74-7",
            received_at=now,
            observed_at=now,
        )

        self.db.add(measurement)
        self.db.commit()

    def evaluation_id(self):
        return f"E-{self.evaluation.id:06d}"

    def test_sensor_pre_falla_y_reintento_conserva_evaluacion(self):
        original_id = self.evaluation.id

        with self.assertRaises(HTTPException) as error:
            weight_pre(self.evaluation_id(), self.db)

        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(
            error.exception.detail["code"],
            "SENSOR_DISCONNECTED",
        )

        self.assertEqual(
            self.db.scalar(select(Evaluation.id)),
            original_id,
        )

        self.add_measurement(1, 180.0)

        result = weight_pre(self.evaluation_id(), self.db)

        self.db.refresh(self.evaluation)

        self.assertEqual(result["weightG"], 180.0)
        self.assertEqual(self.evaluation.id, original_id)
        self.assertEqual(self.evaluation.weight_pre_g, 180.0)

    def test_sensor_post_falla_y_reintento_conserva_peso_previo(self):
        original_id = self.evaluation.id

        self.evaluation.weight_pre_g = 180.0
        self.evaluation.weight_pre_at = (
            datetime.now(timezone.utc) - timedelta(seconds=2)
        )
        self.evaluation.device_id = "station-agrop52"
        self.evaluation.boot_id = "boot-agrop52"
        self.db.commit()

        with self.assertRaises(HTTPException) as error:
            weight_post(self.evaluation_id(), self.db)

        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(
            error.exception.detail["code"],
            "SENSOR_DISCONNECTED",
        )

        self.db.refresh(self.evaluation)

        self.assertEqual(self.evaluation.id, original_id)
        self.assertEqual(self.evaluation.weight_pre_g, 180.0)
        self.assertIsNone(self.evaluation.weight_post_g)

        self.add_measurement(1, 175.0)

        result = weight_post(self.evaluation_id(), self.db)

        self.db.refresh(self.evaluation)

        self.assertEqual(result["weightG"], 175.0)
        self.assertEqual(self.evaluation.id, original_id)
        self.assertEqual(self.evaluation.weight_pre_g, 180.0)
        self.assertEqual(self.evaluation.weight_post_g, 175.0)

    def test_peso_inestable_no_genera_confirmacion_falsa(self):
        original_id = self.evaluation.id

        self.add_measurement(
            1,
            180.0,
            stable=False,
        )

        with self.assertRaises(HTTPException) as error:
            weight_pre(self.evaluation_id(), self.db)

        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(
            error.exception.detail["code"],
            "WEIGHT_UNSTABLE",
        )

        self.db.refresh(self.evaluation)

        self.assertEqual(self.evaluation.id, original_id)
        self.assertIsNone(self.evaluation.weight_pre_g)

    def test_cero_no_confirmado_no_genera_confirmacion_falsa(self):
        original_id = self.evaluation.id

        self.add_measurement(
            1,
            180.0,
            zero_confirmed=False,
        )

        with self.assertRaises(HTTPException) as error:
            weight_pre(self.evaluation_id(), self.db)

        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(
            error.exception.detail["code"],
            "ZERO_NOT_CONFIRMED",
        )

        self.db.refresh(self.evaluation)

        self.assertEqual(self.evaluation.id, original_id)
        self.assertIsNone(self.evaluation.weight_pre_g)


if __name__ == "__main__":
    unittest.main()
