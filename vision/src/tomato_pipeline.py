"""Pipeline experimental de atributos externos del tomate AGROP-41."""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageStat

from .tomato_surface import analyze_tomato_surface


RUBRIC_VERSION = "tomato-ext-v0.1"
PRODUCT = "tomate"

NON_OBSERVABLE = [
    "firmeza",
    "grados_brix",
    "sabor",
    "madurez_interna",
    "condicion_microbiologica",
]


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest(manifest):
    if not isinstance(manifest, dict):
        raise ValueError("El manifiesto debe ser un objeto.")

    piece = manifest.get("piece")
    if not isinstance(piece, dict):
        raise ValueError("Falta la identificacion de la pieza.")

    if str(piece.get("product", "")).strip().lower() != PRODUCT:
        raise ValueError("Este pipeline acepta exclusivamente tomate.")

    if not piece.get("piece_id") or not piece.get("lot_id"):
        raise ValueError("Se requiere identificador de pieza y lote.")

    images = manifest.get("images")
    if not isinstance(images, list):
        raise ValueError("Las fotografias deben estar en una lista.")

    return piece, images


def validate_roi(roi, image_width, image_height):
    if not isinstance(roi, list) or len(roi) != 4:
        return None

    if any(type(value) is not int for value in roi):
        return None

    x, y, width, height = roi

    if width <= 0 or height <= 0:
        return None

    if x < 0 or y < 0:
        return None

    if x + width > image_width or y + height > image_height:
        return None

    return x, y, width, height


def describe_image(item, root):
    result = {
        "image_id": item.get("image_id"),
        "view": item.get("view"),
        "evidence_preserved": False,
        "sha256": None,
        "path": None,
        "quality_status": "pendiente_revision",
        "color_descriptors": None,
        "geometry_descriptors": None,
        "surface_analysis": None,
        "mask_analysis": None,
        "reason": None,
    }

    relative = item.get("path")
    if not isinstance(relative, str) or not relative.strip():
        result["reason"] = "ruta_no_declarada"
        return result

    root = Path(root).resolve()
    source = (root / relative).resolve()

    if not source.is_relative_to(root):
        result["reason"] = "ruta_fuera_del_directorio_permitido"
        return result

    if not source.is_file():
        result["reason"] = "archivo_no_disponible"
        return result

    result["path"] = relative.replace("\\", "/")
    result["sha256"] = sha256_file(source)
    result["evidence_preserved"] = True

    try:
        with Image.open(source) as original:
            original.verify()

        with Image.open(source) as original:
            image = original.convert("RGB")
            image.load()

    except (OSError, ValueError):
        result["reason"] = "imagen_invalida"
        return result

    # Segmentacion experimental independiente de la ROI y de la
    # confirmacion de calidad. Nunca confirma automaticamente el fruto.
    surface = analyze_tomato_surface(image)

    result["surface_analysis"] = surface["surface_analysis"]
    result["mask_analysis"] = surface["mask_analysis"]

    quality = item.get("quality")
    if not isinstance(quality, dict):
        quality = {}

    checks = ("focus_ok", "lighting_ok", "unoccluded")

    if any(quality.get(check) is False for check in checks):
        result["quality_status"] = "recaptura_requerida"
        result["reason"] = "calidad_visual_insuficiente"
        return result

    if any(quality.get(check) is not True for check in checks):
        result["quality_status"] = "pendiente_revision"
        result["reason"] = "calidad_visual_no_verificada"
        return result

    roi = validate_roi(
        item.get("roi_xywh"),
        image.width,
        image.height,
    )

    if roi is None or item.get("roi_verified") is not True:
        result["quality_status"] = "pendiente_revision"
        result["reason"] = "region_del_tomate_no_verificada"
        return result

    x, y, width, height = roi
    crop = image.crop((x, y, x + width, y + height))

    stats = ImageStat.Stat(crop)
    means = [round(value, 3) for value in stats.mean]
    medians = [round(value, 3) for value in stats.median]
    deviations = [round(value, 3) for value in stats.stddev]

    pixels = list(crop.get_flattened_data())
    pixel_count = len(pixels)

    channels = list(zip(*pixels))
    percentiles = []

    for channel in channels:
        ordered = sorted(channel)
        percentiles.append({
            "p10": ordered[int((pixel_count - 1) * 0.10)],
            "p50": ordered[int((pixel_count - 1) * 0.50)],
            "p90": ordered[int((pixel_count - 1) * 0.90)],
        })

    result["quality_status"] = "evaluable"
    result["color_descriptors"] = {
        "color_space": "RGB",
        "mean_rgb": means,
        "median_rgb": medians,
        "standard_deviation_rgb": deviations,
        "channel_percentiles": percentiles,
        "interpretation": "descriptivo_no_diagnostico",
    }

    result["geometry_descriptors"] = {
        "roi_width_px": width,
        "roi_height_px": height,
        "bounding_box_area_px": width * height,
        "aspect_ratio": round(width / height, 5),
        "interpretation": "geometria_de_region_no_calibre_real",
    }

    return result


def evaluate_caliber(measurement):
    if not isinstance(measurement, dict):
        return {
            "status": "pendiente",
            "diameter_mm": None,
            "reason": "medicion_no_declarada",
        }

    diameter = measurement.get("diameter_mm")

    if (
        not isinstance(diameter, (int, float))
        or isinstance(diameter, bool)
        or diameter <= 0
    ):
        return {
            "status": "pendiente",
            "diameter_mm": None,
            "reason": "diametro_invalido",
        }

    if not measurement.get("equipment_id"):
        return {
            "status": "pendiente",
            "diameter_mm": diameter,
            "reason": "equipo_no_identificado",
        }

    if measurement.get("calibrated") is not True:
        return {
            "status": "pendiente",
            "diameter_mm": diameter,
            "reason": "instrumento_no_verificado",
        }

    return {
        "status": "medicion_valida_pendiente_de_referencia",
        "diameter_mm": diameter,
        "equipment_id": measurement["equipment_id"],
        "calibrated": True,
        "unit": "mm",
    }


def evaluate_manifest(manifest, root):
    piece, images = validate_manifest(manifest)

    results = [
        describe_image(item, root)
        for item in images
    ]

    valid = [
        item for item in results
        if item["quality_status"] == "evaluable"
    ]

    coverage = manifest.get("coverage_verified")

    if coverage is not True:
        visual_status = (
            "no_evaluable" if coverage is False
            else "pendiente_revision"
        )
    elif not valid:
        visual_status = "no_evaluable"
    elif len(valid) != len(results):
        visual_status = "pendiente_revision"
    else:
        visual_status = "evaluable"

    observations = manifest.get("observations", {})
    if not isinstance(observations, dict):
        observations = {}

    criteria = {}

    for code in ("R03", "R04", "R05", "R06", "R07", "R08", "R09"):
        criteria[code] = observations.get(
            code,
            {
                "presence": "no_determinable",
                "location": None,
                "review_note": None,
                "reviewed_by_operator": False,
            },
        )

    criteria["R01"] = {
        "product": PRODUCT,
        "variety_declared": piece.get("variety_declared"),
        "commercial_type": piece.get("commercial_type"),
        "coverage_verified": coverage,
    }

    criteria["R02"] = evaluate_caliber(
        manifest.get("measurement")
    )

    criteria["R04"]["color_descriptors"] = [
        item["color_descriptors"]
        for item in valid
    ]

    criteria["R10"] = {
        "not_evaluated_by_rgb_or_weight": NON_OBSERVABLE,
        "status": "requiere_metodos_adicionales",
    }

    label = manifest.get("operator_visual_label")

    if label not in (None, "E0", "E1", "E2"):
        raise ValueError("Etiqueta del operador no valida.")

    return {
        "experiment_id": manifest.get("experiment_id"),
        "rubric_version": RUBRIC_VERSION,
        "product": PRODUCT,
        "piece": {
            "piece_id": piece["piece_id"],
            "lot_id": piece["lot_id"],
            "variety_declared": piece.get("variety_declared"),
            "commercial_type": piece.get("commercial_type"),
        },
        "visual_status": visual_status,
        "operator_visual_label": label,
        "visual_label_source": (
            "operador" if label is not None else None
        ),
        "criteria": criteria,
        "images": results,
        "image_count": len(results),
        "evaluable_image_count": len(valid),
        "evidence_complete": (
            len(results) > 0
            and all(item["evidence_preserved"] for item in results)
        ),
        "automated_commercial_classification": False,
        "human_review_required": True,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Procesamiento experimental de tomate AGROP-41"
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--image-root", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    image_root = Path(args.image_root).resolve()

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    result = evaluate_manifest(manifest, image_root)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Experimento de tomate procesado.")
    print("Estado visual:", result["visual_status"])
    print("Fotografias evaluables:", result["evaluable_image_count"])
    print("Evidencia completa:", result["evidence_complete"])
    print("Informe:", output)


if __name__ == "__main__":
    main()

