"""AG-034 / Incremento 12: preparación y control documental de revisión E0/E1/E2.

La revisión asistida por IA NO es ground truth ni acredita identidad física,
sesión, variedad, licencias o etiquetas. No entrena ni calcula métricas comerciales.
Usa el ZIP y el CSV de revisión del Incremento 09, sin editar los originales.
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
from pathlib import Path

from .consolidar_ag034 import EvidenceError, _load_csv, _read_bytes, _zip_index

VERSION = 'ag034-revision-calidad-v1'
EDITABLE = (
    'estado_revision', 'etiqueta_e0_e1_e2', 'revisor_id', 'fecha_revision_iso',
    'rubrica_version', 'justificacion_rubrica', 'observaciones_revisor',
    'referencia_soporte_pieza_sesion', 'referencia_soporte_etiqueta',
)
FIXED = (
    'producto', 'id_ejemplar_fuente', 'vistas_declaradas', 'archivos_vistas',
    'sha256_vistas', 'revision_mascaras_ia', 'observaciones_ia',
    'variedad_mango_fuente', 'procedencia',
)
COLUMNS = FIXED + EDITABLE
STATUSES = {'pendiente', 'revisada_sin_etiqueta', 'no_evaluable', 'etiquetada'}
LABELS = {'E0', 'E1', 'E2'}
SHA = re.compile(r'[0-9a-f]{64}\Z')
ID = re.compile(r'[A-Za-z0-9_-]{1,80}\Z')
MAX_CSV = 4 * 1024 * 1024


class ReviewError(ValueError):
    """La revisión tiene un error estructural o una acreditación inconsistente."""


def _csv_read(blob: bytes, name: str) -> list[dict[str, str]]:
    if len(blob) > MAX_CSV:
        raise ReviewError('CSV demasiado grande: ' + name)
    try:
        reader = csv.DictReader(io.StringIO(blob.decode('utf-8-sig'), newline=''), strict=True)
        headers = reader.fieldnames
        if headers is None or len(headers) != len(set(headers)):
            raise ReviewError('Encabezados duplicados o ausentes: ' + name)
        rows = list(reader)
        if not rows or any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ReviewError('CSV malformado: ' + name)
        return rows
    except (UnicodeError, csv.Error) as exc:
        raise ReviewError('CSV inválido: ' + name) from exc


def _csv_bytes(rows: list[dict[str, str]]) -> bytes:
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode('utf-8-sig')


def _clean_note(value: object) -> str:
    """Evita inyección de fórmulas al abrir el CSV como hoja de cálculo."""
    value = str(value or '').strip()
    if value.startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
        return "'" + value
    return value[:1200]


def _timestamp(value: str) -> bool:
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return d.tzinfo is not None and d.utcoffset() is not None
    except ValueError:
        return False


def _review_source(zip_path: Path, review_csv: Path) -> tuple[dict[tuple[str, str], dict], dict]:
    zip_hash, photo_index = _zip_index(zip_path)
    rows = _load_csv(_read_bytes(review_csv), 'revisión_IA_incremento09')
    required = {'producto', 'id_ejemplar_fuente', 'vista', 'archivo_origen', 'sha256',
                'revision_visual_mascara_IA', 'observaciones_visual_IA', 'es_mango_kent',
                'aprobacion_operador_o_experto', 'etiqueta_E0_E1_E2_acreditada'}
    if not rows or not required.issubset(rows[0]):
        raise ReviewError('La revisión de IA no tiene los campos esperados del incremento 09')
    seen = set()
    by_group = defaultdict(list)
    for row in rows:
        product, piece = row['producto'].strip(), row['id_ejemplar_fuente'].strip()
        try:
            view = int(row['vista'])
        except (TypeError, ValueError) as exc:
            raise ReviewError('Vista inválida en revisión IA') from exc
        key = product, piece, view
        src = photo_index.get(key)
        if (product not in {'mango', 'tomate'} or not ID.fullmatch(piece) or src is None
                or src['sha256'] != row['sha256'].strip().lower()
                or src['archivo'] != row['archivo_origen']
                or key in seen):
            raise ReviewError('La revisión IA no coincide con el ZIP: ' + str(key))
        if (row['etiqueta_E0_E1_E2_acreditada'].strip()
                or row['aprobacion_operador_o_experto'].strip() != 'pendiente'):
            raise ReviewError('El CSV de IA pretende revisión humana no acreditada')
        seen.add(key)
        by_group[(product, piece)].append((view, row))
    if seen != set(photo_index):
        raise ReviewError('Faltan vistas del ZIP en la revisión IA')
    expected: dict[tuple[str, str], dict[str, str]] = {}
    for key, views in sorted(by_group.items()):
        views.sort(key=lambda pair: pair[0])
        nums = [v for v, _ in views]
        if nums != list(range(1, len(nums) + 1)):
            raise ReviewError('Vistas no consecutivas: ' + str(key))
        row0 = views[0][1]
        variety = row0['es_mango_kent'].strip() if key[0] == 'mango' else 'no_aplica'
        if any(row['es_mango_kent'].strip() != row0['es_mango_kent'].strip() for _, row in views):
            raise ReviewError('Variedad inconsistente entre vistas: ' + str(key))
        states = [row['revision_visual_mascara_IA'].strip() for _, row in views]
        if any(s not in {'compatible_visual_provisional', 'mascara_parcial',
                         'sin_mascara', 'mascara_no_utilizable'} for s in states):
            raise ReviewError('Revisión de máscaras desconocida')
        notes = list(dict.fromkeys(_clean_note(row['observaciones_visual_IA']) for _, row in views))
        expected[key] = {
            'producto': key[0], 'id_ejemplar_fuente': key[1],
            'vistas_declaradas': str(len(views)),
            'archivos_vistas': '|'.join(row['archivo_origen'] for _, row in views),
            'sha256_vistas': '|'.join(row['sha256'].lower() for _, row in views),
            'revision_mascaras_ia': '|'.join(states),
            'observaciones_ia': _clean_note(' | '.join(notes)),
            'variedad_mango_fuente': variety,
            'procedencia': 'externa_no_verificada_como_captura_propia',
        }
    return expected, {'zip_sha256': zip_hash, 'vistas': len(photo_index),
                      'ejemplares_declarados': len(expected),
                      'revision_ia_sha256': hashlib.sha256(_read_bytes(review_csv)).hexdigest()}


def generar_plantilla(zip_path: Path, review_csv: Path) -> tuple[bytes, dict]:
    expected, source = _review_source(zip_path, review_csv)
    rows = [{**fixed, **{name: ('pendiente' if name == 'estado_revision' else '') for name in EDITABLE}}
            for fixed in expected.values()]
    return _csv_bytes(rows), source


def auditar(zip_path: Path, review_csv: Path, decisions_csv: Path) -> tuple[dict, list[dict[str, str]]]:
    expected, source = _review_source(zip_path, review_csv)
    rows = _csv_read(_read_bytes(decisions_csv), 'decisiones_E0_E1_E2')
    if set(rows[0]) != set(COLUMNS):
        raise ReviewError('Las columnas del CSV de decisiones no coinciden con la plantilla')
    seen, errors = set(), []
    statuses = Counter()
    declared = Counter()
    for number, row in enumerate(rows, 2):
        key = row['producto'].strip(), row['id_ejemplar_fuente'].strip()
        if key in seen or key not in expected:
            errors.append(f'fila {number}: identificador duplicado o no contenido en el dataset')
            continue
        seen.add(key)
        if any(row[name] != expected[key][name] for name in FIXED):
            errors.append(f'fila {number}: campos de procedencia o SHA modificados')
            continue
        status, label = row['estado_revision'].strip(), row['etiqueta_e0_e1_e2'].strip()
        statuses[key[0], status] += 1
        if status not in STATUSES:
            errors.append(f'fila {number}: estado_revision desconocido')
            continue
        if label and label not in LABELS:
            errors.append(f'fila {number}: etiqueta E0/E1/E2 inválida')
            continue
        if status != 'etiquetada' and label:
            errors.append(f'fila {number}: etiqueta prohibida en estado {status}')
            continue
        if status == 'etiquetada' and not label:
            errors.append(f'fila {number}: falta etiqueta en registro etiquetado')
            continue
        if status == 'pendiente':
            if any(row[col].strip() for col in EDITABLE if col != 'estado_revision'):
                errors.append(f'fila {number}: registro pendiente contiene acreditaciones')
            continue
        if (not row['revisor_id'].strip()
                or re.search(r'\b(chatgpt|inteligencia artificial|asistente ia|\bai\b)\b',
                             row['revisor_id'], re.IGNORECASE)
                or not _timestamp(row['fecha_revision_iso'].strip())):
            errors.append(f'fila {number}: faltan revisor humano y fecha con zona horaria')
            continue
        if status in {'no_evaluable', 'revisada_sin_etiqueta'}:
            if len(row['observaciones_revisor'].strip()) < 8:
                errors.append(f'fila {number}: falta motivo de revisión o exclusión')
            continue
        # Etiquetado solo documental; las afirmaciones del formulario no se
        # confunden con validación independiente de la evidencia física.
        if (len(row['justificacion_rubrica'].strip()) < 20
                or not row['referencia_soporte_etiqueta'].strip()
                or not row['referencia_soporte_pieza_sesion'].strip()
                or not row['rubrica_version'].strip()):
            errors.append(f'fila {number}: justificación/rúbrica/soportes incompletos')
            continue
        if key[0] == 'mango' and (
            'kent' in row['rubrica_version'].lower() or
            'ataulfo' in row['variedad_mango_fuente'].lower()
        ):
            errors.append(f'fila {number}: el dataset Ataulfo no acredita la rúbrica de mango Kent')
            continue
        if key[0] == 'tomate' and not row['rubrica_version'].lower().startswith('tomato-ext-'):
            errors.append(f'fila {number}: rúbrica de tomate no reconocida')
            continue
        declared[key[0], label] += 1
    if seen != set(expected):
        errors.append('El CSV de decisiones no contiene todos los ejemplares del ZIP')
    state = 'bloqueado_por_integridad' if errors else 'pendiente_de_validacion_externa'
    report = {
        'version': VERSION, 'actividad': 'AG-034 / AGROP-42',
        'estado': state, 'dataset': source, 'filas_esperadas': len(expected),
        'filas_recibidas': len(rows), 'errores_integridad': errors,
        'decisiones_csv_sha256': hashlib.sha256(_read_bytes(decisions_csv)).hexdigest(),
        'revision': {
            product: {
                'pendientes': statuses[product, 'pendiente'],
                'revisadas_sin_etiqueta': statuses[product, 'revisada_sin_etiqueta'],
                'no_evaluables': statuses[product, 'no_evaluable'],
                'etiquetas_declaradas_sin_acreditacion_independiente': {
                    label: declared[product, label] for label in sorted(LABELS)
                },
                'etiquetas_acreditadas': 0,
            } for product in ('mango', 'tomate')
        },
        'revisiones_ia_equivalen_a_ground_truth': False,
        'identidad_fisica_y_sesiones_verificadas': False,
        'metricas_e0_e1_e2': None,
        'entrenamiento_comercial_autorizado': False,
        'AG034_cierre_total_acreditado': False,
        'pendientes_para_cierre': [
            'Capturas propias o dataset con independencia física y sesiones documentadas',
            'Mango Kent con variedad confirmada y rúbrica correspondiente',
            'Anotaciones E0/E1/E2 revisadas por persona competente con soportes auditados',
            'Partición por pieza/sesión; comparación de ambos métodos sobre etiquetas verificadas',
            'Medición de recursos y límites en hardware objetivo',
        ],
    }
    return report, rows


def informe_md(report: dict) -> str:
    d = report['dataset']
    lines = [
        '# AG-034 — Revisión de etiquetas E0/E1/E2 (Incremento 12)', '',
        f"Estado documental: **{report['estado']}**.", '',
        f"Dataset: {d['vistas']} vistas; {d['ejemplares_declarados']} identificadores de fuente.",
        f"SHA-256 ZIP: `{d['zip_sha256']}`.", '',
        '## Resultados', '',
        '| Producto | Pendientes | Sin etiqueta | No evaluables | Etiquetas acreditadas |',
        '|---|---:|---:|---:|---:|',
    ]
    for product, r in report['revision'].items():
        lines.append(f"| {product} | {r['pendientes']} | {r['revisadas_sin_etiqueta']} | {r['no_evaluables']} | 0 |")
    lines.extend(['', '## Interpretación y límites', '',
                  'Las observaciones y máscaras revisadas por IA no constituyen patrones de referencia.',
                  'La etiqueta declarada en una ficha no acredita por sí sola variedad, sesión, identidad ni rúbrica.',
                  'El ZIP procede de fuentes externas y sus identificadores no prueban piezas físicamente independientes.',
                  'Las fotografías Ataulfo no acreditan la rúbrica específica de mango Kent.',
                  'La clasificación E0/E1/E2 y sus métricas **no están validadas**.', '',
                  '## Pendientes antes del cierre de AG-034', ''])
    lines.extend('- ' + item for item in report['pendientes_para_cierre'])
    if report['errores_integridad']:
        lines.extend(['', '## Errores de integridad', ''])
        lines.extend('- ' + err for err in report['errores_integridad'])
    return '\n'.join(lines) + '\n'


def _new_file(path: Path, contents: bytes) -> None:
    if path.exists():
        raise ReviewError('No se sobrescribe archivo existente: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as file:
        file.write(contents)


def verificar(zip_path: Path, review_csv: Path, decisions_csv: Path, output: Path) -> dict:
    """Verifica de nuevo fuentes y los tres resultados, sin modificar archivos."""
    if not output.is_dir() or output.is_symlink():
        raise ReviewError('No existe directorio verificable de resultados')
    manifest_path = output / 'AG034_manifest_integridad.json'
    manifest = json.loads(_read_bytes(manifest_path).decode('utf-8'))
    fresh, _ = auditar(zip_path, review_csv, decisions_csv)
    expected = {
        'AG034_revision_calidad_auditoria.json': (
            json.dumps(fresh, ensure_ascii=False, indent=2) + '\n').encode('utf-8'),
        'AG034_informe_revision_calidad.md': informe_md(fresh).encode('utf-8'),
    }
    if (manifest.get('version') != VERSION
            or manifest.get('zip_sha256') != fresh['dataset']['zip_sha256']
            or manifest.get('revision_ia_sha256') != fresh['dataset']['revision_ia_sha256']
            or manifest.get('decisiones_csv_sha256') != fresh['decisiones_csv_sha256']
            or manifest.get('archivos_sha256') != {
                name: hashlib.sha256(blob).hexdigest() for name, blob in expected.items()
            }):
        raise ReviewError('Manifiesto no coincide con las fuentes o los resultados calculados')
    for name, original in expected.items():
        if _read_bytes(output / name) != original:
            raise ReviewError('El resultado fue modificado: ' + name)
    return {'estado': 'integridad_revision_verificada', 'archivos_resultados': 3,
            'fichas': fresh['filas_recibidas'], 'etiquetas_acreditadas': 0,
            'cierre_total_AG034_acreditado': False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('plantilla', help='Genera 30 fichas por identificador sin etiquetas')
    a.add_argument('--zip', required=True, type=Path)
    a.add_argument('--revision-ia', required=True, type=Path)
    a.add_argument('--salida', required=True, type=Path)
    b = sub.add_parser('auditar', help='Audita fichas y genera informe sin entrenar')
    b.add_argument('--zip', required=True, type=Path)
    b.add_argument('--revision-ia', required=True, type=Path)
    b.add_argument('--csv', required=True, type=Path)
    b.add_argument('--salida', required=True, type=Path)
    c = sub.add_parser('verificar', help='Recalcula auditoría y comprueba tres archivos de salida')
    c.add_argument('--zip', required=True, type=Path)
    c.add_argument('--revision-ia', required=True, type=Path)
    c.add_argument('--csv', required=True, type=Path)
    c.add_argument('--salida', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.cmd == 'plantilla':
            blob, source = generar_plantilla(args.zip, args.revision_ia)
            _new_file(args.salida, blob)
            print(json.dumps({'estado': 'plantilla_creada', 'fichas': source['ejemplares_declarados'],
                              'fotografias': source['vistas'], 'salida': str(args.salida)}, ensure_ascii=False))
        elif args.cmd == 'verificar':
            print(json.dumps(verificar(args.zip, args.revision_ia, args.csv, args.salida), ensure_ascii=False))
        else:
            if args.salida.exists():
                raise ReviewError('No se sobrescribe una carpeta de resultados existente')
            report, _ = auditar(args.zip, args.revision_ia, args.csv)
            args.salida.mkdir(parents=True, exist_ok=False)
            outputs = {
                'AG034_revision_calidad_auditoria.json': (
                    json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode('utf-8'),
                'AG034_informe_revision_calidad.md': informe_md(report).encode('utf-8'),
            }
            for name, blob in outputs.items():
                _new_file(args.salida / name, blob)
            manifest = {
                'version': VERSION,
                'zip_sha256': report['dataset']['zip_sha256'],
                'revision_ia_sha256': report['dataset']['revision_ia_sha256'],
                'decisiones_csv_sha256': report['decisiones_csv_sha256'],
                'archivos_sha256': {name: hashlib.sha256(blob).hexdigest()
                                    for name, blob in outputs.items()},
            }
            _new_file(args.salida / 'AG034_manifest_integridad.json',
                      (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
            print(json.dumps({'estado': report['estado'], 'fichas': report['filas_recibidas'],
                              'errores_integridad': len(report['errores_integridad']),
                              'etiquetas_acreditadas': 0, 'cierre_total_AG034_acreditado': False}, ensure_ascii=False))
            return 2 if report['errores_integridad'] else 0
        return 0
    except (EvidenceError, ReviewError, OSError, ValueError) as exc:
        print(json.dumps({'estado': 'error', 'detalle': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
