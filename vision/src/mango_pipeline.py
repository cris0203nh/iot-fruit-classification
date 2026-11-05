"""AGROP-40: contrato y pipeline experimental de atributos externos de mango Kent.

Rúbrica kent-ext-v0.5 (AGROP-13). No constituye un clasificador entrenado.
Nunca asigna automáticamente E0, E1, E2 ni inferencias de calidad interna.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat, UnidentifiedImageError

from .surface_analysis import propose_surface_regions, save_candidate_preview
from .surface_masks import InvalidSurfaceSelection, describe_surface_masks, save_mask_preview

RUBRIC_VERSION = "kent-ext-v0.5"
PIPELINE_VERSION = "agrop40-mango-provisional-masks-v0.3"
SUPPORTED_FORMATS = {"PNG", "JPEG"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MIN_IMAGE_SIDE = 128  # Control técnico provisional; NO umbral validado del mango.

CRITERIA = {
    "R01": "Identidad y cobertura",
    "R02": "Peso y calibre",
    "R03": "Integridad superficial",
    "R04": "Deterioro visible",
    "R05": "Defectos de cáscara",
    "R06": "Limpieza e indicios de plagas",
    "R07": "Forma y color",
    "R08": "Atributos no observables",
}


def _is_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def classify_caliber(measurement: object) -> dict[str, Any]:
    """R02: calibre por PESO validado, independiente del estado visual.

    La rúbrica deja pendientes lecturas en frontera e incertidumbre cruzada.
    No se usa ninguna medida derivada de fotografías.
    """
    pending = {"status": "pendiente", "reference": None, "reason": "pesaje_no_verificado"}
    if not isinstance(measurement, dict):
        return pending
    grams = measurement.get("grams")
    uncertainty = measurement.get("uncertainty_g")
    if not _is_number(grams) or grams < 0:
        return {**pending, "reason": "peso_ausente_o_invalido"}
    if measurement.get("stable") is not True or measurement.get("calibrated") is not True:
        return pending
    if not _is_number(uncertainty) or uncertainty < 0:
        return {**pending, "reason": "incertidumbre_no_documentada"}
    low, high = grams - uncertainty, grams + uncertainty
    for band, (minimum, maximum) in (
        ("A", (200, 350)), ("B", (351, 550)), ("C", (551, 800)),
    ):
        if low >= minimum and high <= maximum:
            return {"status": "determinado", "reference": band, "reason": None}
    if high < 200 or low > 800:
        return {"status": "fuera_de_referencia", "reference": None, "reason": "peso_fuera_200_800_g"}
    return {**pending, "reason": "frontera_o_incertidumbre"}


def _image_metadata(item: object, manifest_dir: Path) -> dict[str, Any]:
    """Lee una imagen local; describe la región de interés SOLO si fue verificada."""
    if not isinstance(item, dict):
        return {"status": "error", "reason": "entrada_imagen_invalida"}
    record = {
        "image_id": item.get("image_id"),
        "view": item.get("view"),
        "status": "error",
        "reason": None,
        "sha256": None,
        "dimensions_px": None,
        "roi_descriptor": None,
        "surface_analysis": None,
        "mask_analysis": None,
    }
    path_value = item.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        record["reason"] = "ruta_no_indicada"
        return record
    path = Path(path_value)
    if not path.is_absolute():
        path = manifest_dir / path
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            record["reason"] = "imagen_vacia_o_supera_5mb"
            return record
        with Image.open(path) as source:
            image_format = source.format
            if image_format not in SUPPORTED_FORMATS:
                record["reason"] = "formato_no_admitido"
                return record
            source.load()
            rgb = source.convert("RGB")
        width, height = rgb.size
        record["sha256"] = hashlib.sha256(raw).hexdigest()
        record["dimensions_px"] = [width, height]
        if min(width, height) < MIN_IMAGE_SIDE:
            record["reason"] = "resolucion_insuficiente_para_este_prototipo"
            return record
        quality = item.get("quality")
        if not isinstance(quality, dict):
            record["status"] = "pendiente_revision"
            record["reason"] = "calidad_sin_revision"
            return record
        flags = ("focus_ok", "lighting_ok", "unoccluded")
        if any(quality.get(field) is False for field in flags):
            record["reason"] = "recaptura_requerida_por_revision"
            return record
        if any(quality.get(field) is not True for field in flags):
            record["status"] = "pendiente_revision"
            record["reason"] = "calidad_sin_confirmar"
            return record
        # Propuesta heurística separada de la ROI manual y del estado de la pieza.
        record["surface_analysis"] = propose_surface_regions(rgb)
        record["mask_analysis"] = describe_surface_masks(
            rgb, record["surface_analysis"], item.get("surface_selection")
        )
        roi = item.get("roi_xywh")
        if roi is not None:
            if (
                not isinstance(roi, list)
                or len(roi) != 4
                or any(type(x) is not int for x in roi)
            ):
                record["reason"] = "roi_invalida"
                return record
            x, y, w, h = roi
            if x < 0 or y < 0 or w < 1 or h < 1 or x + w > width or y + h > height:
                record["reason"] = "roi_fuera_de_imagen"
                return record
            if item.get("roi_verified") is True:
                roi_image = rgb.crop((x, y, x + w, y + h))
                median = ImageStat.Stat(roi_image).median
                record["roi_descriptor"] = {
                    "method": "roi_rectangular_revisada_por_operador",
                    "median_rgb": [round(v, 2) for v in median],
                    "aspect_ratio_h_over_w": round(h / w, 3),
                    "warning": (
                        "Describe píxeles de la región revisada; no equivale a "
                        "segmentación validada de cáscara, clase comercial ni madurez."
                    ),
                }
            else:
                record["reason"] = "roi_sin_verificacion"
                record["status"] = "pendiente_revision"
                return record
        record["status"] = "valida"
        record["reason"] = None
        return record
    except InvalidSurfaceSelection:
        raise
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        record["reason"] = "archivo_no_disponible_o_invalido"
        return record


def evaluate_manifest(manifest: dict[str, Any], manifest_dir: Path) -> dict[str, Any]:
    """Construye un informe reproducible, sin inferencias de defectos no entrenadas."""
    if not isinstance(manifest, dict):
        raise ValueError("El manifiesto debe ser un objeto JSON.")
    piece = manifest.get("piece")
    if not isinstance(piece, dict):
        raise ValueError("El campo piece debe ser un objeto.")
    images = manifest.get("images", [])
    if not isinstance(images, list):
        raise ValueError("El campo images debe ser una lista.")
    coverage = manifest.get("coverage_verified")
    if coverage is not None and type(coverage) is not bool:
        raise ValueError("coverage_verified debe ser true, false o null.")

    product = piece.get("product")
    variety = piece.get("variety_declared")
    in_scope = product == "mango" and variety == "Kent"
    evidence = [_image_metadata(item, manifest_dir) for item in images] if in_scope else []
    problems: list[str] = []
    pending: list[str] = []
    if not piece.get("lot_id") or not piece.get("piece_id"):
        problems.append("identificacion_de_pieza_incompleta")
    if not images:
        problems.append("sin_imagenes")
    if coverage is False:
        problems.append("cobertura_insuficiente")
    elif coverage is None:
        pending.append("cobertura_no_verificada")
    for index, image in enumerate(evidence):
        if image["status"] == "error":
            problems.append(f"imagen_{index + 1}:{image['reason']}")
        elif image["status"] == "pendiente_revision":
            pending.append(f"imagen_{index + 1}:{image['reason']}")

    if not in_scope:
        visual_status = "no_reconocido"
        reasons = ["solo_se_admite_mango_kent_declarado"]
    elif problems:
        visual_status = "no_evaluable"
        reasons = problems
    elif pending:
        visual_status = "pendiente_revision"
        reasons = pending
    else:
        visual_status = "evaluable"
        reasons = []

    surface_proposals = [
        {"image_id": record["image_id"], **record["surface_analysis"]}
        for record in evidence if record["surface_analysis"] is not None
    ]
    mask_observations = [
        {"image_id": record["image_id"], **record["mask_analysis"]}
        for record in evidence if record["mask_analysis"] is not None
    ]
    color_observations = [
        {"image_id": record["image_id"], **record["roi_descriptor"]}
        for record in evidence if record["roi_descriptor"] is not None
    ]
    criteria: dict[str, Any] = {
        "R01": {
            "name": CRITERIA["R01"], "status": visual_status,
            "source": "identidad_y_cobertura_declaradas", "reasons": reasons,
        },
        "R02": {
            "name": CRITERIA["R02"], "source": "pesaje_verificado_no_rgb",
            **classify_caliber(manifest.get("weight")),
        },
        "R07": {
            "name": CRITERIA["R07"], "source": "roi_confirmada_manualmente",
            "color_descriptors": color_observations,
            "surface_proposals": surface_proposals,
            "provisional_surface_masks": mask_observations,
            "form_compliance": "no_determinable_sin_pauta_validada",
        },
        "R08": {
            "name": CRITERIA["R08"], "source": "limite_de_alcance",
            "internal_traits": "no_evaluados",
            "excluded": ["firmeza", "brix", "sabor", "condicion_interna"],
        },
    }
    for code in ("R03", "R04", "R05", "R06"):
        criteria[code] = {
            "name": CRITERIA[code], "presence": "no_determinable",
            "source": "requiere_anotacion_y_validacion_humana_o_modelo_validado",
        }
    return {
        "task": "AGROP-40",
        "pipeline_version": PIPELINE_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "experiment_id": manifest.get("experiment_id"),
        "piece": {
            "lot_id": piece.get("lot_id"),
            "piece_id": piece.get("piece_id"),
            "product": product,
            "variety_declared": variety,
        },
        "visual_status": visual_status,
        "visual_label": None,
        "visual_label_reason": "E0/E1/E2 requieren anotaciones o inferencia validada; no se asignan por color.",
        "weight_status_separate_from_visual": True,
        "criteria": {key: criteria[key] for key in CRITERIA},
        "images": evidence,
        "requires_human_review": True,
        "experiment_limitations": [
            "Sin modelo de defectos entrenado o validado para mango Kent.",
            "Sin inferencias internas ni certificados de conformidad comercial.",
            "La revisión manual de captura y ROI se declara en el manifiesto; no se verifica automáticamente.",
            "Las cajas de superficie son heurísticas no validadas; no equivalen a segmentación confirmada ni detección de defectos.",
            "Las máscaras cromáticas son provisionales: la selección humana no prueba clase de fruto, cobertura ni defectos.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AGROP-40: análisis externo experimental de mango Kent")
    parser.add_argument("--manifest", required=True, type=Path, help="Ruta de un manifiesto JSON local")
    parser.add_argument("--output", required=True, type=Path, help="Ruta del informe JSON de salida")
    parser.add_argument("--preview-dir", type=Path, help="Directorio opcional para cajas de diagnóstico; nunca modifica el original")
    parser.add_argument("--mask-preview-dir", type=Path, help="Directorio opcional para máscaras cromáticas de diagnóstico")
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
        result = evaluate_manifest(manifest, args.manifest.resolve().parent)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
        return 2
    if args.preview_dir is not None or args.mask_preview_dir is not None:
        # Previsualizaciones solo para imágenes procesadas; jamás sobreescriben el original.
        for index, (item, record) in enumerate(zip(manifest["images"], result["images"])):
            if record["surface_analysis"] is None:
                continue
            image_path = Path(item["path"])
            if not image_path.is_absolute():
                image_path = args.manifest.resolve().parent / image_path
            safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(record["image_id"]))[:48]
            if args.preview_dir is not None:
                output = args.preview_dir / f"{index + 1:02d}_{safe_id}_propuesta.png"
                save_candidate_preview(image_path, record["surface_analysis"], output)
                print(f"Vista de diagnóstico: {output}")
            if args.mask_preview_dir is not None and record["mask_analysis"] is not None:
                output = args.mask_preview_dir / f"{index + 1:02d}_{safe_id}_mascara.png"
                save_mask_preview(image_path, record["surface_analysis"], output)
                print(f"Máscara de diagnóstico: {output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Informe generado: {args.output}")
    print(f"Estado visual: {result['visual_status']}; etiqueta automática: ninguna")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
