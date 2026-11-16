"""AG-046 I02: ejecución local reproducible sin credenciales reales.

Genera logs + JSON + CSV bajo docs/ag046/runs/ (no escribe en SQLite real).
Ejecutar con el mismo Python de backend/.venv; Node.js para SEC-04.
"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
FRONTEND = ROOT / 'frontend'
# Clave usada solo en subprocesos de test. No se registra en ninguna evidencia.
TEST_SECRET = 'AG046-I02-TEST-ONLY-NOT-FOR-DEPLOYMENT-2026-48bytes'

CASES = [
    ('i02_backend', BACKEND, [sys.executable, '-m', 'unittest', 'discover',
        '-s', 'tests', '-p', 'test_ag046_i02_security.py', '-v']),
    ('regresion_roles', BACKEND, [sys.executable, '-m', 'unittest', 'discover',
        '-s', 'tests', '-p', 'test_agrop47_*.py', '-v']),
    ('regresion_revisiones', BACKEND, [sys.executable, '-m', 'unittest', 'discover',
        '-s', 'tests', '-p', 'test_agrop46_review_decisions.py', '-v']),
    ('regresion_cola', BACKEND, [sys.executable, '-m', 'unittest', 'discover',
        '-s', 'tests', '-p', 'test_ag056_review_queue.py', '-v']),
    ('regresion_backup_permisos', BACKEND, [sys.executable, '-m', 'unittest', 'discover',
        '-s', 'tests', '-p', 'test_agrop53_backup_api.py', '-v']),
    ('i02_frontend_fuente', FRONTEND, ['node', '--test', '--test-reporter=tap', 'tests/ag046-i02-token-security.test.mjs']),
]


def main() -> int:
    run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    output = ROOT / 'docs' / 'ag046' / 'runs' / f'AG046_I02_{run}'
    output.mkdir(parents=True, exist_ok=False)

    env = os.environ.copy()
    # No heredar secretos personales en el proceso de pruebas.
    env['AGROSCAN_JWT_SECRET'] = TEST_SECRET
    env['AGROSCAN_JWT_ALGORITHM'] = 'HS256'
    env['AGROSCAN_ACCESS_TOKEN_MINUTES'] = '30'
    env['PYTHONPATH'] = str(BACKEND)
    evidence = {
        'activity': 'AG-046 / AGROP-54', 'increment': 'I02',
        'timestampUtc': datetime.now(timezone.utc).isoformat(),
        'environment': 'local isolated unittest/TestClient and static frontend checks',
        'productionDataUsed': False, 'realDeviceTested': False,
        'modelAccuracyTested': False, 'steps': [],
    }
    success = True
    for title, cwd, command in CASES:
        logfile = output / f'{title}.log'
        if command[0] == 'node' and shutil.which('node') is None:
            status, code, stdout = 'BLOQUEADO_NODE_NO_DISPONIBLE', None, 'Node.js no disponible.\n'
        else:
            try:
                result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                    text=True, errors='replace', timeout=240, check=False)
                stdout = result.stdout + ('\n' if result.stdout else '') + result.stderr
                code = result.returncode
                status = 'APROBADO' if code == 0 else 'FALLIDO'
            except (OSError, subprocess.TimeoutExpired) as exc:
                status, code, stdout = 'BLOQUEADO', None, f'{type(exc).__name__}: {exc}\n'
        logfile.write_text(stdout, encoding='utf-8')
        python_counts = re.search(r'Ran (\d+) tests?', stdout)
        node_counts = re.search(r'^# tests (\d+)', stdout, flags=re.MULTILINE)
        tests = int((python_counts or node_counts).group(1)) if (python_counts or node_counts) else None
        if status == 'APROBADO' and (tests is None or tests == 0):
            status = 'BLOQUEADO_SIN_CASOS_DETECTADOS'
        evidence['steps'].append({
            'step': title, 'status': status, 'exitCode': code,
            'testCountReported': tests, 'log': logfile.relative_to(ROOT).as_posix(),
        })
        print(f'{title}: {status} | tests={tests if tests is not None else "no determinado"}')
        if status != 'APROBADO':
            success = False

    core = next(s for s in evidence['steps'] if s['step'] == 'i02_backend')['status'] == 'APROBADO'
    frontend = next(s for s in evidence['steps'] if s['step'] == 'i02_frontend_fuente')['status'] == 'APROBADO'
    all_regressions = all(s['status'] == 'APROBADO'
        for s in evidence['steps'] if s['step'].startswith('regresion_'))

    matrix = []
    for number in range(1, 13):
        cid = f'SEC-{number:02d}'
        if number == 11:
            result = 'RIESGO_OBSERVADO_NO_APROBADO' if core else 'PENDIENTE_PRUEBA'
            comment = 'La prueba caracteriza POST IoT sin token como HTTP 200; requiere política de dispositivo y exposición de red.'
        elif number == 12:
            result = 'PENDIENTE_DECISION_FUNCIONAL' if core else 'PENDIENTE_PRUEBA'
            comment = 'Dos rutas humanas tienen privilegios distintos; no se presupone que deban unificarse.'
        elif number == 4:
            result = 'FUENTE_VALIDADA_NO_BROWSER' if frontend else 'PENDIENTE_PRUEBA'
            comment = 'Verificación estructural; prueba de sesión en navegador queda pendiente si se exige.'
        else:
            result = 'PRUEBAS_AUTOMATIZADAS_OK' if core and all_regressions else 'NO_VALIDADO'
            comment = 'Tests I02 y regresiones; ver logs. No equivale a auditoría externa.'
        matrix.append({'ID': cid, 'Resultado_I02': result, 'Comentario': comment})

    with (output / 'AG046_I02_MATRIZ_RESULTADOS.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['ID', 'Resultado_I02', 'Comentario'], delimiter=';')
        writer.writeheader()
        writer.writerows(matrix)

    evidence['overallAutomatedSteps'] = 'APROBADO' if success else 'INCOMPLETO_O_FALLIDO'
    evidence['policyDecisionsStillPending'] = ['SEC-11', 'SEC-12']
    (output / 'AG046_I02_RESULTADOS.json').write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False), encoding='utf-8')

    report = [
        '# AG-046 — Incremento 02 · Resultados de ejecución',
        '', f'**Corte UTC:** {evidence["timestampUtc"]}',
        f'**Estado de pasos automatizados:** {evidence["overallAutomatedSteps"]}',
        '', 'Pruebas con usuarios y SQLite sintéticos. Sin fotos de campo ni hardware.',
        '', '| Etapa | Estado | Casos informados | Log |', '|---|---|---:|---|',
    ]
    for step in evidence['steps']:
        report.append(f'| {step["step"]} | {step["status"]} | {step["testCountReported"] if step["testCountReported"] is not None else "N/D"} | `{Path(step["log"]).name}` |')
    report += [
        '', '## Criterios no cerrados automáticamente',
        '', '- **SEC-11:** aceptación de lecturas IoT sin credencial no demuestra cumplimiento; definir seguridad según despliegue.',
        '- **SEC-12:** la separación operador/revisor requiere decisión del equipo para anotación experimental.',
        '- **SEC-04:** lectura de fuente del frontend; no sustituye prueba real en navegador.',
        '- Un paso fallido o bloqueado no se convierte en APROBADO por la existencia de código.',
        '', 'La matriz I01 permanece intacta; para actualizarla conservar este reporte y referencias al SHA local.',
    ]
    (output / 'AG046_I02_RESUMEN.md').write_text('\n'.join(report) + '\n', encoding='utf-8')
    print('Evidencias:', output)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
