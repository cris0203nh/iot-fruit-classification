"""AGROP-40, incremento 03: máscaras cromáticas PROVISIONALES de superficie.

Las máscaras separan píxeles de alto contraste cromático del fondo neutro.
No garantizan que los píxeles sean cáscara de mango, ni reconocen defectos.
Su uso con selección manual conserva procedencia y no certifica calidad.
"""

from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from .surface_analysis import (
    MAX_PROCESSING_SIDE,
    _candidate_mask_components,
    _corner_background,
)

class InvalidSurfaceSelection(ValueError):
    """La selección manual no cumple el contrato del manifiesto."""


ALGORITHM = "neutral-chroma-component-mask-v0.1"
WARNING = (
    "Máscara cromática provisional sobre fondo neutro: puede omitir zonas "
    "de baja saturación o incluir reflejos, pedúnculo y artefactos. "
    "No equivale a segmentación validada ni a detección de defectos."
)


def _percentile(samples: list[int], pct: float) -> int:
    values = sorted(samples)
    index = (len(values) - 1) * pct
    low = math.floor(index)
    high = math.ceil(index)
    return round(values[low] + (values[high] - values[low]) * (index - low))


def _selected_indices(selection: object, candidate_count: int) -> list[int]:
    if selection is None:
        return []
    if not isinstance(selection, dict):
        raise InvalidSurfaceSelection("surface_selection debe ser un objeto o null.")
    indices = selection.get("candidate_indices")
    reviewed = selection.get("reviewed_by_operator")
    note = selection.get("review_note")
    if (
        not isinstance(indices, list) or not indices
        or any(type(idx) is not int or idx < 1 or idx > candidate_count for idx in indices)
        or len(indices) != len(set(indices))
        or reviewed is not True
        or not isinstance(note, str) or not note.strip()
    ):
        raise InvalidSurfaceSelection(
            "surface_selection requiere índices válidos únicos, "
            "reviewed_by_operator=true y review_note no vacío."
        )
    return sorted(indices)


def _processing_components(image: Image.Image, proposal: dict[str, Any]) -> tuple[Image.Image, list[list[int]]]:
    thumb = image.convert("RGB")
    thumb.thumbnail((MAX_PROCESSING_SIDE, MAX_PROCESSING_SIDE), Image.Resampling.BILINEAR)
    if (
        proposal.get("candidate_count", 0) == 0
        or len(proposal.get("candidates", [])) != proposal.get("candidate_count", 0)
        or "estimated_background_median_rgb" not in proposal
    ):
        return thumb, []
    corner = _corner_background(thumb)
    if corner is None:
        return thumb, []
    # Recalcular con el mismo fondo que usó la propuesta y confirmar correspondencia.
    blobs = _candidate_mask_components(thumb, proposal["estimated_background_median_rgb"])
    if len(blobs) != proposal["candidate_count"]:
        return thumb, []
    return thumb, blobs


def describe_surface_masks(
    image: Image.Image,
    proposal: dict[str, Any],
    selection: object = None,
) -> dict[str, Any]:
    """Devuelve descriptores de píxeles de la máscara sin validarlos como fruto.

    Un operador puede declarar una selección, pero dicha declaración no prueba
    que varias regiones pertenezcan a la misma pieza o vista fotográfica.
    """
    indices = _selected_indices(selection, int(proposal.get("candidate_count", 0)))
    thumb, blobs = _processing_components(image, proposal)
    w, h = thumb.size
    result: dict[str, Any] = {
        "method": ALGORITHM,
        "status": "provisional_unverified",
        "processing_dimensions_px": [w, h],
        "selected_candidate_indices": indices,
        "operator_selection_declared": bool(indices),
        "assignment_of_regions_to_piece": "not_verified",
        "requires_independent_validation": True,
        "segments": [],
        "warning": WARNING,
    }
    if not blobs:
        result["status"] = "unavailable"
        result["reason"] = proposal.get("reason", "no_se_puede_obtener_mascara")
        return result
    pixels = list(thumb.get_flattened_data())
    for index, (candidate, blob) in enumerate(zip(proposal["candidates"], blobs), start=1):
        # No usar la caja completa para calcular RGB: incluiría píxeles del fondo.
        xs = [p % w for p in blob]
        ys = [p // w for p in blob]
        box_area = (max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1)
        channels = [[pixels[p][c] for p in blob] for c in range(3)]
        result["segments"].append({
            "candidate_index": index,
            "bbox_xywh": candidate["bbox_xywh"],
            "pixel_count_processing": len(blob),
            "pixel_fraction_of_processing_image": round(len(blob) / (w * h), 4),
            "mask_fill_fraction_of_bbox": round(len(blob) / box_area, 4),
            "masked_median_rgb": [round(statistics.median(channel)) for channel in channels],
            "masked_rgb_p10": [_percentile(channel, 0.10) for channel in channels],
            "masked_rgb_p90": [_percentile(channel, 0.90) for channel in channels],
            "selected_by_operator": index in indices,
            "interpretation": "descripcion_de_pixeles_cromaticos_no_atributo_agronomico",
        })
    if indices:
        result["status"] = "operator_selected_provisional_masks"
        result["review_note"] = selection["review_note"].strip()
    else:
        result["status"] = "pending_operator_selection"
    return result


def save_mask_preview(image_path: Path, proposal: dict[str, Any], output: Path) -> None:
    """Previsualización en PNG; no escribe sobre la imagen original."""
    if image_path.resolve() == output.resolve():
        raise ValueError("La máscara de diagnóstico no puede sobrescribir la fotografía original.")
    with Image.open(image_path) as photo:
        original = photo.convert("RGB")
    thumb, blobs = _processing_components(original, proposal)
    # Las regiones no seleccionadas siguen siendo propuestas; la vista es diagnóstica.
    background = Image.blend(original, ImageOps.grayscale(original).convert("RGB"), 0.78)
    for index, blob in enumerate(blobs, start=1):
        bits = bytearray(thumb.width * thumb.height)
        for pixel_index in blob:
            bits[pixel_index] = 255
        mask = Image.frombytes("L", thumb.size, bytes(bits)).resize(original.size, Image.Resampling.NEAREST)
        tint = (0, 225, 205) if index % 2 else (255, 70, 190)
        colored = Image.blend(original, Image.new("RGB", original.size, tint), 0.32)
        background.paste(colored, mask=mask)
    draw = ImageDraw.Draw(background)
    for candidate in proposal.get("candidates", []):
        x, y, bw, bh = candidate["bbox_xywh"]
        draw.rectangle((x, y, x + bw - 1, y + bh - 1), outline=(230, 0, 180), width=3)
        draw.text((x + 4, max(0, y - 14)), f"mascara {candidate['candidate_index']}", fill=(230, 0, 180))
    output.parent.mkdir(parents=True, exist_ok=True)
    background.save(output, format="PNG")
