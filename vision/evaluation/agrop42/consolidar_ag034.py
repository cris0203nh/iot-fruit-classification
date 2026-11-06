"""AG-034 / Incremento 11: consolidación trazable de evidencias técnicas.

No entrena ni atribuye anotaciones humanas; las fuentes originales no se alteran.
Entrada: resultados 08, revisión visual IA y benchmark 09, perfil 10, ZIP externo.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

VERSION = 'ag034-consolidacion-evidencias-v1'
SOURCES = {
    'incremento08/resultados_por_vista.csv': 'rgb_csv',
    'incremento08/informe_tecnico.json': 'rgb_informe',
    'incremento09/AG034_revision_visual_90_vistas_IA.csv': 'revision_ia',
    'incremento09/AG034_benchmark_auxiliar.json': 'benchmark',
    'incremento10/AG034_perfil_recursos.json': 'perfil',
}
PRODUCTS = {'mangos': 'mango', 'tomates': 'tomate'}
MAX_FILE = 16 * 1024 * 1024
MAX_ZIP_FILES = 1000
MAX_ZIP_UNCOMPRESSED = 500 * 1024 * 1024
SHA = re.compile(r'[0-9a-f]{64}\Z')
REVIEW_STATES = {'compatible_visual_provisional', 'mascara_parcial', 'sin_mascara', 'mascara_no_utilizable'}


class EvidenceError(ValueError):
    """Un conjunto de evidencias no supera controles de trazabilidad."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_bytes(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise EvidenceError('Falta archivo o es un enlace simbólico: ' + path.name)
    if path.stat().st_size > MAX_FILE:
        raise EvidenceError('Archivo de evidencia demasiado grande: ' + path.name)
    return path.read_bytes()


def _load_json(blob: bytes, name: str) -> dict:
    try:
        result = json.loads(blob.decode('utf-8-sig'))
    except (UnicodeError, json.JSONDecodeError) as e:
        raise EvidenceError('JSON inválido: ' + name) from e
    if not isinstance(result, dict):
        raise EvidenceError('Se esperaba objeto JSON: ' + name)
    return result


def _load_csv(blob: bytes, name: str) -> list[dict]:
    try:
        reader = csv.DictReader(io.StringIO(blob.decode('utf-8-sig')))
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise EvidenceError('Encabezados CSV incompletos o repetidos: ' + name)
        records = list(reader)
    except (UnicodeError, csv.Error) as e:
        raise EvidenceError('CSV inválido: ' + name) from e
    if not records or any(None in r for r in records):
        raise EvidenceError('CSV vacío o fila malformada: ' + name)
    return records


def _need(row: dict, fields: tuple[str, ...], name: str) -> None:
    if not set(fields).issubset(row):
        raise EvidenceError('Campos faltantes en ' + name + ': ' + ','.join(sorted(set(fields) - set(row))))


def _key(row: dict) -> tuple[str, str, int, str]:
    _need(row, ('producto', 'id_ejemplar_fuente', 'vista', 'sha256'), 'vista')
    product = row['producto'].strip().lower()
    piece = row['id_ejemplar_fuente'].strip()
    sha = row['sha256'].strip().lower()
    try:
        view = int(row['vista'])
    except (ValueError, TypeError) as e:
        raise EvidenceError('Vista no numérica') from e
    if (product not in {'mango', 'tomate'} or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', piece)
            or not 1 <= view <= 20 or not SHA.fullmatch(sha)):
        raise EvidenceError('Identificador o SHA de fotografía inválido')
    return product, piece, view, sha


def _unique(rows: list[dict], name: str) -> dict[tuple[str, str, int], dict]:
    result = {}
    hashes = set()
    for row in rows:
        product, piece, view, sha = _key(row)
        k = product, piece, view
        if k in result or sha in hashes:
            raise EvidenceError('Vista o SHA duplicado en ' + name)
        result[k] = row
        hashes.add(sha)
    return result


def _zip_index(dataset: Path) -> tuple[str, dict]:
    if not dataset.is_file() or dataset.is_symlink():
        raise EvidenceError('No existe ZIP del dataset')
    if dataset.stat().st_size > MAX_ZIP_UNCOMPRESSED:
        raise EvidenceError('ZIP demasiado grande')
    raw_hash = hashlib.sha256()
    with dataset.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            raw_hash.update(chunk)
    try:
        with ZipFile(dataset) as z:
            entries = z.infolist()
            if len(entries) > MAX_ZIP_FILES or sum(i.file_size for i in entries) > MAX_ZIP_UNCOMPRESSED:
                raise EvidenceError('ZIP supera el límite de entradas o tamaño')
            names = [i.filename for i in entries]
            if len(set(names)) != len(names) or 'trazabilidad.csv' not in names:
                raise EvidenceError('Inventario ZIP ausente o nombres duplicados')
            info = {i.filename: i for i in entries}
            rows = _load_csv(z.read('trazabilidad.csv'), 'trazabilidad.csv')
            result, shas = {}, set()
            for row in rows:
                _need(row, ('archivo', 'id_ejemplar', 'vista', 'sha256'), 'trazabilidad.csv')
                path = row['archivo'].strip()
                p = PurePosixPath(path)
                if (p.is_absolute() or '\\' in path or ':' in path or len(p.parts) != 3
                        or any(part in ('.', '..') for part in p.parts)
                        or p.parts[0] not in PRODUCTS or p.suffix.lower() not in ('.jpg', '.jpeg', '.png')
                        or path not in info or info[path].is_dir() or info[path].file_size > MAX_FILE
                        or p.parts[1] != row['id_ejemplar'].strip()):
                    raise EvidenceError('Ruta insegura o pieza no coherente en ZIP: ' + path)
                sha = row['sha256'].strip().lower()
                if not SHA.fullmatch(sha) or _sha(z.read(path)) != sha or sha in shas:
                    raise EvidenceError('SHA inválido, alterado o duplicado en ZIP: ' + path)
                shas.add(sha)
                k = _key({'producto': PRODUCTS[p.parts[0]], 'id_ejemplar_fuente': row['id_ejemplar'],
                          'vista': row['vista'], 'sha256': sha})[:3]
                if k in result:
                    raise EvidenceError('Vista duplicada en ZIP')
                result[k] = {'archivo': path, 'sha256': sha}
            extra = [n for n in names if n.lower().endswith(('.jpg', '.jpeg', '.png')) and n not in {r['archivo'] for r in result.values()}]
            if extra:
                raise EvidenceError('ZIP contiene fotografías sin inventariar')
    except (BadZipFile, UnicodeError, KeyError, OSError) as e:
        raise EvidenceError('No se pudo verificar el ZIP') from e
    return raw_hash.hexdigest(), result


def _metric(profile: dict, method: str, section: str, field: str) -> float:
    try:
        n = profile['enfoques'][method][section][field]
        if type(n) not in (int, float) or not math.isfinite(n) or n < 0:
            raise ValueError('Número fuera de rango')
        return float(n)
    except (KeyError, TypeError, ValueError) as e:
        raise EvidenceError('Métrica de recursos incompleta: ' + method + '/' + section + '/' + field) from e


def _metrics_confusion(m: dict, n: int, name: str) -> None:
    try:
        conf = m['matriz_confusion_fuente']
        counts = [conf[a][b] for a in ('mango', 'tomate') for b in ('mango', 'tomate')]
        acc = m['accuracy_vistas']
        if (any(type(x) is not int or x < 0 for x in counts)
                or sum(counts) != n or m['n_vistas'] != n
                or type(acc) not in (float, int) or not math.isfinite(acc)
                or not math.isclose(acc, (conf['mango']['mango'] + conf['tomate']['tomate']) / n, abs_tol=1e-12)):
            raise EvidenceError('Inconsistencia de matriz o exactitud: ' + name)
    except (KeyError, TypeError, ZeroDivisionError) as e:
        raise EvidenceError('Matriz incompleta: ' + name) from e


def validar(evidencias: Path, dataset: Path) -> tuple[dict, dict]:
    """Verifica cadena fuente->RGB->revisión IA->benchmark->perfil; no acredita humano."""
    blobs = {rel: _read_bytes(evidencias / rel) for rel in SOURCES}
    rgb = _load_csv(blobs['incremento08/resultados_por_vista.csv'], 'RGB08')
    rgb_report = _load_json(blobs['incremento08/informe_tecnico.json'], 'RGB08 informe')
    rev = _load_csv(blobs['incremento09/AG034_revision_visual_90_vistas_IA.csv'], 'revisión IA09')
    bm = _load_json(blobs['incremento09/AG034_benchmark_auxiliar.json'], 'benchmark09')
    perfil = _load_json(blobs['incremento10/AG034_perfil_recursos.json'], 'perfil10')
    index_rgb = _unique(rgb, 'RGB08')
    index_rev = _unique(rev, 'revisión IA09')
    zip_hash, index_zip = _zip_index(dataset)
    if set(index_rgb) != set(index_rev) or set(index_rgb) != set(index_zip):
        raise EvidenceError('Fotografías no coinciden entre RGB, revisión y ZIP')
    counts = Counter()
    groups = defaultdict(int)
    reviews = Counter()
    masks = Counter()
    for key, r in index_rgb.items():
        v = index_rev[key]
        sha = r['sha256'].strip().lower()
        if sha != v['sha256'].strip().lower() or sha != index_zip[key]['sha256']:
            raise EvidenceError('SHA no coincide entre evidencias: ' + str(key))
        if v.get('archivo_origen') != index_zip[key]['archivo']:
            raise EvidenceError('Ruta de origen no coincide con ZIP: ' + str(key))
        if (r.get('etiqueta_e0_e1_e2', '').strip() or r.get('operador_confirmo_region') != 'no'
                or v.get('etiqueta_E0_E1_E2_acreditada', '').strip()
                or v.get('aprobacion_operador_o_experto') != 'pendiente'
                or v.get('identidad_fisica_verificada') != 'no'
                or v.get('sesion_captura_AgroScan_verificada') != 'no'
                or v.get('utilizable_para_entrenamiento_comercial') != 'no'):
            raise EvidenceError('Datos pretenden acreditación humana no soportada: ' + str(key))
        state = v.get('revision_visual_mascara_IA', '')
        if state not in REVIEW_STATES:
            raise EvidenceError('Estado de revisión IA desconocido: ' + state)
        if r.get('mascara_estado') == 'unavailable' and state in ('compatible_visual_provisional', 'mascara_parcial'):
            raise EvidenceError('Revisión informa máscara cuando no existe: ' + str(key))
        counts[key[0]] += 1
        groups[key[0], key[1]] += 1
        reviews[key[0], state] += 1
        if r.get('mascara_estado') not in ('pending_operator_selection', 'unavailable'):
            raise EvidenceError('Estado de máscara inesperado')
        masks[key[0], r['mascara_estado']] += 1
    if any(n != 3 for n in groups.values()):
        raise EvidenceError('Las tres vistas declaradas de un ID no están completas')
    if rgb_report.get('fotografias_procesadas') != len(index_rgb) or rgb_report.get('identificadores_de_fuente') != len(groups):
        raise EvidenceError('Informe 08 no coincide con inventario')
    if (rgb_report.get('entrenamiento_autorizado') is not False
            or rgb_report.get('etiquetas_e0_e1_e2_verificadas') != 0
            or rgb_report.get('regiones_confirmadas_por_operador') != 0
            or rgb_report.get('modelo_entrenado') is not False):
        raise EvidenceError('Informe 08 tiene acreditación distinta al dataset')
    for product in ('mango', 'tomate'):
        reported = rgb_report.get('conteo_por_producto', {}).get(product, {})
        if (reported.get('fotografias') != counts[product]
                or reported.get('ejemplares_declarados_por_fuente') != sum(p == product for p, _ in groups)
                or reported.get('fotos_con_mascara_candidata') != masks[product, 'pending_operator_selection']):
            raise EvidenceError('Conteos de RGB08 incongruentes para ' + product)
    if (bm.get('AG034_cierre_total_acreditado') is not False
            or perfil.get('decision', {}).get('cierre_total_AG034_acreditado') is not False
            or perfil.get('decision', {}).get('hardware_objetivo_validado') is not False
            or perfil.get('decision', {}).get('clasificacion_e0_e1_e2_evaluada') is not False
            or perfil.get('decision', {}).get('despliegue_autorizado') is not False
            or perfil.get('dataset', {}).get('independencia_fisica_de_piezas_acreditada') is not False
            or perfil.get('zip_sha256') != zip_hash):
        raise EvidenceError('Perfil o benchmark pretenden acreditación no sustentada / ZIP diferente')
    total = bm.get('totales', {})
    part = perfil.get('dataset', {}).get('particion_vistas', {})
    if (total.get('vistas') != len(index_rgb) or total.get('grupos_fuente') != len(groups)
            or total.get('vistas_train') != part.get('entrenamiento')
            or total.get('vistas_val') != part.get('validacion')
            or total.get('vistas_test') != part.get('prueba')
            or perfil.get('dataset', {}).get('vistas') != len(index_rgb)
            or perfil.get('dataset', {}).get('grupos_fuente_declarados') != len(groups)):
        raise EvidenceError('Particiones o conteos 09/10 incongruentes')
    preds = bm.get('predicciones_test')
    if not isinstance(preds, list) or len(preds) != total['vistas_test']:
        raise EvidenceError('Predicciones de prueba incompletas')
    seen, group_test = set(), defaultdict(int)
    for pred in preds:
        try:
            path = pred['archivo']
            product = pred['producto_fuente']
            piece = pred['id_ejemplar']
            if (path in seen or product not in ('mango', 'tomate')
                    or pred['reglas'] not in ('mango', 'tomate')
                    or pred['modelo_ligero'] not in ('mango', 'tomate')):
                raise EvidenceError('Predicción de prueba inválida o repetida')
            seen.add(path)
            found = [key for key, item in index_zip.items() if item['archivo'] == path]
            if len(found) != 1 or found[0][:2] != (product, piece):
                raise EvidenceError('Predicción ajena al dataset o ID no coincidente')
            group_test[(product, piece)] += 1
        except (KeyError, TypeError) as e:
            raise EvidenceError('Predicción de prueba malformada') from e
    if any(group_test[key] != groups[key] for key in group_test):
        raise EvidenceError('Predicciones separan vistas de un mismo identificador')
    for method in ('reglas', 'modelo_ligero'):
        _metrics_confusion(bm['evaluacion_prueba_comun'][method], len(preds), 'benchmark09 ' + method)
        _metrics_confusion(perfil['enfoques'][method]['metricas_test'], len(preds), 'perfil10 ' + method)
        if (bm['evaluacion_prueba_comun'][method]['matriz_confusion_fuente']
                != perfil['enfoques'][method]['metricas_test']['matriz_confusion_fuente']):
            raise EvidenceError('Las matrices 09/10 difieren: ' + method)
        conf_pred = {'mango': {'mango': 0, 'tomate': 0}, 'tomate': {'mango': 0, 'tomate': 0}}
        for pred in preds:
            conf_pred[pred['producto_fuente']][pred[method]] += 1
        if conf_pred != bm['evaluacion_prueba_comun'][method]['matriz_confusion_fuente']:
            raise EvidenceError('Predicciones no reproducen la matriz 09: ' + method)
    timings = {method: {
        'accuracy_producto': perfil['enfoques'][method]['metricas_test']['accuracy_vistas'],
        'inferencia_mediana_ms': _metric(perfil, method, 'inferencia_sin_extraccion', 'mediana_ms'),
        'pipeline_mediana_ms': _metric(perfil, method, 'pipeline_completo_en_equipo_local', 'mediana_ms'),
        'p95_pipeline_ms': _metric(perfil, method, 'pipeline_completo_en_equipo_local', 'p95_ms'),
        'modelo_json_bytes': perfil['enfoques'][method]['modelo_json_bytes'],
        'tracemalloc_pico_mib': perfil['enfoques'][method]['tracemalloc_pico_mib_en_test'],
    } for method in ('reglas', 'modelo_ligero')}
    result = {
        'version': VERSION,
        'actividad': 'AG-034 / AGROP-42',
        'alcance': 'comparacion_auxiliar_mango_vs_tomate_no_defectos',
        'dataset': {
            'zip_sha256': zip_hash,
            'fotografias': len(index_zip),
            'identificadores_fuente_declarados': len(groups),
            'fotografias_por_producto': dict(sorted(counts.items())),
            'tres_vistas_por_id': True,
            'identidad_fisica_acreditada': False,
            'sesiones_agroscan_acreditadas': False,
            'origen': 'fuentes_externas',
            'mango_kent_acreditado': False,
        },
        'segmentacion': {'mascaras_candidatas': sum(v for (p, state), v in masks.items() if state == 'pending_operator_selection'),
                         'sin_mascara': sum(v for (p, state), v in masks.items() if state == 'unavailable'),
                         'por_producto': {p: dict(sorted((s, n) for (k, s), n in masks.items() if k == p)) for p in ('mango', 'tomate')},
                         'mascaras_patron_humano': 0},
        'revision_visual_ia': {'estados': dict(sorted((p + ':' + state, n) for (p, state), n in reviews.items())),
                               'etiquetas_comerciales_acreditadas': 0,
                               'aprobacion_operador': False},
        'benchmark': {'particion_vistas': dict(part), 'test_mismo_conjunto': True,
                      'test_grupos_fuente': len(group_test),
                      'metodos': {p: bm['evaluacion_prueba_comun'][p] for p in ('reglas', 'modelo_ligero')}},
        'rendimiento': {'entorno': perfil.get('entorno', {}), 'metodos': timings,
                        'limitacion_memoria': 'tracemalloc no mide RSS ni memoria nativa'},
        'decision': {'alternativa_provisional': 'reglas',
                     'razon': 'misma exactitud auxiliar; inferencia y serializacion menores; no necesariamente pipeline completo mas rapido',
                     'modelo_ligero_descartado_definitivamente': False,
                     'hardware_objetivo_validado': False,
                     'despliegue_autorizado': False},
        'cierre': {'estado': 'cierre_parcial_documentado', 'AG034_cierre_total_acreditado': False,
                   'pendientes': ['etiquetas_E0_E1_E2_independientemente_validadas',
                                  'comparacion_defectos_con_mismas_particiones',
                                  'medicion_hardware_objetivo_y_limites',
                                  'aceptacion_formal_alcance_por_responsable']},
        'sha256_fuentes': {rel: _sha(data) for rel, data in sorted(blobs.items())},
    }
    return result, blobs


def _csv_evidence(result: dict) -> str:
    out = io.StringIO(newline='')
    w = csv.writer(out, lineterminator='\n')
    w.writerow(('evidencia', 'archivo', 'sha256', 'alcance', 'acreditacion'))
    details = {
        'incremento08/resultados_por_vista.csv': ('descriptores RGB y máscaras candidatas', 'tecnica_sin_referencia_humana'),
        'incremento08/informe_tecnico.json': ('estadisticas del procesamiento', 'tecnica_sin_referencia_humana'),
        'incremento09/AG034_revision_visual_90_vistas_IA.csv': ('observaciones visuales de IA', 'solo_revision_IA'),
        'incremento09/AG034_benchmark_auxiliar.json': ('identificacion mango/tomate', 'auxiliar_no_defectos'),
        'incremento10/AG034_perfil_recursos.json': ('latencia y memoria medidas', 'entorno_local_no_hardware_final'),
    }
    for path, (scope, accredited) in details.items():
        w.writerow((path.split('/')[0], path, result['sha256_fuentes'][path], scope, accredited))
    w.writerow(('dataset', 'ZIP externo (no se copia)', result['dataset']['zip_sha256'],
                '90 vistas / 30 identificadores de fuente', 'no_captura_propia'))
    return out.getvalue()


def _report_md(result: dict) -> str:
    d, seg, bench, perf = (result[x] for x in ('dataset', 'segmentacion', 'benchmark', 'rendimiento'))
    r, m = perf['metodos']['reglas'], perf['metodos']['modelo_ligero']
    rows = [
        '# AG-034 — Consolidación de evidencias y decisión técnica (Incremento 11)',
        '',
        '> **Estado: cierre parcial documentado.** No está acreditado el cierre total ni el despliegue del clasificador de defectos.',
        '',
        '## Alcance y trazabilidad',
        '',
        f'- Dataset: **{d["fotografias"]} vistas**, **{d["identificadores_fuente_declarados"]} identificadores de fuente**, tres vistas declaradas por ID. Fuente externa.',
        f'- SHA-256 del ZIP: `{d["zip_sha256"]}`.',
        '- Verificación de integridad: referencias SHA-256 y claves (producto, identificador, vista) coinciden entre ZIP, RGB08 y revisión IA09.',
        '- Identidad física de los frutos, sesión AgroScan y variedad Kent: **no acreditadas**. El mango se declara Ataulfo según procedencia.',
        '- Etiquetas comerciales E0/E1/E2 y máscaras de referencia humana: **0**.',
        '',
        '## Segmentación y revisión visual',
        '',
        f'- Máscaras cromáticas candidatas: **{seg["mascaras_candidatas"]}** de {d["fotografias"]} vistas. Sin máscara: **{seg["sin_mascara"]}**.',
    ]
    for p in ('mango', 'tomate'):
        n = {k.split(':', 1)[1]: v for k, v in result['revision_visual_ia']['estados'].items() if k.startswith(p + ':')}
        rows.append(f'- {p.capitalize()}: observación IA {json.dumps(n, ensure_ascii=False, sort_keys=True)}.')
    rows += [
        '- La revisión asistida por IA no es *ground truth*; no se puede calcular IoU/Dice validado ni tasa de defectos a partir de estas máscaras.',
        '',
        '## Comparación auxiliar con la misma partición',
        '',
        f'- Entrenamiento: **{bench["particion_vistas"]["entrenamiento"]}** vistas; validación: **{bench["particion_vistas"]["validacion"]}**; prueba: **{bench["particion_vistas"]["prueba"]}**.',
        f'- Prueba: **{bench["test_grupos_fuente"]}** identificadores declarados, sin repartir sus vistas entre subconjuntos.',
        '',
        '| Indicador | Reglas clásicas | Regresión logística ligera |',
        '|---|---:|---:|',
        f'| Exactitud identificación mango/tomate | {r["accuracy_producto"] * 100:.1f} % | {m["accuracy_producto"] * 100:.1f} % |',
        f'| Inferencia mediana (ms, sin extracción) | {r["inferencia_mediana_ms"]:.6f} | {m["inferencia_mediana_ms"]:.6f} |',
        f'| Pipeline mediana (ms, equipo local) | {r["pipeline_mediana_ms"]:.4f} | {m["pipeline_mediana_ms"]:.4f} |',
        f'| Pipeline p95 (ms, equipo local) | {r["p95_pipeline_ms"]:.4f} | {m["p95_pipeline_ms"]:.4f} |',
        f'| Modelo serializado (bytes) | {r["modelo_json_bytes"]} | {m["modelo_json_bytes"]} |',
        f'| Pico tracemalloc (MiB) | {r["tracemalloc_pico_mib"]} | {m["tracemalloc_pico_mib"]} |',
        '',
        f'Entorno de las mediciones: **{perf["entorno"].get("sistema", "no_declarado")}**, Python {perf["entorno"].get("python", "no_declarado")}.',
        'Los tiempos no son pruebas del dispositivo de despliegue. `tracemalloc` no representa memoria total RSS ni consumo del ESP32.',
        'La exactitud obtenida solo diferencia mango de tomate. Fuentes fotográficas diferentes pueden introducir sesgos.',
        '',
        '## Decisión técnica condicionada',
        '',
        'Se mantienen **reglas clásicas** como referencia auxiliar provisional por su inferencia y serialización menores a igualdad de exactitud de identificación. **No** se afirma superioridad absoluta del pipeline completo ni se descarta el modelo ligero para datos futuros.',
        '',
        '## Criterios AG-034 y estado',
        '',
        '- [x] Implementación y comparación auxiliar de métodos con misma prueba: **acreditada en el alcance mango/tomate**.',
        '- [x] Medición de recursos en equipo de ejecución: **acreditada localmente**.',
        '- [x] Decisión provisional con fundamentos: **documentada**.',
        '- [ ] Comparación de clasificación de defectos E0/E1/E2 con etiquetas independientes: **no acreditada**.',
        '- [ ] Restricciones y mediciones en hardware objetivo: **no acreditadas**.',
        '- [ ] Aprobación formal del cierre integral: **pendiente**.',
        '',
        '**Recomendación para Jira:** registrar evidencia técnica como avance de AG-034, sin mover a Done por cierre integral. El informe no constituye validación agronómica ni certificación de hardware.',
        '',
        '## Evidencias adjuntas',
        '',
        'El archivo `AG034_matriz_evidencias.csv` contiene SHA-256 de las cinco evidencias de entrada y del ZIP externo. La subcarpeta `fuentes/` conserva copias exactas de los cinco documentos. `AG034_manifest_integridad.json` permite comprobar que no se modificaron.',
        '',
    ]
    return '\n'.join(rows)


def generar(evidencias: Path, dataset: Path, salida: Path) -> dict:
    evidencias, dataset, salida = evidencias.resolve(), dataset.resolve(), salida.resolve()
    if salida.exists():
        raise EvidenceError('La carpeta de salida ya existe; no se sobrescribe')
    if salida == evidencias or evidencias in salida.parents or dataset == salida:
        raise EvidenceError('La salida no puede ubicarse dentro de las evidencias')
    result, blobs = validar(evidencias, dataset)
    salida.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.ag034_11_', dir=salida.parent))
    try:
        for rel, data in blobs.items():
            target = tmp / 'fuentes' / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        generated = {
            'AG034_resumen_consolidado.json': json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
            'AG034_matriz_evidencias.csv': _csv_evidence(result),
            'AG034_informe_para_Jira.md': _report_md(result),
        }
        for filename, txt in generated.items():
            (tmp / filename).write_text(txt, encoding='utf-8', newline='\n')
        manifest = {
            'version': VERSION, 'zip_externo_no_duplicado_sha256': result['dataset']['zip_sha256'],
            'archivos_sha256': {str(p.relative_to(tmp)).replace('\\', '/'): _sha(p.read_bytes())
                                for p in sorted(tmp.rglob('*')) if p.is_file()},
            'nota': 'integridad de copias; no firma digital ni acreditacion de operador',
        }
        (tmp / 'AG034_manifest_integridad.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        tmp.rename(salida)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return result


def verificar(salida: Path, dataset: Path | None = None) -> dict:
    salida = salida.resolve()
    manifest = _load_json(_read_bytes(salida / 'AG034_manifest_integridad.json'), 'manifest')
    if manifest.get('version') != VERSION:
        raise EvidenceError('Versión de manifiesto incorrecta')
    hashes = manifest.get('archivos_sha256')
    if not isinstance(hashes, dict) or not hashes:
        raise EvidenceError('Manifiesto vacío')
    actual = {str(p.relative_to(salida)).replace('\\', '/') for p in salida.rglob('*') if p.is_file()}
    if actual != set(hashes) | {'AG034_manifest_integridad.json'}:
        raise EvidenceError('Archivos agregados o ausentes en salida')
    for rel, declared in hashes.items():
        p = PurePosixPath(rel)
        if p.is_absolute() or '..' in p.parts or '\\' in rel or not SHA.fullmatch(declared):
            raise EvidenceError('Ruta o SHA de manifiesto inseguro')
        real = (salida / rel).resolve()
        if not real.is_relative_to(salida) or not real.is_file() or _sha(_read_bytes(real)) != declared:
            raise EvidenceError('Archivo derivado o evidencia alterada: ' + rel)
    resumen = _load_json(_read_bytes(salida / 'AG034_resumen_consolidado.json'), 'resumen')
    if resumen.get('cierre', {}).get('AG034_cierre_total_acreditado') is not False:
        raise EvidenceError('El consolidado no mantiene estado condicionado')
    if dataset is not None:
        digest, _ = _zip_index(dataset.resolve())
        if digest != manifest.get('zip_externo_no_duplicado_sha256'):
            raise EvidenceError('ZIP externo no coincide con el consolidado')
    return {'estado': 'integridad_consolidado_verificada', 'archivos_verificados': len(hashes),
            'cierre_total_AG034_acreditado': False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='AG-034 Incremento 11: consolidación de evidencias')
    subs = parser.add_subparsers(dest='comando', required=True)
    run = subs.add_parser('consolidar', help='Comprueba fuentes y genera informe + hashes')
    run.add_argument('--evidencias', type=Path, required=True)
    run.add_argument('--zip', type=Path, required=True)
    run.add_argument('--salida', type=Path, required=True)
    verify = subs.add_parser('verificar', help='Comprueba huellas del paquete generado')
    verify.add_argument('--salida', type=Path, required=True)
    verify.add_argument('--zip', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.comando == 'consolidar':
            result = generar(args.evidencias, args.zip, args.salida)
            response = {'estado': 'cierre_parcial_documentado', 'vistas': result['dataset']['fotografias'],
                        'evidencias_fuente': len(SOURCES), 'AG034_cierre_total_acreditado': False,
                        'salida': str(args.salida)}
        else:
            response = verificar(args.salida, args.zip)
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0
    except (EvidenceError, OSError, KeyError, TypeError, ValueError) as e:
        print(json.dumps({'estado': 'error', 'detalle': str(e)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
