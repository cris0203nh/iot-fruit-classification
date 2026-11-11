"""AG-036: cobertura y concordancia entre dos revisiones humanas independientes.

La integridad digital no acredita por sí sola la autenticidad de una revisión humana.
Nunca imputa E0/E1/E2, ni modifica etiquetas originales o rúbricas.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath

from PIL import Image, UnidentifiedImageError

VERSION = 'ag036-auditoria-doble-revision-v2'
PRODUCTS = ('mango', 'tomate')
LABELS = ('E0', 'E1', 'E2')
UNIVERSE_COLS = ('producto', 'variedad_declarada', 'lote_id', 'pieza_id', 'sesion_id',
                 'imagen_relativa', 'sha256_imagen', 'rubrica_version',
                 'seleccion_doble', 'criterio_seleccion')
REVIEW_COLS = ('producto', 'lote_id', 'pieza_id', 'revisor_id', 'fecha_revision_iso',
               'rubrica_version', 'estado_revision', 'etiqueta_e0_e1_e2',
               'justificacion', 'criterios_rxx', 'ubicacion_evidencia', 'soporte_relativo')
ADJ_COLS = ('producto', 'lote_id', 'pieza_id', 'estado_conciliacion', 'etiqueta_final',
            'revisor_arbitro', 'fecha_iso', 'justificacion', 'soporte_relativo',
            'rubrica_nueva_propuesta')
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,89}\Z')
SHA = re.compile(r'[0-9a-fA-F]{64}\Z')
MAX_CSV = 4 * 1024 * 1024
MAX_IMAGE = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000  # admite 6000x3376 de v2, mantiene límite de decodificación


class AuditError(ValueError):
    pass


def load_csv(path: Path, cols: tuple[str, ...]) -> tuple[list[dict[str, str]], str]:
    blob = path.read_bytes()
    if len(blob) > MAX_CSV:
        raise AuditError(f'CSV demasiado grande: {path.name}')
    try:
        reader = csv.DictReader(io.StringIO(blob.decode('utf-8-sig'), newline=''), strict=True)
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)) or set(reader.fieldnames) != set(cols):
            raise AuditError(f'Encabezados inválidos: {path.name}')
        rows = list(reader)
        if any(None in r or any(v is None for v in r.values()) for r in rows):
            raise AuditError(f'CSV malformado: {path.name}')
        return [{k: v.strip() for k, v in r.items()} for r in rows], hashlib.sha256(blob).hexdigest()
    except (UnicodeError, csv.Error) as exc:
        raise AuditError(f'CSV ilegible: {path.name}') from exc


def safe_file(root: Path, relative: str, limit: int) -> tuple[bytes, str]:
    if not relative or '\\' in relative or ':' in relative:
        raise AuditError('Ruta insegura o vacía')
    p = PurePosixPath(relative)
    if p.is_absolute() or any(x in ('', '.', '..') for x in p.parts):
        raise AuditError('Ruta insegura: ' + relative)
    root = root.resolve(strict=True)
    target = root.joinpath(*p.parts)
    if not target.is_file() or not target.resolve().is_relative_to(root):
        raise AuditError('Evidencia ausente o fuera de raíz: ' + relative)
    if any(x.is_symlink() for x in [target, *target.parents] if x != root):
        raise AuditError('Enlaces simbólicos prohibidos: ' + relative)
    if target.stat().st_size > limit:
        raise AuditError('Evidencia demasiado grande: ' + relative)
    blob = target.read_bytes()
    if not blob:
        raise AuditError('Evidencia vacía: ' + relative)
    return blob, hashlib.sha256(blob).hexdigest()


def has_timezone(value: str) -> bool:
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.tzinfo is not None and dt.utcoffset() is not None
    except ValueError:
        return False


def rubric_matches(product: str, rubric: str) -> bool:
    return rubric.startswith('kent-ext-' if product == 'mango' else 'tomato-ext-')


def load_universe(path: Path, images: Path) -> tuple[dict, dict]:
    rows, fingerprint = load_csv(path, UNIVERSE_COLS)
    universe: dict[tuple[str, str], dict] = {}
    views = set()
    owners = {}
    excluded = Counter()
    for n, row in enumerate(rows, 2):
        p, lot, pid, sid = row['producto'], row['lote_id'], row['pieza_id'], row['sesion_id']
        if p not in PRODUCTS or not ID.fullmatch(lot) or not ID.fullmatch(pid) or not ID.fullmatch(sid):
            raise AuditError(f'Universo fila {n}: producto/lote/pieza/sesión inválidos')
        if not rubric_matches(p, row['rubrica_version']):
            raise AuditError(f'Universo fila {n}: rúbrica no corresponde al producto')
        if row['seleccion_doble'] not in ('si', 'no'):
            raise AuditError(f'Universo fila {n}: selección debe ser si/no')
        if row['seleccion_doble'] == 'si' and not row['criterio_seleccion']:
            raise AuditError(f'Universo fila {n}: falta criterio de selección del subconjunto')
        if not SHA.fullmatch(row['sha256_imagen']):
            raise AuditError(f'Universo fila {n}: SHA256 inválido')
        data, sha = safe_file(images, row['imagen_relativa'], MAX_IMAGE)
        if sha != row['sha256_imagen'].lower():
            raise AuditError(f'Universo fila {n}: SHA256 no coincide')
        try:
            with Image.open(io.BytesIO(data)) as img:
                if img.format not in ('JPEG', 'PNG', 'MPO') or img.width * img.height > MAX_IMAGE_PIXELS:
                    raise AuditError(f'Universo fila {n}: imagen no admitida')
                img.verify()
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise AuditError(f'Universo fila {n}: imagen inválida') from exc
        key = (p, lot, pid)
        vk = (p, lot, pid, row['imagen_relativa'])
        if vk in views:
            raise AuditError(f'Universo fila {n}: fotografía duplicada en la pieza')
        views.add(vk)
        if sha in owners and owners[sha] != key:
            raise AuditError(f'Universo fila {n}: misma imagen asignada a diferentes piezas')
        owners[sha] = key
        is_eligible = p != 'mango' or row['variedad_declarada'].casefold() == 'kent'
        if not is_eligible:
            excluded[p] += 1
        existing = universe.get(key)
        if existing and (existing['seleccion_doble'] != row['seleccion_doble']
                         or existing['rubrica_version'] != row['rubrica_version']
                         or existing['variedad_declarada'].casefold() != row['variedad_declarada'].casefold()
                         or existing['elegible'] != is_eligible):
            raise AuditError(f'Universo fila {n}: datos contradictorios para una pieza')
        if existing:
            existing['vistas'] += 1
            existing['sesiones'].add(sid)
        else:
            universe[key] = {**row, 'elegible': is_eligible, 'vistas': 1, 'sesiones': {sid}}
    return universe, {'sha256': fingerprint, 'filas_vistas': len(rows), 'piezas': len(universe),
                      'vistas_excluidas_por_variedad': dict(excluded)}


def load_reviews(path: Path, universe: dict, supports: Path, slot: str) -> tuple[dict, dict]:
    rows, fingerprint = load_csv(path, REVIEW_COLS)
    records = {}
    identities = set()
    for n, row in enumerate(rows, 2):
        key = row['producto'], row['lote_id'], row['pieza_id']
        if key in records or key not in universe or not universe[key]['elegible'] or universe[key]['seleccion_doble'] != 'si':
            raise AuditError(f'Revisión {slot} fila {n}: pieza duplicada/no seleccionada/fuera de alcance')
        if not ID.fullmatch(row['revisor_id']):
            raise AuditError(f'Revisión {slot} fila {n}: revisor_id inválido')
        identities.add(row['revisor_id'])
        if row['rubrica_version'] != universe[key]['rubrica_version']:
            raise AuditError(f'Revisión {slot} fila {n}: versión de rúbrica no coincide')
        if not has_timezone(row['fecha_revision_iso']):
            raise AuditError(f'Revisión {slot} fila {n}: fecha sin zona horaria')
        state, grade = row['estado_revision'], row['etiqueta_e0_e1_e2']
        if state not in ('pendiente', 'no_evaluable', 'etiquetada'):
            raise AuditError(f'Revisión {slot} fila {n}: estado no admitido')
        if (state == 'etiquetada' and grade not in LABELS) or (state != 'etiquetada' and grade):
            raise AuditError(f'Revisión {slot} fila {n}: etiqueta no corresponde al estado')
        crit = [x.strip() for x in row['criterios_rxx'].split(',') if x.strip()]
        limit = 8 if row['producto'] == 'mango' else 10
        if len(crit) != len(set(crit)) or any(not re.fullmatch(r'R\d{2}', x) or not 1 <= int(x[1:]) <= limit for x in crit):
            raise AuditError(f'Revisión {slot} fila {n}: criterio Rxx inválido para el producto')
        if state == 'etiquetada' and grade in ('E1', 'E2') and (not crit or not row['ubicacion_evidencia']):
            raise AuditError(f'Revisión {slot} fila {n}: E1/E2 exige criterio Rxx y ubicación de evidencia')
        if state != 'pendiente':
            if not row['justificacion'] or not row['soporte_relativo']:
                raise AuditError(f'Revisión {slot} fila {n}: faltan justificación y soporte')
            safe_file(supports, row['soporte_relativo'], MAX_CSV)
        elif row['soporte_relativo']:
            safe_file(supports, row['soporte_relativo'], MAX_CSV)
        records[key] = row
    if len(identities) > 1:
        raise AuditError(f'Revisión {slot}: debe usar un único identificador de revisor en su archivo')
    return records, {'sha256': fingerprint, 'filas': len(rows), 'revisor_id': next(iter(identities), None)}


def kappa(matrix: dict[str, dict[str, int]]) -> float | None:
    n = sum(matrix[a][b] for a in LABELS for b in LABELS)
    if n == 0:
        return None
    po = sum(matrix[c][c] for c in LABELS) / n
    pe = sum(sum(matrix[c][b] for b in LABELS) * sum(matrix[a][c] for a in LABELS)
             for c in LABELS) / (n * n)
    if abs(1 - pe) < 1e-12:
        return None  # distribución degenerada: kappa indefinido, no reemplazar por 1
    return round((po - pe) / (1 - pe), 6)


def load_adjudications(path: Path | None, disagreements: dict, supports: Path,
                       reviewer_a: str | None, reviewer_b: str | None) -> tuple[dict, dict]:
    if path is None:
        return {}, {'proporcionadas': False, 'filas': 0}
    rows, fingerprint = load_csv(path, ADJ_COLS)
    out = {}
    for n, row in enumerate(rows, 2):
        key = row['producto'], row['lote_id'], row['pieza_id']
        if key not in disagreements or key in out:
            raise AuditError(f'Conciliación fila {n}: caso no discrepante o repetido')
        status = row['estado_conciliacion']
        if status not in ('pendiente', 'resuelto', 'ajuste_rubrica_propuesto'):
            raise AuditError(f'Conciliación fila {n}: estado no permitido')
        if status == 'resuelto':
            if row['etiqueta_final'] not in (*LABELS, 'no_evaluable'):
                raise AuditError(f'Conciliación fila {n}: decisión final inválida')
            if not ID.fullmatch(row['revisor_arbitro']) or row['revisor_arbitro'] in (reviewer_a, reviewer_b):
                raise AuditError(f'Conciliación fila {n}: requiere árbitro diferente de revisores A/B')
            if not has_timezone(row['fecha_iso']) or not row['justificacion'] or not row['soporte_relativo']:
                raise AuditError(f'Conciliación fila {n}: falta evidencia y justificación')
            safe_file(supports, row['soporte_relativo'], MAX_CSV)
        else:
            if row['etiqueta_final']:
                raise AuditError(f'Conciliación fila {n}: no declarar etiqueta final sin resolución')
            if status == 'ajuste_rubrica_propuesto' and not (row['justificacion'] and row['rubrica_nueva_propuesta']):
                raise AuditError(f'Conciliación fila {n}: propuesta de rúbrica incompleta')
            if row['soporte_relativo']:
                safe_file(supports, row['soporte_relativo'], MAX_CSV)
        out[key] = row
    return out, {'proporcionadas': True, 'filas': len(rows), 'sha256': fingerprint}


def audit(universe_csv: Path, a_csv: Path, b_csv: Path, images: Path, supports: Path,
          adjudications_csv: Path | None = None) -> dict:
    universe, uv = load_universe(universe_csv, images)
    ra, meta_a = load_reviews(a_csv, universe, supports, 'A')
    rb, meta_b = load_reviews(b_csv, universe, supports, 'B')
    if meta_a['revisor_id'] and meta_b['revisor_id'] and meta_a['revisor_id'] == meta_b['revisor_id']:
        raise AuditError('Los archivos A y B deben identificar a revisores distintos')
    result = {'version': VERSION, 'actividad': 'AG-036',
              'universo': uv, 'revisiones': {'A': meta_a, 'B': meta_b}, 'por_producto': {},
              'revision_humana_independiente_autenticada_por_software': False,
              'esquema_etiquetado_visual': 'E0/E1/E2',
              'equivalencia_con_primera_segunda_AG035': 'NO ESTABLECIDA',
              'referencia_documental': 'AGROP-15 v0.2; AGROP-13 Kent v0.4; AGROP-14 tomate v0.2',
              'rubricas_aprobadas_verificadas_por_software': False,
              'cierre_total_AG036_acreditado': False}
    disputes = {}
    for p in PRODUCTS:
        eligible = sorted(k for k, v in universe.items() if k[0] == p and v['elegible'])
        selected = [k for k in eligible if universe[k]['seleccion_doble'] == 'si']
        selected_rubrics = {universe[key]['rubrica_version'] for key in selected}
        if len(selected_rubrics) > 1:
            raise AuditError(f'{p}: no combinar piezas de diferentes versiones de rúbrica en una sola concordancia')
        matrix = {x: {y: 0 for y in LABELS} for x in LABELS}
        n_pair = n_agreement = n_no_eval = n_incomplete = n_both_not_evaluable = 0
        missing_cases = []
        distribution_a, distribution_b = Counter(), Counter()
        for key in selected:
            x, y = ra.get(key), rb.get(key)
            sx = x['estado_revision'] if x else 'sin_revision'
            sy = y['estado_revision'] if y else 'sin_revision'
            if sx in ('sin_revision', 'pendiente') or sy in ('sin_revision', 'pendiente'):
                n_incomplete += 1
                missing_cases.append({'producto': p, 'lote_id': key[1], 'pieza_id': key[2],
                                      'estado_A': sx, 'estado_B': sy})
                continue
            if sx == 'no_evaluable' or sy == 'no_evaluable':
                n_no_eval += 1
                if sx == sy:
                    n_both_not_evaluable += 1
                if sx != sy:
                    disputes[key] = {'producto': p, 'lote_id': key[1], 'pieza_id': key[2], 'tipo': 'evaluabilidad',
                                     'A': x['etiqueta_e0_e1_e2'] or sx,
                                     'B': y['etiqueta_e0_e1_e2'] or sy}
                continue
            n_pair += 1
            cx, cy = x['etiqueta_e0_e1_e2'], y['etiqueta_e0_e1_e2']
            matrix[cx][cy] += 1
            distribution_a[cx] += 1
            distribution_b[cy] += 1
            if cx == cy:
                n_agreement += 1
            else:
                disputes[key] = {'producto': p, 'lote_id': key[1], 'pieza_id': key[2], 'tipo': 'grado', 'A': cx, 'B': cy}
        status = ('sin_subconjunto_seleccionado' if not selected else
                  'bloqueado_por_falta_de_pares_calificables' if n_pair == 0 else
                  'acuerdo_calculado_pendiente_validacion_independiente')
        result['por_producto'][p] = {
            'estado': status, 'piezas_elegibles': len(eligible), 'piezas_seleccionadas_para_doble_revision': len(selected),
            'cobertura_seleccion_sobre_elegibles': round(len(selected)/len(eligible), 6) if eligible else None,
            'revisiones_A_registradas': sum(key in ra for key in selected),
            'revisiones_B_registradas': sum(key in rb for key in selected),
            'pares_con_dos_grados': n_pair,
            'pares_completos_incluyendo_no_evaluable': n_pair + n_no_eval,
            'cobertura_doble_revision_sobre_seleccionadas': round((n_pair+n_no_eval)/len(selected),6) if selected else None,
            'ambos_no_evaluables': n_both_not_evaluable,
            'cobertura_doble_grado_sobre_seleccionadas': round(n_pair/len(selected), 6) if selected else None,
            'pares_con_algun_no_evaluable': n_no_eval,
            'pares_incompletos': n_incomplete,
            'casos_pendientes_de_par': missing_cases,
            'acuerdos_exactos': n_agreement,
            'rubrica_del_subconjunto': next(iter(selected_rubrics), None),
            'distribucion_grados_A': {grade: distribution_a[grade] for grade in LABELS},
            'distribucion_grados_B': {grade: distribution_b[grade] for grade in LABELS},
            'acuerdo_observado': round(n_agreement/n_pair, 6) if n_pair else None,
            'kappa_cohen_no_ponderado': kappa(matrix),
            'matriz_A_filas_B_columnas': matrix,
            'discrepancias': sum(k[0] == p for k in disputes),
        }
    decisions, adj = load_adjudications(adjudications_csv, disputes, supports, meta_a['revisor_id'], meta_b['revisor_id'])
    result['conciliacion'] = {**adj, 'resueltas_documentalmente': sum(r['estado_conciliacion']=='resuelto' for r in decisions.values()),
                              'ajustes_rubrica_propuestos': sum(r['estado_conciliacion']=='ajuste_rubrica_propuesto' for r in decisions.values())}
    result['casos_discrepantes'] = [dict(value, conciliacion=decisions.get(key, {}).get('estado_conciliacion', 'sin_registro'))
                                   for key, value in sorted(disputes.items())]
    result['advertencias'] = [
        'AGROP-15 v0.2 usa E0/E1/E2 como etiquetas visuales operativas. AG-035/AGROP-43 usa primera/segunda: no existe equivalencia aprobada; NO mezclar métricas ni convertir etiquetas.',
        'Las rúbricas documentales de referencia (kent-ext-v0.4, tomato-ext-v0.2) y las versiones usadas por AG-034/los pipelines pueden ser distintas; cotejar cada registro y obtener aprobación antes de conclusiones.',
        'Las coincidencias no son exactitud respecto a la verdad de campo.',
        'Kappa usa solo pares E0/E1/E2. No evaluables, pendientes y ausentes se reportan por separado.',
        'Los SHA256 y archivos de respaldo acreditan integridad/presencia digital, no autenticidad ni independencia humana.',
        'La aprobación de la rúbrica debe acreditarse externamente; una propuesta no modifica su versión oficial.',
        'Si el subconjunto no fue elegido con un protocolo representativo, no generalizar las tasas a todas las frutas.',
        'La actividad depende de AG-030 y AG-035; el script no acredita esos cierres.',
    ]
    return result


def markdown(report: dict) -> str:
    out = ['# AG-036 — Informe reproducible de cobertura y concordancia', '',
           '## Alcance', 'Medición de acuerdo de dos revisiones humanas declaradas, sujeta a validación externa.', '',
           '| Producto | Elegibles | Subconjunto | Pares E0/E1/E2 | Cobertura de pares | Acuerdo | Kappa | Discrepancias |',
           '|---|---:|---:|---:|---:|---:|---:|---:|']
    for product, d in report['por_producto'].items():
        def fmt(v): return 'No calculable' if v is None else str(v)
        out.append(f'| {product} | {d["piezas_elegibles"]} | {d["piezas_seleccionadas_para_doble_revision"]} '
                   f'| {d["pares_con_dos_grados"]} | {fmt(d["cobertura_doble_grado_sobre_seleccionadas"])} '
                   f'| {fmt(d["acuerdo_observado"])} | {fmt(d["kappa_cohen_no_ponderado"])} '
                   f'| {d["discrepancias"]} |')
    out.extend(['', '## Casos discrepantes', ''])
    if not report['casos_discrepantes']:
        out.append('Ninguno registrado; ello no acredita que haya doble revisión suficiente.')
    else:
        out.append('| Producto | Lote | Pieza | Tipo | Revisor A | Revisor B | Conciliación |')
        out.append('|---|---|---|---|---|---|---|')
        for c in report['casos_discrepantes']:
            out.append(f'| {c["producto"]} | {c["lote_id"]} | {c["pieza_id"]} | {c["tipo"]} | {c["A"]} | {c["B"]} | {c["conciliacion"]} |')
    out.extend(['', '## Pares pendientes o incompletos', '',
                '| Producto | Lote | Pieza | Estado A | Estado B |',
                '|---|---|---|---|---|'])
    pending = [x for d in report['por_producto'].values() for x in d['casos_pendientes_de_par']]
    if not pending:
        out.append('| — | — | — | Ninguno documentado | — |')
    for x in pending:
        out.append(f'| {x["producto"]} | {x["lote_id"]} | {x["pieza_id"]} | {x["estado_A"]} | {x["estado_B"]} |')
    out.extend(['', '## Limitaciones y pendientes', ''])
    out.extend('- ' + s for s in report['advertencias'])
    out.extend(['', '**Cierre AG-036 acreditado:** No. Confirmar revisiones, protocolos, conciliaciones y dependencias AG-030/AG-035 antes de marcar Done.', ''])
    return '\n'.join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('universo', 'revision-a', 'revision-b', 'raiz-imagenes', 'raiz-soportes', 'salida'):
        ap.add_argument('--' + name, type=Path, required=True)
    ap.add_argument('--conciliaciones', type=Path)
    args = ap.parse_args(argv)
    try:
        json_out = args.salida
        md_out = args.salida.with_suffix('.md')
        if json_out.suffix.lower() != '.json' or json_out == md_out or json_out.exists() or md_out.exists():
            raise AuditError('Salida debe ser un JSON nuevo; no se sobrescriben resultados existentes')
        report = audit(args.universo, args.revision_a, args.revision_b,
                       args.raiz_imagenes, args.raiz_soportes, args.conciliaciones)
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        md_out.write_text(markdown(report), encoding='utf-8')
        print(json.dumps({'estado': 'informe_generado_cierre_pendiente', 'json': str(json_out),
                          'md': str(md_out), 'cierre_total_AG036_acreditado': False}, ensure_ascii=False))
        return 0
    except (OSError, AuditError) as exc:
        print(json.dumps({'estado': 'error_de_integridad', 'detalle': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
