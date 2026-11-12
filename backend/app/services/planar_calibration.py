"""AG-054 I02: medicion de proyecciones al plano de un ArUco verificado.

NO obtiene dimensiones reales 3D ni corrige altura de la fruta o distorsion
sin parametros intrinsecos de la webcam. Nunca sustituye calibracion metrologica.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

import cv2
import numpy as np


class CalibrationRejected(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _marker_corners(frame: np.ndarray, marker_id: int) -> list[list[float]]:
    if not hasattr(cv2, 'aruco'):
        raise RuntimeError('OpenCV sin modulo aruco (requiere opencv-contrib-python).')
    aruco = cv2.aruco
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    params = aruco.DetectorParameters()
    if hasattr(aruco, 'ArucoDetector'):
        corners, ids, _ = aruco.ArucoDetector(dictionary, params).detectMarkers(frame)
    else:
        corners, ids, _ = aruco.detectMarkers(frame, dictionary, parameters=params)
    if ids is None:
        raise CalibrationRejected('marker_not_found')
    matching = [i for i, code in enumerate(ids.flatten().tolist()) if code == marker_id]
    if len(matching) != 1:
        raise CalibrationRejected('marker_not_found' if not matching else 'marker_ambiguous')
    points = np.asarray(corners[matching[0]], dtype=np.float64).reshape(4, 2)
    if not np.isfinite(points).all():
        raise CalibrationRejected('marker_invalid')
    height, width = frame.shape[:2]
    if (points[:, 0].min() < 4 or points[:, 0].max() > width - 4 or
            points[:, 1].min() < 4 or points[:, 1].max() > height - 4):
        raise CalibrationRejected('marker_cropped')
    area = abs(float(cv2.contourArea(points.astype(np.float32))))
    if area < 900 or not math.isfinite(area):
        raise CalibrationRejected('marker_too_small')
    sides = [float(np.linalg.norm(points[(i+1) % 4] - points[i])) for i in range(4)]
    if min(sides) < 25 or max(sides) / min(sides) > 2.5:
        raise CalibrationRejected('marker_perspective_excessive')
    return [[round(float(v), 2) for v in pt] for pt in points]


def measure_plane_projection(frame: np.ndarray, polygon: Sequence[Sequence[float]],
                             marker_id: int, marker_side_mm: float) -> dict:
    """Transforma mascara YOLOE a milimetros del PLANO DEL MARCADOR.

    El resultado NO es un diametro fisico de una fruta elevada del plano.
    """
    if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
        raise CalibrationRejected('image_invalid')
    if not (15.0 <= marker_side_mm <= 150.0 and math.isfinite(marker_side_mm)):
        raise CalibrationRejected('marker_size_invalid')
    if not 0 <= marker_id < 50:
        raise CalibrationRejected('marker_id_invalid')
    height, width = frame.shape[:2]
    if height < 128 or width < 128:
        raise CalibrationRejected('image_too_small')
    try:
        fruit = np.asarray(polygon, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CalibrationRejected('fruit_polygon_invalid') from exc
    if fruit.ndim != 2 or fruit.shape[1] != 2 or len(fruit) < 3 or not np.isfinite(fruit).all():
        raise CalibrationRejected('fruit_polygon_invalid')
    # Evitar mediciones de frutos parcialmente fuera de la imagen.
    margin = max(5.0, min(width, height) * 0.012)
    if (fruit[:, 0].min() <= margin or fruit[:, 0].max() >= width-margin or
            fruit[:, 1].min() <= margin or fruit[:, 1].max() >= height-margin):
        raise CalibrationRejected('fruit_partially_out_of_frame')
    marker = _marker_corners(frame, marker_id)
    marker_contour = np.asarray(marker, dtype=np.float32).reshape(-1, 1, 2)
    fruit_contour = fruit.astype(np.float32).reshape(-1, 1, 2)
    # El marcador no puede estar tapado ni invadir la mascara de la fruta.
    if cv2.intersectConvexConvex(cv2.convexHull(marker_contour), cv2.convexHull(fruit_contour))[0] > 1:
        raise CalibrationRejected('marker_overlaps_fruit')

    side_cm = marker_side_mm / 10.0
    src = np.asarray(marker, dtype=np.float32)
    dst = np.asarray([[0., 0.], [side_cm, 0.], [side_cm, side_cm], [0., side_cm]], dtype=np.float32)
    transform = cv2.getPerspectiveTransform(src, dst)
    if not np.isfinite(transform).all():
        raise CalibrationRejected('invalid_homography')
    # Descartar medidas con fuerte extrapolacion: fruto demasiado lejos del marcador.
    marker_center = src.mean(axis=0)
    fruit_center = fruit.mean(axis=0)
    marker_side_px = float(np.mean([np.linalg.norm(src[(i+1)%4]-src[i]) for i in range(4)]))
    if np.linalg.norm(fruit_center-marker_center) > 9 * marker_side_px:
        raise CalibrationRejected('fruit_too_far_from_marker')

    points = cv2.perspectiveTransform(fruit_contour, transform).reshape(-1, 2)
    if not np.isfinite(points).all():
        raise CalibrationRejected('invalid_homography')
    x_lo, y_lo = points.min(axis=0)
    x_hi, y_hi = points.max(axis=0)
    area = abs(float(cv2.contourArea(points.astype(np.float32))))
    perimeter = float(cv2.arcLength(points.astype(np.float32).reshape(-1, 1, 2), True))
    rect = cv2.minAreaRect(points.astype(np.float32).reshape(-1, 1, 2))
    major, minor = sorted([float(rect[1][0]), float(rect[1][1])], reverse=True)
    values = [x_hi-x_lo, y_hi-y_lo, major, minor, area, perimeter]
    if not all(math.isfinite(float(v)) and v > 0 for v in values):
        raise CalibrationRejected('invalid_projected_geometry')
    return {
        'markerCornersPx': marker,
        'measurements': {
            'widthCm': round(float(x_hi-x_lo), 3),
            'heightCm': round(float(y_hi-y_lo), 3),
            'majorAxisCm': round(float(major), 3),
            'minorAxisCm': round(float(minor), 3),
            'projectedAreaCm2': round(area, 3),
            'projectedPerimeterCm': round(perimeter, 3),
        },
    }
