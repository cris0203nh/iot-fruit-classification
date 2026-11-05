#!/usr/bin/env python3
"""Comprobaciones HTTP sobre FastAPI aislada, sin datos ni credenciales reales."""

import json
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8765"


def request(path: str, method: str = "GET", body=None, headers=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    sent_headers = dict(headers or {})
    if data is not None:
        sent_headers["Content-Type"] = "application/json"
    req = Request(BASE + path, data=data, headers=sent_headers, method=method)
    try:
        with urlopen(req, timeout=8) as response:
            return response.status, json.load(response), response.headers
    except HTTPError as exc:
        with exc:
            return exc.code, json.load(exc), exc.headers


def check_security_headers(headers, *, api=True):
    assert headers.get("X-Content-Type-Options") == "nosniff", "falta nosniff"
    assert headers.get("Cross-Origin-Resource-Policy") == "same-origin", "falta CORP"
    assert headers.get("Referrer-Policy") == "no-referrer", "falta Referrer-Policy"
    if api:
        assert headers.get("Cache-Control") == "no-store", "falta no-store API"


def verify() -> None:
    status, data, headers = request("/api/health")
    assert status == 200 and data.get("status") == "ok", "health no disponible"
    check_security_headers(headers)

    status, data, headers = request("/openapi.json")
    assert status == 200 and data.get("openapi"), "OpenAPI no disponible"
    check_security_headers(headers, api=False)

    for path in ("/api/iot/status", "/api/auth/me", "/api/users"):
        status, _, headers = request(path)
        assert status == 401, f"{path} no devolvió 401; estado={status}"
        check_security_headers(headers)

    status, _, headers = request("/api/iot/measurements", "POST", {
        "schema_version": 1, "device_id": "DAST-DEVICE", "boot_id": "test-boot",
        "seq": 0, "weight_g": 250, "stable": True,
        "calibration_version": "DAST-TEST", "zero_confirmed": True,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    })
    assert status == 401, f"POST IoT sin clave no devolvió 401; estado={status}"
    check_security_headers(headers)

    # Un preflight real debe conservar CORS, incluida la cabecera IoT del
    # puente y los Authorization Bearer usados por React.
    preflight = Request(BASE + "/api/iot/measurements", method="OPTIONS", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,x-device-key,content-type",
    })
    with urlopen(preflight, timeout=8) as response:
        assert response.status == 200, "preflight CORS rechazado"
        assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173", "CORS origen incorrecto"
        check_security_headers(response.headers)


if __name__ == "__main__":
    try:
        verify()
        print("Smoke DAST: health/OpenAPI, seguridad HTTP, CORS y 401 correctos.")
    except (OSError, ValueError, AssertionError) as exc:
        print(f"Error en smoke DAST: {exc}", file=sys.stderr)
        raise SystemExit(1)
