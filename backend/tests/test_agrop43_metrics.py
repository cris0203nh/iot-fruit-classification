import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from metrics.evaluate_performance import evaluate_records


class TestAGROP43(unittest.TestCase):

    def setUp(self):
        self.records = [
            {"sample_id": "M1", "product": "mango",
             "y_true": "primera", "y_pred": "primera",
             "confidence": 0.95},
            {"sample_id": "M2", "product": "mango",
             "y_true": "primera", "y_pred": "segunda",
             "confidence": 0.70},
            {"sample_id": "M3", "product": "mango",
             "y_true": "segunda", "y_pred": "primera",
             "confidence": 0.80},
            {"sample_id": "M4", "product": "mango",
             "y_true": "segunda", "y_pred": "segunda",
             "confidence": 0.90},
            {"sample_id": "T1", "product": "tomate",
             "y_true": "primera", "y_pred": "primera",
             "confidence": 0.88},
        ]

    def test_matriz_confusion_mango(self):
        result = evaluate_records(self.records)
        matrix = result["products"]["mango"]["confusion_matrix"]

        self.assertEqual(matrix["primera"]["primera"], 1)
        self.assertEqual(matrix["primera"]["segunda"], 1)
        self.assertEqual(matrix["segunda"]["primera"], 1)
        self.assertEqual(matrix["segunda"]["segunda"], 1)

    def test_metricas_por_producto(self):
        result = evaluate_records(self.records)

        self.assertEqual(result["products"]["mango"]["accuracy"], 0.5)
        self.assertEqual(result["products"]["tomate"]["accuracy"], 1.0)

    def test_precision_recall_y_f1(self):
        result = evaluate_records(self.records)
        metrics = result["products"]["mango"]["metrics_by_category"]

        self.assertEqual(metrics["primera"]["precision"], 0.5)
        self.assertEqual(metrics["primera"]["recall"], 0.5)
        self.assertEqual(metrics["primera"]["f1_score"], 0.5)

    def test_no_evaluable_sin_etiqueta_real(self):
        records = [
            {"sample_id": "X1", "product": "mango",
             "y_true": None, "y_pred": "primera"}
        ]

        result = evaluate_records(records)

        self.assertEqual(result["valid_sample_count"], 0)
        self.assertEqual(result["non_evaluable_count"], 1)
        self.assertEqual(result["evaluation_status"], "insufficient_data")

    def test_confianza_no_es_exactitud(self):
        result = evaluate_records(self.records)

        self.assertEqual(
            result["products"]["mango"]["mean_confidence"],
            0.8375
        )
        self.assertEqual(
            result["products"]["mango"]["accuracy"],
            0.5
        )

    def test_identifica_errores(self):
        result = evaluate_records(self.records)

        self.assertEqual(len(result["classification_errors"]), 2)

    def test_rechaza_producto_no_admitido(self):
        records = [
            {"product": "manzana", "y_true": "primera",
             "y_pred": "primera"}
        ]

        result = evaluate_records(records)
        self.assertEqual(result["valid_sample_count"], 0)

    def test_rechaza_confianza_invalida(self):
        records = [
            {"product": "mango", "y_true": "primera",
             "y_pred": "primera", "confidence": 1.5}
        ]

        result = evaluate_records(records)
        self.assertEqual(result["valid_sample_count"], 0)


    def test_reporta_ambos_productos_sin_muestras_validas(self):
        records = [
            {
                "sample_id": "M-sin-etiqueta",
                "product": "mango",
                "y_true": None,
                "y_pred": "primera",
            },
            {
                "sample_id": "T-sin-etiqueta",
                "product": "tomate",
                "y_true": None,
                "y_pred": "segunda",
            },
        ]

        result = evaluate_records(records)

        self.assertEqual(
            set(result["products"].keys()),
            {"mango", "tomate"},
        )

        for product in ("mango", "tomate"):
            report = result["products"][product]

            self.assertEqual(report["sample_count"], 0)
            self.assertIsNone(report["accuracy"])

            for category in ("primera", "segunda"):
                metrics = report["metrics_by_category"][category]
                self.assertIsNone(metrics["precision"])
                self.assertIsNone(metrics["recall"])
                self.assertIsNone(metrics["f1_score"])
                self.assertEqual(metrics["support"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
