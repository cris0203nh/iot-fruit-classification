"""Regresión v2; imágenes sintéticas para las pruebas de código."""
import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image
from vision.evaluation.ag036.ingestar_dataset_multifuente import ingest, IngestionError

ROOT = "AgroScan_Imagenes_Revisadas_v2/"

def png(size=(64, 64)):
    data = io.BytesIO()
    Image.new("RGB", size, (90, 130, 30)).save(data, format="PNG")
    return data.getvalue()


class TestIngestaV2(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        self.zip = self.d / "imagenes.zip"
        self.out = self.d / "salida"

    def create_zip(self, entries):
        with zipfile.ZipFile(self.zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, blob in entries:
                archive.writestr(ROOT + name, blob)

    def inventory(self):
        with (self.out / "inventario_multifuente.csv").open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def test_new_folder_names_and_groups_v2(self):
        img = png()
        self.create_zip([
            ("01_ZIP_Capturas_reales/Mango_variedad/Candidato_M01_rojo/E-000024_a.png", img),
            ("01_ZIP_Capturas_reales/Tomate/Candidato_T02/E-000044_b.png", img + b"\x00"),
            ("02_Datasets_externos/Mango_Kent_COFiLAB_dos_vistas/KENT_EXT_01/Mango_01_A.png", img + b"\x01"),
            ("02_Datasets_externos/Tomate_Rojo_Hohenheim_3_vistas/TOM_EXT_01_Tc_01/Tc_0101_D3.png", img + b"\x02"),
        ])
        result = ingest(self.zip, self.out)
        self.assertEqual(result["fotografias_total"], 4)
        self.assertEqual(result["grupos_de_carpetas_candidatos"], 4)
        rows = self.inventory()
        self.assertEqual([x["producto_candidato"] for x in rows].count("tomate"), 2)
        self.assertTrue(all(not x["etiqueta_e0_e1_e2"] for x in rows))
        self.assertTrue(all(x["identidad_pieza_confirmada"] == "no" for x in rows))
        self.assertEqual(next(x for x in rows if x["grupo_candidato"].startswith("TOM_EXT"))["variedad_tipo_en_nombre"], "Rojo (solo carpeta)")

    def test_reject_unrecognized_names(self):
        self.create_zip([("02_Datasets_externos/Tomate_Desconocido/TOM_EXT_01/im.png", png())])
        with self.assertRaisesRegex(IngestionError, "Subcategoría no reconocida"):
            ingest(self.zip, self.out)

    def test_no_labels_or_confirmations(self):
        self.create_zip([("01_ZIP_Capturas_reales/Tomate/Candidato_T01/E-000028.png", png())])
        report = ingest(self.zip, self.out)
        self.assertEqual(report["etiquetas_e0_e1_e2_acreditadas"], 0)
        self.assertEqual(report["piezas_fisicas_independientes_acreditadas"], 0)
        self.assertFalse(report["aprobado_para_entrenamiento_supervisado"])

    def test_pixel_limit_shared_for_all_tools(self):
        from vision.evaluation.ag036.auditar_etiquetado import MAX_IMAGE_PIXELS
        self.assertGreaterEqual(MAX_IMAGE_PIXELS, 6000 * 3376)
        self.assertLessEqual(MAX_IMAGE_PIXELS, 24_000_000)

if __name__ == "__main__":
    unittest.main()
