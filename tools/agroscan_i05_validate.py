#!/usr/bin/env python3
"""AgroScan I05: auditoría reproducible de software, sin inferencia ni escrituras al backend.

Ejecutar desde la raíz:
  .\\backend\\.venv\\Scripts\\python.exe tools/agroscan_i05_validate.py --preflight
  .\\backend\\.venv\\Scripts\\python.exe tools/agroscan_i05_validate.py --run --evaluation E-000019

Los ensayos son pruebas automatizadas; NO acreditan hardware ni precisión del modelo.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
FRONT = ROOT / 'frontend'
I05_TESTS = [
    'agroscan-product-i01.test.mjs', 'agroscan-product-i02.test.mjs',
    'agroscan-i02-auto.test.mjs', 'agroscan-i03-a4.test.mjs',
    'agroscan-i03-a4-global-fit.test.mjs', 'agroscan-i03-pixel-scale.test.mjs',
    'agroscan-i03-auto.test.mjs', 'agroscan-i04-evidence.test.mjs',
    'agroscan-i05-integral.test.mjs',
]
REQUIRED = [
    'backend/app/main.py', 'frontend/package.json',
    'frontend/src/features/evaluation/evaluationFlow.ts',
    'frontend/src/features/quality/autoV2Preview.ts',
    'frontend/src/features/geometry/autoApproxA4Runner.ts',
    'frontend/src/features/history/evaluationEvidenceSnapshot.ts',
    'frontend/src/features/history/EvaluationEvidenceSnapshot.tsx',
    'frontend/tests/agroscan-i05-integral.test.mjs',
    *['frontend/tests/' + f for f in I05_TESTS],
    'tests/test_agroscan_i03_a4_fit.py',
    'tests/test_agroscan_i03_pixel_scale.py',
    'tests/test_agroscan_i03_auto_nominal.py',
]


def tool_path(name: str) -> str | None:
    return shutil.which(name)


def preflight() -> tuple[list[str], dict]:
    missing = sorted(set(x for x in REQUIRED if not (ROOT / x).is_file()))
    commands = {name: tool_path(name) is not None for name in ('git', 'node', 'npm')}
    supplied = os.environ.get('AGROSCAN_V2_MODELS_PATH')
    base = Path(supplied).expanduser() if supplied else ROOT / 'backend/data/ag055_v2/models'
    installed = {
        name: (base / ('ag055_v2_' + name + '.json')).is_file()
        for name in ('mango', 'tomate')
    }
    details = {
        'required_files': len(set(REQUIRED)),
        'missing_files': missing,
        'executables_available': commands,
        'models_v2_files_present': installed,
        'model_path_source': 'AGROSCAN_V2_MODELS_PATH' if supplied else 'backend/data/ag055_v2/models',
        'sqlite_present': (ROOT / 'backend/data/agroscan.db').is_file(),
    }
    problems = [*['Falta ' + f for f in missing], *[f'No se encontró {k} en PATH' for k, v in commands.items() if not v]]
    return problems, details


def safe_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1048576), b''):
            h.update(part)
    return h.hexdigest()


def readonly_inventory(evaluation_id: str | None) -> dict:
    dbfile = ROOT / 'backend/data/agroscan.db'
    if not dbfile.is_file():
        return {'status': 'not_available', 'note': 'SQLite local no encontrada; no se crean registros.'}
    result = {'status': 'available', 'sha256_before': safe_sha(dbfile), 'evaluation': evaluation_id}
    if evaluation_id is None:
        return result
    numeric_id = int(evaluation_id[2:])
    try:
        uri = dbfile.resolve().as_uri() + '?mode=ro'
        with sqlite3.connect(uri, uri=True, timeout=3) as conn:
            conn.execute('PRAGMA query_only=ON')
            tables = {x[0] for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'evaluations' not in tables:
                return {**result, 'status': 'unavailable_schema'}
            ev = conn.execute('SELECT status, weight_pre_g, weight_post_g FROM evaluations WHERE id=?', (numeric_id,)).fetchone()
            if ev is None:
                result.update(status='evaluation_missing')
                return result
            result['evaluation_status'] = ev[0]
            result['weight_initial_present'] = ev[1] is not None
            result['weight_final_present'] = ev[2] is not None
            if 'images' in tables:
                result['images_persisted'] = conn.execute('SELECT COUNT(*) FROM images WHERE evaluation_id=?',(numeric_id,)).fetchone()[0]
            if 'ag054_board_calibrations' in tables:
                result['dimensional_snapshots'] = [
                    {'rules_version': version, 'status': status, 'count': count}
                    for version, status, count in conn.execute(
                        'SELECT rules_version,status,COUNT(*) FROM ag054_board_calibrations '
                        'WHERE evaluation_id=? GROUP BY rules_version,status ORDER BY rules_version,status', (numeric_id,))
                ]
    except (sqlite3.Error, OSError) as exc:
        result.update(status='sqlite_read_error', note=type(exc).__name__)
    return result


def run_cmd(label: str, argv: list[str], cwd: Path, logs: Path, timeout: int = 180) -> dict:
    log = logs / (label + '.log')
    print(f'  · {label}: ejecutando', flush=True)
    try:
        outcome = subprocess.run(argv, cwd=cwd, text=True, errors='replace', encoding='utf-8',
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 timeout=timeout, check=False)
        output = outcome.stdout or ''
        status = 'passed' if outcome.returncode == 0 else 'failed'
        rc = outcome.returncode
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or b''
        output = raw.decode('utf-8', errors='replace') if isinstance(raw, bytes) else raw
        output += '\nTIMEOUT: ejecución cancelada; comprobar el proceso manualmente.\n'
        status = 'failed'
        rc = 124
    except OSError as exc:
        output = f'No se pudo ejecutar: {type(exc).__name__}: {exc}\n'
        status = 'failed'
        rc = 127
    log.write_text(output, encoding='utf-8')
    print(f'  · {label}: {status.upper()} (exit={rc})', flush=True)
    return {'name': label, 'status': status, 'exit_code': rc, 'log': log.name,
            'output_tail': output[-900:]}


def snapshot_inventory():
    files = [
        'frontend/src/features/evaluation/evaluationFlow.ts',
        'frontend/src/features/quality/autoV2Preview.ts',
        'frontend/src/features/geometry/autoApproxA4Runner.ts',
        'frontend/src/features/history/evaluationEvidenceSnapshot.ts',
        'backend/app/services/board_calibration.py',
        'backend/app/routers/board_calibration.py',
    ]
    return {name: safe_sha(ROOT/name) for name in files if (ROOT/name).is_file()}


def render_report(report: dict) -> str:
    steps = report['steps']
    all_ok = bool(steps) and all(s['status'] == 'passed' for s in steps)
    lines = [
        '# AGROSCAN — I05 · Validación integral y cierre técnico', '',
        f"Fecha de ejecución: {report['executed_at']}",
        f"Revisión de código (HEAD): `{report['git_head']}`", '',
        f"**Resultado de pruebas ejecutadas: {'APROBADAS' if all_ok else 'CON FALLAS'}**.",
        'Este resultado es una validación de software, **no** una certificación de operación física.', '',
        'Archivos de modelos V2 detectados: ' + ', '.join(f'{k}={v}' for k,v in report['preflight']['models_v2_files_present'].items()) + '.',
        'La presencia del archivo no demuestra que FastAPI tenga esa ruta activa.', '',
        '## Ejecuciones automatizadas', '',
        '| Etapa | Estado | Código de salida | Evidencia |', '|---|---|---:|---|',
    ]
    for s in steps:
        lines.append(f"| {s['name']} | {s['status']} | {s['exit_code']} | `{s['log']}` |")
    lines += ['', '## Cobertura verificada por pruebas', '',
              '- I01: precondiciones de adquisición y separación de confirmación de FastAPI.',
              '- I02: V2 experimental, concordancia por vistas, ausencia de modelo y errores.',
              '- I03: cálculo nominal por ArUco A4, rechazo geométrico y separación de proyección 2D.',
              '- I04: lectura histórica, identidad de fotografías, sin promediar ni confundir modelos.',
              '- I05: pruebas transversales con datos sintéticos y regresión de componentes.',
              '', '## Inventario local (lectura de SQLite)', '',
              '```json', json.dumps(report['sqlite_inventory'], indent=2, ensure_ascii=False), '```', '',
              '## Puertas de aceptación no acreditadas por esta ejecución', '',
              '- [ ] **Prueba física integrada:** ESP32/HX711 → puente serie/HTTP → FastAPI → ambos pesos y confirmación de adquisición.',
              '- [ ] **Precisión externa E0/E1/E2:** conjunto independiente, etiquetado con rúbrica y métricas por clase.',
              '- [ ] **Exactitud dimensional:** comparación contra instrumento real, repeticiones, múltiples frutas y perspectivas.',
              '- [ ] **Prueba operativa en navegador:** recorrido completo con usuario operador y revisor, capturas y evidencias fechadas.',
              '', '## Criterio de cierre', '',
              ('**Cierre técnico de software aprobado condicionalmente**: las etapas automatizadas reportadas pasaron.'
               if all_ok else '**Cierre técnico de software bloqueado**: revisar los logs con fallas.'),
              'No afirmar validación física ni uso productivo del modelo. La ausencia de peso real mantiene la evaluación parcial.',
              'Si el SHA-256 de SQLite cambió, investigar también escrituras concurrentes de FastAPI antes de atribuirlas a pruebas.',
              'No atribuir a las puntuaciones V2 una confianza calibrada; los centímetros son estimaciones nominales no metrológicas.',
              '', '## Integridad', '',
              'Hashes SHA-256 del código de la ejecución (no incluyen archivos de usuario):', '',
              '```json', json.dumps(report['code_sha256'], indent=2, ensure_ascii=False), '```', '',
              'Los logs y JSON son evidencias de la ejecución local; las pruebas sintéticas no sustituyen un piloto físico.',
              ]
    return '\n'.join(lines) + '\n'


def run(evaluation_id: str | None, output_dir: str | None):
    if output_dir:
        target = Path(output_dir).expanduser().resolve()
        if target == ROOT or target == FRONT:
            raise ValueError('El directorio de salida debe ser una carpeta exclusiva de evidencias.')
    else:
        target = ROOT / 'docs/agroscan-i05/runs' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    problems, pre = preflight()
    if problems:
        print('PREVALIDACIÓN FALLIDA:')
        for p in problems: print('  ·', p)
        return 1
    target.mkdir(parents=True, exist_ok=False)
    node = tool_path('node')
    npm = tool_path('npm')
    git = tool_path('git')
    assert node and npm and git
    venv_python = sys.executable
    def git_output(args):
        result = subprocess.run([git,*args],cwd=ROOT,capture_output=True,text=True,check=False)
        return result.stdout.strip() if result.returncode == 0 else 'no_disponible'
    baseline = readonly_inventory(evaluation_id)
    report = {
        'increment': 'I05', 'executed_at': datetime.now(timezone.utc).isoformat(),
        'git_head': git_output(['rev-parse','--short','HEAD']),
        'preflight': pre, 'evaluation_requested': evaluation_id,
        'sqlite_inventory': baseline, 'code_sha256': snapshot_inventory(), 'steps': [],
    }
    stages = [
        ('frontend-eslint', [npm, 'run', 'lint'], FRONT, 180),
        ('frontend-build', [npm, 'run', 'build'], FRONT, 180),
        ('frontend-general', [npm, 'test'], FRONT, 180),
        ('frontend-integrated-i01-i05', [node, '--experimental-strip-types', '--test', *['tests/'+x for x in I05_TESTS]], FRONT, 180),
        ('backend-i03-regression', [venv_python,'-m','unittest','discover','-s','tests','-p','test_agroscan_i03_*.py','-q'], ROOT, 180),
        ('git-diff-check', [git,'-c','core.whitespace=cr-at-eol','diff','--check'], ROOT, 45),
    ]
    for name, args, cwd, timeout in stages:
        report['steps'].append(run_cmd(name, args, cwd, target, timeout))
    current = readonly_inventory(evaluation_id)
    if baseline.get('sha256_before') and current.get('sha256_before'):
        report['sqlite_file_unchanged'] = baseline['sha256_before'] == current['sha256_before']
        if not report['sqlite_file_unchanged']:
            report['steps'].append({'name':'sqlite-integrity','status':'failed','exit_code':1,
                                    'log':'no-log','output_tail':'Hash SQLite cambió durante la ejecución.'})
    else:
        report['sqlite_file_unchanged'] = None
    (target/'AGROSCAN_I05_RESULTADOS.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (target/'AGROSCAN_I05_CIERRE_TECNICO.md').write_text(render_report(report),encoding='utf-8')
    passed = sum(s['status']=='passed' for s in report['steps'])
    total = len(report['steps'])
    print(f'REPORTE: {target / "AGROSCAN_I05_CIERRE_TECNICO.md"}',flush=True)
    print(f'ETAPAS: {passed}/{total} aprobadas',flush=True)
    return 0 if passed == total else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--preflight',action='store_true')
    group.add_argument('--run',action='store_true')
    parser.add_argument('--evaluation',help='Evaluación opcional solo para inventario SQLite, ej. E-000019')
    parser.add_argument('--output-dir',help='Directorio NUEVO de reportes; si se omite, docs/agroscan-i05/runs/<fecha>')
    args = parser.parse_args()
    if args.evaluation and not re.fullmatch(r'E-\d{6,9}',args.evaluation):
        parser.error('--evaluation debe ser E- seguido de 6 a 9 dígitos')
    if args.preflight:
        errors, details = preflight()
        print(json.dumps(details,ensure_ascii=False,indent=2))
        if errors:
            for err in errors:print('FALTA:',err,file=sys.stderr)
        else:
            print('PREVALIDACIÓN I05 APROBADA. No se ejecutaron pruebas ni se modificó SQLite.')
        return int(bool(errors))
    return run(args.evaluation,args.output_dir)

if __name__ == '__main__':
    try:sys.exit(main())
    except (OSError, ValueError) as exc:
        print(f'I05 DETENIDO: {exc}',file=sys.stderr)
        sys.exit(1)
