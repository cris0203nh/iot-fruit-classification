"""AG-046/I05: consolidacion local, solo lectura de evidencias I01-I04.

No ejecuta pruebas, migraciones, respaldos ni escribe sobre SQLite operativo.
Valida estados + recuentos + logs + metadatos y genera evidencia con SHA-256.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN_IDS = {
    'I02': 'AG046_I02_20261116T132352_050856Z',
    'I03': 'AG046_I03_20261116T141329_104177Z',
    'I04': 'AG046_I04_20261116T144223_566776Z',
}
EXPECT = {
    'I02': {'i02_backend': 14, 'regresion_roles': 24,
            'regresion_revisiones': 18, 'regresion_cola': 18,
            'regresion_backup_permisos': 9, 'i02_frontend_fuente': 4},
    'I03': {'i03_integridad': 16, 'regresion_archivos': 2,
            'regresion_backup_unitario': 8, 'regresion_backup_integracion': 1,
            'regresion_dos_vistas': 9, 'regresion_trazabilidad': 24,
            'bkp05_prueba_estricta': 1},
    'I04': {f'RST-{k:02d}': 1 for k in range(1, 5)},
}
EXPECTED_STATUS = {
    'I02': 'APROBADO', 'I03': 'AUTOMATIZADO_APROBADO_INCLUYE_BKP05',
    'I04': 'REINICIO_REAL_AISLADO_APROBADO',
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def safe_read_json(path: Path, failures: list[str]):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        failures.append(f'No se pudo leer {path.name}: {type(exc).__name__}')
        return None


def check_log(path: Path, expected: int, is_node: bool, failures: list[str]):
    if not path.is_file():
        failures.append(f'Log no disponible: {path.name}')
        return
    data = path.read_text(encoding='utf-8', errors='replace')
    if is_node:
        match = re.search(r'^# tests\s+(\d+)\s*$', data, flags=re.MULTILINE)
        ok = (re.search(r'^# pass\s+' + str(expected) + r'\s*$', data, flags=re.MULTILINE)
              and re.search(r'^# fail\s+0\s*$', data, flags=re.MULTILINE))
    else:
        match = re.search(r'Ran (\d+) tests?', data)
        ok = bool(re.search(r'(?m)^OK(?:\s|$)', data)) and not bool(re.search(r'(?m)^FAILED', data))
    if not match or int(match.group(1)) != expected or not ok:
        failures.append(f'Log sin resultado verificable ({expected} casos): {path.name}')


def check_suite(tag: str, folder: Path, failures: list[str], observations: list[str]) -> bool:
    beginning = len(failures)
    result_file = folder / f'AG046_{tag}_RESULTADOS.json'
    data = safe_read_json(result_file, failures)
    if not isinstance(data, dict):
        return False
    if tag == 'I02':
        if data.get('overallAutomatedSteps') != 'APROBADO':
            failures.append('I02 no tiene estado global aprobado')
        stages = data.get('steps')
        key, count_key = 'step', 'testCountReported'
    elif tag == 'I03':
        if data.get('overall') != EXPECTED_STATUS[tag]:
            failures.append('I03 no acredita BKP-05 y las regresiones')
        stages = data.get('stages')
        key, count_key = 'id', 'cases'
    else:
        if data.get('overall') != EXPECTED_STATUS[tag] or data.get('error'):
            failures.append('I04 no acredita los reinicios')
        checks = data.get('checks', {})
        if set(checks) != set(EXPECT[tag]):
            failures.append('I04: matriz RST incompleta')
        for cid in EXPECT[tag]:
            if checks.get(cid, {}).get('status') != 'APROBADO':
                failures.append(f'I04: {cid} no aprobado')
        comp = data.get('comparison', {})
        if (comp.get('processLaunches') != 3 or comp.get('controlledStops') != 2
                or comp.get('forcedStops') != 1
                or comp.get('identicalAfterControlledRestart') is not True
                or comp.get('identicalAfterForcedRestart') is not True
                or len(set(comp.get('processPids', []))) != 3
                or not comp.get('imageSha256')):
            failures.append('I04: falta evidencia de procesos y comparación de hashes')
        # El host I04 usa log_level='warning' y access_log=False. En una
        # corrida sin advertencias, Uvicorn no escribe contenido en los tres
        # archivos que crea _start(). Un log vacío no prueba un arranque, pero
        # tampoco invalida los checkpoints y snapshots JSON ya verificados.
        # La ausencia del archivo, en cambio, sigue siendo un bloqueo.
        expected_checkpoints = (
            'sandbox temporal creado, sin datos operativos',
            'proceso 1 cerrado por solicitud HTTP; API indisponible',
            'proceso 2: API, SQL, imagenes, hashes y decisiones identicos',
            'proceso 2 terminado abruptamente despues de un HTTP 201 confirmado',
            'proceso 3: persistencia despues de terminacion forzada verificada',
        )
        recorded = data.get('checkpoints', [])
        if not isinstance(recorded, list) or any(point not in recorded for point in expected_checkpoints):
            failures.append('I04: faltan checkpoints del ciclo completo de reinicio')
        if (data.get('productionDataUsed') is not False
                or data.get('hardwareUsed') is not False
                or data.get('multiWorkerVerified') is not False):
            failures.append('I04: alcance declarado incompatible con prueba aislada')
        if not data.get('finishedUtc'):
            failures.append('I04: no consta finalización de la corrida')
        for n in (1, 2, 3):
            logfile = folder / f'uvicorn_proceso_{n}.log'
            if not logfile.is_file():
                failures.append(f'I04: archivo Uvicorn inexistente para proceso {n}')
            elif logfile.stat().st_size == 0:
                observations.append(
                    f'I04: {logfile.name} está vacío (warning sin access_log); '
                    'no acredita por sí mismo el arranque, usar JSON y matriz RST')
            elif 'Traceback (most recent call last)' in logfile.read_text(encoding='utf-8', errors='replace'):
                failures.append(f'I04: el log de proceso {n} contiene una excepción')
        stages = []
    if tag in ('I02', 'I03'):
        if not isinstance(stages, list):
            failures.append(f'{tag}: etapas faltantes')
            stages = []
        found = {item.get(key): item for item in stages if isinstance(item, dict)}
        if set(found) != set(EXPECT[tag]):
            failures.append(f'{tag}: nombres/cantidad de etapas divergentes')
        for name, expected in EXPECT[tag].items():
            step = found.get(name, {})
            if step.get('status') != 'APROBADO' or step.get(count_key) != expected or step.get('exitCode') != 0:
                failures.append(f'{tag}: {name} no cumple aprobado / casos / salida cero')
            check_log(folder / f'{name}.log', expected,
                      is_node=(tag == 'I02' and name == 'i02_frontend_fuente'), failures=failures)
    summary = folder / f'AG046_{tag}_RESUMEN.md'
    matrix = folder / f'AG046_{tag}_MATRIZ_RESULTADOS.csv'
    for path in (summary, matrix):
        if not path.is_file() or path.stat().st_size < 40:
            failures.append(f'{tag}: falta fuente {path.name}')
    return len(failures) == beginning


def read_matrix(base: Path, failures: list[str]):
    try:
        with base.open('r', encoding='utf-8-sig', newline='') as stream:
            return list(csv.DictReader(stream, delimiter=';'))
    except OSError as exc:
        failures.append(f'Matriz base I01 ilegible: {type(exc).__name__}')
        return []


def source_status(cid: str, ok: dict, docs_ok: bool) -> tuple[str, str]:
    if cid == 'SEC-11':
        return ('RIESGO_ABIERTO', 'Escritura de mediciones IoT sin credencial; evaluar exposición y autenticación de estación')
    if cid == 'SEC-12':
        return ('PENDIENTE_DECISION_FUNCIONAL', 'Aprobar formalmente separación de anotación experimental y revisión auditada')
    if cid == 'SEC-04':
        return (('FUENTE_APROBADA_NAVEGADOR_PENDIENTE' if ok['I02'] else 'NO_VERIFICADO'),
                'Cuatro pruebas de fuente; no sustituye interacción E2E en navegador')
    if cid.startswith('SEC-'):
        return ('APROBADO_AUTOMATIZADO' if ok['I02'] else 'NO_VERIFICADO',
                'I02: JWT, roles y regresiones con usuarios/SQLite de prueba')
    if cid == 'INT-08':
        return (('APROBADO_CON_HASH_HISTORICO_LIMITADO' if ok['I03'] else 'NO_VERIFICADO'),
                'Valida hash previamente registrado; no acredita archivos históricos sin digest')
    if cid.startswith('INT-'):
        return ('APROBADO_AISLADO' if ok['I03'] else 'NO_VERIFICADO',
                'I03: SQLite e imágenes sintéticas, no registros operativos')
    if cid == 'BKP-05':
        return ('APROBADO_UN_PROCESO' if ok['I03'] else 'NO_VERIFICADO',
                'Protección durante suspensión ensayada con un proceso; multiproceso y escrituras externas pendientes')
    if cid.startswith('BKP-'):
        return ('APROBADO_AISLADO' if ok['I03'] else 'NO_VERIFICADO',
                'I03: ZIP, manifiesto, SHA, restore y rollback sintéticos')
    if cid.startswith('RST-'):
        return ('APROBADO_REINICIO_AISLADO' if ok['I04'] else 'NO_VERIFICADO',
                'I04: tres procesos secuenciales con SQLite de prueba; sin entorno remoto')
    if cid == 'MNT-01':
        return ('DOCUMENTACION_CORREGIDA' if docs_ok else 'DOCUMENTACION_PENDIENTE',
                'README corregido y verificado contra secciones implementadas')
    if cid == 'MNT-02':
        return ('MANIFIESTO_CON_SHA256' if all(ok.values()) else 'EVIDENCIAS_PARCIALES',
                'Archivos de ejecuciones locales conciliados sin adjuntar secretos')
    if cid == 'MNT-03':
        return ('REGISTRO_DE_DEFECTOS_ACTUALIZADO', 'Incidencias y riesgos separados por tipo y estado')
    return ('NO_CLASIFICADO', 'Control no reconocido: revisar manualmente')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='Ruta a la raíz del repositorio')
    for tag in RUN_IDS:
        parser.add_argument(f'--{tag.lower()}', default=RUN_IDS[tag],
                            help=f'Carpeta aprobada del incremento {tag}')
    args = parser.parse_args()
    root = args.root.resolve()
    docs = root / 'docs' / 'ag046'
    runs = docs / 'runs'
    failures = []
    observations = []
    resolved = {tag: runs / getattr(args, tag.lower()) for tag in RUN_IDS}
    for tag, path in resolved.items():
        if not path.is_dir() or path.parent.resolve() != runs.resolve():
            failures.append(f'{tag}: carpeta de ejecución no localizada en docs/ag046/runs')
    ok = {}
    for tag, path in resolved.items():
        ok[tag] = check_suite(tag, path, failures, observations) if path.is_dir() else False

    base = docs / 'AG046_I01_MATRIZ_CONTROLES.csv'
    rows = read_matrix(base, failures)
    expected_ids = ({f'SEC-{i:02d}' for i in range(1, 13)}
                    | {f'INT-{i:02d}' for i in range(1, 11)}
                    | {f'BKP-{i:02d}' for i in range(1, 6)}
                    | {f'RST-{i:02d}' for i in range(1, 5)}
                    | {f'MNT-{i:02d}' for i in range(1, 4)})
    if {row.get('ID') for row in rows} != expected_ids or len(rows) != 34:
        failures.append('I01: la matriz base debe contener exactamente 34 controles reconocidos')

    readme = root / 'backend' / 'README.md'
    try:
        readme_text = readme.read_text(encoding='utf-8')
        docs_ok = ('AGROSCAN_JWT_SECRET' in readme_text
                   and 'alembic' in readme_text.lower()
                   and '/api/auth/login' in readme_text
                   and '/api/admin/backups' in readme_text
                   and 'no borrar' in readme_text.lower()
                   and 'Sin inicio de sesión' not in readme_text
                   and 'Sin migraciones' not in readme_text)
    except OSError:
        docs_ok = False
    if not docs_ok:
        failures.append('MNT-01: README del backend sigue desactualizado o es inaccesible')

    def write_csv(path: Path, headers: list[str], values: list[dict]):
        with path.open('w', encoding='utf-8-sig', newline='') as stream:
            w = csv.DictWriter(stream, delimiter=';', fieldnames=headers)
            w.writeheader()
            w.writerows(values)

    docs.mkdir(parents=True, exist_ok=True)
    new_rows = []
    for row in rows:
        cid = row.get('ID', '')
        status, note = source_status(cid, ok, docs_ok)
        tag = ('I02' if cid.startswith('SEC-') else
               'I03' if cid.startswith(('INT-', 'BKP-')) else
               'I04' if cid.startswith('RST-') else 'I05')
        new_rows.append({'ID': cid, 'Categoria': row.get('Categoria', ''),
                         'Control_I01': row.get('Control', ''), 'Estatus_I05': status,
                         'Alcance_o_riesgo': note,
                         'Evidencia': (resolved[tag].relative_to(root).as_posix()
                                      if tag in resolved else 'docs/ag046/AG046_I05_CIERRE_EVIDENCIADO.md')})

    matrix_name = 'AG046_I05_MATRIZ_FINAL.csv'
    write_csv(docs / matrix_name,
              ['ID', 'Categoria', 'Control_I01', 'Estatus_I05', 'Alcance_o_riesgo', 'Evidencia'],
              new_rows)

    # Manifiesto reproducible: no copiar datos reales ni logs posiblemente sensibles.
    manifest_rows = []
    for tag, path in resolved.items():
        if not path.is_dir():
            continue
        for file in sorted(path.iterdir()):
            if file.is_file() and file.suffix.lower() in ('.json', '.csv', '.md', '.log'):
                silent_uvicorn = (tag == 'I04' and file.name.startswith('uvicorn_proceso_')
                                  and file.suffix == '.log' and file.stat().st_size == 0)
                manifest_rows.append({'Incremento': tag, 'Ruta': file.relative_to(root).as_posix(),
                                      'Bytes': file.stat().st_size, 'SHA256': sha(file),
                                      'Revision_antes_de_adjuntar': (
                                          'LOG_VACIO_NO_ACREDITA_ARRANQUE' if silent_uvicorn
                                          else 'REQUERIDA_SIN_SECRETOS')})
    write_csv(docs / 'AG046_I05_MANIFIESTO_SHA256.csv',
              ['Incremento', 'Ruta', 'Bytes', 'SHA256', 'Revision_antes_de_adjuntar'],
              manifest_rows)

    now = datetime.now(timezone.utc).isoformat()
    result = ('CIERRE_TECNICO_AUTOMATIZADO_CON_PENDIENTES'
              if all(ok.values()) and docs_ok and len(rows) == 34 and not failures
              else 'CONSOLIDACION_INCOMPLETA')
    try:
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root,
                                capture_output=True, text=True, timeout=5, check=False).stdout.strip()
        branch = subprocess.run(['git', 'branch', '--show-current'], cwd=root,
                                capture_output=True, text=True, timeout=5, check=False).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        commit, branch = 'NO_VERIFICADO', 'NO_VERIFICADO'

    result_md = [
        '# AG-046 / AGROP-54 — I05: cierre técnico con evidencia conciliada', '',
        f'**Corte UTC:** {now}', f'**Estado:** `{result}`',
        f'**Git HEAD observado al consolidar:** `{commit}` · rama `{branch}`',
        '', '## Evidencia de ejecución', '',
        '| Incremento | Estado conciliado | Casos / controles | Ejecución seleccionada |',
        '|---|---|---:|---|',
        f'| I01 | Checklist estático incorporado | 34 controles definidos | `AG046_I01_MATRIZ_CONTROLES.csv` |',
        f'| I02 | {"VALIDADO" if ok["I02"] else "NO_VERIFICADO"} | 87 pruebas (14+24+18+18+9+4) | `{resolved["I02"].name}` |',
        f'| I03 | {"VALIDADO" if ok["I03"] else "NO_VERIFICADO"} | 61 pruebas (16+2+8+1+9+24+1) | `{resolved["I03"].name}` |',
        f'| I04 | {"VALIDADO" if ok["I04"] else "NO_VERIFICADO"} | 4/4 controles, 3 procesos secuenciales | `{resolved["I04"].name}` |',
        '', '## Correcciones verificadas y alcance', '',
        '- **BKP-05 (I03):** inicialmente se admitió un `POST /api/lots` durante la suspensión (brecha). La corrección con guard HTTP fue reejecutada y verificada mediante la prueba estricta: **un solo proceso FastAPI**. No se acredita exclusión entre workers.',
        '- **I02:** se corrigieron un token de prueba no ASCII, fixtures históricos sin evidencia y el recuento de Node.js. Son ajustes de pruebas/ejecutor, no cambios de autenticación.',
        '- **I03:** se cerraron conexiones SQLite temporales en Windows para evitar `WinError 32` durante la limpieza.',
        '- **I04:** se corrigieron la validación del sandbox y la inyección de `Request` del endpoint temporal de apagado; las pruebas de reinicio posteriores pasaron.',
        f'- **MNT-01:** README actualizado: {"VERIFICADO" if docs_ok else "PENDIENTE"}.',
        '', '## Condiciones de cierre / riesgos conservados', '',
        '1. **SEC-11, riesgo alto condicionado a exposición:** mediciones IoT aceptadas sin credencial. Mantener red aislada / loopback hasta definir autenticación del puente y ensayarla; CORS no protege HTTP directo.',
        '2. **SEC-12, pendiente de negocio:** aprobar distinción entre operador (anotación experimental) y revisor (decisión formal).',
        '3. **SEC-04:** comprobación estructural del JWT en memoria aprobada; prueba funcional en navegador pendiente.',
        '4. **BKP-05:** no ensayado en múltiples workers o instancias, ni frente a escrituras externas y lecturas concurrentes durante restauración.',
        '5. **INT-08:** los SHA-256 existentes validan snapshots concretos, no imágenes antiguas sin hash de captura acreditado.',
        '6. **RST:** tres procesos Uvicorn sucesivos con SQLite temporal y fotografías sintéticas; no equivale a despliegue Render/Vercel ni a falla a mitad de transacción.',
        '', '## Límites y siguiente decisión', '',
        'El estado es **cierre técnico automatizado de alcance acotado**, no certificación de seguridad productiva ni cierre incondicional de AGROP-54. Publicación Git, aprobación del equipo y transición Jira quedan pendientes de acción explícita.',
        'Revisar `AG046_I05_MATRIZ_FINAL.csv`, `AG046_I05_REGISTRO_DEFECTOS.csv` y `AG046_I05_MANIFIESTO_SHA256.csv` antes de adjuntar evidencia.',
    ]
    if observations:
        result_md += ['', '## Observaciones de evidencia (no equivalen a logs de arranque)', '']
        result_md += [f'- {reason}' for reason in observations]
        result_md += [
            '- I04 se sustenta en JSON de resultados, checkpoints, PID únicos, '
            'comparaciones API/SQLite/SHA-256 y matriz de controles RST. '
            'Un archivo Uvicorn de 0 bytes no demuestra actividad del proceso.',
        ]
    if failures:
        result_md += ['', '## Bloqueos detectados', ''] + [f'- {reason}' for reason in failures]
    (docs / 'AG046_I05_CIERRE_EVIDENCIADO.md').write_text('\n'.join(result_md) + '\n', encoding='utf-8')

    defects = [
        ('AG046-H01', 'SEC-11', 'Alta si API expuesta', 'RIESGO_ABIERTO', 'API IoT sin autenticación de dispositivo', 'Definir red/credencial y probar con puente', 'I02'),
        ('AG046-H02', 'BKP-05', 'Crítica condicional', 'CORREGIDO_VERIFICADO_UN_PROCESO' if ok['I03'] else 'PENDIENTE', 'Guarda de escritura para solicitudes API durante backup/restore', 'Evaluar multiproceso, rutas externas y lecturas concurrentes', 'I03'),
        ('AG046-H03', 'SEC-12', 'Media', 'PENDIENTE_APROBACION_FUNCIONAL', 'Roles de anotación experimental y decisión formal diferentes', 'Obtener acuerdo funcional del equipo', 'I02'),
        ('AG046-H04 / BUG-001', 'MNT-01', 'Baja', 'CORREGIDO_DOCUMENTAL' if docs_ok else 'PENDIENTE', 'README describía autenticación, migraciones y backup como inexistentes', 'Validar instrucciones en instalación y aprobar README', 'I05'),
        ('AG046-H05', 'RST-01..04', 'Media', 'CERRADO_SOLO_ENTORNO_AISLADO' if ok['I04'] else 'PENDIENTE', 'Faltaba ensayo real de detener y arrancar FastAPI', 'Prueba de entorno desplegado si es requisito', 'I04'),
        ('AG046-H06', 'INT-08', 'Media', 'LIMITACION_HISTORICA_ABIERTA', 'No todas las imágenes conservan digest de captura universal', 'Definir seguimiento de evidencias históricas', 'I03'),
        ('AG046-OBS-01', 'I02', 'Baja', 'CORREGIDO_PRUEBA' if ok['I02'] else 'PENDIENTE', 'Test de token no ASCII y fixtures históricos', 'Mantener regresiones', 'I02'),
        ('AG046-OBS-02', 'I03', 'Baja', 'CORREGIDO_PRUEBA' if ok['I03'] else 'PENDIENTE', 'Conexiones SQLite temporales retenidas en Windows', 'Mantener closing/cleanup', 'I03'),
        ('AG046-OBS-03', 'I04', 'Baja', 'CORREGIDO_EJECUTOR' if ok['I04'] else 'PENDIENTE', 'Sandbox y endpoint temporal de apagado', 'Mantener regresión de reinicio', 'I04'),
    ]
    write_csv(docs / 'AG046_I05_REGISTRO_DEFECTOS.csv',
              ['ID', 'Control', 'Severidad', 'Estado', 'Descripcion', 'Accion_siguiente', 'Evidencia'],
              [dict(zip(['ID', 'Control', 'Severidad', 'Estado', 'Descripcion', 'Accion_siguiente', 'Evidencia'], row))
               for row in defects])
    jira = [
        'AG-046 / AGROP-54 — Consolidación I01-I05', '',
        f'Estado local de la auditoría: {result}',
        'I01: auditoría estática y checklist de 34 controles.',
        f'I02: 87/87 pruebas, conciliación {"válida" if ok["I02"] else "no validada"}.',
        f'I03: 61/61 pruebas, conciliación {"válida" if ok["I03"] else "no validada"}.',
        f'I04: 4/4 controles de reinicio aislado, conciliación {"válida" if ok["I04"] else "no validada"}.',
        'I04: los archivos Uvicorn pueden estar vacíos por logging en nivel warning sin access_log;',
        'la ejecución se acredita por JSON y comparaciones, no por contenido de logs vacíos.',
        'BKP-05: brecha de escritura durante respaldo corregida y verificada con una instancia FastAPI.',
        'Pendientes: SEC-11 IoT sin credencial; SEC-12 decisión de política; SEC-04 navegador;',
        'BKP-05 multiproceso/escrituras externas, cobertura histórica SHA y despliegue remoto.',
        'Pruebas con SQLite y fotos sintéticas. No se certificó hardware ni servicio productivo.',
        'Evidencias: docs/ag046/AG046_I05_CIERRE_EVIDENCIADO.md;',
        'docs/ag046/AG046_I05_MATRIZ_FINAL.csv;',
        'docs/ag046/AG046_I05_MANIFIESTO_SHA256.csv;',
        'y fuentes locales listadas en el manifiesto.',
        f'HEAD: {commit} · rama: {branch}',
        '', 'No mover a Done sin decisión del equipo sobre criterios pendientes y publicación de cambios.',
    ]
    (docs / 'AG046_I05_TEXTO_JIRA.txt').write_text('\n'.join(jira) + '\n', encoding='utf-8')
    print(f'I02: {"CONCILIADO" if ok["I02"] else "NO_VERIFICADO"} | 87 pruebas esperadas')
    print(f'I03: {"CONCILIADO" if ok["I03"] else "NO_VERIFICADO"} | 61 pruebas esperadas')
    print(f'I04: {"CONCILIADO" if ok["I04"] else "NO_VERIFICADO"} | 4 controles esperados')
    print(f'MNT-01 README: {"VERIFICADO" if docs_ok else "NO_VERIFICADO"}')
    print(f'Controles matriz: {len(rows)}; fuentes con SHA256: {len(manifest_rows)}')
    print('Estado:', result)
    if observations:
        for observation in observations:
            print('OBSERVACION:', observation)
    if failures:
        for failure in failures:
            print('BLOQUEO:', failure)
    print('Informe:', docs / 'AG046_I05_CIERRE_EVIDENCIADO.md')
    return 0 if result == 'CIERRE_TECNICO_AUTOMATIZADO_CON_PENDIENTES' else 2


if __name__ == '__main__':
    raise SystemExit(main())
