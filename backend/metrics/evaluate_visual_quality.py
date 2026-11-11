"""AG-035/AGROP-43: metrics for external *visual* grades E0/E1/E2.

This is not the commercial primera/segunda evaluator. Declared evidence references
and flags do not independently establish human ground truth or model provenance.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

PRODUCTS = ("mango", "tomate")
GRADES = ("E0", "E1", "E2")
SOURCES = ("AG036_acuerdo_doble", "AG036_conciliacion")
VERSION = "agrop43-visual-e0e1e2-v1"


def _text(value):
    """Only accept actual strings; booleans, lists and numbers are not labels."""
    return value.strip() if isinstance(value, str) else ""


def _empty_product():
    return {
        "sample_count": 0,
        "correct": 0,
        "matrix": {grade: {pred: 0 for pred in GRADES} for grade in GRADES},
        "confidences": [],
        "rubrics": set(),
    }


def _score_product(item):
    matrix, n = item["matrix"], item["sample_count"]
    per_grade = {}
    for grade in GRADES:
        tp = matrix[grade][grade]
        support = sum(matrix[grade].values())
        fp = sum(matrix[actual][grade] for actual in GRADES if actual != grade)
        fn = support - tp
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = None
        if support:
            f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0
        per_grade[grade] = {
            "precision": precision, "recall": recall, "f1_score": f1,
            "support": support,
        }
    supported = [per_grade[g]["f1_score"] for g in GRADES if per_grade[g]["support"]]
    return {
        "evaluation_status": "metricas_exploratorias_pendientes_validacion_externa" if n else "insufficient_data",
        "sample_count": n,
        "confusion_matrix": matrix,
        "accuracy": item["correct"] / n if n else None,
        "metrics_by_grade": per_grade,
        "macro_f1_clases_presentes": sum(supported) / len(supported) if supported else None,
        "macro_f1_tres_clases": sum(supported) / 3 if len(supported) == 3 else None,
        "n_clases_presentes": len(supported),
        "mean_confidence": sum(item["confidences"]) / len(item["confidences"]) if item["confidences"] else None,
        "confidence_sample_count": len(item["confidences"]),
        "rubric_versions": sorted(item["rubrics"]),
    }


def evaluate_visual_records(records):
    """Evaluate one model prediction per physical piece, never perform implicit label mapping.

    Rejected rows remain in ``non_evaluable_cases`` with explicit reason. Labels
    and supporting references must be checked independently before publication.
    """
    if not isinstance(records, list):
        raise ValueError("La entrada debe ser una lista JSON de registros.")

    # Reject all repeated physical pieces (even if some duplicate rows are pending),
    # as well as repeated sample IDs. This avoids dependence on input row order.
    piece_counts = Counter()
    sample_counts = Counter()
    for row in records:
        if not isinstance(row, dict):
            continue
        product, lot, piece = (_text(row.get(key)) for key in ("product", "lot_id", "piece_id"))
        sample = _text(row.get("sample_id"))
        if product and lot and piece:
            piece_counts[(product.lower(), lot, piece)] += 1
        if sample:
            sample_counts[sample] += 1

    accepted = []
    rejected = []
    for index, row in enumerate(records):
        sample_id = _text(row.get("sample_id")) if isinstance(row, dict) else ""
        identifier = sample_id or f"fila-{index+1}"
        product = _text(row.get("product")).lower() if isinstance(row, dict) else ""
        def reject(reason):
            rejected.append({"sample_id": identifier, "product": product or None, "reason": reason})

        if not isinstance(row, dict):
            reject("registro_invalido")
            continue
        if product not in PRODUCTS:
            reject("producto_no_admitido")
            continue
        lot, piece = _text(row.get("lot_id")), _text(row.get("piece_id"))
        if not sample_id or not lot or not piece:
            reject("trazabilidad_incompleta_lote_pieza_muestra")
            continue
        if piece_counts[(product, lot, piece)] != 1 or sample_counts[sample_id] != 1:
            reject("pieza_o_muestra_duplicada")
            continue
        rubric = _text(row.get("rubric_version"))
        prefix = "kent-ext-" if product == "mango" else "tomato-ext-"
        if not rubric.startswith(prefix):
            reject("rubrica_incompatible_o_ausente")
            continue
        if product == "mango" and _text(row.get("variedad_declarada")).casefold() != "kent":
            reject("variedad_kent_no_declarada")
            continue
        actual = _text(row.get("y_true")).upper()
        predicted = _text(row.get("y_pred")).upper()
        if actual not in GRADES:
            reject("etiqueta_visual_e0e1e2_ausente_o_invalida")
            continue
        if predicted not in GRADES:
            reject("prediccion_visual_e0e1e2_ausente_o_invalida")
            continue
        # These are declarations in the input, NOT independent certification.
        if _text(row.get("label_verification")) != "verified":
            reject("etiqueta_humana_no_verificada")
            continue
        if _text(row.get("ground_truth_source")) not in SOURCES or not _text(row.get("ground_truth_reference")):
            reject("sin_referencia_a_revision_humana_independiente")
            continue
        if _text(row.get("prediction_source")) != "model" or _text(row.get("prediction_verification")) != "verified":
            reject("prediccion_no_acreditada_como_salida_de_modelo")
            continue
        if not _text(row.get("source_model_version")):
            reject("version_modelo_ausente")
            continue
        status = _text(row.get("source_status"))
        if status and status not in ("completed", "evaluated"):
            reject("evaluacion_no_finalizada")
            continue
        confidence = row.get("confidence")
        if confidence is not None and (
            isinstance(confidence, bool) or not isinstance(confidence, (float, int))
            or not math.isfinite(confidence) or not 0 <= confidence <= 1
        ):
            reject("confianza_invalida")
            continue
        accepted.append({
            "sample_id": sample_id, "product": product, "lot_id": lot,
            "piece_id": piece, "rubric_version": rubric,
            "actual": actual, "predicted": predicted, "confidence": confidence,
            "source_model_version": _text(row.get("source_model_version")),
        })

    # A performance estimate must not pool different rubric versions: retroactive
    # label reinterpretation would give a misleading confusion matrix.
    rubrics_by_product = {p: {r["rubric_version"] for r in accepted if r["product"] == p}
                          for p in PRODUCTS}
    if any(len(rubrics_by_product[p]) > 1 for p in PRODUCTS):
        keep = []
        for r in accepted:
            if len(rubrics_by_product[r["product"]]) > 1:
                rejected.append({"sample_id": r["sample_id"], "product": r["product"],
                                 "reason": "versiones_de_rubrica_mezcladas_por_producto"})
            else:
                keep.append(r)
        accepted = keep

    product_data = {p: _empty_product() for p in PRODUCTS}
    errors = []
    for row in accepted:
        p = row["product"]
        item = product_data[p]
        item["matrix"][row["actual"]][row["predicted"]] += 1
        item["sample_count"] += 1
        item["rubrics"].add(row["rubric_version"])
        if row["confidence"] is not None:
            item["confidences"].append(row["confidence"])
        if row["actual"] == row["predicted"]:
            item["correct"] += 1
        else:
            errors.append({
                "sample_id": row["sample_id"], "product": p,
                "lot_id": row["lot_id"], "piece_id": row["piece_id"],
                "actual": row["actual"], "predicted": row["predicted"],
                "error_type": "confusion_entre_grados_visuales",
                "confidence": row["confidence"],
            })

    valid_count = len(accepted)
    return {
        "story": "AGROP-43", "version": VERSION,
        "taxonomy": "visual_e0_e1_e2", "classes": list(GRADES),
        "products": {p: _score_product(product_data[p]) for p in PRODUCTS},
        "total_records": len(records), "valid_sample_count": valid_count,
        "non_evaluable_count": len(rejected), "non_evaluable_cases": rejected,
        "coverage_evaluable": valid_count / len(records) if records else None,
        "classification_errors": errors,
        "evaluation_status": "metricas_exploratorias_pendientes_validacion_externa" if valid_count else "insufficient_data",
        "external_evidence_independently_verified_by_software": False,
        "commercial_category_comparison_authorized": False,
        "AG036_double_review_independence_automatically_verified": False,
        "warning": (
            "E0/E1/E2 son grados visuales, NO primera/segunda ni clases Codex. "
            "Referencias de revision y banderas verified son declaraciones del CSV: "
            "el programa no prueba autenticidad, independencia ni aprobación de rúbricas. "
            "Accuracy del modelo NO equivale a acuerdo humano de AG-036; "
            "ninguna métrica basta para cerrar AG-035/AG-036 sin evidencia."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.input.resolve() == args.output.resolve() or args.output.exists():
            raise ValueError("No sobrescribir el archivo de entrada ni informes previos")
        records = json.loads(args.input.read_text(encoding="utf-8"))
        report = evaluate_visual_records(records)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                               encoding="utf-8")
        print(json.dumps({"estado": report["evaluation_status"],
                          "muestras_evaluables": report["valid_sample_count"],
                          "no_evaluables": report["non_evaluable_count"],
                          "salida": str(args.output)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"AG-035 visual: error de entrada/salida: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
