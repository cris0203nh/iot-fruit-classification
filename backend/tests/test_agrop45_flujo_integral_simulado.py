"""AG-037: flujo HTTP completo con pesajes y detector SIMULADOS.

No requiere ESP32, cámara real ni pesos YOLOE. Usa SQLite y archivos temporales;
NO modifica backend/data/agroscan.db ni acredita una prueba física del hardware.
"""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Evaluation, Image, Lot, Measurement, Review, Role, User
from app.routers import evaluations, images, uncertainty as gate_router
from app.security import create_access_token, hash_password
from app.uncertainty import GateResult
from app.vision_assessment_models import VisionAssessment


class AG037FlujoIntegralSimuladoTests(unittest.TestCase):
    """Ejercita endpoints verdaderos; SOLO sensor e inferencia son sustituidos."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ag037-simulacion-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data_root = self.root / "evidencias"
        self.data_root.mkdir()
        self.sqlite_file = self.root / "ag037_prueba.sqlite"
        self.engine = create_engine(
            f"sqlite:///{self.sqlite_file.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

        now = datetime.now(timezone.utc)
        self.users = {}
        with self.Session() as db:
            for role_name in ("administrador", "operador", "revisor"):
                user = User(
                    username=f"sim_{role_name}",
                    full_name=f"Simulacion {role_name}",
                    password_hash=hash_password("ClaveSoloDePruebas123"),
                    is_active=True,
                    roles=[Role(name=role_name)],
                )
                db.add(user)
                db.flush()
                self.users[role_name] = user.id
            lot = Lot(code="AG037-LOTE-SIM", product="mango", status="open")
            db.add(lot)
            db.flush()
            evaluation = Evaluation(
                lot_id=lot.id,
                piece_id="AG037-PIEZA-SIM",
                product="mango",
                status="processing",
                created_at=now - timedelta(seconds=4),
            )
            db.add(evaluation)
            db.flush()
            self.evaluation_pk = evaluation.id
            db.commit()
        self.evaluation_id = f"E-{self.evaluation_pk:06d}"

        def override_db():
            with self.Session() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        self.addCleanup(lambda: app.dependency_overrides.pop(get_db, None))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

        # Almacenamiento segregado: las rutas originales de producción no se tocan.
        for obj, attribute, replacement in (
            (images, "DATA_DIR", self.data_root),
            (images, "IMAGES_DIR", self.data_root / "images"),
            (evaluations, "DATA_DIR", self.data_root),
            (gate_router, "DATA_DIR", self.data_root),
        ):
            p = patch.object(obj, attribute, replacement)
            p.start()
            self.addCleanup(p.stop)

        valid, image = cv2.imencode(
            ".jpg", np.full((96, 96, 3), (35, 130, 210), dtype=np.uint8)
        )
        self.assertTrue(valid)
        self.photo = image.tobytes()
        self.photo_hash = hashlib.sha256(self.photo).hexdigest()
        self.image_id = None

    def auth(self, role):
        return {"Authorization": f"Bearer {create_access_token(self.users[role])}"}

    def measurement(self, sequence, *, stable=True, weight=250.0):
        # Se inserta una nueva lectura antes de CADA paso, simulando los dos
        # eventos que un ESP32 real enviaría. No se alteran los validadores.
        at = datetime.now(timezone.utc)
        with self.Session() as db:
            db.add(Measurement(
                device_id="sensor-SIM-no-hardware",
                boot_id="sesion-SIM-001",
                seq=sequence,
                weight_g=weight,
                stable=stable,
                calibration_version="cal-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-1",
                received_at=at,
                observed_at=at,
                zero_confirmed=True,
            ))
            db.commit()

    def upload(self, idem="a" * 64):
        response = self.client.post(
            f"/api/evaluations/{self.evaluation_id}/images",
            headers={**self.auth("operador"), "Idempotency-Key": idem},
            data={"view": "vista-1"},
            files={"file": ("mango_simulado.jpg", self.photo, "image/jpeg")},
        )
        if response.status_code == 201:
            self.image_id = response.json()["id"]
        return response

    def confirmed_acquisition(self):
        self.measurement(1)
        pre = self.client.post(
            f"/api/evaluations/{self.evaluation_id}/weight/pre",
            headers=self.auth("operador"),
        )
        self.assertEqual(pre.status_code, 200, pre.text)
        self.assertEqual(pre.json()["stage"], "pre")

        image = self.upload()
        self.assertEqual(image.status_code, 201, image.text)

        self.measurement(2, weight=251.0)
        post = self.client.post(
            f"/api/evaluations/{self.evaluation_id}/weight/post",
            headers=self.auth("operador"),
        )
        self.assertEqual(post.status_code, 200, post.text)
        self.assertEqual(post.json()["stage"], "post")

        confirmation = self.client.post(
            f"/api/evaluations/{self.evaluation_id}/acquisition/confirm",
            headers=self.auth("operador"),
        )
        self.assertEqual(confirmation.status_code, 200, confirmation.text)
        self.assertTrue(confirmation.json()["confirmed"])
        self.assertEqual(confirmation.json()["imageCount"], 1)

    def gate(self, simulated_prediction, *, role="operador"):
        with patch.object(gate_router, "_infer", return_value=simulated_prediction):
            return self.client.post(
                f"/api/evaluations/{self.evaluation_id}/vision/review-gate",
                headers=self.auth(role),
                json={"imageId": self.image_id},
            )

    def resolve(self, outcome, role="revisor"):
        return self.client.post(
            f"/api/evaluations/{self.evaluation_id}/vision/resolve",
            headers=self.auth(role),
            json={"outcome": outcome,
                  "reason": "Inspección de fotografía de prueba y verificación del estado visual"},
        )

    def test_uncertain_result_to_review_and_resume_with_original_intact(self):
        self.confirmed_acquisition()
        prediction = (
            GateResult(True, "confianza_insuficiente", 0.35, 1),
            [{"label": "mango fruit", "confidence": 0.35,
              "box": [4, 3, 89, 92], "mask": True}],
        )
        gate = self.gate(prediction)
        self.assertEqual(gate.status_code, 200, gate.text)
        self.assertEqual(gate.json()["status"], "pending_review")
        self.assertFalse(gate.json()["classificationE0E1E2Produced"])
        self.assertEqual(gate.json()["imageSha256"], self.photo_hash)

        pending = self.client.get(
            "/api/evaluations?status=pending_review", headers=self.auth("revisor")
        )
        self.assertEqual(pending.status_code, 200, pending.text)
        self.assertIn(self.evaluation_id, [e["id"] for e in pending.json()])

        unauthorized = self.resolve("E1", role="operador")
        self.assertEqual(unauthorized.status_code, 403)
        accepted = self.resolve("E1")
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["reviewOutcome"], "E1")
        self.assertTrue(accepted.json()["originalPreserved"])

        detail = self.client.get(
            f"/api/evaluations/{self.evaluation_id}", headers=self.auth("revisor")
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["status"], "completed")
        self.assertIsNone(detail.json()["visualCategory"])
        self.assertEqual(detail.json()["imageCount"], 1)

        image = self.client.get(
            f"/api/images/{self.image_id}", headers=self.auth("revisor")
        )
        self.assertEqual(image.status_code, 200, image.text)
        self.assertEqual(image.content, self.photo)

        trace = self.client.get(
            f"/api/evaluations/{self.evaluation_id}/traceability",
            headers=self.auth("revisor"),
        )
        self.assertEqual(trace.status_code, 200, trace.text)
        self.assertIn("uncertainty", [e["type"] for e in trace.json()["reviews"]])
        self.assertIn("review", [e["type"] for e in trace.json()["reviews"]])
        assessment = self.client.get(
            f"/api/evaluations/{self.evaluation_id}/vision/assessments",
            headers=self.auth("revisor"),
        )
        self.assertEqual(assessment.status_code, 200, assessment.text)
        self.assertEqual(assessment.json()[0]["imageSha256"], self.photo_hash)
        self.assertEqual(assessment.json()[0]["outcome"], "pending_review")

        # Reapertura independiente de SQLite (no depende del objeto Session).
        separate_engine = create_engine(f"sqlite:///{self.sqlite_file.as_posix()}")
        try:
            with Session(separate_engine) as db:
                ev = db.get(Evaluation, self.evaluation_pk)
                self.assertEqual(ev.status, "completed")
                self.assertIsNone(ev.visual_category)
                self.assertEqual(
                    db.scalar(select(VisionAssessment)).image_sha256, self.photo_hash
                )
                self.assertEqual(len(db.scalars(select(Review)).all()), 2)
        finally:
            separate_engine.dispose()

    def test_no_evaluable_does_not_invent_grade(self):
        self.confirmed_acquisition()
        gate = self.gate((GateResult(True, "sin_deteccion", None, 0), []))
        self.assertEqual(gate.status_code, 200, gate.text)
        self.assertEqual(gate.json()["reason"], "sin_deteccion")
        resolved = self.resolve("no_evaluable")
        self.assertEqual(resolved.status_code, 200, resolved.text)
        self.assertEqual(resolved.json()["reviewOutcome"], "no_evaluable")
        with self.Session() as db:
            evaluation = db.get(Evaluation, self.evaluation_pk)
            self.assertIsNone(evaluation.visual_category)
            self.assertEqual(evaluation.status, "completed")
            self.assertEqual(len(db.scalars(select(VisionAssessment)).all()), 1)

    def test_missing_weight_blocks_confirmation_even_with_photo(self):
        self.assertEqual(self.upload().status_code, 201)
        response = self.client.post(
            f"/api/evaluations/{self.evaluation_id}/acquisition/confirm",
            headers=self.auth("operador"),
        )
        self.assertEqual(response.status_code, 409, response.text)
        with self.Session() as db:
            self.assertEqual(db.get(Evaluation, self.evaluation_pk).status, "processing")

    def test_unstable_sensor_is_rejected_without_bypass(self):
        self.measurement(1, stable=False)
        response = self.client.post(
            f"/api/evaluations/{self.evaluation_id}/weight/pre",
            headers=self.auth("operador"),
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "WEIGHT_UNSTABLE")

    def test_detector_unavailable_must_be_reviewed(self):
        self.confirmed_acquisition()
        with patch.object(gate_router, "_infer", side_effect=RuntimeError("SIM-SIN-YOLOE")):
            response = self.client.post(
                f"/api/evaluations/{self.evaluation_id}/vision/review-gate",
                headers=self.auth("operador"),
                json={"imageId": self.image_id},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["reason"], "detector_no_disponible")
        self.assertEqual(response.json()["status"], "pending_review")

    def test_ready_detection_does_not_generate_e0_e1_e2(self):
        self.confirmed_acquisition()
        response = self.gate((
            GateResult(False, "deteccion_apta_para_captura", 0.91, 1),
            [{"label": "mango fruit", "confidence": 0.91,
              "box": [4, 3, 89, 92], "mask": True}],
        ))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["decision"], "ready_to_capture")
        self.assertFalse(response.json()["classificationE0E1E2Produced"])
        with self.Session() as db:
            self.assertIsNone(db.get(Evaluation, self.evaluation_pk).visual_category)
            self.assertEqual(len(db.scalars(select(Review)).all()), 0)

    def test_upload_replay_is_idempotent(self):
        first = self.upload()
        second = self.upload()
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(first.json()["id"], second.json()["id"])
        with self.Session() as db:
            self.assertEqual(db.get(Evaluation, self.evaluation_pk).image_count, 1)
            self.assertEqual(len(db.scalars(select(Image)).all()), 1)


if __name__ == "__main__":
    unittest.main()
