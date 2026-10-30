"""AGROP-22: pruebas unitarias de caducidad de lectura del contrato FastAPI."""
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.iot_schemas import MeasurementCreate
from app.models import Measurement
from app.routers.iot import receive_measurement, iot_status


class IotStatusTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_sin_lectura_no_publica_masa(self):
        status = iot_status(self.db)
        self.assertFalse(status["online"])
        self.assertIsNone(status["weightG"])

    def test_lectura_estable_fresca_incluye_timestamp(self):
        payload = MeasurementCreate(schema_version=1, device_id="station-001", boot_id="boot-a", seq=1,
                                    weight_g=250, stable=True, calibration_version="demo")
        receive_measurement(payload, self.db)
        status = iot_status(self.db)
        self.assertTrue(status["online"])
        self.assertEqual(status["weightG"], 250)
        self.assertTrue(status["stable"])
        self.assertIn("T", status["receivedAt"])

    def test_inestable_se_reporta_y_no_se_convierta_en_estable(self):
        receive_measurement(MeasurementCreate(device_id="station-001", boot_id="b1", seq=1,
            weight_g=249, stable=False, calibration_version="demo"), self.db)
        status = iot_status(self.db)
        self.assertFalse(status["stable"])
        self.assertEqual(status["weightG"], 249)

    def test_caducada_oculta_masa_y_conserva_fecha_de_la_ultima_muestra(self):
        self.db.add(Measurement(device_id="station-001", boot_id="b1", seq=1,
            weight_g=450, stable=True, calibration_version="demo",
            received_at=datetime.now(timezone.utc) - timedelta(seconds=30)))
        self.db.commit()
        status = iot_status(self.db)
        self.assertFalse(status["online"])
        self.assertIsNone(status["weightG"])
        self.assertIsNone(status["stable"])
        self.assertIsNotNone(status["receivedAt"])

    def test_reenvio_duplicado_no_actualiza_antigua_fecha(self):
        payload = MeasurementCreate(device_id="station-001", boot_id="b1", seq=2,
            weight_g=450, stable=True, calibration_version="demo")
        receive_measurement(payload, self.db)
        measurement = self.db.query(Measurement).one()
        measurement.received_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        self.db.commit()
        result = receive_measurement(payload, self.db)
        self.assertTrue(result["duplicate"])
        self.assertFalse(iot_status(self.db)["online"])


if __name__ == "__main__":
    unittest.main()
