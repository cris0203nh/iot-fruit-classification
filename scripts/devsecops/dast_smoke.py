#!/usr/bin/env python3
"""Comprobaciones HTTP mínimas contra API aislada, sin enviar credenciales."""

import json
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8765"


def request(path: str, method: str = "GET", body=None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=8) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        with exc:
            return exc.code, json.load(exc)


def verify() -> None:
    status, data = request("/api/health")
    assert status == 200 and data.get("status") == "ok", "health no disponible"
    status, data = request("/openapi.json")
    assert status == 200 and data.get("openapi"), "OpenAPI no disponible"
    for path in ("/api/iot/status", "/api/auth/me", "/api/users"):
        status, _ = request(path)
        assert status == 401, f"{path} no devolvió 401; estado={status}"
    status, _ = request("/api/iot/measurements", "POST", {
        "schema_version": 1, "device_id": "DAST-DEVICE", "boot_id": "test-boot",
        "seq": 0, "weight_g": 250, "stable": True,
        "calibration_version": "DAST-TEST", "zero_confirmed": True,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    })
    assert status == 401, f"POST IoT sin clave no devolvió 401; estado={status}"


if __name__ == "__main__":
    try:
        verify()
        print("Smoke DAST: health/OpenAPI OK y rutas protegidas responden 401.")
    except (OSError, ValueError, AssertionError) as exc:
        print(f"Error en smoke DAST: {exc}", file=sys.stderr)
        raise SystemExit(1)
