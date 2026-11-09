"""AG-037: reglas de incertidumbre de DETECCIÓN; no clasifican calidad E0/E1/E2.

Umbral conservador respaldado exploratoriamente por AG-036 (97 imágenes, 32 revisadas).
No se afirma calibración estadística ni exactitud del detector sobre todo el conjunto.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

CAPTURE_THRESHOLD = 0.40
INFERENCE_FLOOR = 0.25
RULE_VERSION = 'ag037-deteccion-incierta-v1'


@dataclass(frozen=True)
class GateResult:
    pending: bool
    reason: str
    confidence: float | None
    candidate_count: int


def classify_detection(product: str, detections: list[dict]) -> GateResult:
    """Clasifica aptitud de la DETECCIÓN, nunca la calidad visual de la fruta.

    `detections` contiene label, confidence y mask (bool) de YOLOE.
    Se bloquea por incertidumbre si hay 0 o >1 detecciones de la clase esperada,
    clase errónea, ausencia de máscara o confianza <0,40.
    """
    if product not in ('mango', 'tomate'):
        raise ValueError('Producto no admitido')
    if not isinstance(detections, list):
        raise ValueError('Predicciones inválidas')
    if not detections:
        return GateResult(True, 'sin_deteccion', None, 0)

    valid = []
    for d in detections:
        if not isinstance(d, dict):
            raise ValueError('Predicción inválida')
        label = str(d.get('label', '')).lower()
        try:
            confidence = float(d.get('confidence'))
        except (TypeError, ValueError) as exc:
            raise ValueError('Confianza inválida') from exc
        if not isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError('Confianza no finita o fuera de rango')
        expected = 'mango' in label if product == 'mango' else 'tomato' in label or 'tomate' in label
        if expected:
            valid.append((confidence, bool(d.get('mask', False))))
    if not valid:
        return GateResult(True, 'clase_no_esperada', None, 0)
    if len(valid) > 1:
        return GateResult(True, 'multiples_candidatos', max(x[0] for x in valid), len(valid))
    confidence, mask = valid[0]
    if confidence < CAPTURE_THRESHOLD:
        return GateResult(True, 'confianza_insuficiente', confidence, 1)
    if not mask:
        return GateResult(True, 'segmentacion_no_evaluable', confidence, 1)
    return GateResult(False, 'deteccion_apta_para_captura', confidence, 1)
