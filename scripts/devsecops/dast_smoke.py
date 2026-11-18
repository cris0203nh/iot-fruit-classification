#!/usr/bin/env python3
"""Smoke de solo lectura y rechazos de acceso contra API local efímera (SaaS-07)."""
import json
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = 'http://127.0.0.1:8765'


def request(path, method='GET', payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    h = dict(headers or {})
    if data is not None:
        h['Content-Type'] = 'application/json'
    r = Request(BASE + path, method=method, headers=h, data=data)
    try:
        with urlopen(r, timeout=8) as response:
            return response.status, response.read(), response.headers
    except HTTPError as error:
        with error:
            return error.code, error.read(), error.headers


def verify():
    code, raw, _ = request('/api/health')
    assert code == 200 and json.loads(raw).get('status') == 'ok', 'Health no disponible'
    code, raw, _ = request('/openapi.json')
    assert code == 200 and 'openapi' in json.loads(raw), 'OpenAPI no disponible'
    for url in ('/api/auth/me', '/api/iot/status', '/api/lots'):
        code, _, _ = request(url)
        assert code == 401, f'{url} sin credenciales: HTTP {code} en vez de 401'
    # SaaS-07: Bearer individual obligatorio, NO X-Device-Key ni JWT humano.
    code, _, _ = request('/api/iot/measurements', 'POST', {
        'schema_version': 1, 'device_id': 'DAST-DEVICE', 'boot_id': 'dast',
        'seq': 0, 'weight_g': 250, 'stable': True,
        'calibration_version': 'DAST', 'zero_confirmed': True,
        'observed_at': datetime.now(timezone.utc).isoformat(),
    })
    assert code == 401, f'IoT sin Bearer respondió {code}, no 401'
    # CORS con Authorization; no prueba de permiso de escritura.
    preflight = Request(BASE + '/api/iot/measurements', method='OPTIONS', headers={
        'Origin': 'http://localhost:5173',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'authorization,content-type',
    })
    with urlopen(preflight, timeout=8) as response:
        assert response.status == 200, 'CORS preflight rechazado'
        assert response.headers.get('Access-Control-Allow-Origin') == 'http://localhost:5173', 'CORS origen incorrecto'
    # Las cabeceras de protección se auditan con ZAP, sin asumir que ya están remediadas.


if __name__ == '__main__':
    try:
        verify()
        print('DAST smoke: auth SaaS-07, CORS, OpenAPI y health aprobados')
    except (OSError, ValueError, AssertionError) as exc:
        print('DAST smoke: comprobación no aprobada', file=sys.stderr)
        raise SystemExit(1)
