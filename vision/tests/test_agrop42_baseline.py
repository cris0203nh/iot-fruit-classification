"""Pruebas de contrato AGROP-42 Incremento 02; datos inventados SOLO para QA."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from vision.evaluation.agrop42.baseline_reglas import (
    RulesInputError, baseline, evaluate_rules, identify_report, main, read_reports,
)


def mango(status="evaluable", images=None):
    if images is None:
        images = [{"status": "valida", "mask_analysis": {"status": "operator_selected_provisional_masks"},
                   "surface_analysis": {"status": "single_candidate_unverified"}}]
    return {"task": "AGROP-40", "pipeline_version": "v0.3", "rubric_version": "kent-ext-v0.5",
            "piece": {"product": "mango"}, "experiment_id": "M-1", "visual_status": status,
            "criteria": {"R01": {}}, "images": images, "visual_label": None}


def tomato(status="evaluable", images=None):
    if images is None:
        images = [{"quality_status": "evaluable", "mask_analysis": {"status": "pending_operator_selection"}}]
    return {"product": "tomate", "rubric_version": "tomato-ext-v0.1",
            "automated_commercial_classification": False, "experiment_id": "T-1",
            "visual_status": status, "criteria": {"R01": {}}, "images": images, "operator_visual_label": "E1"}


class BaselineRulesTests(unittest.TestCase):
    def test_identifica_mango(self):
        self.assertEqual(identify_report(mango()), "mango")

    def test_identifica_tomate(self):
        self.assertEqual(identify_report(tomato()), "tomate")

    def test_no_confunde_manifiesto_con_reporte(self):
        self.assertIsNone(identify_report({"piece": {"product": "mango"}, "images": []}))

    def test_rechaza_reporte_no_soportado(self):
        with self.assertRaises(RulesInputError):
            evaluate_rules({"product": "banano"})

    def test_mango_apta_para_revision_externa_no_comercial(self):
        r = evaluate_rules(mango())
        self.assertEqual(r["decision_tecnica"], "apta_para_revision_externa")
        self.assertIsNone(r["predicted_visual_label"])
        self.assertFalse(r["commercial_quality_assessed"])

    def test_mango_cobertura_pendiente(self):
        r = evaluate_rules(mango(status="pendiente_revision"))
        self.assertEqual(r["decision_tecnica"], "revision_de_captura_pendiente")

    def test_sin_imagenes_no_evaluable(self):
        r = evaluate_rules(mango(images=[]))
        self.assertEqual(r["decision_tecnica"], "no_evaluable")

    def test_reconocimiento_fuera_alcance(self):
        self.assertEqual(evaluate_rules(mango(status="no_reconocido"))["decision_tecnica"], "fuera_de_alcance")

    def test_no_evaluable_precede_errores(self):
        self.assertEqual(evaluate_rules(mango(status="no_evaluable"))["decision_tecnica"], "no_evaluable")

    def test_recaptura_precede_mascara(self):
        r = evaluate_rules(tomato(images=[{"quality_status": "recaptura_requerida"}]))
        self.assertEqual(r["decision_tecnica"], "recaptura_requerida")

    def test_mango_no_evaluable_por_foco_prioriza_recaptura(self):
        data = mango(status="no_evaluable", images=[{"status": "error", "reason": "recaptura_requerida_por_revision"}])
        self.assertEqual(evaluate_rules(data)["decision_tecnica"], "recaptura_requerida")

    def test_tomate_mascara_no_confirmada(self):
        self.assertEqual(evaluate_rules(tomato())["decision_tecnica"], "revision_de_segmentacion")

    def test_mango_dos_region_candidato_ambiguo(self):
        data = mango(images=[{"status": "valida", "surface_analysis": {"status": "ambiguous_multiple_regions"},
                              "mask_analysis": {"status": "operator_selected_provisional_masks"}}])
        self.assertEqual(evaluate_rules(data)["rule_ids"], ["R07_REGIONES_AMBIGUAS"])

    def test_tomate_captura_inconsistente(self):
        data = tomato(images=[{"quality_status": "pendiente_revision"}])
        self.assertEqual(evaluate_rules(data)["rule_ids"], ["R06_ESTADO_IMAGENES_INCONSISTENTE"])

    def test_rgb_no_influye_en_clase(self):
        a = mango()
        b = copy.deepcopy(a)
        b["images"][0]["roi_descriptor"] = {"median_rgb": [255, 0, 0]}
        self.assertEqual(evaluate_rules(a), evaluate_rules(b))

    def test_etiqueta_del_operador_no_es_prediccion(self):
        r = evaluate_rules(tomato())
        self.assertIsNone(r["predicted_visual_label"])
        self.assertFalse(r["defect_detection_performed"])

    def test_determinismo(self):
        a = mango()
        self.assertEqual(evaluate_rules(a), evaluate_rules(a))

    def test_auditoria_bloqueada_no_produce_metricas(self):
        audit = {"task": "AGROP-42", "status": "bloqueado_por_datos_insuficientes", "por_producto": {}}
        out = baseline([("mango.json", mango())], audit, repeats=3)
        self.assertTrue(out["comparison"]["model_comparison_blocked"])
        self.assertIsNone(out["comparison"]["f1"])
        self.assertIsNone(out["comparison"]["accuracy"])
        self.assertEqual(out["decisions_by_product"]["mango"], {"apta_para_revision_externa": 1})

    def test_auditoria_potencial_no_finge_modelo(self):
        audit = {"task": "AGROP-42", "status": "potencial_para_particion_por_producto", "por_producto": {}}
        result = baseline([("tomato.json", tomato())], audit, repeats=2)
        self.assertFalse(result["comparison"]["lightweight_model_trained"])
        self.assertFalse(result["comparison"]["same_test_set_comparison_performed"])

    def test_latencias_no_negativas_scope_explicito(self):
        out = baseline([("1", mango()), ("2", tomato())], repeats=5)
        self.assertEqual(out["timing"]["runs"], 10)
        self.assertGreaterEqual(out["timing"]["median_ms"], 0)
        self.assertIn("no_incluye_decodificacion", out["timing"]["scope"])

    def test_repeats_invalidos(self):
        for n in (0, 1001, True):
            with self.subTest(n=n), self.assertRaises(RulesInputError):
                baseline([], repeats=n)

    def test_sin_reportes_es_honesto(self):
        out = baseline([], repeats=1)
        self.assertEqual(out["status"], "sin_informes_de_pipeline")
        self.assertIsNone(out["timing"])

    def test_auditoria_malformada(self):
        with self.assertRaises(RulesInputError):
            baseline([], {"status": "ok"})

    def test_reader_ignora_manifest_y_json_roto(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mango.json").write_text(json.dumps(mango()), encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps({"piece": {}, "images": []}), encoding="utf-8")
            (root / "invalid.json").write_text("{", encoding="utf-8")
            reports, skipped = read_reports(root)
            self.assertEqual(len(reports), 1)
            self.assertEqual(skipped, {"skipped_not_pipeline_report": 1, "invalid_json": 1})

    def test_cli_genera_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tomato.json").write_text(json.dumps(tomato()), encoding="utf-8")
            out = root / "baseline.json"
            self.assertEqual(main(["--reports-dir", str(root), "--output", str(out), "--repeats", "2"]), 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["evaluated_pipeline_reports"], 1)
            self.assertIsNone(data["comparison"]["precision"])


if __name__ == "__main__":
    unittest.main()
