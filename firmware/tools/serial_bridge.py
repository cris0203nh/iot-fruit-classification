"""Read ESP32 JSON lines and optionally forward valid weights to a backend.
No network is used unless --url is supplied. Simulation is rejected by default.
"""
import argparse
import datetime as dt
import http.client
import json
import math
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

FIELDS = {
    'schema_version',
    'device_id',
    'boot_id',
    'seq',
    'weight_g',
    'stable',
    'zero_confirmed',
    'calibration_version'
}

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def validate_url(url):
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.fragment:
        raise ValueError('URL HTTP(S) sin credenciales ni fragmento requerida')

def extract_measurement(envelope, allow_simulated=False):
    if not isinstance(envelope, dict) or envelope.get('type') != 'telemetry':
        return None
    simulated = envelope.get('simulated')
    if type(simulated) is not bool:
        raise ValueError('Falta indicador simulated booleano')
    m = envelope.get('measurement')
    if m is None:
        return None  # Never invent zero for disconnected/uncalibrated sensors.
    if not isinstance(m, dict) or set(m) != FIELDS:
        raise ValueError('Campos de measurement incompatibles')
    if type(m['schema_version']) is not int or m['schema_version'] != 1:
        raise ValueError('schema_version incompatible')
    if type(m['seq']) is not int or not 1 <= m['seq'] <= 4294967295:
        raise ValueError('seq inválido')
    if type(m['stable']) is not bool:
        raise ValueError('stable debe ser booleano')
    w = m['weight_g']
    if type(m['zero_confirmed']) is not bool:
        raise ValueError('zero_confirmed debe ser booleano')
    if type(w) not in (int, float) or not math.isfinite(w) or not 0 <= w <= 5000:
        raise ValueError('Peso inválido')
    for field in ('device_id', 'boot_id', 'calibration_version'):
        if not isinstance(m[field], str) or not 1 <= len(m[field]) <= 64:
            raise ValueError(f'{field} inválido')
    marked = m['device_id'].startswith('simulator-') or m['calibration_version'].startswith('simulated-')
    if simulated != marked:
        raise ValueError('Identificación de simulación inconsistente')
    if simulated and not allow_simulated:
        raise ValueError('Simulación bloqueada para envío; usa --allow-simulated solo en pruebas')
    if envelope.get('status') not in ('stable', 'unstable') or (envelope['status'] == 'stable') != m['stable']:
        raise ValueError('Estado inconsistente con measurement')
    return dict(m)

def send(url, payload, attempts=3, timeout=2.0, delay=0.25):
    validate_url(url)
    if type(attempts) is not int or not 1 <= attempts <= 3 or not 0 < timeout <= 2 or not 0 <= delay <= 1:
        raise ValueError('Intentos 1–3, timeout (0,2], delay [0,1] requeridos')
    body = json.dumps(payload, allow_nan=False, separators=(',', ':')).encode()
    opener = build_opener(NoRedirect())
    last_error = None
    for i in range(attempts):
        req = Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with opener.open(req, timeout=timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f'HTTP inesperado {response.status}')
                try:
                    raw = response.read(65537)
                    if len(raw) > 65536:
                        raise RuntimeError('Respuesta demasiado grande')
                    declared = response.headers.get('Content-Length')
                    if declared is not None and declared.isdigit() and len(raw) < int(declared):
                        raise http.client.IncompleteRead(raw, int(declared)-len(raw))
                    ack = json.loads(raw)
                except (ValueError, UnicodeError) as exc:
                    raise RuntimeError('Respuesta no es JSON válido') from exc
                if (not isinstance(ack, dict) or ack.get('received') is not True
                        or type(ack.get('duplicate')) is not bool
                        or not isinstance(ack.get('receivedAt'), str) or not ack['receivedAt']):
                    raise RuntimeError('Respuesta no confirma el contrato comunicado')
                return ack
        except HTTPError as exc:
            code = exc.code
            exc.close()
            if not 500 <= code <= 599:
                raise RuntimeError(f'HTTP {code}; no se reintenta') from exc
            last_error = exc
        except (URLError, OSError, http.client.HTTPException) as exc:
            # Includes truncated responses/IncompleteRead after persistence.
            last_error = exc
        if i+1 < attempts:
            time.sleep(delay * 2**i)
    raise RuntimeError(f'Envío fallido tras {attempts} intentos: {last_error}')

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, help='COM3 en Windows o /dev/ttyUSB0 en Linux')
    parser.add_argument('--url', help='Endpoint POST explícito; omitir para solo visualizar')
    parser.add_argument('--allow-simulated', action='store_true')
    parser.add_argument('--tare-on-open', action='store_true', help='Solo con plataforma vacía; solicita tara al abrir')
    args = parser.parse_args(argv)
    if args.url:
        validate_url(args.url)
    try:
        import serial
    except ImportError:
        parser.exit(1, 'Instala pyserial: python -m pip install pyserial==3.5\n')
    try:
        with serial.Serial(args.port, 115200, timeout=1) as port:
            time.sleep(2)  # USB opening can reset the ESP32.
            port.reset_input_buffer()
            if args.tare_on_open:
                port.write(b'TARE\n')  # Explicit operator request; platform must be empty.
            last_identity = None
            while True:
                line = port.readline(4097)
                if not line:
                    continue
                if len(line) > 4096 or not line.endswith(b'\n'):
                    port.reset_input_buffer()
                    print('Línea parcial/excesiva descartada', file=sys.stderr)
                    continue
                try:
                    envelope = json.loads(line)
                    print(json.dumps({'observed_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                                      'telemetry': envelope}, allow_nan=False), flush=True)
                    if not args.url:
                        continue
                    message = extract_measurement(envelope, args.allow_simulated)
                    if message is None:
                        continue
                    identity = (message['device_id'], message['boot_id'], message['seq'])
                    if identity == last_identity:
                        continue
                    print(json.dumps({'ack': send(args.url, message)}), flush=True)
                    last_identity = identity
                    port.reset_input_buffer()  # Do not replay queued stale weights after retries.
                except (ValueError, RuntimeError) as exc:
                    print(f'Descartado: {exc}', file=sys.stderr)
                    port.reset_input_buffer()
    except KeyboardInterrupt:
        return 0
    except serial.SerialException as exc:
        parser.exit(1, f'Conexión serial interrumpida: {exc}\n')

if __name__ == '__main__':
    main()
