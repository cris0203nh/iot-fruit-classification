from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageStat

PROJECT_ROOT = Path(__file__).resolve().parents[3]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from vision.src.surface_analysis import propose_surface_regions
from vision.src.surface_masks import describe_surface_masks
from vision.src.tomato_surface import analyze_tomato_surface


def _prepare_frame(frame_bgr, polygon):
    if not isinstance(frame_bgr, np.ndarray):
        raise ValueError("fotograma_invalido")

    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        raise ValueError("formato_de_fotograma_invalido")

    height, width = frame_bgr.shape[:2]

    if width < 128 or height < 128:
        raise ValueError("resolucion_insuficiente")

    if not isinstance(polygon, list) or len(polygon) < 3:
        raise ValueError("segmentacion_no_disponible")

    rgb_array = np.ascontiguousarray(frame_bgr[:, :, ::-1])
    rgb = Image.fromarray(rgb_array).convert("RGB")

    points = np.asarray(polygon, dtype=np.float32)

    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("poligono_invalido")

    if not np.isfinite(points).all():
        raise ValueError("coordenadas_invalidas")

    if (
        (points[:, 0] < 0).any()
        or (points[:, 0] >= width).any()
        or (points[:, 1] < 0).any()
        or (points[:, 1] >= height).any()
    ):
        raise ValueError("poligono_fuera_de_imagen")

    import cv2

    binary_mask = np.zeros((height, width), dtype=np.uint8)

    cv2.fillPoly(
        binary_mask,
        [np.round(points).astype(np.int32)],
        255,
    )

    ys, xs = np.where(binary_mask > 0)

    if len(xs) == 0:
        raise ValueError("mascara_vacia")

    x1, x2 = int(xs.min()), int(xs.max()) + 1
    y1, y2 = int(ys.min()), int(ys.max()) + 1

    if x2 - x1 < 32 or y2 - y1 < 32:
        raise ValueError("region_segmentada_insuficiente")

    crop_array = np.asarray(rgb)[y1:y2, x1:x2].copy()
    crop_mask = binary_mask[y1:y2, x1:x2] > 0

    if np.count_nonzero(crop_mask) < 100:
        raise ValueError("mascara_insuficiente")

    isolated_array = np.full_like(crop_array, 128)
    isolated_array[crop_mask] = crop_array[crop_mask]

    isolated = Image.fromarray(isolated_array)

    return isolated, crop_array, crop_mask, {
        "bbox_xyxy": [x1, y1, x2, y2],
        "width_px": x2 - x1,
        "height_px": y2 - y1,
        "mask_pixels": int(np.count_nonzero(crop_mask)),
        "polygon_points": int(len(points)),
    }


def _color_descriptors(rgb_array, mask):
    pixels = rgb_array[mask]

    if len(pixels) == 0:
        raise ValueError("sin_pixeles_de_fruta")

    return {
        "color_space": "RGB",
        "mean_rgb": [
            round(float(v), 3)
            for v in pixels.mean(axis=0)
        ],
        "median_rgb": [
            round(float(v), 3)
            for v in np.median(pixels, axis=0)
        ],
        "standard_deviation_rgb": [
            round(float(v), 3)
            for v in pixels.std(axis=0)
        ],
        "interpretation": "descriptivo_no_diagnostico",
        "pixel_count": int(len(pixels)),
    }


def evaluate_live_frame(
    product: str,
    frame_bgr: np.ndarray,
    polygon: list[list[float]],
) -> dict[str, Any]:

    product = product.strip().lower()

    if product not in ("mango", "tomate"):
        raise ValueError("producto_no_compatible")

    crop, rgb_array, mask, geometry = _prepare_frame(
        frame_bgr,
        polygon,
    )

    result = {
        "product": product,
        "source": "camera_live_frame",
        "geometry": geometry,
        "color_descriptors": _color_descriptors(
            rgb_array,
            mask,
        ),
        "identity_confirmed": False,
        "human_review_required": True,
        "analysis_status": "pendiente_revision",
    }

    if product == "mango":
        proposal = propose_surface_regions(crop)

        proposal["warning"] = (
            "Analisis superficial provisional; requiere revision humana."
        )
        proposal["requires_manual_confirmation"] = True

        masks = describe_surface_masks(
            crop,
            proposal,
            None,
        )

        result.update({
            "pipeline": "AGROP-40",
            "rubric_version": "kent-ext-v0.5",
            "surface_analysis": proposal,
            "mask_analysis": masks,
        })

    else:
        analysis = analyze_tomato_surface(crop)

        result.update({
            "pipeline": "AGROP-41",
            "rubric_version": "tomato-ext-v0.1",
            "surface_analysis": analysis["surface_analysis"],
            "mask_analysis": analysis["mask_analysis"],
        })

    return result
