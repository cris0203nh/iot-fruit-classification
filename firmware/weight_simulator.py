"""Cliente de pruebas IoT. Genera pesos simulados; no lee ni calibra hardware."""
import argparse
import datetime as dt
import http.client
import json
import math
import os
import ipaddress
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def measurement(weight, seq, boot_id, stable=False):
    if not math.isfinite(weight) or not 0 <= weight <= 5000:
        raise ValueError('El peso debe ser finito y estar entre 0 y 5000 g')
    return dict(schema_version=1, device_id='simulator-fernando-001',
                boot_id=boot_id, seq=seq, weight_g=weight, stable=stable,
                calibration_version='simulated-not-calibrated')


def send(url, payload, attempts=3, timeout=2, delay=0.5, *, device_key=None):
    """Reintenta solo red/5xx; conserva exactamente el mensaje original."""
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ValueError('Usa una URL HTTP(S) sin credenciales')
    if parts.scheme == 'http':
        try:
            is_local = parts.hostname.lower() == 'localhost' or ipaddress.ip_address(parts.hostname).is_loopback
        except ValueError:
            is_local = False
        if not is_local:
            raise ValueError('Se requiere HTTPS fuera de localhost')
    if device_key is None:
        device_key = os.getenv('AGROSCAN_IOT_DEVICE_KEY')
    if not isinstance(device_key, str) or not 32 <= len(device_key) <= 256:
        raise ValueError('Configura AGROSCAN_IOT_DEVICE_KEY con al menos 32 caracteres')
    if not 1 <= attempts <= 3 or not 0 < timeout <= 2:
        raise ValueError('Máximo 3 intentos y timeout de hasta 2 segundos')
    body = json.dumps(payload, allow_nan=False).encode('utf-8')
    opener = build_opener(NoRedirect())
    last_error = None
    for attempt in range(attempts):
        request = Request(url, data=body, headers={'Content-Type': 'application/json', 'X-Device-Key': device_key}, method='POST')
        try:
            with opener.open(request, timeout=timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f'HTTP inesperado: {response.status}')
                result = json.loads(response.read())
                if (not isinstance(result, dict)
                        or type(result.get('received')) is not bool
                        or type(result.get('duplicate')) is not bool
                        or not isinstance(result.get('receivedAt'), str)):
                    raise RuntimeError('Respuesta incompatible con el contrato comunicado')
                if not result['received']:
                    raise RuntimeError('El servidor no confirmó recepción')
                return result
        except HTTPError as exc:
            exc.close()
            if not 500 <= exc.code <= 599:
                raise RuntimeError(f'HTTP {exc.code}: no se reintenta este mensaje') from exc
            last_error = exc
        except (URLError, OSError, http.client.HTTPException) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(delay * (2 ** attempt))
    raise RuntimeError(f'Envío fallido después de {attempts} intentos: {last_error}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights', nargs='+', type=float, default=[0, 152.8, 480, 0])
    parser.add_argument('--stable', action='store_true', help='Simula estabilidad; no la calcula')
    parser.add_argument('--url', help='Endpoint POST. Sin esta opción solo imprime JSON')
    args = parser.parse_args()
    if args.url and not os.getenv('AGROSCAN_IOT_DEVICE_KEY'):
        parser.error('Configura AGROSCAN_IOT_DEVICE_KEY antes de reenviar datos')
    boot_id = str(uuid.uuid4())
    try:
        # Validar toda la secuencia antes del primer envío.
        messages = [measurement(w, i, boot_id, args.stable) for i, w in enumerate(args.weights, 1)]
        print('SIMULACIÓN: no son mediciones de una balanza real', flush=True)
        for message in messages:
            if args.url:
                # El backend exige timestamp UTC del emisor; crearlo una sola vez
                # para conservar exactamente el mismo cuerpo durante reintentos.
                message['observed_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
            print(json.dumps(message, ensure_ascii=False, allow_nan=False), flush=True)
            if args.url:
                print(json.dumps(send(args.url, message)), flush=True)
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
