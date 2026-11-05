import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tomato_pipeline import evaluate_manifest


class TestTomatoPipeline(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

        image = Image.new("RGB", (200, 150), (210, 60, 45))
        image.save(self.root / "tomate.jpg", quality=95)

        self.manifest = {
            "experiment_id": "AGROP41-TEST-001",
            "piece": {
                "piece_id": "TOM-001",
                "lot_id": "LOTE-TOM-001",
                "product": "tomate",
                "variety_declared": "variedad-piloto-pendiente",
                "commercial_type": None
            },
            "coverage_verified": True,
            "images": [{
                "image_id": "IMG-TOM-001",
                "view": "vista-lateral",
                "path": "tomate.jpg",
                "quality": {
                    "focus_ok": True,
                    "lighting_ok": True,
                    "unoccluded": True
                },
                "roi_xywh": [20, 20, 120, 100],
                "roi_verified": True
            }],
            "measurement": None,
            "observations": {},
            "operator_visual_label": None
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_procesa_tomate_correctamente(self):
        result = evaluate_manifest(self.manifest, self.root)

        self.assertEqual(result["product"], "tomate")
        self.assertEqual(result["visual_status"], "evaluable")
        self.assertEqual(result["evaluable_image_count"], 1)

    def test_rechaza_mango(self):
        self.manifest["piece"]["product"] = "mango"

        with self.assertRaises(ValueError):
            evaluate_manifest(self.manifest, self.root)

    def test_conserva_evidencia_sha256(self):
        result = evaluate_manifest(self.manifest, self.root)

        image = result["images"][0]

        self.assertTrue(image["evidence_preserved"])
        self.assertEqual(len(image["sha256"]), 64)

    def test_extrae_descriptores_rgb(self):
        result = evaluate_manifest(self.manifest, self.root)

        descriptors = result["images"][0]["color_descriptors"]

        self.assertIsNotNone(descriptors)
        self.assertEqual(descriptors["color_space"], "RGB")
        self.assertEqual(len(descriptors["mean_rgb"]), 3)

    def test_no_infiere_calibre_desde_pixeles(self):
        result = evaluate_manifest(self.manifest, self.root)

        self.assertIsNone(result["criteria"]["R02"]["diameter_mm"])
        self.assertIn("pendiente", result["criteria"]["R02"]["status"])

    def test_medicion_sin_calibracion_queda_pendiente(self):
        self.manifest["measurement"] = {
            "diameter_mm": 68,
            "equipment_id": "CALIPER-001",
            "calibrated": False
        }

        result = evaluate_manifest(self.manifest, self.root)

        self.assertEqual(
            result["criteria"]["R02"]["status"],
            "pendiente"
        )

    def test_imagen_borrosa_requiere_recaptura(self):
        self.manifest["images"][0]["quality"]["focus_ok"] = False

        result = evaluate_manifest(self.manifest, self.root)

        self.assertEqual(
            result["images"][0]["quality_status"],
            "recaptura_requerida"
        )

    def test_region_no_verificada_no_se_analiza(self):
        self.manifest["images"][0]["roi_verified"] = False

        result = evaluate_manifest(self.manifest, self.root)

        self.assertIsNone(
            result["images"][0]["color_descriptors"]
        )

    def test_atributos_no_observables_separados(self):
        result = evaluate_manifest(self.manifest, self.root)

        not_observable = result["criteria"]["R10"][
            "not_evaluated_by_rgb_or_weight"
        ]

        self.assertIn("firmeza", not_observable)
        self.assertIn("grados_brix", not_observable)

    def test_etiqueta_del_operador_se_conserva(self):
        self.manifest["operator_visual_label"] = "E1"

        result = evaluate_manifest(self.manifest, self.root)

        self.assertEqual(result["operator_visual_label"], "E1")
        self.assertEqual(result["visual_label_source"], "operador")


if __name__ == "__main__":
    unittest.main(verbosity=2)
