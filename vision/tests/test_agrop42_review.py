"""Pruebas del Incremento 04: entradas sintéticas SOLO para validar el software."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from vision.evaluation.agrop42 import revisar_anotaciones as review
from vision.evaluation.agrop42 import auditar


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dataset = self.root / "dataset_v1"
        (self.dataset / "images").mkdir(parents=True)
        self.inv = []
        for n, (product, rgb) in enumerate((("mango", (100, 130, 40)),
                                              ("tomate", (200, 55, 40))), start=1):
            file = self.dataset / "images" / f"temp_{n}.png"
            Image.new("RGB", (160, 160), rgb).save(file)
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            new_name = f"images/{digest}.png"
            file.rename(self.dataset / new_name)
            self.inv.append({
                "record_id": f"REG-{n:05d}", "product": product, "sha256": digest,
                "image_path": new_name, "origin": "externo_original", "source_url": f"https://example.test/{n}",
                "source_id": f"EXT-{n}", "license": "CC BY 4.0", "rights_confirmed_declared": True,
                "visible_to_audit": True, "view": "vista-lateral",
                "variety_declared": "Kent" if product == "mango" else "tipo_pendiente",
            })
        self._write_inventory()
        self.template = self.root / "revision.csv"
        review.create_template(self.dataset, self.template)
        self.rows = review.read_reviews(self.template)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_inventory(self):
        (self.dataset / "inventory.json").write_text(json.dumps(self.inv), encoding="utf8")

    def _save_csv(self):
        with self.template.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=review.FIELDS)
            w.writeheader()
            w.writerows(self.rows)

    def _finish(self, name="rev_01"):
        self._save_csv()
        return review.finalize(self.dataset, self.template, self.root / name)

    def _reviewed(self, index=0, **more):
        row = self.rows[index]
        row.update({
            "estado_revision": "revisada", "revisor_id": "operador-de-prueba",
            "revisado_en": "2026-11-05T18:30:00-05:00",
            "rubrica_version": review.RUBRICS[row["producto"]],
            "nota_revision": "Inspección humana declarada para probar contrato, no una revisión real",
        })
        row.update(more)
        return row

    def _labeled(self, index=0, label="E1"):
        row = self._reviewed(index, calidad_confirmada="si", cobertura_confirmada="si",
                             etiqueta_visual=label, etiqueta_documentada="si",
                             justificacion_etiqueta="Declaración manual basada en criterio externo observado",
                             observacion_r03="Observación humana declarada de R03")
        if row["producto"] == "mango":
            row["variedad_verificada"] = "si"
            row["evidencia_variedad"] = "Referencia externa Kent revisada documentalmente"
        return row

    def test_plantilla_preserva_campos_e_inicia_sin_etiquetas(self):
        self.assertEqual(len(self.rows), 2)
        self.assertEqual({r["estado_revision"] for r in self.rows}, {"pendiente"})
        self.assertTrue(all(not r["etiqueta_visual"] and not r["revisor_id"] for r in self.rows))
        self.assertEqual(self.rows[0]["sha256"], self.inv[0]["sha256"])

    def test_plantilla_dentro_del_dataset_original_rechazada(self):
        with self.assertRaisesRegex(review.ReviewInputError, "fuera del dataset"):
            review.create_template(self.dataset, self.dataset / "revision.csv")

    def test_salida_revision_dentro_del_dataset_rechazada(self):
        self._save_csv()
        with self.assertRaisesRegex(review.ReviewInputError, "fuera del dataset"):
            review.finalize(self.dataset, self.template, self.dataset / "revision_interna")

    def test_plantilla_no_sobrescribe(self):
        with self.assertRaises(review.ReviewInputError):
            review.create_template(self.dataset, self.template)

    def test_revision_pendiente_no_inventa_etiquetas_ni_sesiones(self):
        result = self._finish()
        self.assertEqual(result["anotaciones_exportadas_para_auditoria"], 0)
        self.assertEqual(result["manifiestos_generados"], 2)
        files = list((self.root / "rev_01/manifests").glob("*.json"))
        self.assertTrue(files)
        for file in files:
            manifest = json.loads(file.read_text(encoding="utf-8"))
            self.assertIsNone(manifest["piece"]["piece_id"])
            self.assertIsNone(manifest["images"][0]["capture"]["boot_id"])
            self.assertIsNone(manifest["operator_visual_label"])
        rows, info = auditar._read_manifests(self.root / "rev_01/manifests", self.root)
        self.assertEqual(info["records"], 2)
        self.assertTrue(all(r["file_status"] == "valida" and r["session_key"] is None for r in rows))

    def test_etiqueta_declarada_genera_annotation_para_auditor_sin_crear_grupo(self):
        self._labeled()
        self._finish()
        path = self.root / "rev_01/annotations_to_review.json"
        ann, report = auditar._read_annotations(path)
        self.assertEqual(report["con_revision_documentada"], 1)
        self.assertEqual(ann[0]["label"], "E1")
        rows, _ = auditar._read_manifests(self.root / "rev_01/manifests", self.root)
        result = auditar.audit(rows, ann, {})
        self.assertEqual(result["por_producto"]["mango"]["grupos_independientes_verificables"], 0)
        self.assertEqual(result["status"], "bloqueado_por_datos_insuficientes")

    def test_no_evaluable_con_motivo_no_exporta_etiquetas(self):
        self._reviewed(0, estado_revision="no_evaluable", motivo_no_evaluable="Fondo no apto")
        report = self._finish()
        self.assertEqual(report["estados_revision"]["no_evaluable"], 1)
        self.assertEqual(report["anotaciones_exportadas_para_auditoria"], 0)

    def test_no_evaluable_no_se_exporta_a_manifiestos_elegibles(self):
        self._reviewed(0, estado_revision="no_evaluable", motivo_no_evaluable="No se distingue fruto único")
        result = self._finish()
        self.assertEqual(result["registros_fuera_de_manifiestos"], 1)
        manifests = list((self.root / "rev_01/manifests").glob("*.json"))
        self.assertEqual(len(manifests), 1)
        self.assertEqual(json.loads(manifests[0].read_text(encoding="utf8"))["piece"]["product"], "tomate")

    def test_excluida_no_se_exporta_a_manifiestos(self):
        self._reviewed(1, estado_revision="excluida", motivo_no_evaluable="Permiso no confirmado")
        result = self._finish()
        self.assertEqual(result["registros_fuera_de_manifiestos"], 1)

    def test_no_evaluable_sin_motivo_rechazado(self):
        self._reviewed(0, estado_revision="no_evaluable")
        with self.assertRaisesRegex(review.ReviewInputError, "motivo"):
            self._finish()

    def test_pendiente_con_etiqueta_rechazado(self):
        self.rows[0]["etiqueta_visual"] = "E1"
        with self.assertRaises(review.ReviewInputError):
            self._finish()

    def test_no_etiqueta_si_no_confirma_calidad(self):
        self._labeled()["calidad_confirmada"] = "pendiente"
        with self.assertRaisesRegex(review.ReviewInputError, "calidad"):
            self._finish()

    def test_no_etiqueta_si_no_confirma_cobertura(self):
        self._labeled()["cobertura_confirmada"] = "no"
        with self.assertRaisesRegex(review.ReviewInputError, "cobertura"):
            self._finish()

    def test_mango_sin_verificar_variedad_no_recibe_etiqueta(self):
        self._labeled()["variedad_verificada"] = "pendiente"
        with self.assertRaisesRegex(review.ReviewInputError, "Kent"):
            self._finish()

    def test_tomate_no_necesita_verificar_kent(self):
        self._labeled(index=1, label="E2")
        result = self._finish()
        self.assertEqual(result["por_producto"]["tomate"]["anotaciones_con_revision_documentada"], 1)

    def test_etiqueta_sin_observacion_de_rubrica_no_procede(self):
        self._labeled()["observacion_r03"] = ""
        with self.assertRaisesRegex(review.ReviewInputError, "criterio"):
            self._finish()

    def test_fecha_sin_zona_horaria_no_procede(self):
        self._reviewed(revisado_en="2026-11-05T18:30:00")
        with self.assertRaisesRegex(review.ReviewInputError, "zona horaria"):
            self._finish()

    def test_rubrica_incorrecta_rechazada(self):
        self._reviewed(rubrica_version="tomato-ext-v0.1")
        with self.assertRaisesRegex(review.ReviewInputError, "rúbrica"):
            self._finish()

    def test_sha_inalterable_en_csv(self):
        self.rows[0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(review.ReviewInputError, "solo lectura"):
            self._finish()

    def test_prohibido_modificar_producto_del_csv(self):
        self.rows[0]["producto"] = "tomate"
        with self.assertRaisesRegex(review.ReviewInputError, "solo lectura"):
            self._finish()

    def test_falta_una_fila_rechazada(self):
        self.rows.pop()
        with self.assertRaisesRegex(review.ReviewInputError, "filas"):
            self._finish()

    def test_fila_duplicada_rechazada(self):
        self.rows[1]["registro_id"] = self.rows[0]["registro_id"]
        with self.assertRaisesRegex(review.ReviewInputError, "filas"):
            self._finish()

    def test_sha_del_archivo_alterado_rechazado(self):
        source = self.dataset / self.inv[0]["image_path"]
        source.write_bytes(source.read_bytes() + b"cambio")
        with self.assertRaisesRegex(review.ReviewInputError, "modificada"):
            self._finish()

    def test_ruta_de_archivo_traversal_rechazada(self):
        self.inv[0]["image_path"] = "../fuera.png"
        self._write_inventory()
        with self.assertRaisesRegex(review.ReviewInputError, "ruta"):
            self._finish()

    def test_fuente_excluida_no_puede_generar_etiqueta(self):
        self.inv[0]["visible_to_audit"] = False
        self._write_inventory()
        self._labeled()
        with self.assertRaisesRegex(review.ReviewInputError, "fuente excluida"):
            self._finish()

    def test_pieza_sin_evidencia_rechazada(self):
        self._reviewed(pieza_confirmada="si", lote_id="LOTE-1", pieza_id="PIEZA-1")
        with self.assertRaisesRegex(review.ReviewInputError, "evidencia"):
            self._finish()

    def test_sesion_sin_pieza_rechazada(self):
        self._reviewed(sesion_confirmada="si", dispositivo_id="CAM-1", sesion_id="RUN-1", evidencia_sesion="EXIF")
        with self.assertRaisesRegex(review.ReviewInputError, "pieza confirmada"):
            self._finish()

    def test_pieza_y_sesion_con_evidencia_generan_un_grupo_para_auditoria(self):
        self._reviewed(pieza_confirmada="si", lote_id="LOT", pieza_id="FRUTA-1",
                       evidencia_pieza="Registro fotográfico enlazado al código real",
                       sesion_confirmada="si", dispositivo_id="CAM-1", sesion_id="SES-1",
                       evidencia_sesion="Bitácora de cámara verificada")
        self._finish()
        rows, _ = auditar._read_manifests(self.root / "rev_01/manifests", self.root)
        self.assertEqual(len([r for r in rows if r["piece_key"] and r["session_key"]]), 1)
        result = auditar.audit(rows, [], {})
        self.assertEqual(result["por_producto"]["mango"]["grupos_independientes_verificables"], 1)

    def test_revisada_sin_etiqueta_no_inventa_etiqueta(self):
        self._reviewed()
        result = self._finish()
        self.assertEqual(result["estados_revision"]["revisada"], 1)
        self.assertEqual(result["anotaciones_exportadas_para_auditoria"], 0)

    def test_no_sobrescribir_informe_generado(self):
        self._finish()
        with self.assertRaisesRegex(review.ReviewInputError, "ya existe"):
            self._finish()

    def test_similitud_sospechosa_impide_declarar_dos_piezas_sin_evidencia(self):
        (self.dataset / "report.json").write_text(json.dumps({"near_duplicate_candidates_dhash": [
            {"registro_1": self.inv[0]["record_id"], "registro_2": self.inv[1]["record_id"], "distancia_dhash": 3}
        ]}), encoding="utf8")
        for i in range(2):
            self._reviewed(i, pieza_confirmada="si", lote_id="LOT", pieza_id=f"PIEZA-{i}",
                           evidencia_pieza="Registro externo verificable de identidad física")
        with self.assertRaisesRegex(review.ReviewInputError, "duplicado visual"):
            self._finish()

    def test_similitud_documentada_permite_piezas_distintas_declaradas(self):
        (self.dataset / "report.json").write_text(json.dumps({"near_duplicate_candidates_dhash": [
            {"registro_1": self.inv[0]["record_id"], "registro_2": self.inv[1]["record_id"], "distancia_dhash": 3}
        ]}), encoding="utf8")
        for i in range(2):
            self._reviewed(i, pieza_confirmada="si", lote_id="LOT", pieza_id=f"PIEZA-{i}",
                           evidencia_pieza="Identidad física documentada",
                           revision_similitud="distintas_piezas", evidencia_similitud="Fotos de piezas físicas separadas verificadas")
        result = self._finish()
        self.assertEqual(result["pares_dhash_sospechosos"], 1)
        self.assertEqual(result["pares_dhash_sin_independencia_confirmada"], 0)

    def test_reporte_sin_revision_no_declara_etapas_terminadas(self):
        result = self._finish()
        self.assertEqual(result["status"], "sin_revisiones_efectuadas")

    def test_mango_r09_no_admitido(self):
        self._reviewed(observacion_r09="Campo fuera de rúbrica Kent")
        with self.assertRaisesRegex(review.ReviewInputError, "R09"):
            self._finish()

    def test_original_no_se_modifica_al_exportar(self):
        original = (self.dataset / self.inv[0]["image_path"]).read_bytes()
        self._finish()
        self.assertEqual((self.dataset / self.inv[0]["image_path"]).read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
