"""Pruebas offline de la integridad y cálculo de la auditoría final."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from verificar_evidencias import ROOT, calculate, load_verified


class EvidenceFinalTests(unittest.TestCase):
    def test_snapshots_originales_y_comparacion(self):
        result = calculate(ROOT)
        self.assertEqual(result["baseline"]["total"], 17)
        self.assertEqual(result["after_increment02"]["total"], 5)
        self.assertEqual(result["after_increment04"]["total"], 5)
        self.assertEqual(result["reduction_percent"], 70.6)
        self.assertEqual(result["dast_before_http"]["rules"], 5)
        self.assertEqual(result["dast_after_http"]["rules"], 3)
        self.assertEqual(result["dast_after_http"]["by_severity"]["LOW"], 0)

    def test_resultado_congelado_coincide_con_recalculo(self):
        saved = json.loads((ROOT.parent / "RESULTADOS-FINALES.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, calculate(ROOT))

    def test_cambios_en_evidencia_detectados(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "evidencias"
            shutil.copytree(ROOT, dest)
            file = dest / "dast04" / "zap.json"
            file.write_bytes(file.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "Evidencia modificada"):
                load_verified(dest)

    def test_falta_de_snapshot_bloquea(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "evidencias"
            shutil.copytree(ROOT, dest)
            (dest / "post04" / "npm.json").unlink()
            with self.assertRaises(FileNotFoundError):
                load_verified(dest)

    def test_manifiesto_incompleto_falla(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "evidencias"
            shutil.copytree(ROOT, dest)
            p = dest / "manifest.json"
            d = json.loads(p.read_text())
            d["files"].pop("baseline/npm.json")
            p.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError, "20 reportes"):
                load_verified(dest)


if __name__ == "__main__":
    unittest.main()
