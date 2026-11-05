"""AGROP-40: candidatos EXPERIMENTALES de superficie visible sobre fondo neutro.

No es un segmentador entrenado ni un detector de defectos. Requiere inspección
humana de cada caja antes de utilizarla como superficie real del fruto.
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

ALGORITHM = "neutral-background-chroma-proposal-v0.1"
MAX_PROCESSING_SIDE = 512
MIN_COMPONENT_FRACTION = 0.025
MAX_CANDIDATES = 10
WARNING = (
    "Cajas propuestas por contraste cromático con fondo neutro; "
    "requieren verificación humana. No detectan defectos, forma "
    "conforme, madurez ni superficie física."
)


def _median_rgb(pixels: list[tuple[int, int, int]]) -> list[int]:
    return [round(statistics.median(p[channel] for p in pixels)) for channel in range(3)]


def _corner_background(image: Image.Image) -> tuple[list[int], float] | None:
    """Estimación del fondo SOLO en cuatro esquinas externas de la fotografía."""
    w, h = image.size
    cw, ch = max(2, w // 12), max(2, h // 12)
    pixels = image.load()
    samples: list[tuple[int, int, int]] = []
    for xmin, ymin in ((0, 0), (w - cw, 0), (0, h - ch), (w - cw, h - ch)):
        for y in range(ymin, ymin + ch, 2):
            for x in range(xmin, xmin + cw, 2):
                samples.append(pixels[x, y])
    neutral = [p for p in samples if max(p) - min(p) <= 28]
    fraction = len(neutral) / max(len(samples), 1)
    if fraction < 0.85:
        return None
    median = _median_rgb(neutral)
    # Una gran variación de fondo en las esquinas invalida el supuesto neutro.
    if max(statistics.pstdev(p[c] for p in neutral) for c in range(3)) > 42:
        return None
    return median, round(fraction, 4)


def _components(mask: bytes, w: int, h: int) -> list[list[int]]:
    """Componentes conexas 4-vecinas, sin librerías externas."""
    seen = bytearray(len(mask))
    found: list[list[int]] = []
    minimum = max(48, math.ceil(w * h * MIN_COMPONENT_FRACTION))
    for start, active in enumerate(mask):
        if not active or seen[start]:
            continue
        stack = deque([start])
        seen[start] = 1
        component: list[int] = []
        while stack:
            idx = stack.pop()
            component.append(idx)
            x, y = idx % w, idx // w
            for neighbor in (
                (idx - 1 if x else -1),
                (idx + 1 if x < w - 1 else -1),
                (idx - w if y else -1),
                (idx + w if y < h - 1 else -1),
            ):
                if neighbor >= 0 and mask[neighbor] and not seen[neighbor]:
                    seen[neighbor] = 1
                    stack.append(neighbor)
        if len(component) >= minimum:
            found.append(component)
    return sorted(found, key=lambda items: (-len(items), min(items)))


def _candidate_mask_components(thumb: Image.Image, bg: list[int]) -> list[list[int]]:
    """Misma máscara cromática usada para propuestas y análisis de píxeles.

    La máscara es heurística: NO es un contorno de fruto validado.
    """
    w, h = thumb.size
    mask = Image.new("L", (w, h))
    mask.putdata([
        255 if (
            max(p) - min(p) >= 40
            and sum(abs(p[c] - bg[c]) for c in range(3)) >= 65
        ) else 0
        for p in thumb.get_flattened_data()
    ])
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    return _components(bytes(1 if n else 0 for n in mask.get_flattened_data()), w, h)


def propose_surface_regions(image: Image.Image) -> dict[str, Any]:
    """Propone cajas en fondos fotográficos aproximadamente neutros.

    La salida NUNCA convierte una propuesta en región de fruto validada. No
    altera el estado de la captura ni la etiqueta visual del pipeline principal.
    """
    thumb = image.convert("RGB")
    width, height = thumb.size
    thumb.thumbnail((MAX_PROCESSING_SIDE, MAX_PROCESSING_SIDE), Image.Resampling.BILINEAR)
    tw, th = thumb.size
    result: dict[str, Any] = {
        "method": ALGORITHM,
        "status": "no_candidate",
        "requires_manual_confirmation": True,
        "candidate_count": 0,
        "candidates": [],
        "warning": WARNING,
    }
    background = _corner_background(thumb)
    if background is None:
        result["status"] = "background_not_supported"
        result["reason"] = "esquinas_no_compatibles_con_fondo_neutro"
        return result
    bg, neutral_fraction = background
    result["estimated_background_median_rgb"] = bg
    result["neutral_corner_fraction"] = neutral_fraction

    # Máscara cromática compartida con el módulo de descriptores.
    blobs = _candidate_mask_components(thumb, bg)
    if len(blobs) > MAX_CANDIDATES:
        result["status"] = "ambiguous_many_regions"
        result["reason"] = "demasiadas_regiones_candidatas"
        result["candidate_count"] = len(blobs)
        return result
    rgb_pixels = list(thumb.get_flattened_data())
    candidates: list[dict[str, Any]] = []
    for blob in blobs:
        xs = [idx % tw for idx in blob]
        ys = [idx // tw for idx in blob]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs) + 1, max(ys) + 1
        # Rectángulo en coordenadas de la fotografía ORIGINAL.
        xx0, yy0 = math.floor(x0 * width / tw), math.floor(y0 * height / th)
        xx1, yy1 = math.ceil(x1 * width / tw), math.ceil(y1 * height / th)
        samples = [rgb_pixels[idx] for idx in blob]
        median_rgb = _median_rgb(samples)
        candidates.append({
            "candidate_index": len(candidates) + 1,
            "bbox_xywh": [xx0, yy0, min(width, xx1) - xx0, min(height, yy1) - yy0],
            "coverage_fraction_of_image": round(len(blob) / (tw * th), 4),
            "candidate_median_rgb": median_rgb,
            "touches_image_border": x0 == 0 or y0 == 0 or x1 == tw or y1 == th,
            "verified_as_mango": False,
        })
    result["candidate_count"] = len(candidates)
    result["candidates"] = candidates
    if not candidates:
        result["reason"] = "no_se_obtuvieron_componentes_suficientes"
    elif len(candidates) > 1:
        result["status"] = "ambiguous_multiple_regions"
        result["reason"] = "varias_regiones_no_se_pueden_asignar_a_una_pieza"
    elif candidates[0]["touches_image_border"]:
        result["status"] = "partial_border_region"
        result["reason"] = "region_en_contacto_con_borde"
    else:
        result["status"] = "single_candidate_unverified"
        result["reason"] = "requiere_verificar_caja_y_pertenencia_a_la_pieza"
    return result


def save_candidate_preview(image_path: Path, analysis: dict[str, Any], output: Path) -> None:
    """Escribe vista de diagnóstico; NUNCA sobreescribe la imagen original."""
    if image_path.resolve() == output.resolve():
        raise ValueError("La vista de diagnóstico no puede sobrescribir la imagen original.")
    with Image.open(image_path) as source:
        rgb = source.convert("RGB")
    draw = ImageDraw.Draw(rgb)
    for candidate in analysis.get("candidates", []):
        x, y, w, h = candidate["bbox_xywh"]
        draw.rectangle((x, y, x + w - 1, y + h - 1), outline=(255, 0, 255), width=5)
        draw.text((x + 6, max(0, y - 16)), f"candidato {candidate['candidate_index']}", fill=(255, 0, 255))
    output.parent.mkdir(parents=True, exist_ok=True)
    rgb.save(output, format="PNG")
