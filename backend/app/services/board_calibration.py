"""AG-054 I03: robusta proyeccion a un marco ArUco EXTERNO coplanar.

No mide profundidad ni convierte la mascara de una fruta 3D en diametros fisicos.
Admite patrones A3 (histórico) y A4 (compacto), cada uno con coordenadas
FÍSICAS propias. No puede corregir por sí sola la altura 3D de la fruta.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

import cv2
import numpy as np

from .planar_calibration import CalibrationRejected

BOARD_VERSION = 'ag054-board-a3-v1'  # Mantener por compatibilidad con AG054 I03
A4_BOARD_VERSION = 'ag054-board-a4-v1'
BOARD_WIDTH_MM = 390.0
BOARD_HEIGHT_MM = 275.0
MARKER_SIDE_MM = 40.0
MARKER_LAYOUT_MM: dict[int, tuple[float, float]] = {
    0: (15.0, 15.0),
    1: (335.0, 15.0),
    2: (335.0, 220.0),
    3: (15.0, 220.0),
}
BOARD_LAYOUTS = {
    BOARD_VERSION: {
        'width_mm': BOARD_WIDTH_MM,
        'height_mm': BOARD_HEIGHT_MM,
        'marker_side_mm': MARKER_SIDE_MM,
        'markers_mm': MARKER_LAYOUT_MM,
    },
    A4_BOARD_VERSION: {
        'width_mm': 277.0,
        'height_mm': 190.0,
        'marker_side_mm': 30.0,
        'markers_mm': {
            0: (11.0, 11.0),
            1: (236.0, 11.0),
            2: (236.0, 149.0),
            3: (11.0, 149.0),
        },
    },
}
MIN_MARKERS = 3
MIN_MARKER_SIDE_PX = 24.0
MAX_RMS_MM = 1.5


def _marker_candidates(frame: np.ndarray) -> tuple[list[np.ndarray], np.ndarray | None]:
    if not hasattr(cv2, 'aruco'):
        raise RuntimeError('OpenCV sin aruco: instalar opencv-contrib-python.')
    aruco = cv2.aruco
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    params = aruco.DetectorParameters()
    if hasattr(aruco, 'ArucoDetector'):
        corners, ids, _ = aruco.ArucoDetector(dictionary, params).detectMarkers(frame)
    else:
        corners, ids, _ = aruco.detectMarkers(frame, dictionary, parameters=params)
    return corners, ids


def _validated_fruit_polygon(frame: np.ndarray, polygon: Sequence[Sequence[float]]) -> np.ndarray:
    if frame is None or frame.ndim != 3 or frame.shape[2] != 3 or min(frame.shape[:2]) < 128:
        raise CalibrationRejected('image_invalid')
    try:
        fruit = np.asarray(polygon, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CalibrationRejected('fruit_polygon_invalid') from exc
    if fruit.ndim != 2 or fruit.shape[1] != 2 or fruit.shape[0] < 3 or not np.isfinite(fruit).all():
        raise CalibrationRejected('fruit_polygon_invalid')
    height, width = frame.shape[:2]
    margin = max(5.0, 0.012 * min(height, width))
    if (fruit[:, 0].min() <= margin or fruit[:, 0].max() >= width - margin or
        fruit[:, 1].min() <= margin or fruit[:, 1].max() >= height - margin):
        raise CalibrationRejected('fruit_partially_out_of_frame')
    contour = fruit.astype(np.float32).reshape(-1, 1, 2)
    if cv2.contourArea(contour) <= 25.0:
        raise CalibrationRejected('fruit_polygon_invalid')
    return contour


def _board_points(marker_id: int, layout: dict) -> np.ndarray:
    x, y = layout['markers_mm'][marker_id]
    side = layout['marker_side_mm']
    return np.asarray([
        [x, y], [x + side, y], [x + side, y + side], [x, y + side]
    ], dtype=np.float32)


def measure_board_projection(
    frame: np.ndarray,
    polygon: Sequence[Sequence[float]],
    board_version: str = BOARD_VERSION,
) -> dict:
    """Homografia multimarcas; magnitudes 2D en cm del PLANO del tablero.

    Se descarta si marcadores no son independientes, si se recorta la fruta,
    o si la reproyeccion es inconsistente. NO corrige la altura 3D de la fruta.
    """
    if board_version not in BOARD_LAYOUTS:
        raise CalibrationRejected('board_version_unsupported')
    layout = BOARD_LAYOUTS[board_version]
    marker_layout = layout['markers_mm']
    fruit = _validated_fruit_polygon(frame, polygon)
    corners, ids = _marker_candidates(frame)
    if ids is None:
        raise CalibrationRejected('board_markers_insufficient')
    identified: dict[int, np.ndarray] = {}
    ids_flat = ids.flatten().tolist()
    height, width = frame.shape[:2]
    for index, marker_id in enumerate(ids_flat):
        if marker_id not in marker_layout:
            continue
        if marker_id in identified:
            raise CalibrationRejected('board_marker_duplicated')
        points = np.asarray(corners[index], dtype=np.float32).reshape(4, 2)
        if not np.isfinite(points).all():
            raise CalibrationRejected('board_marker_invalid')
        margin = 4.0
        if (points[:, 0].min() < margin or points[:, 0].max() > width - margin or
            points[:, 1].min() < margin or points[:, 1].max() > height - margin):
            raise CalibrationRejected('board_marker_cropped')
        lengths = [float(np.linalg.norm(points[(i + 1) % 4] - points[i])) for i in range(4)]
        if min(lengths) < MIN_MARKER_SIDE_PX or max(lengths) / min(lengths) > 2.5:
            raise CalibrationRejected('board_marker_deformed')
        # Incluso si la fruta es grande, nunca declarar medida si oculta la marca.
        intersection, _ = cv2.intersectConvexConvex(
            cv2.convexHull(fruit), cv2.convexHull(points.reshape(-1, 1, 2)),
        )
        if intersection > 1.0:
            raise CalibrationRejected('board_marker_overlaps_fruit')
        identified[int(marker_id)] = points

    used = sorted(identified)
    if len(used) < MIN_MARKERS:
        raise CalibrationRejected('board_markers_insufficient')
    # Tres marcadores deben cubrir ambas direcciones: evita una sola fila.
    layout_x = {marker_layout[i][0] for i in used}
    layout_y = {marker_layout[i][1] for i in used}
    if len(layout_x) < 2 or len(layout_y) < 2:
        raise CalibrationRejected('board_coverage_insufficient')

    source = np.vstack([identified[i] for i in used]).astype(np.float32)
    target = np.vstack([_board_points(i, layout) for i in used]).astype(np.float32)
    transform, inliers = cv2.findHomography(source, target, cv2.RANSAC, 1.5)
    if transform is None or inliers is None or not np.isfinite(transform).all():
        raise CalibrationRejected('board_homography_invalid')
    if int(inliers.sum()) < len(used) * 4 - 1:
        raise CalibrationRejected('board_inconsistent_markers')
    reconstructed = cv2.perspectiveTransform(source.reshape(-1, 1, 2), transform).reshape(-1, 2)
    errors = np.linalg.norm(reconstructed - target, axis=1)
    rms_mm = float(np.sqrt(np.mean(np.square(errors))))
    if not math.isfinite(rms_mm) or rms_mm > MAX_RMS_MM:
        raise CalibrationRejected('board_reprojection_error')

    projected = cv2.perspectiveTransform(fruit, transform).reshape(-1, 2)
    if not np.isfinite(projected).all():
        raise CalibrationRejected('board_projection_invalid')
    # Exigir que la fruta esté dentro de la región espacial calibrada.
    if (projected[:, 0].min() < 0 or projected[:, 0].max() > layout['width_mm'] or
        projected[:, 1].min() < 0 or projected[:, 1].max() > layout['height_mm']):
        raise CalibrationRejected('fruit_outside_board_area')
    planar_cm = (projected / 10.0).astype(np.float32)
    contour = planar_cm.reshape(-1, 1, 2)
    x_lo, y_lo = planar_cm.min(axis=0)
    x_hi, y_hi = planar_cm.max(axis=0)
    area = abs(float(cv2.contourArea(contour)))
    perimeter = float(cv2.arcLength(contour, True))
    rotated = cv2.minAreaRect(contour)
    major, minor = sorted((float(rotated[1][0]), float(rotated[1][1])), reverse=True)
    values = [x_hi - x_lo, y_hi - y_lo, major, minor, area, perimeter]
    if not all(math.isfinite(float(v)) and float(v) > 0 for v in values):
        raise CalibrationRejected('board_projection_invalid')

    return {
        'boardVersion': board_version,
        'markerIds': used,
        'markerCornersPx': {str(i): [[round(float(x), 2), round(float(y), 2)]
                                    for x, y in identified[i]] for i in used},
        'rmsReprojectionMm': round(rms_mm, 4),
        'measurementPlane': 'marco_independiente_a_nivel_plataforma',
        'measurements': {
            'widthCm': round(float(x_hi - x_lo), 3),
            'heightCm': round(float(y_hi - y_lo), 3),
            'majorAxisCm': round(major, 3),
            'minorAxisCm': round(minor, 3),
            'projectedAreaCm2': round(area, 3),
            'projectedPerimeterCm': round(perimeter, 3),
        },
    }


def compare_with_caliper(projected: dict, major_cm: float, minor_cm: float) -> dict:
    """Comparación, no corrección ni acreditación automática."""
    major = float(projected['majorAxisCm'])
    minor = float(projected['minorAxisCm'])
    if not all(math.isfinite(v) for v in (major, minor, major_cm, minor_cm)):
        raise ValueError('non_finite_dimension')
    if not (0.1 <= minor_cm <= major_cm <= 60.0):
        raise ValueError('invalid_manual_reference')
    delta_major = major - major_cm
    delta_minor = minor - minor_cm
    return {
        'major': {
            'projectedCm': round(major, 3), 'manualCm': round(major_cm, 3),
            'signedErrorCm': round(delta_major, 3),
            'absoluteErrorCm': round(abs(delta_major), 3),
            'relativeAbsoluteErrorPct': round(100.0 * abs(delta_major) / major_cm, 2),
        },
        'minor': {
            'projectedCm': round(minor, 3), 'manualCm': round(minor_cm, 3),
            'signedErrorCm': round(delta_minor, 3),
            'absoluteErrorCm': round(abs(delta_minor), 3),
            'relativeAbsoluteErrorPct': round(100.0 * abs(delta_minor) / minor_cm, 2),
        },
        'physicalDimensionsValidated': False,
        'status': 'comparison_only',
    }
