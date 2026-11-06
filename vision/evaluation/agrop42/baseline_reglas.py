"""AGROP-42 / Incremento 02: baseline explicable de *estado técnico*.

No predice defectos ni E0/E1/E2. Consume RESULTADOS de AGROP-40/41,
no fotografías ni manifiestos, para decidir si la evidencia exige recaptura,
revisión de captura o revisión de segmentación. No sirve como clasificador
comercial ni como comparación de exactitud con un modelo entrenado.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

VERSION = "agrop42-reglas-tecnicas-v0.1"
SUPPORTED_PRODUCTS = ("mango", "tomate")
SUPPORTED_STATUS = {"evaluable", "no_evaluable", "pendiente_revision", "no_reconocido"}


class RulesInputError(ValueError):
    """Entrada que no cumple el contrato de reportes procesados."""


def identify_report(data: object) -> str | None:
    """Reconoce informes *procesados*, evitando confundirlos con manifiestos."""
    if not isinstance(data, dict) or not isinstance(data.get("images"), list):
        return None
    if not isinstance(data.get("criteria"), dict) or data.get("visual_status") not in SUPPORTED_STATUS:
        return None
    if data.get("task") == "AGROP-40" and data.get("pipeline_version") and data.get("rubric_version"):
        piece = data.get("piece")
        if isinstance(piece, dict) and piece.get("product") == "mango":
            return "mango"
    if (data.get("product") == "tomate"
            and data.get("rubric_version") == "tomato-ext-v0.1"
            and data.get("automated_commercial_classification") is False):
        return "tomate"
    return None


def _images(data: dict[str, Any], product: str) -> tuple[int, int, int, int, int]:
    """(total, validas, recaptura, seg_ambiguas, seg_sin_confirmar)."""
    valid = recapture = ambiguous = unconfirmed = 0
    for image in data["images"]:
        if not isinstance(image, dict):
            continue
        st = image.get("status") if product == "mango" else image.get("quality_status")
        if st in ({"valida"} if product == "mango" else {"evaluable"}):
            valid += 1
        if st == "recaptura_requerida" or (product == "mango" and image.get("reason") == "recaptura_requerida_por_revision"):
            recapture += 1
        proposal = image.get("surface_analysis")
        mask = image.get("mask_analysis")
        if isinstance(proposal, dict) and proposal.get("status") in {"ambiguous_multiple_regions", "ambiguous_many_regions"}:
            ambiguous += 1
        if not isinstance(mask, dict) or mask.get("status") != "operator_selected_provisional_masks":
            unconfirmed += 1
    return len(data["images"]), valid, recapture, ambiguous, unconfirmed


def evaluate_rules(data: dict[str, Any]) -> dict[str, Any]:
    """Aplica una precedencia explícita, sin examinar etiquetas ni RGB.

    El estado 'apta_para_revision_externa' significa solo aptitud técnica para
    revisión humana; no aprueba la fruta ni su clase comercial.
    """
    product = identify_report(data)
    if product is None:
        raise RulesInputError("Solo se aceptan informes procesados AGROP-40/41")
    status = data["visual_status"]
    total, valid, recapture, ambiguous, unconfirmed = _images(data, product)
    triggered: list[str] = []

    if status == "no_reconocido":
        outcome = "fuera_de_alcance"
        triggered.append("R01_PRODUCTO_NO_ADMITIDO")
    elif total == 0:
        outcome = "no_evaluable"
        triggered.append("R03_SIN_IMAGENES")
    elif recapture:
        outcome = "recaptura_requerida"
        triggered.append("R04_CALIDAD_RECAPTURA")
    elif status == "no_evaluable":
        outcome = "no_evaluable"
        triggered.append("R02_CAPTURA_NO_EVALUABLE")
    elif status == "pendiente_revision":
        outcome = "revision_de_captura_pendiente"
        triggered.append("R05_CAPTURA_PENDIENTE")
    elif valid != total:
        outcome = "revision_de_captura_pendiente"
        triggered.append("R06_ESTADO_IMAGENES_INCONSISTENTE")
    elif ambiguous:
        outcome = "revision_de_segmentacion"
        triggered.append("R07_REGIONES_AMBIGUAS")
    elif unconfirmed:
        outcome = "revision_de_segmentacion"
        triggered.append("R08_MASCARA_NO_CONFIRMADA")
    else:
        outcome = "apta_para_revision_externa"
        triggered.append("R09_CAPTURA_APTA_PARA_REVISION_HUMANA")

    # Nunca revelar la clase que pudiera haberse escrito manualmente ni
    # convertirla en una predicción. No usar RGB, percentiles o peso para clase.
    return {
        "product": product,
        "experiment_id": data.get("experiment_id"),
        "rubric_version": data["rubric_version"],
        "input_visual_status": status,
        "decision_tecnica": outcome,
        "rule_ids": triggered,
        "total_image_records": total,
        "valid_image_records": valid,
        "ambiguous_region_records": ambiguous,
        "human_review_required": True,
        "predicted_visual_label": None,
        "commercial_quality_assessed": False,
        "defect_detection_performed": False,
        "note": "Decisión técnica para preparar revisión; no clasificación comercial ni validación agronómica.",
    }


def read_reports(directory: Path) -> tuple[list[tuple[str, dict[str, Any]]], dict[str, int]]:
    """Lee recursivamente JSON procesados en una raíz local, sin seguir symlinks."""
    if not directory.is_dir():
        raise RulesInputError("El directorio de reportes no existe")
    base = directory.resolve()
    reports: list[tuple[str, dict[str, Any]]] = []
    ignored = invalid_json = 0
    for file in sorted(directory.rglob("*.json")):
        if not file.resolve().is_relative_to(base) or file.is_symlink():
            ignored += 1
            continue
        try:
            candidate = json.loads(file.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, UnicodeError):
            invalid_json += 1
            continue
        if identify_report(candidate) is None:
            ignored += 1
            continue
        reports.append((file.relative_to(directory).as_posix(), candidate))
    return reports, {"skipped_not_pipeline_report": ignored, "invalid_json": invalid_json}


def _latency(runs: list[int]) -> dict[str, Any]:
    ordered = sorted(runs)
    pos = math.ceil(0.95 * len(ordered)) - 1
    return {"runs": len(ordered), "median_ms": round(statistics.median(ordered) / 1e6, 6),
            "p95_ms": round(ordered[pos] / 1e6, 6)}


def baseline(reports: list[tuple[str, dict[str, Any]]], audit: dict[str, Any] | None = None,
             repeats: int = 30) -> dict[str, Any]:
    if type(repeats) is not int or not (1 <= repeats <= 1000):
        raise RulesInputError("repeats debe estar entre 1 y 1000")
    audit_status = "no_proporcionada"
    if audit is not None:
        if not isinstance(audit, dict) or audit.get("task") != "AGROP-42" or "por_producto" not in audit:
            raise RulesInputError("Se requiere un informe de auditoría AGROP-42 válido")
        audit_status = audit.get("status", "desconocido")
    entries: list[dict[str, Any]] = []
    per_product: dict[str, Counter] = {p: Counter() for p in SUPPORTED_PRODUCTS}
    timings: list[int] = []
    for source, report in reports:
        result = evaluate_rules(report)
        for _ in range(repeats):
            start = time.perf_counter_ns()
            repeat_result = evaluate_rules(report)
            elapsed = time.perf_counter_ns() - start
            if result != repeat_result:
                raise AssertionError("Reglas no deterministas")
            timings.append(elapsed)
        result["source_report"] = source
        entries.append(result)
        per_product[result["product"]][result["decision_tecnica"]] += 1
    return {
        "task": "AGROP-42", "increment": "02", "baseline_version": VERSION,
        "status": "evaluacion_tecnica_reproducida" if entries else "sin_informes_de_pipeline",
        "dataset_audit_status": audit_status,
        "evaluated_pipeline_reports": len(entries),
        "decisions_by_product": {p: dict(sorted(v.items())) for p, v in per_product.items()},
        "results": entries,
        "timing": ({"scope": "solo_decision_sobre_json_en_memoria_no_incluye_decodificacion_ni_segmentacion",
                    **_latency(timings)} if timings else None),
        "comparison": {
            "same_test_set_comparison_performed": False,
            "lightweight_model_trained": False,
            "accuracy": None, "precision": None, "recall": None, "f1": None,
            "model_comparison_blocked": audit_status != "potencial_para_particion_por_producto",
            "reason": "sin_etiquetas_verificadas_y_particion_independiente" if audit_status != "potencial_para_particion_por_producto" else "requiere_particion_validada_y_modelo",
        },
        "limitations": [
            "Baseline de reglas de estado técnico, NO predictor de E0/E1/E2 ni defectos.",
            "Las salidas de mango y tomate usan rúbricas distintas; no se combinan etiquetas.",
            "Latencias de decisión JSON no representan tiempo total de captura o inferencia de visión.",
            "Múltiples reportes de una misma fotografía no son muestras independientes.",
            "Un reporte técnicamente evaluable no garantiza cobertura completa ni exactitud agronómica.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AGROP-42: baseline explicable de reglas técnicas, sin inferir defectos")
    parser.add_argument("--reports-dir", type=Path, required=True, help="Directorio con resultados JSON de AGROP-40/41")
    parser.add_argument("--audit", type=Path, help="Informe JSON de auditoría AGROP-42")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=30)
    args = parser.parse_args(argv)
    try:
        reports, skipped = read_reports(args.reports_dir)
        audit = json.loads(args.audit.read_text(encoding="utf-8-sig")) if args.audit else None
        result = baseline(reports, audit, args.repeats)
        result["input_summary"] = skipped
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (RulesInputError, OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    print("AGROP-42 reglas:", result["status"], "| informes=", result["evaluated_pipeline_reports"])
    print("Salida:", args.output)
    print("Sin predicción E0/E1/E2; comparación con modelo NO ejecutada")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
