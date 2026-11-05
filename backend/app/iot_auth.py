"""Validación del origen HTTP de las lecturas publicadas por el puente IoT.

Las claves son del puente de confianza, no del ESP32. La autenticación del
hardware, la calibración y la protección de la conexión USB son controles
independientes y requieren validación física.
"""
import hmac
import json
import os

from fastapi import Header, HTTPException

from .iot_schemas import MeasurementCreate


def authenticate_measurement_sender(
    payload: MeasurementCreate,
    x_device_key: str | None = Header(default=None, alias="X-Device-Key"),
) -> None:
    """Verifica el token para el device_id declarado, fallando cerrado."""
    raw = os.getenv("AGROSCAN_IOT_KEYS_JSON", "")
    try:
        keys = json.loads(raw)
    except (ValueError, TypeError):
        keys = None

    if not isinstance(keys, dict) or not keys:
        raise HTTPException(status_code=503, detail="Autenticación IoT no configurada.")

    # Las claves son independientes por dispositivo; nunca se registran ni devuelven.
    expected = keys.get(payload.device_id)
    if (
        not isinstance(expected, str)
        or len(expected) < 32
        or len(expected) > 256
        or not isinstance(x_device_key, str)
        or len(x_device_key) > 256
        or not hmac.compare_digest(expected, x_device_key)
    ):
        raise HTTPException(status_code=401, detail="Credencial de dispositivo inválida.")
