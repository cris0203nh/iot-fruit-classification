"""AGROP-42 / Incremento 03: procesamiento exploratorio reproducible por lotes.

Usa el mismo analisis cromatico que AGROP-40/41, SIN elevar fotografías
externas sin identidad/sesion a evaluaciones formales ni generar etiquetas.
Conserva el original, valida SHA256 y mide decodificacion+analisis; las
vistas de diagnostico se guardan separadas y NO son máscaras validadas.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import statistics
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import PIL
from PIL import Image, UnidentifiedImageError

from vision.src.surface_analysis import propose_surface_regions
from vision.src.surface_masks import describe_surface_masks
from vision.src.tomato_surface import analyze_tomato_surface

VERSION = "agrop42-batch-exploratory-v0.1"
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
PRODUCTS = {"mango", "tomate"}
SHA_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,60}$")


class BatchInputError(ValueError):
    """Fuente o salida que incumple el contrato del dataset 01A."""


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise BatchInputError("JSON de inventario no disponible o no valido") from exc


def _load_inventory(dataset_dir: Path) -> list[dict[str, Any]]:
    data = _json(dataset_dir / "inventory.json")
    if not isinstance(data, list) or not data:
        raise BatchInputError("inventory.json debe contener registros de fotografías")
    seen_ids: set[str] = set()
    records: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            raise BatchInputError("Cada entrada del inventario debe ser un objeto")
        record_id = item.get("record_id")
        sha = item.get("sha256")
        product = item.get("product")
        relative = item.get("image_path")
        if (not isinstance(record_id, str) or not ID_PATTERN.fullmatch(record_id)
                or record_id in seen_ids or product not in PRODUCTS
                or not isinstance(sha, str) or not SHA_PATTERN.fullmatch(sha)
                or not isinstance(relative, str)):
            raise BatchInputError("Identificador, producto, SHA256 o ruta de inventario inválidos")
        seen_ids.add(record_id)
        records.append(item)
    return sorted(records, key=lambda item: item["record_id"])


def _locate_image(dataset_dir: Path, relative: str, sha: str) -> Path:
    """Solo fotografías dentro de dataset/images, sin rutas externas ni enlaces."""
    image_root = (dataset_dir / "images").resolve()
    path_value = Path(relative)
    if path_value.is_absolute() or ".." in path_value.parts:
        raise BatchInputError("Ruta absoluta o ascendente prohibida")
    path = dataset_dir / path_value
    if path.is_symlink() or not path.resolve().is_relative_to(image_root):
        raise BatchInputError("La imagen debe estar dentro de images sin enlaces externos")
    if path.parent.resolve() != image_root:
        raise BatchInputError("El inventario debe referenciar imágenes de primer nivel")
    if path.stem != sha or path.suffix.lower() not in {".jpg", ".png"}:
        raise BatchInputError("Nombre de imagen distinto de SHA256 de inventario")
    return path


def _process_image(path: Path, expected_sha: str, product: str) -> dict[str, Any]:
    """Incluye apertura, SHA y cómputo cromático. Nunca inventa controles de calidad."""
    if not path.is_file():
        raise BatchInputError("Archivo de imagen no disponible")
    if path.stat().st_size > MAX_IMAGE_BYTES or path.stat().st_size == 0:
        raise BatchInputError("Tamaño de imagen no admitido")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha:
        raise BatchInputError("SHA256 de imagen alterado respecto al inventario")
    try:
        with Image.open(path) as img:
            if img.format not in {"JPEG", "PNG"}:
                raise BatchInputError("Formato JPEG/PNG requerido")
            img.verify()
        with Image.open(path) as img:
            if img.width * img.height > MAX_IMAGE_PIXELS:
                raise BatchInputError("Resolución superior al límite técnico de 40 MP")
            rgb = img.convert("RGB")
            rgb.load()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise BatchInputError("Imagen no decodificable") from exc
    if min(rgb.size) < 128:
        raise BatchInputError("Imagen menor de 128 px por lado")
    if product == "mango":
        surface = propose_surface_regions(rgb)
        masks = describe_surface_masks(rgb, surface)
    else:
        adapted = analyze_tomato_surface(rgb)
        surface = adapted["surface_analysis"]
        masks = adapted["mask_analysis"]
    return {
        "sha256_verified": True,
        "original_dimensions_px": list(rgb.size),
        "surface_analysis": surface,
        "mask_analysis": masks,
    }


def _write_previews(photo: Path, proposal: dict[str, Any], stage: Path, prefix: str) -> None:
    """PNG de diagnóstico <=960 px. No afecta análisis ni imagen original.

    Las cajas se reescalan desde la propuesta calculada sobre el original. La
    máscara se recalcula para la miniatura y es SOLO una visualización; sus
    píxeles no sustituyen los descriptores emitidos por _process_image.
    """
    from PIL import ImageDraw, ImageOps
    from vision.src.surface_masks import _processing_components

    with Image.open(photo) as source:
        thumb = source.convert("RGB")
        original_size = thumb.size
        thumb.thumbnail((960, 960), Image.Resampling.LANCZOS)
    sx, sy = thumb.width / original_size[0], thumb.height / original_size[1]
    rectangles = []
    for candidate in proposal.get("candidates", []):
        x, y, width, height = candidate["bbox_xywh"]
        rectangles.append((round(x * sx), round(y * sy),
                           round(width * sx), round(height * sy),
                           candidate["candidate_index"]))
    boxes = thumb.copy()
    draw = ImageDraw.Draw(boxes)
    for x, y, width, height, index in rectangles:
        draw.rectangle((x, y, x + width - 1, y + height - 1), outline=(255, 0, 255), width=3)
        draw.text((x + 4, max(0, y - 14)), f"candidato {index}", fill=(255, 0, 255))
    boxes.save(stage / f"{prefix}_candidatos.png", compress_level=1)
    # Propuesta nueva SOBRE LA MINIATURA exclusivamente para dibujar máscara.
    # El análisis persistido permanece calculado sobre fotografía ORIGINAL.
    mini_proposal = propose_surface_regions(thumb)
    bg = Image.blend(thumb, ImageOps.grayscale(thumb).convert("RGB"), 0.78)
    proc_thumb, blobs = _processing_components(thumb, mini_proposal)
    for idx, blob in enumerate(blobs, start=1):
        bits = bytearray(proc_thumb.width * proc_thumb.height)
        for pos in blob:
            bits[pos] = 255
        mask = Image.frombytes("L", proc_thumb.size, bytes(bits)).resize(thumb.size, Image.Resampling.NEAREST)
        tint = (0, 225, 205) if idx % 2 else (255, 70, 190)
        overlay = Image.blend(thumb, Image.new("RGB", thumb.size, tint), 0.32)
        bg.paste(overlay, mask=mask)
    draw = ImageDraw.Draw(bg)
    for cand in mini_proposal.get("candidates", []):
        x, y, w, h = cand["bbox_xywh"]
        draw.rectangle((x, y, x + w - 1, y + h - 1), outline=(230, 0, 180), width=2)
        draw.text((x + 4, max(0, y - 13)), f"mascara {cand['candidate_index']}", fill=(230, 0, 180))
    bg.save(stage / f"{prefix}_mascara.png", compress_level=1)


def _timing(samples: list[int]) -> dict[str, Any]:
    values = sorted(samples)
    n = len(values)
    return {
        "runs": n,
        "median_ms": round(statistics.median(values) / 1e6, 4),
        "p95_ms": round(values[math.ceil(0.95 * n) - 1] / 1e6, 4),
        "min_ms": round(values[0] / 1e6, 4),
        "max_ms": round(values[-1] / 1e6, 4),
        "scope": "lectura_sha256_decodificacion_segmentacion_provisional_mascaras",
        "excludes": ["captura", "anotacion_humana", "escritura_de_vistas_png", "entrenamiento", "modelo_ligero"],
    }


def _technical_decision(result: dict[str, Any]) -> tuple[str, list[str]]:
    """Estado de revisión, NO predicción de clases ni reglas de defectos."""
    if not result["piece_identity_confirmed_declared"] or not result["session_documented"]:
        return "revision_trazabilidad_pendiente", ["L01_PIEZA_O_SESION_SIN_VERIFICAR"]
    # El importador 01A registra quality/coverage como null: no inferir un control humano.
    return "revision_de_captura_pendiente", ["L02_CALIDAD_Y_COBERTURA_NO_VERIFICADAS"]


def process_dataset(dataset_dir: Path, output_dir: Path, repeats: int = 1,
                    previews: bool = True) -> dict[str, Any]:
    """Crea NUEVA salida de forma atómica. Nunca modifica fotos ni inventario."""
    if type(repeats) is not int or not (1 <= repeats <= 10):
        raise BatchInputError("repeats requiere entero de 1 a 10")
    dataset_dir = dataset_dir.resolve()
    output_dir = output_dir.resolve()
    if not dataset_dir.is_dir() or not (dataset_dir / "images").is_dir():
        raise BatchInputError("Dataset 01A no disponible o incompleto")
    if output_dir.exists() or output_dir == dataset_dir or output_dir.is_relative_to(dataset_dir):
        raise BatchInputError("La salida debe ser nueva y externa al dataset")
    inventory = _load_inventory(dataset_dir)
    # Un SHA de dos productos distintos nunca se emplea como evidencia de identidad.
    hashes_products: dict[str, set[str]] = defaultdict(set)
    for item in inventory:
        hashes_products[item["sha256"]].add(item["product"])
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    rejected: list[dict[str, str]] = []
    for item in inventory:
        rid = item["record_id"]
        if item.get("visible_to_audit") is not True or item.get("rights_confirmed_declared") is not True:
            rejected.append({"record_id": rid, "reason": "fuera_de_alcance_o_derechos_no_acreditados_en_registro"})
            continue
        if len(hashes_products[item["sha256"]]) > 1:
            rejected.append({"record_id": rid, "reason": "mismo_sha256_en_productos_distintos"})
            continue
        groups[(item["product"], item["sha256"])].append(item)
    accepted: list[dict[str, Any]] = []
    timings: dict[str, list[int]] = defaultdict(list)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="agrop42_batch_stage_", dir=output_dir.parent) as temp_name:
        stage = Path(temp_name)
        (stage / "results").mkdir()
        if previews:
            (stage / "previews").mkdir()
        for (product, sha), items in sorted(groups.items()):
            path = _locate_image(dataset_dir, items[0]["image_path"], sha)
            samples: list[int] = []
            analysis: dict[str, Any] | None = None
            try:
                for _ in range(repeats):
                    start = time.perf_counter_ns()
                    fresh = _process_image(path, sha, product)
                    samples.append(time.perf_counter_ns() - start)
                    if analysis is not None and fresh != analysis:
                        raise BatchInputError("Análisis no determinista en las repeticiones")
                    analysis = fresh
            except BatchInputError as exc:
                for item in items:
                    rejected.append({"record_id": item["record_id"], "reason": str(exc)})
                continue
            assert analysis is not None
            timings[product].extend(samples)
            identity = all(item.get("piece_identity_declared") is True and item.get("piece_id") for item in items)
            session = all(item.get("device_id") and item.get("boot_id") for item in items)
            record = {
                "task": "AGROP-42", "increment": "03", "version": VERSION,
                "analysis_type": "propuesta_cromatica_exploratoria_no_evaluacion_formal",
                "product": product, "sha256": sha,
                "linked_record_ids": sorted(item["record_id"] for item in items),
                "piece_identity_confirmed_declared": bool(identity),
                "session_documented": bool(session),
                "capture_quality_verified": False,
                "coverage_verified": False,
                "rubric_status": "no_evaluable_sin_control_de_captura",
                "predicted_visual_label": None,
                "defect_detection_performed": False,
                "commercial_quality_assessed": False,
                "original_file_modified": False,
                "source_provenance": [
                    {"record_id": x["record_id"], "source_id": x.get("source_id"),
                     "source_url": x.get("source_url"), "license": x.get("license"),
                     "variety_declared": x.get("variety_declared"),
                     "variety_confirmed_declared": x.get("variety_confirmed_declared") is True}
                    for x in items
                ],
                **analysis,
            }
            decision, rules = _technical_decision(record)
            record["decision_tecnica"] = decision
            record["technical_rule_ids"] = rules
            record["processing_timing"] = _timing(samples)
            safe_name = f"{product}_{sha[:16]}"
            (stage / "results" / f"{safe_name}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            if previews:
                # Caja y máscara usan el módulo ya implementado en AGROP-40/41;
                # mantienen la fotografía original intacta.
                _write_previews(path, analysis["surface_analysis"],
                                stage / "previews", safe_name)
            accepted.append({
                "product": product, "sha256": sha, "linked_record_ids": record["linked_record_ids"],
                "candidate_count": record["surface_analysis"].get("candidate_count", 0),
                "region_status": record["surface_analysis"].get("status"),
                "mask_status": record["mask_analysis"].get("status"),
                "decision_tecnica": decision,
                "result_file": f"results/{safe_name}.json",
            })
        by_product = {p: {"processed_unique_images": sum(x["product"] == p for x in accepted),
                          "decisions": dict(sorted(Counter(x["decision_tecnica"] for x in accepted if x["product"] == p).items())),
                          "timing": _timing(timings[p]) if timings[p] else None}
                      for p in sorted(PRODUCTS)}
        summary = {
            "task": "AGROP-42", "increment": "03", "version": VERSION,
            "status": "procesamiento_exploratorio_completado" if accepted else "sin_imagenes_procesables",
            "input_inventory_records": len(inventory),
            "processed_unique_sha256": len(accepted),
            "processed_linked_records": sum(len(x["linked_record_ids"]) for x in accepted),
            "excluded_records": sorted(rejected, key=lambda x: x["record_id"]),
            "products": by_product, "images": accepted,
            "environment": {
                "python_version": platform.python_version(), "pillow_version": PIL.__version__,
                "system": platform.system(), "machine": platform.machine(),
                "processor": platform.processor() or "no_identificado",
                "logical_cpu_count": os.cpu_count(), "memory_peak": "no_medido",
                "hardware_scope": "equipo_ejecutor_de_Python_no_dispositivo_ESP32",
            },
            "comparison": {"same_test_set_comparison_performed": False,
                           "lightweight_model_trained": False,
                           "accuracy": None, "precision": None, "recall": None, "f1": None},
            "limitations": [
                "Fotografías sin identidad física de pieza y sesión no constituyen grupos independientes.",
                "La variedad y los derechos son declaraciones del inventario, no certificaciones del software.",
                "Sin revisión de calidad ni cobertura, las propuestas no son evaluaciones formales AGROP-40/41.",
                "Las cajas y máscaras cromáticas no son segmentaciones ni defectos validados.",
                "No se asignaron etiquetas E0/E1/E2 ni se calculó exactitud predictiva.",
                "Los tiempos incluyen lectura/decodificación y algoritmo; excluyen captura, PNG y revisión humana.",
                "Las vistas PNG se limitan a 960 px y sus máscaras se recalculan solo para visualización.",
            ],
        }
        (stage / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if output_dir.exists():
            raise BatchInputError("El directorio destino apareció durante la ejecución")
        os.rename(stage, output_dir)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AGROP-42: procesamiento por lotes de diagnósticos cromáticos provisionales")
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--repeats", default=1, type=int)
    parser.add_argument("--no-previews", action="store_true")
    args = parser.parse_args(argv)
    try:
        allowed = (Path(__file__).resolve().parents[3] / "vision/experiments").resolve()
        output = args.output_dir.resolve()
        if not output.is_relative_to(allowed) or output == allowed:
            raise BatchInputError("--output-dir debe ser nuevo y estar bajo vision/experiments")
        report = process_dataset(args.dataset_dir, args.output_dir, args.repeats, not args.no_previews)
    except (BatchInputError, OSError) as exc:
        parser.error(str(exc))
    print("AGROP-42 incremento 03:", report["status"])
    print("  registros de inventario:", report["input_inventory_records"])
    print("  archivos únicos procesados:", report["processed_unique_sha256"])
    print("  registros excluidos:", len(report["excluded_records"]))
    for p, data in report["products"].items():
        print(f"  {p}: {data['processed_unique_images']} archivos | decisiones={data['decisions']}")
    print("  salida:", args.output_dir)
    print("  sin clasificación E0/E1/E2 ni modelo ligero")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
