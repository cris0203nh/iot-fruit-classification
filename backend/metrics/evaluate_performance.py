"""AGROP-43: evaluacion del desempeno del clasificador."""

import argparse
import json
from collections import Counter
from pathlib import Path

PRODUCTS = ("mango", "tomate")
CATEGORIES = ("primera", "segunda")


def evaluate_records(records):
    if not isinstance(records, list):
        raise ValueError("Los registros deben ser una lista.")

    results = {
        product: {
            "matrix": {
                actual: {pred: 0 for pred in CATEGORIES}
                for actual in CATEGORIES
            },
            "total": 0,
            "confidence_values": [],
            "correct": 0,
        }
        for product in PRODUCTS
    }
    errors = []
    non_evaluable = []
    valid_count = 0

    for index, row in enumerate(records):
        if not isinstance(row, dict):
            non_evaluable.append({
                "index": index,
                "reason": "registro_invalido"
            })
            continue

        product = str(row.get("product", "")).strip().lower()
        sample_id = row.get("sample_id", str(index))

        if product not in PRODUCTS:
            non_evaluable.append({
                "sample_id": sample_id,
                "reason": "producto_no_admitido"
            })
            continue

        true_label = str(row.get("y_true") or "").strip().lower()
        predicted = str(row.get("y_pred") or "").strip().lower()

        if true_label not in CATEGORIES:
            non_evaluable.append({
                "sample_id": sample_id,
                "product": product,
                "reason": "etiqueta_real_no_verificada_o_invalida"
            })
            continue

        if predicted not in CATEGORIES:
            non_evaluable.append({
                "sample_id": sample_id,
                "product": product,
                "reason": "prediccion_no_disponible_o_invalida"
            })
            continue

        confidence = row.get("confidence")

        if confidence is not None:
            if (
                isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not 0 <= confidence <= 1
            ):
                non_evaluable.append({
                    "sample_id": sample_id,
                    "product": product,
                    "reason": "confianza_invalida"
                })
                continue

        if product not in results:
            results[product] = {
                "matrix": {
                    actual: {pred: 0 for pred in CATEGORIES}
                    for actual in CATEGORIES
                },
                "total": 0,
                "confidence_values": [],
                "correct": 0,
            }

        item = results[product]
        item["matrix"][true_label][predicted] += 1
        item["total"] += 1
        valid_count += 1

        if confidence is not None:
            item["confidence_values"].append(confidence)

        if true_label == predicted:
            item["correct"] += 1
        else:
            errors.append({
                "sample_id": sample_id,
                "product": product,
                "actual": true_label,
                "predicted": predicted,
                "error_type": (
                    "falso_positivo" if predicted == "primera"
                    else "falso_negativo"
                ),
                "confidence": confidence,
            })

    product_reports = {}

    for product, item in results.items():
        matrix = item["matrix"]
        metrics = {}

        for category in CATEGORIES:
            tp = matrix[category][category]
            fp = sum(
                matrix[actual][category]
                for actual in CATEGORIES if actual != category
            )
            fn = sum(
                matrix[category][pred]
                for pred in CATEGORIES if pred != category
            )

            precision = tp / (tp + fp) if tp + fp else None
            recall = tp / (tp + fn) if tp + fn else None

            f1 = (
                2 * precision * recall / (precision + recall)
                if precision is not None
                and recall is not None
                and precision + recall > 0
                else None
            )

            metrics[category] = {
                "precision": precision,
                "recall": recall,
                "f1_score": f1,
                "support": sum(matrix[category].values()),
            }

        confidence_values = item["confidence_values"]

        product_reports[product] = {
            "evaluation_status": (
                "evaluated" if item["total"] else "insufficient_data"
            ),
            "sample_count": item["total"],
            "confusion_matrix": matrix,
            "accuracy": item["correct"] / item["total"] if item["total"] else None,
            "metrics_by_category": metrics,
            "mean_confidence": (
                sum(confidence_values) / len(confidence_values)
                if confidence_values else None
            ),
            "confidence_sample_count": len(confidence_values),
        }

    return {
        "story": "AGROP-43",
        "version": "1.1",
        "products": product_reports,
        "total_records": len(records),
        "valid_sample_count": valid_count,
        "non_evaluable_count": len(non_evaluable),
        "non_evaluable_cases": non_evaluable,
        "classification_errors": errors,
        "evaluation_status": (
            "evaluated" if valid_count else "insufficient_data"
        ),
        "warning": (
            "Las metricas requieren etiquetas reales verificadas "
            "y predicciones independientes del modelo. "
            "La confianza no representa exactitud."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluador de desempeno AGROP-43"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source = Path(args.input)
    records = json.loads(source.read_text(encoding="utf-8"))

    result = evaluate_records(records)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("AGROP-43: evaluacion finalizada")
    print("Estado:", result["evaluation_status"])
    print("Muestras evaluables:", result["valid_sample_count"])
    print("Casos no evaluables:", result["non_evaluable_count"])
    print("Errores:", len(result["classification_errors"]))
    print("Informe:", output)


if __name__ == "__main__":
    main()
