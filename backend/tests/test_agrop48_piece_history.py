"""AG-040 / AGROP-48: expediente integral y conteo de piezas sin joins multiplicadores.

Pruebas con SQLite temporal, sin hardware ni clasificador instalado.
"""
import json
import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.dependencies import require_authenticated
from app.main import app
from app.models import Evaluation, Image, Lot, Piece, Review
from app.vision_assessment_models import VisionAssessment
from app.decision_models import ReviewDecisionEvidence


class PieceHistoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.Session = lambda: Session(self.engine)
        self.lot_code = "AG040-LOTE-MANGO"
        with self.Session() as db:
            db.add_all([
                Lot(code=self.lot_code, product="mango", status="open"),
                Lot(code="AG040-OTRO-LOTE", product="mango", status="open"),
            ])
            db.flush()
            self.lot1, self.lot2 = [v.id for v in db.query(Lot).order_by(Lot.id)]
            piece = Piece(lot_id=self.lot1, code="FRUTA-001", status="registered")
            second = Piece(lot_id=self.lot1, code="FRUTA-002", status="registered")
            third = Piece(lot_id=self.lot2, code="FRUTA-001", status="registered")
            empty = Piece(lot_id=self.lot1, code="SIN-INTENTOS", status="registered")
            db.add_all([piece, second, third, empty])
            db.flush()
            self.piece1 = piece.id
            # 3 intentos de la MISMA pieza (uno historico sin FK), 4 fotos.
            evaluations = [
                Evaluation(lot_id=self.lot1, piece_ref_id=self.piece1, piece_id="FRUTA-001", product="mango", status="error"),
                Evaluation(lot_id=self.lot1, piece_ref_id=self.piece1, piece_id="FRUTA-001", product="mango", status="pending_review"),
                Evaluation(lot_id=self.lot1, piece_ref_id=None, piece_id="FRUTA-001", product="mango", status="completed"),
                Evaluation(lot_id=self.lot1, piece_ref_id=second.id, piece_id="FRUTA-002", product="mango", status="completed"),
                Evaluation(lot_id=self.lot2, piece_ref_id=third.id, piece_id="FRUTA-001", product="mango", status="completed"),
                Evaluation(lot_id=self.lot1, piece_ref_id=None, piece_id="HISTORICA", product="mango", status="completed"),
            ]
            db.add_all(evaluations)
            db.flush()
            self.attempt_ids = [x.id for x in evaluations]
            photos = [
                Image(evaluation_id=evaluations[0].id, view="vista-1", relative_path="test/a.jpg", content_type="image/jpeg", size_bytes=8),
                Image(evaluation_id=evaluations[1].id, view="vista-1", relative_path="test/b.jpg", content_type="image/jpeg", size_bytes=8),
                Image(evaluation_id=evaluations[1].id, view="vista-2", relative_path="test/c.jpg", content_type="image/jpeg", size_bytes=8),
                Image(evaluation_id=evaluations[2].id, view="vista-1", relative_path="test/d.jpg", content_type="image/jpeg", size_bytes=8),
            ]
            db.add_all(photos)
            db.flush()
            self.img_id = photos[1].id
            # Dos snapshots de la misma foto: NO crean nuevos intentos ni piezas.
            for ver in ["ag040-1", "ag040-2"]:
                db.add(VisionAssessment(
                    evaluation_id=evaluations[1].id, image_id=photos[1].id,
                    image_sha256="a"*64, model_version=ver, rules_version="reglas-v1",
                    inference_size=512, inference_confidence=0.25, acceptance_threshold=0.40,
                    outcome="pending_review", reason="confianza_insuficiente", confidence=.35,
                    candidate_count=1, detections_json=json.dumps([{"label":"mango", "confidence":.35}]),
                ))
            reviews = [
                Review(evaluation_id=evaluations[1].id, type="uncertainty", actor_id="operador", reason="Revisar captura", previous_value="processing", updated_value="pending_review"),
                Review(evaluation_id=evaluations[1].id, type="review", actor_id="revisor", reason="Confirmado por evidencia", previous_value=None, updated_value="E1"),
                Review(evaluation_id=evaluations[1].id, type="review", actor_id="revisor", reason="Correccion verificada", previous_value="E1", updated_value="E2"),
            ]
            db.add_all(reviews)
            db.flush()
            db.add(ReviewDecisionEvidence(
                evaluation_id=evaluations[1].id, review_id=reviews[2].id,
                image_id=photos[1].id, image_sha256="a"*64, action="correct",
                request_id="00000000-0000-4000-8000-000000000001", payload_sha256="b"*64,
            ))
            db.commit()

        def override():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = override
        app.dependency_overrides[require_authenticated] = lambda: None
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def _list(self, lot=None):
        return self.client.get("/api/piece-history", params={"lot": lot or self.lot_code})

    def _detail(self, piece="FRUTA-001", lot=None):
        return self.client.get(f"/api/piece-history/{lot or self.lot_code}/{piece}")

    def test_piece_count_not_multiplied_by_captures_or_reviews(self):
        response = self._list()
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["pieceCount"], 4)
        self.assertEqual(data["attemptCount"], 5)
        self.assertEqual(data["captureCount"], 4)
        p = next(p for p in data["pieces"] if p["pieceCode"] == "FRUTA-001")
        self.assertEqual(p["attemptCount"], 3)
        self.assertEqual(p["captureCount"], 4)
        self.assertEqual(p["reviewEventCount"], 3)
        self.assertEqual(p["automaticAssessmentCount"], 2)

    def test_multiple_attempts_appear_in_order(self):
        r = self._detail()
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(len(d["attempts"]), 3)
        self.assertEqual([a["attemptNumber"] for a in d["attempts"]], [1, 2, 3])
        self.assertEqual([a["id"] for a in d["attempts"]], [f"E-{n:06d}" for n in self.attempt_ids[:3]])

    def test_snapshots_show_actual_model_and_rule_versions(self):
        attempt = self._detail().json()["attempts"][1]
        snapshots = attempt["automaticAssessments"]
        self.assertEqual([p["modelVersion"] for p in snapshots], ["ag040-1", "ag040-2"])
        self.assertEqual(snapshots[0]["rulesVersion"], "reglas-v1")
        self.assertEqual(snapshots[0]["confidence"], .35)
        self.assertEqual(len(attempt["captures"]), 2)

    def test_all_reviews_and_ag038_metadata_survive(self):
        attempts = self._detail().json()["attempts"]
        events = attempts[1]["reviews"]
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]["type"], "uncertainty")
        self.assertIsNone(events[1]["action"])
        self.assertEqual(events[2]["action"], "correct")
        self.assertEqual(events[2]["previousValue"], "E1")
        self.assertEqual(events[2]["updatedValue"], "E2")
        self.assertEqual(events[2]["imageSha256"], "a"*64)

    def test_conflicting_reference_hashes_are_not_silently_accepted(self):
        with self.Session() as db:
            meta = db.query(ReviewDecisionEvidence).first()
            meta.image_sha256 = "c"*64
            db.commit()
        d = self._detail().json()["attempts"][1]
        img = next(x for x in d["captures"] if x["id"] == f"I-{self.img_id:06d}")
        self.assertTrue(img["hashConflict"])
        self.assertIsNone(img["imageSha256"])
        self.assertTrue(any("SHA256" in note for note in d["dataQualityNotes"]))

    def test_historical_without_fk_is_not_duplicated(self):
        d = self._detail().json()
        self.assertEqual(d["piece"]["identitySource"], "registered")
        self.assertEqual(d["piece"]["attemptCount"], 3)
        self.assertIsNone(d["identityWarning"])

    def test_legacy_unregistered_piece_has_explicit_warning(self):
        r = self._detail("HISTORICA")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["piece"]["identitySource"], "legacy_inferred")
        self.assertIsNotNone(r.json()["identityWarning"])
        self.assertEqual(r.json()["piece"]["attemptCount"], 1)

    def test_registered_piece_without_attempts_is_not_invented(self):
        d = self._detail("SIN-INTENTOS").json()
        self.assertEqual(d["piece"]["attemptCount"], 0)
        self.assertEqual(d["attempts"], [])

    def test_same_piece_code_different_lots_remain_distinct(self):
        self.assertEqual(self._detail().json()["piece"]["attemptCount"], 3)
        self.assertEqual(self._detail(lot="AG040-OTRO-LOTE").json()["piece"]["attemptCount"], 1)

    def test_no_snapshot_does_not_invent_versions(self):
        attempt = self._detail().json()["attempts"][0]
        self.assertEqual(attempt["automaticAssessments"], [])
        self.assertIsNone(attempt["declaredModelVersion"])
        self.assertIsNone(attempt["declaredRulesVersion"])

    def test_missing_lot_and_piece_are_explicit(self):
        self.assertEqual(self._list("INEXISTENTE").status_code, 404)
        self.assertEqual(self._detail("INEXISTENTE").status_code, 404)
        self.assertEqual(self._list("x"*33).status_code, 422)

    def test_bad_fk_prevents_silent_incorrect_grouping(self):
        with self.Session() as db:
            ev = db.get(Evaluation, self.attempt_ids[0])
            ev.piece_id = "FRUTA-002"
            db.commit()
        response = self._list()
        self.assertEqual(response.status_code, 409)
        self.assertIn("identidad", response.text)

    def test_get_is_read_only_and_repeatable(self):
        with self.Session() as db:
            before = db.query(Evaluation).count(), db.query(Image).count(), db.query(Review).count()
        first, second = self._detail().json(), self._detail().json()
        self.assertEqual(first, second)
        with self.Session() as db:
            after = db.query(Evaluation).count(), db.query(Image).count(), db.query(Review).count()
        self.assertEqual(before, after)

    def test_authentication_is_required(self):
        app.dependency_overrides.pop(require_authenticated)
        try:
            r = self._list()
            self.assertEqual(r.status_code, 401)
        finally:
            app.dependency_overrides[require_authenticated] = lambda: None


if __name__ == "__main__":
    unittest.main()
