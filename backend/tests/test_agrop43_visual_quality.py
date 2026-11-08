"""Regresión de la vía visual AG-035; ejemplos sintéticos, no resultados reales."""
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from metrics.evaluate_visual_quality import evaluate_visual_records, main


def entry(sample, product="mango", grade="E0", predicted="E0", lot="L1",
          piece=None, **kwargs):
    d = {
        "sample_id": sample, "product": product, "lot_id": lot,
        "piece_id": piece or sample,
        "variedad_declarada": "Kent" if product == "mango" else "tomate de prueba",
        "rubric_version": "kent-ext-v0.4" if product == "mango" else "tomato-ext-v0.2",
        "y_true": grade, "y_pred": predicted, "confidence": 0.8,
        "label_verification": "verified", "ground_truth_source": "AG036_acuerdo_doble",
        "ground_truth_reference": "acta-01", "prediction_source": "model",
        "prediction_verification": "verified", "source_model_version": "modelo-test-v1",
        "source_status": "completed",
    }
    d.update(kwargs)
    return d


class TestAG035Visual(unittest.TestCase):
    def test_vacio_no_fabrica_metricas(self):
        r = evaluate_visual_records([])
        self.assertEqual(r["valid_sample_count"], 0)
        self.assertIsNone(r["coverage_evaluable"])
        self.assertIsNone(r["products"]["mango"]["accuracy"])
        self.assertIsNone(r["products"]["tomate"]["macro_f1_tres_clases"])

    def test_seis_piezas_matriz_y_metricas(self):
        rows = [entry("M1", grade="E0"), entry("M2", grade="E0", predicted="E1"),
                entry("M3", grade="E1", predicted="E1"),
                entry("M4", grade="E1", predicted="E2"),
                entry("M5", grade="E2", predicted="E2"),
                entry("M6", grade="E2", predicted="E0")]
        r = evaluate_visual_records(rows)
        m = r["products"]["mango"]
        self.assertEqual(r["valid_sample_count"], 6)
        self.assertEqual(m["accuracy"], 0.5)
        self.assertEqual(m["confusion_matrix"]["E0"]["E1"], 1)
        self.assertAlmostEqual(m["macro_f1_tres_clases"], .5)
        self.assertEqual(m["n_clases_presentes"], 3)
        self.assertEqual(len(r["classification_errors"]), 3)
        self.assertEqual(r["classification_errors"][0]["error_type"], "confusion_entre_grados_visuales")

    def test_tomate_y_mango_separados(self):
        r = evaluate_visual_records([entry("M1"), entry("T1", product="tomate", grade="E2", predicted="E1")])
        self.assertEqual(r["products"]["mango"]["accuracy"], 1)
        self.assertEqual(r["products"]["tomate"]["accuracy"], 0)
        self.assertIsNone(r["products"]["tomate"]["macro_f1_tres_clases"])

    def test_comercial_no_se_convierte_a_visual(self):
        r = evaluate_visual_records([entry("M1", grade="primera", predicted="segunda")])
        self.assertEqual(r["valid_sample_count"], 0)
        self.assertEqual(r["non_evaluable_cases"][0]["reason"], "etiqueta_visual_e0e1e2_ausente_o_invalida")

    def test_fuente_ia_no_se_acepta_como_verdad_humana(self):
        r = evaluate_visual_records([entry("M1", ground_truth_source="prediccion_ia")])
        self.assertEqual(r["valid_sample_count"], 0)

    def test_sin_referencias_humanas(self):
        r = evaluate_visual_records([entry("M1", ground_truth_reference="")])
        self.assertEqual(r["valid_sample_count"], 0)

    def test_sin_etiqueta_verificada(self):
        r = evaluate_visual_records([entry("M1", label_verification="pending")])
        self.assertEqual(r["valid_sample_count"], 0)

    def test_prediccion_no_proviene_de_modelo(self):
        r = evaluate_visual_records([entry("M1", prediction_source="human")])
        self.assertEqual(r["valid_sample_count"], 0)

    def test_prediccion_no_verificada(self):
        r = evaluate_visual_records([entry("M1", prediction_verification="pending")])
        self.assertEqual(r["valid_sample_count"], 0)

    def test_falta_version_modelo(self):
        r = evaluate_visual_records([entry("M1", source_model_version="")])
        self.assertEqual(r["valid_sample_count"], 0)

    def test_ataulfo_no_se_toma_como_kent(self):
        r = evaluate_visual_records([entry("M1", variedad_declarada="Ataulfo")])
        self.assertEqual(r["non_evaluable_cases"][0]["reason"], "variedad_kent_no_declarada")

    def test_mango_sin_variedad(self):
        r = evaluate_visual_records([entry("M1", variedad_declarada="")])
        self.assertEqual(r["valid_sample_count"], 0)

    def test_rubrica_de_otro_producto(self):
        r = evaluate_visual_records([entry("M1", rubric_version="tomato-ext-v0.2")])
        self.assertEqual(r["valid_sample_count"], 0)

    def test_rubricas_mezcladas_bloqueadas_por_producto(self):
        r = evaluate_visual_records([entry("M1"), entry("M2", rubric_version="kent-ext-v0.5")])
        self.assertEqual(r["valid_sample_count"], 0)
        self.assertEqual(r["non_evaluable_count"], 2)

    def test_varias_vistas_de_misma_pieza_no_duplican_metricas(self):
        r = evaluate_visual_records([entry("Vista1", piece="P1"), entry("Vista2", piece="P1")])
        self.assertEqual(r["valid_sample_count"], 0)
        self.assertEqual(r["non_evaluable_count"], 2)

    def test_misma_pieza_diferentes_lotes_son_independientes(self):
        r = evaluate_visual_records([entry("M1", piece="P1", lot="L1"), entry("M2", piece="P1", lot="L2")])
        self.assertEqual(r["valid_sample_count"], 2)

    def test_sample_id_duplicado_se_bloquea(self):
        r = evaluate_visual_records([entry("M1", piece="P1"), entry("M1", piece="P2")])
        self.assertEqual(r["valid_sample_count"], 0)

    def test_falta_identidad_de_pieza(self):
        r = evaluate_visual_records([entry("M1", piece_id="")])
        self.assertEqual(r["valid_sample_count"], 0)

    def test_estado_no_finalizado(self):
        r = evaluate_visual_records([entry("M1", source_status="processing")])
        self.assertEqual(r["valid_sample_count"], 0)

    def test_confianza_no_finita_o_booleana(self):
        for confidence in (float("nan"), float("inf"), -0.1, 1.5, True, "0.9"):
            with self.subTest(confidence=str(confidence)):
                r = evaluate_visual_records([entry("M1", confidence=confidence)])
                self.assertEqual(r["valid_sample_count"], 0)

    def test_confianza_ausente_es_admisible(self):
        r = evaluate_visual_records([entry("M1", confidence=None)])
        self.assertEqual(r["valid_sample_count"], 1)
        self.assertIsNone(r["products"]["mango"]["mean_confidence"])

    def test_rechaza_producto_no_admitido(self):
        r = evaluate_visual_records([entry("P1", product="manzana")])
        self.assertEqual(r["valid_sample_count"], 0)

    def test_registro_invalido(self):
        r = evaluate_visual_records([None, 10, []])
        self.assertEqual(r["non_evaluable_count"], 3)

    def test_input_no_lista(self):
        with self.assertRaises(ValueError):
            evaluate_visual_records({})

    def test_declara_limitaciones_externas(self):
        r = evaluate_visual_records([entry("M1")])
        self.assertFalse(r["external_evidence_independently_verified_by_software"])
        self.assertFalse(r["AG036_double_review_independence_automatically_verified"])
        self.assertFalse(r["commercial_category_comparison_authorized"])

    def test_cli_plantilla_vacia(self):
        with tempfile.TemporaryDirectory() as temp:
            src, out = Path(temp)/"entrada.json", Path(temp)/"salida.json"
            src.write_text("[]", encoding="utf-8")
            self.assertEqual(main(["--input", str(src), "--output", str(out)]), 0)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(report["valid_sample_count"], 0)

    def test_cli_no_sobrescribe(self):
        with tempfile.TemporaryDirectory() as temp:
            src = Path(temp)/"entrada.json"
            src.write_text("[]", encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                main(["--input", str(src), "--output", str(src)])
            self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
