"""AG-046 I03: ejecutor aislado con trazabilidad de pruebas y brecha BKP-05.

El runner NO hace restore de backend/data/agroscan.db ni usa datos operativos.
NO debe ejecutarse una prueba destructiva manual sobre la base real.
"""
from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
TEST_SECRET = 'AG046-I03-TEST-ONLY-SECRET-NEVER-DEPLOY-2026-48BYTES'

STEPS = [
    ('i03_integridad', 'test_ag046_i03_integrity.py'),
    ('regresion_archivos', 'test_agrop52_image_recovery.py'),
    ('regresion_backup_unitario', 'test_agrop53_backup.py'),
    ('regresion_backup_integracion', 'test_agrop53_backup_integration.py'),
    ('regresion_dos_vistas', 'test_ag056_final_api.py'),
    ('regresion_trazabilidad', 'test_agrop48_piece_history.py'),
    ('bkp05_prueba_estricta', 'test_ag046_i03_bkp05.py'),
]


def git_head() -> str | None:
    try:
        result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
            capture_output=True, text=True, timeout=5, check=False)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def main() -> int:
    timestamp = datetime.now(timezone.utc)
    output = ROOT / 'docs' / 'ag046' / 'runs' / ('AG046_I03_' + timestamp.strftime('%Y%m%dT%H%M%S_%fZ'))
    output.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env['AGROSCAN_JWT_SECRET'] = TEST_SECRET
    env['AGROSCAN_JWT_ALGORITHM'] = 'HS256'
    env['AGROSCAN_ACCESS_TOKEN_MINUTES'] = '30'
    env['PYTHONPATH'] = str(BACKEND)
    env['PYTHONDONTWRITEBYTECODE'] = '1'

    evidence = {
        'activity': 'AG-046 / AGROP-54', 'increment': 'I03',
        'timestampUtc': timestamp.isoformat(), 'gitCommit': git_head(),
        'python': sys.version.split()[0],
        'environment': 'FastAPI TestClient, SQLite temporal, archivos sinteticos',
        'productionDataUsed': False, 'realHardwareUsed': False,
        'realPhotosUsed': False, 'serverRestartVerified': False,
        'stages': [],
    }

    for label, filename in STEPS:
        command = [sys.executable, '-m', 'unittest', 'discover',
            '-s', 'tests', '-p', filename, '-v']
        try:
            process = subprocess.run(command, cwd=BACKEND, env=env,
                capture_output=True, text=True, errors='replace',
                timeout=240, check=False)
            output_text = process.stdout + ('\n' if process.stdout else '') + process.stderr
            exit_code = process.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            output_text, exit_code = f'{type(exc).__name__}: {exc}\n', None

        count_match = re.search(r'Ran (\d+) tests?', output_text)
        count = int(count_match.group(1)) if count_match else None
        if label == 'bkp05_prueba_estricta':
            if (exit_code == 1 and count == 1
                    and re.search(r'AssertionError:\s*\d+\s*!=\s*503', output_text)
                    and re.search(r'FAILED\s*\(failures=\d+\)', output_text)
                    and not re.search(r'errors=\d+', output_text)):
                status = 'BRECHA_BKP05_CONFIRMADA'
            elif exit_code == 0 and count == 1:
                status = 'APROBADO'
            else:
                status = 'FALLIDO_INESPERADO'
        else:
            status = 'APROBADO' if exit_code == 0 and count and count > 0 else 'FALLIDO_O_BLOQUEADO'
        path = output / f'{label}.log'
        path.write_text(output_text, encoding='utf-8')
        evidence['stages'].append({
            'id': label, 'status': status, 'cases': count,
            'exitCode': exit_code, 'log': path.relative_to(ROOT).as_posix(),
        })
        print(f'{label}: {status} | tests={count if count is not None else "N/D"}')

    good = all(item['status'] == 'APROBADO' for item in evidence['stages'][:-1])
    bkp05 = evidence['stages'][-1]['status']
    if good and bkp05 == 'APROBADO':
        overall = 'AUTOMATIZADO_APROBADO_INCLUYE_BKP05'
    elif good and bkp05 == 'BRECHA_BKP05_CONFIRMADA':
        overall = 'PRUEBAS_APROBADAS_CON_BRECHA_BKP05'
    else:
        overall = 'INCOMPLETO_O_FALLIDO'
    evidence['overall'] = overall

    controls = []
    for prefix, limit in (('INT', 10), ('BKP', 5)):
        for idx in range(1, limit + 1):
            ident = f'{prefix}-{idx:02d}'
            if ident == 'BKP-05':
                result = ('CONTROL_APROBADO_AISLADO' if bkp05 == 'APROBADO'
                          else 'BRECHA_CONFIRMADA' if bkp05 == 'BRECHA_BKP05_CONFIRMADA'
                          else 'NO_EVALUABLE')
                note = 'Suspension concurrente verificada en POST /api/lots; otros endpoints y multiproceso no cubiertos.'
            elif good:
                result = 'PRUEBAS_AISLADAS_APROBADAS'
                note = 'Ver logs I03 + regresiones. No equivale a auditoria de datos reales ni reinicio fisico.'
            else:
                result = 'PENDIENTE_CORRECCION_O_REGRESION'
                note = 'Al menos una etapa automatizada fallo o no se ejecuto; examinar logs.'
            controls.append({'ID': ident, 'Resultado_I03': result, 'Observaciones': note})

    with (output / 'AG046_I03_MATRIZ_RESULTADOS.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['ID', 'Resultado_I03', 'Observaciones'], delimiter=';')
        writer.writeheader()
        writer.writerows(controls)

    (output / 'AG046_I03_RESULTADOS.json').write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    report = [
        '# AG-046 — Incremento 03: Resultados de integridad',
        '', f'**Fecha UTC:** {evidence["timestampUtc"]}',
        f'**Git HEAD:** `{evidence["gitCommit"] or "No disponible"}`',
        f'**Estado:** {overall}',
        '', 'Ambiente: SQLite e imagenes sinteticas temporales; base real y hardware no utilizados.',
        '', '| Etapa | Estado | Casos | Evidencia |',
        '|---|---|---:|---|',
    ]
    for item in evidence['stages']:
        report.append(f'| {item["id"]} | {item["status"]} | {item["cases"] if item["cases"] is not None else "N/D"} | `{Path(item["log"]).name}` |')
    report.extend([
        '', '## Interpretacion obligatoria',
        '', '- **BKP-05:** si aparece `BRECHA_BKP05_CONFIRMADA`, una escritura de lote fue admitida durante `suspend_capture()`; esto **NO** aprueba BKP-05 y exige correccion/aceptacion documentada.',
        '- Los controles INT y BKP 01-04 se ensayan en bases y archivos temporales; esto no verifica la calidad de datos operativos.',
        '- INT-08 valida un SHA-256 previamente registrado en snapshot. No todas las imagenes historicas tienen hash de origen acreditado.',
        '- Ninguna etapa equivale a las pruebas de reinicio real I04 ni valida un despliegue multiproceso.',
        '- Se mantiene inalterada la matriz inicial I01; la salida CSV I03 es una matriz de resultados independiente.',
    ])
    (output / 'AG046_I03_RESUMEN.md').write_text('\n'.join(report) + '\n', encoding='utf-8')
    print('Evidencias:', output)
    return 0 if overall == 'AUTOMATIZADO_APROBADO_INCLUYE_BKP05' else 1


if __name__ == '__main__':
    raise SystemExit(main())
