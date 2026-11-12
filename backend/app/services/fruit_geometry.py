"""AG-054: metricas de la PROYECCION 2D de una mascara YOLOE.

Las unidades son pixeles y pixeles cuadrados. No estima centimetros,
volumen, peso, grado de calidad ni defectos. No modifica la imagen fuente.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

import cv2
import numpy as np


class InvalidGeometry(ValueError):
    """Mascara insuficiente o fuera de las dimensiones de la imagen."""


def measure_polygon(
    polygon: Sequence[Sequence[float]],
    frame_width: int,
    frame_height: int,
) -> dict[str, float]:
    if not (128 <= frame_width <= 12000 and 128 <= frame_height <= 12000):
        raise InvalidGeometry('Dimensiones de imagen invalidas.')
    if not 3 <= len(polygon) <= 4096:
        raise InvalidGeometry('La mascara no tiene suficientes vertices.')
    try:
        vertices = np.asarray(polygon, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise InvalidGeometry('La mascara tiene puntos invalidos.') from exc
    if vertices.shape != (len(polygon), 2) or not np.isfinite(vertices).all():
        raise InvalidGeometry('La mascara contiene coordenadas invalidas.')
    # Se toleran puntos en el borde exacto de la imagen, no fuera de ella.
    if (vertices[:, 0].min() < 0 or vertices[:, 0].max() > frame_width or
            vertices[:, 1].min() < 0 or vertices[:, 1].max() > frame_height):
        raise InvalidGeometry('La mascara excede el encuadre.')

    contour = vertices.astype(np.float32).reshape((-1, 1, 2))
    mask_area = float(cv2.contourArea(contour))
    mask_perimeter = float(cv2.arcLength(contour, True))
    if mask_area < 1 or not math.isfinite(mask_perimeter) or mask_perimeter <= 0:
        raise InvalidGeometry('La mascara no delimita una superficie valida.')

    x_min, y_min = vertices.min(axis=0)
    x_max, y_max = vertices.max(axis=0)
    width = float(x_max - x_min)
    height = float(y_max - y_min)
    if width <= 0 or height <= 0:
        raise InvalidGeometry('La mascara no presenta ancho y alto.')
    (_, _), (r_width, r_height), _ = cv2.minAreaRect(contour)
    major, minor = sorted((float(r_width), float(r_height)), reverse=True)
    if minor <= 0 or major <= 0:
        raise InvalidGeometry('No se puede obtener un rectangulo orientado.')

    area_fraction = mask_area / (frame_width * frame_height)
    if not 0 < area_fraction <= 1:
        raise InvalidGeometry('Superficie segmentada incoherente.')

    return {
        'widthPx': round(width, 2),
        'heightPx': round(height, 2),
        'majorAxisPx': round(major, 2),
        'minorAxisPx': round(minor, 2),
        'areaPx2': round(mask_area, 2),
        'perimeterPx': round(mask_perimeter, 2),
        'aspectRatio': round(major / minor, 4),
        'frameCoverage': round(area_fraction, 6),
    }
