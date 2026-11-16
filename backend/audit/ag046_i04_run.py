"""AG-046/I04: tres arranques reales de FastAPI y comprobación de persistencia.

Un sandbox bajo tempfile contiene TODOS los datos. Nunca abre ni restaura
backend/data/agroscan.db; no usa el puerto de la instancia operativa.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
HOST = Path(__file__).with_name('ag046_i04_host.py')
LABELS = {
    'RST-01': 'Lotes, piezas, evaluaciones y lecturas SQLite sobreviven al reinicio',
    'RST-02': 'Fotografias originales conservan bytes, rutas y SHA-256',
    'RST-03': 'Bitacora de decisiones, autores y reporte de trazabilidad son estables',
    'RST-04': 'FastAPI detiene y reinicia procesos independientes y recupera /api/health',
}


def _head() -> str | None:
    try:
        x = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
            capture_output=True, text=True, timeout=5, check=False)
        return x.stdout.strip() if x.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def _assert(ok: bool, reason: str):
    if not ok:
        raise AssertionError(reason)


def _api(client: httpx.Client, method: str, route: str, expected: int = 200, **kwargs):
    response = client.request(method, route, **kwargs)
    if response.status_code != expected:
        raise AssertionError(f'{method} {route}: esperado HTTP {expected}; '
                             f'recibido {response.status_code}; '
                             f'detalle={response.text[:350]}')
    return response


def _sqlite_snapshot(db_file: Path, root: Path) -> dict:
    with closing(sqlite3.connect(str(db_file), timeout=5)) as db:
        check = db.execute('PRAGMA integrity_check').fetchone()[0]
        foreign = db.execute('PRAGMA foreign_key_check').fetchall()
        _assert(check == 'ok', f'SQLite integrity_check: {check}')
        _assert(not foreign, f'Claves foraneas invalidas: {foreign[:5]}')
        tables = {
            'lots': 'SELECT id, code, product, status FROM lots ORDER BY id',
            'pieces': 'SELECT id, lot_id, code FROM pieces ORDER BY id',
            'evaluations': 'SELECT id, lot_id, piece_ref_id, piece_id, status, image_count FROM evaluations ORDER BY id',
            'images': 'SELECT id, evaluation_id, view, relative_path, content_type, size_bytes FROM images ORDER BY id',
            'reviews': 'SELECT id, evaluation_id, type, actor_id, reason, previous_value, updated_value FROM reviews ORDER BY id',
            'review_decision_evidence': 'SELECT review_id, evaluation_id, image_id, image_sha256, action, request_id, payload_sha256 FROM review_decision_evidence ORDER BY review_id',
            'measurements': 'SELECT id, device_id, boot_id, seq, weight_g, stable FROM measurements ORDER BY id',
        }
        rows = {key: [list(row) for row in db.execute(query).fetchall()]
                for key, query in tables.items()}
    images = {}
    for item in rows['images']:
        path = root / item[3]
        _assert(path.is_file() and path.resolve().is_relative_to(root.resolve()),
                f'Falta imagen o ruta no autorizada: {item[3]}')
        data = path.read_bytes()
        _assert(len(data) == item[5], f'Tamano de imagen inconsistente: {item[3]}')
        images[item[3]] = hashlib.sha256(data).hexdigest()
    return {'integrityCheck': check, 'foreignKeyErrors': len(foreign),
            'tables': rows, 'imageSha256': images}


def _start(sandbox: Path, env: dict, process_number: int, run: Path):
    port = _port()
    launch_env = dict(env)
    launch_env['AG046_I04_PORT'] = str(port)
    file = (run / f'uvicorn_proceso_{process_number}.log').open('w', encoding='utf-8')
    proc = subprocess.Popen([sys.executable, '-u', str(HOST)], cwd=BACKEND,
                            env=launch_env, stdin=subprocess.DEVNULL,
                            stdout=file, stderr=subprocess.STDOUT)
    url = f'http://127.0.0.1:{port}'
    deadline = time.monotonic() + 50
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            file.close()
            tail = (run / f'uvicorn_proceso_{process_number}.log').read_text(
                encoding='utf-8', errors='replace')[-2500:]
            raise RuntimeError(f'Proceso {process_number} finalizo antes del health:\n{tail}')
        try:
            health = httpx.get(url + '/api/health', timeout=1, trust_env=False)
            if health.status_code == 200 and health.json().get('status') == 'ok':
                return proc, file, url
        except (httpx.RequestError, ValueError):
            pass
        time.sleep(.25)
    proc.kill()
    proc.wait(timeout=10)
    file.close()
    raise RuntimeError(f'No respondio /api/health en arranque {process_number}; revisar uvicorn_proceso_{process_number}.log')


def _stop(proc: subprocess.Popen, handle, url: str, nonce: str, abrupt: bool):
    try:
        if proc.poll() is None:
            if abrupt:
                proc.kill()
            else:
                x = httpx.post(url + '/__ag046_i04__/shutdown',
                    headers={'X-AG046-I04-Nonce': nonce}, timeout=4, trust_env=False)
                _assert(x.status_code == 200, f'Apagado HTTP no confirmado: {x.status_code}; detalle={x.text[:350]}')
            proc.wait(timeout=20)
        _assert(proc.poll() is not None, 'Proceso sigue activo tras parada')
        if not abrupt:
            _assert(proc.returncode == 0, f'Apagado no ordenado (exit={proc.returncode})')
        try:
            httpx.get(url + '/api/health', timeout=.8, trust_env=False)
        except httpx.RequestError:
            return
        raise AssertionError('Health respondio despues de terminar el proceso')
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
        handle.close()


def _login(client: httpx.Client, username: str, password: str) -> dict:
    r = _api(client, 'POST', '/api/auth/login', data={
        'username': username, 'password': password}, expected=200)
    token = r.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def _api_snapshot(client: httpx.Client, seed_id: str, code: str,
                  extra_id: str, lot_id: int, headers: dict) -> dict:
    seed = _api(client, 'GET', f'/api/evaluations/{seed_id}', headers=headers).json()
    images = {}
    for image in seed['evidence']:
        content = _api(client, 'GET', image['imageUrl'], headers=headers).content
        images[image['id']] = {'sha256': hashlib.sha256(content).hexdigest(),
                               'bytes': len(content), 'view': image['view']}
    report = _api(client, 'GET', '/api/piece-history/report',
                  headers=headers, params={'lot': 'AG046-I04-SEED'}).json()
    _assert(hashlib.sha256(report['csv'].encode('utf-8')).hexdigest()
            == report['csvSha256'], 'Reporte CSV no coincide con SHA-256')
    decisions = _api(client, 'GET', f'/api/evaluations/{seed_id}/review-decisions',
                     headers=headers).json()
    return {
        'seedEvaluation': seed,
        'seedTraceability': _api(client, 'GET', f'/api/evaluations/{seed_id}/traceability',
                                headers=headers).json(),
        'seedHumanDecisions': decisions,
        'seedImages': images,
        'pieceHistory': _api(client, 'GET', '/api/piece-history',
                             headers=headers, params={'lot': 'AG046-I04-SEED'}).json(),
        'pieceReportComparable': {k: v for k, v in report.items() if k != 'generatedAt'},
        'newLot': _api(client, 'GET', f'/api/lots/{lot_id}', headers=headers).json(),
        'newEvaluations': _api(client, 'GET', '/api/evaluations',
                                headers=headers, params={'lot': code}).json(),
        'extraEvaluation': _api(client, 'GET', f'/api/evaluations/{extra_id}',
                                headers=headers).json(),
    }


def main() -> int:
    started = datetime.now(timezone.utc)
    run = ROOT / 'docs' / 'ag046' / 'runs' / ('AG046_I04_' + started.strftime('%Y%m%dT%H%M%S_%fZ'))
    run.mkdir(parents=True, exist_ok=False)
    record = {'activity': 'AG-046/AGROP-54', 'increment': 'I04',
              'timestampUtc': started.isoformat(), 'gitHead': _head(),
              'python': sys.version.split()[0],
              'environment': 'FastAPI Uvicorn real, proceso unico, solo localhost, SQLite temporal',
              'productionDataUsed': False, 'hardwareUsed': False,
              'realPhotosUsed': False, 'multiWorkerVerified': False,
              'checkpoints': [], 'checks': {key: {'status': 'NO_EJECUTADO', 'detail': LABELS[key]}
                                           for key in LABELS}}
    active = None
    process_ids = []
    tempdir = None
    try:
        tempdir = tempfile.TemporaryDirectory(prefix='ag046-i04-')
        sandbox = Path(tempdir.name).resolve()
        sandbox_token = secrets.token_hex(32)
        (sandbox / '.ag046-i04-sandbox').write_text(sandbox_token, encoding='ascii')
        data = sandbox / 'data'
        data.mkdir()
        env = dict(os.environ)
        env.update({'AG046_I04_DATA_DIR': str(data),
                    'AG046_I04_SANDBOX_ROOT': str(sandbox),
                    'AG046_I04_SANDBOX_TOKEN': sandbox_token,
                    'AG046_I04_NONCE': secrets.token_urlsafe(32),
                    'AG046_I04_PASSWORD': secrets.token_urlsafe(24),
                    'AGROSCAN_JWT_SECRET': secrets.token_hex(40),
                    'AGROSCAN_JWT_ALGORITHM': 'HS256',
                    'AGROSCAN_DEMO_ORIGINS': '',
                    'PYTHONPATH': os.pathsep.join([str(BACKEND), str(ROOT)]),
                    'PYTHONDONTWRITEBYTECODE': '1'})
        _assert(not (data / 'agroscan.db').exists(), 'Sandbox no esta vacio')
        record['checkpoints'].append('sandbox temporal creado, sin datos operativos')

        # Proceso 1: API real, escrituras confirmadas y evidencia original.
        print('[I04] Arranque 1: escritura y evidencia inicial...', flush=True)
        active = _start(sandbox, env, 1, run)
        p, h, url = active
        process_ids.append(p.pid)
        with httpx.Client(base_url=url, timeout=8, trust_env=False) as c:
            operator = _login(c, 'ag046_i04_operador', env['AG046_I04_PASSWORD'])
            reviewer = _login(c, 'ag046_i04_revisor', env['AG046_I04_PASSWORD'])
            _assert(_api(c, 'GET', '/api/auth/me', headers=reviewer).json()['roles'] == ['revisor'],
                    'Rol revisor no disponible')
            seed_list = _api(c, 'GET', '/api/evaluations',
                headers=operator, params={'lot': 'AG046-I04-SEED'}).json()
            _assert(len(seed_list) == 1, 'Fixture semilla inesperado')
            seed_id = seed_list[0]['id']
            photos = _api(c, 'GET', f'/api/evaluations/{seed_id}',
                headers=operator).json()['evidence']
            _assert(len(photos) == 2, 'Se requieren dos fotos fuente')
            code = 'AG046-I04-API'
            lot = _api(c, 'POST', '/api/lots', expected=201,
                headers=operator, json={'code': code, 'product': 'tomate',
                                        'responsible': 'Prueba de reinicio I04'}).json()
            ev = _api(c, 'POST', '/api/evaluations', expected=201,
                headers=operator, json={'lotId': code, 'pieceId': 'PIEZA-I04-API'}).json()
            measurement = {'schema_version': 1, 'device_id': 'AG046-I04-SENSOR',
                'boot_id': 'ARRANQUE-I04-01', 'seq': 1, 'weight_g': 180.0,
                'stable': True, 'calibration_version': 'I04-prueba',
                'zero_confirmed': True, 'observed_at': datetime.now(timezone.utc).isoformat()}
            measured = _api(c, 'POST', '/api/iot/measurements', expected=200,
                            json=measurement).json()
            _assert(measured.get('duplicate') is False, 'Medicion no creada')

            # Decisiones reales HTTP sobre fotos sintéticas persistidas.
            decision1 = _api(c, 'POST', f'/api/evaluations/{seed_id}/review-decisions',
                expected=201, headers=reviewer,
                json={'action': 'initial_label', 'imageId': photos[0]['id'],
                      'newValue': 'E1', 'expectedReviewId': None,
                      'reason': 'Revision documentada de fotografia sintetica I04',
                      'requestId': str(uuid4())}).json()
            decision2 = _api(c, 'POST', f'/api/evaluations/{seed_id}/review-decisions',
                expected=201, headers=reviewer,
                json={'action': 'confirm', 'imageId': photos[1]['id'],
                      'newValue': 'E1', 'expectedReviewId': decision1['id'],
                      'reason': 'Confirmacion documentada de segunda vista I04',
                      'requestId': str(uuid4())}).json()
            _assert(decision1['id'] != decision2['id'], 'Decisiones no son independientes')
            baseline_api = _api_snapshot(c, seed_id, code, ev['id'], lot['id'], reviewer)
            baseline_db = _sqlite_snapshot(data / 'agroscan.db', data)
            _assert(len(baseline_db['tables']['review_decision_evidence']) == 2,
                    'No se persistieron las dos decisiones')
            _assert(len(baseline_db['tables']['images']) == 2,
                    'No se persistieron las dos imagenes')
        _stop(p, h, url, env['AG046_I04_NONCE'], abrupt=False)
        active = None
        record['checkpoints'].append('proceso 1 cerrado por solicitud HTTP; API indisponible')

        # Proceso 2: mismo soporte de datos, PID distinto.
        print('[I04] Arranque 2: verificacion tras apagado controlado...', flush=True)
        active = _start(sandbox, env, 2, run)
        p, h, url = active
        process_ids.append(p.pid)
        with httpx.Client(base_url=url, timeout=8, trust_env=False) as c:
            reviewer = _login(c, 'ag046_i04_revisor', env['AG046_I04_PASSWORD'])
            operator = _login(c, 'ag046_i04_operador', env['AG046_I04_PASSWORD'])
            after_api = _api_snapshot(c, seed_id, code, ev['id'], lot['id'], reviewer)
            after_db = _sqlite_snapshot(data / 'agroscan.db', data)
            _assert(after_api == baseline_api, 'Respuesta API cambio tras reinicio controlado')
            _assert(after_db == baseline_db, 'Registros SQLite o fotos cambiaron al reiniciar')
            record['checks']['RST-01']['status'] = 'APROBADO'
            record['checks']['RST-02']['status'] = 'APROBADO'
            record['checks']['RST-03']['status'] = 'APROBADO'
            record['checkpoints'].append('proceso 2: API, SQL, imagenes, hashes y decisiones identicos')
            # Una nueva escritura HTTP confirmada prepara el reinicio abrupto.
            new_ev = _api(c, 'POST', '/api/evaluations', expected=201,
                headers=operator, json={'lotId': code, 'pieceId': 'PIEZA-I04-SEGUNDA'}).json()
            duplicate = _api(c, 'POST', '/api/iot/measurements', expected=200,
                             json=measurement).json()
            _assert(duplicate.get('duplicate') is True, 'Lectura IoT duplicada tras reiniciar')
            abrupt_api = _api_snapshot(c, seed_id, code, ev['id'], lot['id'], reviewer)
            abrupt_db = _sqlite_snapshot(data / 'agroscan.db', data)
            _assert(len(abrupt_db['tables']['measurements']) == 1,
                    'Idempotencia de medicion IoT rota')
        _stop(p, h, url, env['AG046_I04_NONCE'], abrupt=True)
        active = None
        record['checkpoints'].append('proceso 2 terminado abruptamente despues de un HTTP 201 confirmado')

        # Proceso 3: valida la recuperación tras terminación forzada.
        print('[I04] Arranque 3: verificacion tras terminacion forzada...', flush=True)
        active = _start(sandbox, env, 3, run)
        p, h, url = active
        process_ids.append(p.pid)
        with httpx.Client(base_url=url, timeout=8, trust_env=False) as c:
            reviewer = _login(c, 'ag046_i04_revisor', env['AG046_I04_PASSWORD'])
            final_api = _api_snapshot(c, seed_id, code, ev['id'], lot['id'], reviewer)
            final_db = _sqlite_snapshot(data / 'agroscan.db', data)
            _assert(final_api == abrupt_api, 'API cambio tras terminacion abrupta')
            _assert(final_db == abrupt_db, 'Ultima escritura confirmada no sobrevivio a parada abrupta')
            _api(c, 'GET', f'/api/evaluations/{new_ev["id"]}', headers=reviewer)
            _assert(all(item['id'] != new_ev['id'] for item in baseline_api['newEvaluations']),
                    'Nueva evaluacion ya existia en la linea base')
        _stop(p, h, url, env['AG046_I04_NONCE'], abrupt=False)
        active = None
        record['checks']['RST-04']['status'] = 'APROBADO'
        record['checkpoints'].append('proceso 3: persistencia despues de terminacion forzada verificada')
        record['comparison'] = {
            'processPids': process_ids,
            'processLaunches': 3, 'controlledStops': 2, 'forcedStops': 1,
            'lots': len(final_db['tables']['lots']),
            'pieces': len(final_db['tables']['pieces']),
            'evaluations': len(final_db['tables']['evaluations']),
            'images': len(final_db['tables']['images']),
            'humanDecisions': len(final_db['tables']['review_decision_evidence']),
            'measurements': len(final_db['tables']['measurements']),
            'imageSha256': final_db['imageSha256'],
            'reportCsvSha256': baseline_api['pieceReportComparable']['csvSha256'],
            'identicalAfterControlledRestart': True,
            'identicalAfterForcedRestart': True,
        }
    except Exception as exc:
        record['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        if active is not None:
            p, h, url = active
            try:
                if p.poll() is None:
                    p.kill()
                    p.wait(timeout=10)
            finally:
                h.close()
        if tempdir is not None:
            try:
                tempdir.cleanup()
            except OSError as exc:
                record['error'] = (record.get('error', '') + '; ' if record.get('error') else '') + f'Limpieza temporal: {type(exc).__name__}: {exc}'

    success = (not record.get('error') and
               all(item['status'] == 'APROBADO' for item in record['checks'].values()))
    record['overall'] = 'REINICIO_REAL_AISLADO_APROBADO' if success else 'INCOMPLETO_O_FALLIDO'
    record['finishedUtc'] = datetime.now(timezone.utc).isoformat()
    (run / 'AG046_I04_RESULTADOS.json').write_text(json.dumps(record, ensure_ascii=False,
                                   indent=2), encoding='utf-8')
    with (run / 'AG046_I04_MATRIZ_RESULTADOS.csv').open('w', newline='', encoding='utf-8-sig') as fh:
        writer = csv.writer(fh, delimiter=';')
        writer.writerow(['Control', 'Resultado', 'Criterio', 'Evidencia'])
        for key, label in LABELS.items():
            writer.writerow([key, record['checks'][key]['status'], label,
                             'AG046_I04_RESULTADOS.json;uvicorn_proceso_*.log'])
    summary = [
        '# AG-046 — Incremento 04: Pruebas de reinicio', '',
        f'**Fecha UTC:** {record["timestampUtc"]}',
        f'**Git HEAD:** `{record["gitHead"] or "No disponible"}`',
        f'**Estado:** {record["overall"]}',
        '', 'Entorno: tres procesos Uvicorn reales, SQLite temporal y dos PNG sinteticos.',
        '**No** se reinicio ningun servicio productivo ni se uso la base operativa.',
        '', '| Control | Estado | Criterio |', '|---|---|---|',
    ]
    for key, label in LABELS.items():
        summary.append(f'| {key} | {record["checks"][key]["status"]} | {label} |')
    summary += ['', '## Verificaciones registradas']
    summary += [f'- {part}' for part in record['checkpoints']]
    if record.get('error'):
        summary += ['', '## Incidencia', f'- `{record["error"]}`']
    summary += [
        '', '## Limites de la evidencia',
        '- Solo un proceso Uvicorn por arranque y puerto temporal en 127.0.0.1.',
        '- Los datos, imagenes y credenciales de prueba son sinteticos.',
        '- La terminacion forzada ocurre DESPUES de recibir una escritura 2xx;',
        '  no acredita recuperacion ante una interrupcion a mitad de una transaccion.',
        '- No verifica hardware, navegador, multiproceso, Render ni Vercel.',
        '- Los datos temporales se eliminan; la evidencia conservada son logs, resumen, matriz y SHA-256.',
    ]
    (run / 'AG046_I04_RESUMEN.md').write_text('\n'.join(summary) + '\n', encoding='utf-8')
    for key in LABELS:
        print(f'{key}: {record["checks"][key]["status"]}')
    if record.get('error'):
        print('Error:', record['error'])
    print('Estado:', record['overall'])
    print('Evidencias:', run)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
