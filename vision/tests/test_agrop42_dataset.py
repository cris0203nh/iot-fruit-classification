"""Pruebas estructurales con imágenes artificiales TEMPORALES, nunca datasets de aprendizaje."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from vision.evaluation.agrop42.preparar_dataset import (
    FIELDNAMES, DatasetPreparationError, _BKTree, _read_csv, prepare,
)


class DatasetPreparationTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.images = self.root / "fotos"
        self.images.mkdir()
        self.out = self.root / "AGROP42_dataset_v1"
        self._save("a.png", (120, 150, 40))
        self._save("b.png", (180, 190, 55))
        self._save("t.png", (210, 60, 40))
        self.row = {name: "" for name in FIELDNAMES}
        self.row.update({
            "archivo": "a.png", "producto": "mango", "tipo_fuente": "captura_propia",
            "fuente_id": "equipo-agroscan", "licencia": "propia",
            "derechos_confirmados": "true", "evidencia_derechos": "declaracion_de_captura",
            "lote_id": "L-1", "pieza_id": "P-1", "pieza_confirmada": "true",
            "dispositivo_id": "cam1", "sesion_id": "sesion-real-1", "vista": "lateral",
            "variedad_declarada": "Kent", "variedad_confirmada": "true",
            "evidencia_variedad": "registro_de_proveedor",
        })

    def _save(self, name, rgb):
        Image.new("RGB", (160, 145), rgb).save(self.images / name)

    def _load(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def test_importa_original_sin_modificar_foto(self):
        report = prepare([self.row], self.images, self.out)
        self.assertEqual(report["photographic_records"], 1)
        self.assertEqual(report["exported_records_to_auditor"], 1)
        item = self._load(self.out / "inventory.json")[0]
        original_hash = hashlib.sha256((self.images / "a.png").read_bytes()).hexdigest()
        self.assertEqual(item["sha256"], original_hash)
        self.assertEqual((self.out / item["image_path"]).read_bytes(), (self.images / "a.png").read_bytes())

    def test_manifiesto_compatible_con_auditor_y_sesion(self):
        prepare([self.row], self.images, self.out)
        payload = self._load(next((self.out / "manifests").glob("*.json")))
        self.assertEqual(payload["piece"]["product"], "mango")
        self.assertEqual(payload["piece"]["piece_id"], "P-1")
        self.assertEqual(payload["images"][0]["capture"], {"device_id": "cam1", "boot_id": "sesion-real-1"})
        self.assertIsNone(payload["operator_visual_label"])
        self.assertEqual(self._load(self.out / "annotations_to_review.json"), {"annotations": []})

    def test_dos_vistas_una_pieza_no_dos_grupos(self):
        other = {**self.row, "archivo": "b.png", "vista": "superior"}
        report = prepare([self.row, other], self.images, self.out)
        self.assertEqual(report["manifest_count"], 1)
        self.assertEqual(len(self._load(next((self.out / "manifests").glob("*.json")))["images"]), 2)

    def test_sha_repetido_no_se_copia_dos_veces(self):
        second = {**self.row, "archivo": "a.png", "vista": "posterior"}
        report = prepare([self.row, second], self.images, self.out)
        self.assertEqual(report["unique_files_sha256"], 1)
        self.assertEqual(len(list((self.out / "images").iterdir())), 1)
        self.assertEqual(len(report["duplicate_sha_groups"]), 1)

    def test_externo_sin_derechos_confirmados_fuera_de_auditoria(self):
        ext = {**self.row, "tipo_fuente": "externo_original", "fuente_id": "external-1",
               "fuente_url": "https://data.example.org/id", "licencia": "pendiente",
               "derechos_confirmados": "false", "evidencia_derechos": "",
               "variedad_confirmada": "false", "evidencia_variedad": ""}
        report = prepare([ext], self.images, self.out)
        self.assertEqual(report["exported_records_to_auditor"], 0)
        self.assertEqual(len(list((self.out / "manifests").iterdir())), 0)

    def test_imagen_sintetica_no_se_exporta_para_entrenamiento(self):
        generated = {**self.row, "tipo_fuente": "sintetica"}
        report = prepare([generated], self.images, self.out)
        self.assertEqual(report["excluded_from_auditor"], 1)
        self.assertEqual(report["unique_files_sha256"], 1)

    def test_aumentada_no_se_exporta_para_entrenamiento(self):
        generated = {**self.row, "tipo_fuente": "aumentada"}
        report = prepare([generated], self.images, self.out)
        self.assertEqual(report["excluded_from_auditor"], 1)

    def test_variedad_kent_no_confirmada_fuera_de_auditoria(self):
        row = {**self.row, "variedad_confirmada": "false", "evidencia_variedad": ""}
        report = prepare([row], self.images, self.out)
        self.assertEqual(report["exported_records_to_auditor"], 0)

    def test_tomate_no_requiere_variedad_kent(self):
        row = {**self.row, "archivo": "t.png", "producto": "tomate",
               "variedad_declarada": "", "variedad_confirmada": "false", "evidencia_variedad": ""}
        report = prepare([row], self.images, self.out)
        self.assertEqual(report["tomato_records"], 1)
        self.assertEqual(report["exported_records_to_auditor"], 1)

    def test_pieza_no_verificada_no_se_inventa_identidad(self):
        row = {**self.row, "pieza_confirmada": "false", "pieza_id": "P-no-verificado"}
        prepare([row], self.images, self.out)
        payload = self._load(next((self.out / "manifests").glob("*.json")))
        self.assertIsNone(payload["piece"]["piece_id"])

    def test_sesion_no_verificada_no_se_inventa(self):
        row = {**self.row, "sesion_id": ""}
        prepare([row], self.images, self.out)
        payload = self._load(next((self.out / "manifests").glob("*.json")))
        self.assertIsNone(payload["images"][0]["capture"]["boot_id"])

    def test_no_sobrescribe_salida_preexistente(self):
        self.out.mkdir()
        sentinel = self.out / "manual.txt"
        sentinel.write_text("intacto")
        with self.assertRaisesRegex(DatasetPreparationError, "ya existe"):
            prepare([self.row], self.images, self.out)
        self.assertEqual(sentinel.read_text(), "intacto")

    def test_no_copia_si_fila_invalida(self):
        other = {**self.row, "archivo": "missing.png"}
        with self.assertRaisesRegex(DatasetPreparationError, "inexistente"):
            prepare([self.row, other], self.images, self.out)
        self.assertFalse(self.out.exists())

    def test_no_acepta_ruta_fuera_de_input(self):
        row = {**self.row, "archivo": "../otra.png"}
        with self.assertRaisesRegex(DatasetPreparationError, "sale del directorio"):
            prepare([row], self.images, self.out)

    def test_rechaza_confirmacion_de_variedad_sin_evidencia(self):
        row = {**self.row, "evidencia_variedad": ""}
        with self.assertRaisesRegex(DatasetPreparationError, "evidencia_variedad"):
            prepare([row], self.images, self.out)

    def test_rechaza_permisos_sin_soporte(self):
        row = {**self.row, "evidencia_derechos": ""}
        with self.assertRaisesRegex(DatasetPreparationError, "evidencia_derechos"):
            prepare([row], self.images, self.out)

    def test_original_label_no_es_verdad_terreno(self):
        row = {**self.row, "etiqueta_fuente": "good"}
        prepare([row], self.images, self.out)
        self.assertEqual(self._load(self.out / "annotations_to_review.json")["annotations"], [])
        self.assertEqual(self._load(self.out / "inventory.json")[0]["original_label_unverified"], "good")

    def test_imagen_invalida_rechazada(self):
        (self.images / "bad.png").write_bytes(b"no es png")
        with self.assertRaisesRegex(DatasetPreparationError, "decodificar"):
            prepare([{**self.row, "archivo": "bad.png"}], self.images, self.out)

    def test_csv_plantilla_y_columnas(self):
        csv_path = self.root / "carga.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerow(self.row)
        result = _read_csv(csv_path)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["producto"], "mango")

    def test_dhash_independiente_no_dedup_automaticamente(self):
        row = {**self.row, "archivo": "b.png", "pieza_id": "P-2"}
        report = prepare([self.row, row], self.images, self.out)
        self.assertEqual(report["unique_files_sha256"], 2)
        self.assertEqual(len(list((self.out / "images").iterdir())), 2)
        self.assertGreaterEqual(len(report["near_duplicate_candidates_dhash"]), 1)

    def test_integracion_con_auditoria_incremento_01(self):
        from vision.evaluation.agrop42.auditar import run

        prepare([self.row], self.images, self.out)
        result = run(
            db=self.root / "sin_base.db", data_root=self.root,
            allowed_root=self.root, manifests_dir=self.out / "manifests",
            annotations_file=self.out / "annotations_to_review.json",
        )
        self.assertEqual(result["totales"]["registros_fotograficos"], 1)
        self.assertEqual(result["por_producto"]["mango"]["grupos_independientes_verificables"], 1)
        self.assertEqual(result["por_producto"]["mango"]["imagenes_con_revision_documentada"], 0)
        self.assertEqual(result["status"], "bloqueado_por_datos_insuficientes")

    def test_arbol_bk_distancias(self):
        tree = _BKTree()
        self.assertEqual(tree.insert(0b0, "first"), [])
        near = tree.insert(0b111, "second")
        self.assertEqual(near[0][1], "first")
        self.assertEqual(near[0][2], 3)


if __name__ == "__main__":
    unittest.main()
