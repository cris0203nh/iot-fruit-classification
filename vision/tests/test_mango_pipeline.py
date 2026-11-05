"""Fixtures geométricas sintéticas: pruebas de SOFTWARE, no de precisión agronómica."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from vision.src.mango_pipeline import classify_caliber, evaluate_manifest


class MangoPipelineTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        # Patrón de píxeles uniforme, NO fotografía de un mango real.
        Image.new("RGB", (256, 256), (20, 155, 30)).save(self.root / "patron.png")

    def manifest(self):
        return {
            "experiment_id": "test-tecnico-sin-frutas",
            "piece": {"lot_id": "TEST-1", "piece_id": "P-1", "product": "mango", "variety_declared": "Kent"},
            "coverage_verified": True,
            "images": [{
                "image_id": "I-TEST", "view": "vista-1", "path": "patron.png",
                "quality": {"focus_ok": True, "lighting_ok": True, "unoccluded": True},
                "roi_xywh": [10, 10, 100, 200], "roi_verified": True,
            }],
            "weight": {"grams": 600, "stable": True, "calibrated": True, "uncertainty_g": 0},
        }

    def test_estado_evaluable_no_asigna_etiqueta_automatica(self):
        result = evaluate_manifest(self.manifest(), self.root)
        self.assertEqual(result["visual_status"], "evaluable")
        self.assertIsNone(result["visual_label"])
        self.assertEqual(result["criteria"]["R02"]["reference"], "C")
        self.assertEqual(result["criteria"]["R07"]["color_descriptors"][0]["median_rgb"], [20, 155, 30])
        for rule in ("R03", "R04", "R05", "R06"):
            self.assertEqual(result["criteria"][rule]["presence"], "no_determinable")

    def test_sin_imagen_no_evaluable(self):
        manifest = self.manifest()
        manifest["images"] = []
        self.assertEqual(evaluate_manifest(manifest, self.root)["visual_status"], "no_evaluable")

    def test_foco_rechazado_requiere_recaptura(self):
        manifest = self.manifest()
        manifest["images"][0]["quality"]["focus_ok"] = False
        result = evaluate_manifest(manifest, self.root)
        self.assertEqual(result["visual_status"], "no_evaluable")
        self.assertIn("recaptura_requerida_por_revision", result["images"][0]["reason"])

    def test_cobertura_desconocida_no_presume_evaluable(self):
        manifest = self.manifest()
        manifest.pop("coverage_verified")
        self.assertEqual(evaluate_manifest(manifest, self.root)["visual_status"], "pendiente_revision")

    def test_tomate_fuera_de_alcance_sin_imagenes_analizadas(self):
        manifest = self.manifest()
        manifest["piece"]["product"] = "tomate"
        result = evaluate_manifest(manifest, self.root)
        self.assertEqual(result["visual_status"], "no_reconocido")
        self.assertEqual(result["images"], [])

    def test_calibre_en_frontera_pendiente_y_sin_peso_es_independiente(self):
        for value in (350.6, 550.3):
            self.assertEqual(classify_caliber({"grams": value, "stable": True, "calibrated": True, "uncertainty_g": 0})["status"], "pendiente")
        self.assertEqual(classify_caliber({"grams": 350, "stable": True, "calibrated": True, "uncertainty_g": .2})["status"], "pendiente")
        self.assertEqual(classify_caliber({"grams": 600, "stable": False, "calibrated": True, "uncertainty_g": 0})["reference"], None)
        self.assertEqual(classify_caliber({"grams": 820, "stable": True, "calibrated": True, "uncertainty_g": 0})["status"], "fuera_de_referencia")

    def test_roi_no_verificada_no_generar_color_de_cascara(self):
        manifest = self.manifest()
        manifest["images"][0]["roi_verified"] = False
        result = evaluate_manifest(manifest, self.root)
        self.assertEqual(result["visual_status"], "pendiente_revision")
        self.assertEqual(result["criteria"]["R07"]["color_descriptors"], [])

    def test_imagen_ausente_no_fabrica_resultados(self):
        manifest = self.manifest()
        manifest["images"][0]["path"] = "inexistente.png"
        result = evaluate_manifest(manifest, self.root)
        self.assertEqual(result["visual_status"], "no_evaluable")
        self.assertIsNone(result["visual_label"])
        self.assertEqual(result["images"][0]["reason"], "archivo_no_disponible_o_invalido")

    def test_resultado_determinista_sin_uso_de_modelo(self):
        manifest = self.manifest()
        self.assertEqual(evaluate_manifest(manifest, self.root), evaluate_manifest(manifest, self.root))

    def test_cli_genera_reporte_reproducible(self):
        manifest_path = self.root / "datos.json"
        output_path = self.root / "resultado.json"
        manifest_path.write_text(json.dumps(self.manifest()), encoding="utf-8")
        cmd = [
            sys.executable, "-m", "vision.src.mango_pipeline",
            "--manifest", str(manifest_path), "--output", str(output_path),
        ]
        repo_root = Path(__file__).resolve().parents[2]
        first = subprocess.run(cmd, cwd=repo_root, check=True, capture_output=True, text=True)
        payload = output_path.read_bytes()
        self.assertIn("etiqueta automática: ninguna", first.stdout)
        subprocess.run(cmd, cwd=repo_root, check=True, capture_output=True, text=True)
        self.assertEqual(payload, output_path.read_bytes())
        self.assertIsNone(json.loads(payload)["visual_label"])

    def test_manifest_malformado_se_rechaza(self):
        manifest = self.manifest()
        manifest["images"] = {}
        with self.assertRaises(ValueError):
            evaluate_manifest(manifest, self.root)


if __name__ == "__main__":
    unittest.main()
