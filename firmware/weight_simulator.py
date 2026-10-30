"""Cliente de pruebas IoT. Genera pesos simulados; no lee ni calibra hardware."""
import argparse
import http.client
import json
import math
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


def send(url, payload, attempts=3, timeout=2, delay=0.5):
    """Reintenta solo red/5xx; conserva exactamente el mensaje original."""
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
        raise ValueError('Usa una URL HTTP(S) sin credenciales')
    if not 1 <= attempts <= 3 or not 0 < timeout <= 2:
        raise ValueError('Máximo 3 intentos y timeout de hasta 2 segundos')
    body = json.dumps(payload, allow_nan=False).encode('utf-8')
    opener = build_opener(NoRedirect())
    last_error = None
    for attempt in range(attempts):
        request = Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
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
    boot_id = str(uuid.uuid4())
    try:
        # Validar toda la secuencia antes del primer envío.
        messages = [measurement(w, i, boot_id, args.stable) for i, w in enumerate(args.weights, 1)]
        print('SIMULACIÓN: no son mediciones de una balanza real', flush=True)
        for message in messages:
            print(json.dumps(message, ensure_ascii=False, allow_nan=False), flush=True)
            if args.url:
                print(json.dumps(send(args.url, message)), flush=True)
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
