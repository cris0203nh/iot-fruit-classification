"""AG-055 I02: inventario y promoción auditada de datos reales AG-036 -> AG-034.

NO inventa etiquetas, no certifica al revisor, no aprueba licencias ni rúbricas,
no entrena modelos y no escribe en la base de datos. Salidas privadas fuera de Git.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import secrets
from contextlib import contextmanager
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image, ImageOps
from vision.evaluation.ag036.auditar_etiquetado import (
    MAX_IMAGE, REVIEW_COLS, UNIVERSE_COLS, load_csv, load_universe, load_reviews,
)
from vision.evaluation.ag036.auditar_revision_unica import _load_return
from vision.evaluation.agrop42.comparar_calidad_ag034 import (
    COLUMNS as AG034_COLUMNS, LABELS, QualityError, _features,
    aggregate_pieces, connected_groups, load_eligible, split_groups,
)

VERSION = 'ag055-dataset-i02-v1'
PRODUCTS = ('mango', 'tomate')
ROLES = ('roi_verificada', 'derechos_uso', 'identidad_sesion_verificada',
         'rubrica_aprobada', 'variedad_verificada')
EDITABLE = (
    'roi_xywh', 'roi_verificada',
    'derechos_uso', 'soporte_derechos_relativo',
    'identidad_sesion_verificada', 'soporte_identidad_sesion_relativo',
    'rubrica_aprobada', 'soporte_rubrica_relativo',
    'variedad_verificada', 'soporte_variedad_relativo',
    'observacion_verificador',
)
LOCKED = (
    'registro_id', 'producto', 'lote_id', 'pieza_id', 'pieza_id_ag055',
    'sesion_id', 'sesion_id_ag055', 'variedad_declarada', 'imagen_relativa',
    'sha256_imagen', 'formato_detectado', 'ancho_orientado_px', 'alto_orientado_px',
    'seleccion_doble', 'estado_revision_A', 'etiqueta_reportada_A',
    'revisor_id_A', 'fecha_revision_A', 'rubrica_version',
    'soporte_revision_A_relativo',
)
FIELDS = LOCKED + EDITABLE
INVENTORY_FIELDS = LOCKED + ('estado_preparatorio', 'motivos_preparatorios')
REJECTIONS = ('registro_id', 'producto', 'pieza_id_ag055', 'etiqueta_reportada_A', 'motivos_exclusion')
REL = re.compile(r'^[A-Za-z0-9_. -]+$')
MAX_SRC_JSON = 2 * 1024 * 1024


class DatasetError(ValueError):
    """Contrato de datos o evidencia incompatible con una promoción segura."""


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(relative: str) -> PurePosixPath:
    if not relative or '\\' in relative or ':' in relative or '\x00' in relative:
        raise DatasetError('Ruta relativa insegura o vacía')
    p = PurePosixPath(relative)
    if (p.is_absolute() or any(x in ('', '.', '..') for x in p.parts)
            or relative.startswith('/') or relative.endswith('/')):
        raise DatasetError('Ruta relativa insegura')
    return p


def safe_file(root: Path, relative: str, max_size: int = MAX_IMAGE) -> Path:
    p = safe_relative(relative)
    root = root.resolve(strict=True)
    file = root.joinpath(*p.parts)
    if not file.is_file() or not file.resolve().is_relative_to(root):
        raise DatasetError('Archivo de evidencia ausente o fuera de raíz')
    cursor = file
    while cursor != root:
        if cursor.is_symlink():
            raise DatasetError('Enlace simbólico no admitido')
        cursor = cursor.parent
    if not 0 < file.stat().st_size <= max_size:
        raise DatasetError('Archivo de evidencia vacío o demasiado grande')
    return file


def read_rows(path: Path, expected: tuple[str, ...]) -> list[dict[str, str]]:
    raw = path.read_bytes()
    if len(raw) > 4 * 1024 * 1024:
        raise DatasetError('CSV supera 4 MiB')
    try:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)) or tuple(fields) != expected:
            raise DatasetError('Columnas alteradas en fichas de verificación')
        rows = list(reader)
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise DatasetError('CSV malformado o incompleto')
        return [{k: v.strip() for k, v in row.items()} for row in rows]
    except (UnicodeError, csv.Error) as exc:
        raise DatasetError('CSV inválido') from exc


def write_rows(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    if path.exists():
        raise DatasetError('No se sobrescriben archivos previos')
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, obj: dict) -> None:
    if path.exists():
        raise DatasetError('No se sobrescriben archivos previos')
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def _load_sources(universe_csv: Path, images_root: Path, return_zip: Path,
                  supports_temp: Path) -> tuple[list[dict], dict, dict, dict]:
    """Reutiliza los validadores originales de AG-036; no reconstruye una revisión B."""
    universe, u_meta = load_universe(universe_csv, images_root)
    raw_reviews, zip_sha = _load_return(return_zip, supports_temp)
    review_csv = supports_temp.parent / 'revision_A_temporal.csv'
    write_rows(review_csv, REVIEW_COLS, raw_reviews)
    reviews, review_meta = load_reviews(review_csv, universe, supports_temp, 'A')
    selected = {k for k, v in universe.items() if v['elegible'] and v['seleccion_doble'] == 'si'}
    if set(reviews) != selected:
        raise DatasetError('La devolución A no cubre exactamente las piezas seleccionadas de AG-036')
    return raw_reviews, universe, reviews, {
        'sha256_universo': u_meta['sha256'],
        'sha256_devolucion': zip_sha,
        'piezas_universo': len(universe),
        'piezas_revisadas_A': len(reviews),
        'revisor_declarado_A': review_meta['revisor_id'],
    }


def _image_format(file: Path) -> tuple[str, int, int]:
    with Image.open(file) as img:
        fmt = img.format or 'desconocido'
        if img.width * img.height > 24_000_000:
            raise DatasetError('Resolución excede 24 MP')
        if fmt in ('JPEG', 'PNG'):
            im = ImageOps.exif_transpose(img)
            return fmt, im.width, im.height
        return fmt, img.width, img.height


def _make_inventory(universe_csv: Path, images_root: Path, return_zip: Path,
                    supports_temp: Path) -> tuple[list[dict], list[dict], dict, list[dict]]:
    _, universe, reviews, provenance = _load_sources(
        universe_csv, images_root, return_zip, supports_temp)
    # El universo puede contener varias vistas de una pieza: jamás son piezas nuevas.
    # La lectura original ya comprobó integridad, formato y duplicaciones por imagen.
    source_rows, _ = load_csv(universe_csv, UNIVERSE_COLS)
    candidates: list[dict] = []
    inventory: list[dict] = []
    for view in source_rows:
        product, lot, piece, session = (view[k] for k in ('producto', 'lote_id', 'pieza_id', 'sesion_id'))
        key = (product, lot, piece)
        review = reviews.get(key)
        physical_id = sha256_bytes(f'{product}\0{lot}\0{piece}'.encode())[:22]
        session_id = sha256_bytes(session.encode('utf-8'))[:22]
        safe_file(images_root, view['imagen_relativa'], MAX_IMAGE)
        fmt, width, height = _image_format(images_root / view['imagen_relativa'])
        rid = sha256_bytes(f'{product}\0{lot}\0{piece}\0{view["imagen_relativa"]}\0{view["sha256_imagen"]}'.encode())[:32]
        locked = {
            'registro_id': rid, 'producto': product, 'lote_id': lot, 'pieza_id': piece,
            'pieza_id_ag055': f'{product}_{physical_id}',
            'sesion_id': session, 'sesion_id_ag055': f'ses_{session_id}',
            'variedad_declarada': view['variedad_declarada'],
            'imagen_relativa': view['imagen_relativa'],
            'sha256_imagen': view['sha256_imagen'].lower(),
            'formato_detectado': fmt,
            'ancho_orientado_px': str(width), 'alto_orientado_px': str(height),
            'seleccion_doble': view['seleccion_doble'],
            'estado_revision_A': review['estado_revision'] if review else 'sin_revision',
            'etiqueta_reportada_A': review['etiqueta_e0_e1_e2'] if review else '',
            'revisor_id_A': review['revisor_id'] if review else '',
            'fecha_revision_A': review['fecha_revision_iso'] if review else '',
            'rubrica_version': view['rubrica_version'],
            'soporte_revision_A_relativo': (
                f'AG036_A/{review["soporte_relativo"]}' if review and review['soporte_relativo'] else ''),
        }
        reasons = []
        if not review:
            reasons.append('sin_revision_A_de_pieza')
        elif review['estado_revision'] != 'etiquetada':
            reasons.append('sin_etiqueta_final_A')
        if product == 'mango' and view['variedad_declarada'].casefold() != 'kent':
            reasons.append('mango_fuera_de_Kent_declarado')
        if fmt not in ('JPEG', 'PNG'):
            reasons.append('formato_no_admitido_AG034_' + fmt)
        inventory.append({**locked,
            'estado_preparatorio': 'candidato_a_verificacion' if not reasons else 'bloqueado_para_entrenamiento',
            'motivos_preparatorios': '|'.join(reasons)})
        if review and review['estado_revision'] == 'etiquetada':
            candidates.append({**locked, **{
                'roi_xywh': '', 'roi_verificada': 'no',
                'derechos_uso': 'pendiente', 'soporte_derechos_relativo': '',
                'identidad_sesion_verificada': 'no', 'soporte_identidad_sesion_relativo': '',
                'rubrica_aprobada': 'no', 'soporte_rubrica_relativo': '',
                'variedad_verificada': 'no', 'soporte_variedad_relativo': '',
                'observacion_verificador': '',
            }})
    if len({row['registro_id'] for row in inventory}) != len(inventory):
        raise DatasetError('Hay dos vistas con igual identidad: registro duplicado')
    distribution = {p: {c: len({r['pieza_id_ag055'] for r in candidates
                                   if r['producto'] == p and r['etiqueta_reportada_A'] == c})
                        for c in LABELS} for p in PRODUCTS}
    provenance['piezas_con_etiqueta_A'] = len({r['pieza_id_ag055'] for r in candidates})
    provenance['vistas_inventario'] = len(inventory)
    provenance['vistas_con_etiqueta_A'] = len(candidates)
    provenance['distribucion_reportada_A_por_pieza'] = distribution
    provenance['revision_A_es_revision_B'] = False
    provenance['doble_concordancia_verificada'] = False
    provenance['licencias_y_rubricas_aprobadas_por_software'] = False
    return inventory, candidates, provenance, source_rows



def _private_output(output: Path) -> None:
    if output.exists():
        raise DatasetError('Directorio de salida existente: no se sobrescribe')
    root = Path(__file__).resolve().parents[2]
    if (root / '.git').exists() and output.resolve().is_relative_to(root.resolve()):
        raise DatasetError('No guardar dataset ni revisiones privadas dentro del repositorio')
    if not output.parent.is_dir():
        raise DatasetError('Primero crea la carpeta padre fuera de Git')


@contextmanager
def _workspace_temporal(prefix: str, parent: Path):
    """Temporales efímeros: en Windows heredar ACL si 0o700 produce WinError 5.

    CPython 3.13 aplica una DACL especial a mode=0o700. En algunos Windows
    tempfile.TemporaryDirectory falla en un directorio padre escribible.
    No relaja _private_output: el inventario real sigue fuera del repositorio.
    """
    try:
        temporary = tempfile.TemporaryDirectory(prefix=prefix, dir=parent)
    except PermissionError:
        if os.name != 'nt':
            raise
        # Nombres aleatorios no predecibles; mkdir exclusivo y ACL heredada
        # de la carpeta privada del usuario, sin alterar permisos del sistema.
        for _ in range(16):
            candidate = parent / (prefix + secrets.token_hex(16))
            try:
                candidate.mkdir(mode=0o777, exist_ok=False)
            except FileExistsError:
                continue
            try:
                yield str(candidate)
            finally:
                shutil.rmtree(candidate)
            return
        raise DatasetError('No se pudo reservar directorio temporal único')
    else:
        with temporary as path:
            yield path


def inventariar(universe_csv: Path, images_root: Path, return_zip: Path, output: Path) -> dict:
    _private_output(output)
    # Se valida antes de crear la salida final. El temporal siempre se elimina.
    with _workspace_temporal(prefix='ag055-lectura-', parent=output.parent) as temp:
        tmp = Path(temp)
        supports = tmp / 'soportes'
        supports.mkdir()
        inventory, candidates, provenance, _ = _make_inventory(
            universe_csv, images_root, return_zip, supports)
        with _workspace_temporal(prefix='.ag055-i02-', parent=output.parent) as work:
            staging = Path(work) / 'dataset'
            staging.mkdir()
            evidence_dir = staging / 'soportes' / 'AG036_A'
            shutil.copytree(supports, evidence_dir, ignore=shutil.ignore_patterns('revision_A_temporal.csv'))
            # La revisión temporal está fuera del directorio de soportes.
            write_rows(staging / 'AG055_I02_inventario.csv', INVENTORY_FIELDS, inventory)
            write_rows(staging / 'AG055_I02_fichas_verificacion.csv', FIELDS, candidates)
            manifest = {
                'version': VERSION,
                'universo_csv': str(universe_csv.resolve()),
                'raiz_imagenes': str(images_root.resolve()),
                'devolucion_A_zip': str(return_zip.resolve()),
                'sha256_universo': provenance['sha256_universo'],
                'sha256_devolucion': provenance['sha256_devolucion'],
                'total_vistas': provenance['vistas_inventario'],
                'total_fichas': len(candidates),
                'verificacion_externa_automatica': False,
            }
            write_json(staging / 'AG055_I02_fuentes.json', manifest)
            write_json(staging / 'AG055_I02_resumen_inicial.json', {
                **provenance,
                'estado': 'preparado_para_verificacion_no_entrenable_por_defecto',
                'filas_elegibles_confirmadas': 0,
                'nota': 'Etiquetas A conservadas; ROI/licencia/identidad/rúbrica pendientes. No inferir E0/E1/E2.',
            })
            output.parent.mkdir(parents=True, exist_ok=True)
            os.rename(staging, output)
    return provenance


def _reviewed_file(root: Path, name: str, reasons: list[str]) -> bool:
    try:
        safe_file(root, name, 4 * 1024 * 1024)
        return True
    except (DatasetError, OSError, ValueError):
        reasons.append('soporte_no_disponible_o_inseguro')
        return False


def _qualify(row: dict, images: Path, supports: Path) -> tuple[list[str], dict | None]:
    reasons: list[str] = []
    if row['estado_revision_A'] != 'etiquetada' or row['etiqueta_reportada_A'] not in LABELS:
        reasons.append('sin_etiqueta_A_de_revisor')
    if row['producto'] == 'mango' and row['variedad_declarada'].casefold() != 'kent':
        reasons.append('no_es_mango_Kent_declarado')
    if row['formato_detectado'] not in ('JPEG', 'PNG'):
        reasons.append('formato_no_admitido_AG034_' + row['formato_detectado'])
    roi = None
    if row['roi_verificada'] != 'si':
        reasons.append('roi_no_verificada')
    else:
        try:
            roi = json.loads(row['roi_xywh'])
            if not isinstance(roi, list) or len(roi) != 4 or any(type(x) is not int for x in roi):
                raise ValueError('ROI inválida')
            x, y, w, h = roi
            if min(x, y) < 0 or min(w, h) <= 0 or x + w > int(row['ancho_orientado_px']) or y + h > int(row['alto_orientado_px']):
                raise ValueError('ROI fuera del encuadre')
        except (ValueError, TypeError, json.JSONDecodeError):
            reasons.append('roi_invalida_o_fuera_de_encuadre')
    if row['derechos_uso'] != 'permitido':
        reasons.append('licencia_o_uso_pendiente')
    else:
        _reviewed_file(supports, row['soporte_derechos_relativo'], reasons)
    if row['identidad_sesion_verificada'] != 'si':
        reasons.append('identidad_sesion_sin_respaldo')
    else:
        _reviewed_file(supports, row['soporte_identidad_sesion_relativo'], reasons)
    if row['rubrica_aprobada'] != 'si':
        reasons.append('rubrica_pendiente_de_aprobacion')
    else:
        _reviewed_file(supports, row['soporte_rubrica_relativo'], reasons)
    if row['producto'] == 'mango':
        if row['variedad_verificada'] != 'si':
            reasons.append('Kent_sin_evidencia_de_variedad')
        else:
            _reviewed_file(supports, row['soporte_variedad_relativo'], reasons)
    if row['soporte_revision_A_relativo']:
        _reviewed_file(supports, row['soporte_revision_A_relativo'], reasons)
    else:
        reasons.append('sin_soporte_de_etiqueta_original')
    if not reasons and roi is not None:
        try:
            raw = safe_file(images, row['imagen_relativa']).read_bytes()
            if sha256_bytes(raw) != row['sha256_imagen']:
                raise DatasetError('SHA de imagen no coincide')
            _features(raw, json.dumps(roi))  # prueba de compatibilidad exacta con AG-034
        except (QualityError, DatasetError, ValueError, OSError):
            reasons.append('no_se_pueden_extraer_caracteristicas_AG034')
    if reasons:
        return sorted(set(reasons)), None
    return [], {
        'producto': row['producto'], 'variedad_declarada': row['variedad_declarada'],
        'pieza_id': row['pieza_id_ag055'], 'sesion_id': row['sesion_id_ag055'],
        'imagen_relativa': row['imagen_relativa'], 'sha256_imagen': row['sha256_imagen'],
        'roi_xywh': json.dumps(roi, separators=(',', ':')),
        'roi_verificada': 'si', 'estado_revision': 'etiquetada',
        'etiqueta_e0_e1_e2': row['etiqueta_reportada_A'],
        'revisor_id': row['revisor_id_A'], 'fecha_revision_iso': row['fecha_revision_A'],
        'rubrica_version': row['rubrica_version'],
        'soporte_revision_relativo': row['soporte_revision_A_relativo'],
        'soporte_identidad_sesion_relativo': row['soporte_identidad_sesion_relativo'],
    }


def consolidar(prep_dir: Path, output: Path) -> dict:
    _private_output(output)
    manifest_path = prep_dir / 'AG055_I02_fuentes.json'
    if not manifest_path.is_file() or manifest_path.stat().st_size > MAX_SRC_JSON:
        raise DatasetError('Manifiesto de fuentes ausente/inválido')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('version') != VERSION:
        raise DatasetError('Versión de manifiesto incompatible')
    universe, images, returned = (
        Path(manifest[k]) for k in ('universo_csv', 'raiz_imagenes', 'devolucion_A_zip'))
    if sha256_file(universe) != manifest['sha256_universo'] or sha256_file(returned) != manifest['sha256_devolucion']:
        raise DatasetError('Una fuente cambió después del inventario')
    supports = prep_dir / 'soportes'
    if not supports.is_dir():
        raise DatasetError('No existe carpeta de soportes del inventario')
    with _workspace_temporal(prefix='ag055-verificar-', parent=output.parent) as td:
        tmp = Path(td) / 'A'
        tmp.mkdir()
        _, expected, provenance, _ = _make_inventory(universe, images, returned, tmp)
        # Confirma que los respaldos originales exportados no fueron sustituidos.
        for row in expected:
            name = row['soporte_revision_A_relativo']
            if not name:
                continue
            original = safe_file(tmp, name[len('AG036_A/'):], 4 * 1024 * 1024)
            persisted = safe_file(supports, name, 4 * 1024 * 1024)
            if sha256_file(original) != sha256_file(persisted):
                raise DatasetError('El soporte de revisión original fue alterado')
    prepared_rows = read_rows(prep_dir / 'AG055_I02_fichas_verificacion.csv', FIELDS)
    baseline = {r['registro_id']: r for r in expected}
    if len(prepared_rows) != len(expected) or {r['registro_id'] for r in prepared_rows} != set(baseline):
        raise DatasetError('Se añadieron, eliminaron o duplicaron fichas')
    if len({r['registro_id'] for r in prepared_rows}) != len(prepared_rows):
        raise DatasetError('Fichas duplicadas')
    for row in prepared_rows:
        orig = baseline[row['registro_id']]
        if any(row[key] != orig[key] for key in LOCKED):
            raise DatasetError('Campo de fuente o etiqueta humana alterado en registro ' + row['registro_id'][:10])
    eligible: list[dict] = []
    rejected: list[dict] = []
    reasons_counter = Counter()
    seen_eligible_sha = set()
    for row in sorted(prepared_rows, key=lambda r: r['registro_id']):
        reasons, item = _qualify(row, images, supports)
        if item:
            # Una copia byte-idéntica no se contabiliza dos veces en la pieza.
            key = (item['producto'], item['pieza_id'], item['sha256_imagen'])
            if key in seen_eligible_sha:
                reasons, item = ['vista_duplicada_por_SHA256'], None
            else:
                seen_eligible_sha.add(key)
        if item:
            eligible.append(item)
        else:
            reasons_counter.update(reasons)
            rejected.append({'registro_id': row['registro_id'], 'producto': row['producto'],
                             'pieza_id_ag055': row['pieza_id_ag055'],
                             'etiqueta_reportada_A': row['etiqueta_reportada_A'],
                             'motivos_exclusion': '|'.join(reasons)})
    rubrics = {p: set(r['rubrica_version'] for r in eligible if r['producto'] == p) for p in PRODUCTS}
    for p in PRODUCTS:
        if len(rubrics[p]) > 1:
            raise DatasetError('Varias versiones de rúbrica en los datos elegibles de ' + p)
    report: dict[str, Any] = {
        'version': VERSION, 'estado': 'consolidacion_auditada_sin_autorizacion_productiva',
        'datos_reportados_AG036': provenance['distribucion_reportada_A_por_pieza'],
        'vistas_inventariadas': provenance['vistas_inventario'],
        'piezas_reportadas_A': provenance['piezas_con_etiqueta_A'],
        'vistas_propuestas_A': len(prepared_rows),
        'vistas_elegibles_AG034': len(eligible),
        'piezas_elegibles_AG034': len({(r['producto'], r['pieza_id']) for r in eligible}),
        'vistas_pendientes_o_excluidas': len(rejected),
        'motivos_exclusion_por_vista': dict(sorted(reasons_counter.items())),
        'productos': {},
        'revisor_B_independiente_acreditado': False,
        'licencias_autenticadas_por_software': False,
        'rubricas_aprobadas_autenticadas_por_software': False,
        'modelo_entrenado': False, 'despliegue_automatico_autorizado': False,
    }
    if eligible:
        # Validación final contra el mismo parser que consume el entrenador I01.
        with _workspace_temporal(prefix='ag055-csv-', parent=output.parent) as td:
            temp_csv = Path(td) / 'AG034.csv'
            write_rows(temp_csv, AG034_COLUMNS, eligible)
            valid, _ = load_eligible(temp_csv, images, supports)
        pieces = aggregate_pieces(valid)
    else:
        pieces = []
    for product in PRODUCTS:
        subset = [r for r in pieces if r['producto'] == product]
        groups = connected_groups(subset)
        counts = {g: sum(any(r['y'] == g for r in group) for group in groups) for g in LABELS}
        _, issue = split_groups(groups, seed=55)
        report['productos'][product] = {
            'piezas_elegibles': len(subset),
            'grupos_independientes': len(groups),
            'grupos_independientes_por_grado': counts,
            'minimo_exploratorio_por_grado': 5,
            'faltantes_minimos_por_grado': {g: max(0, 5 - counts[g]) for g in LABELS},
            'estado_particion': 'bloqueado' if issue else 'estructura_compatible_no_acreditada',
            'motivo_particion': issue,
        }
    with _workspace_temporal(prefix='.ag055-i02-', parent=output.parent) as work:
        stage = Path(work) / 'consolidacion'
        stage.mkdir()
        write_rows(stage / 'AG055_I02_etiquetas_elegibles_AG034.csv', AG034_COLUMNS, eligible)
        write_rows(stage / 'AG055_I02_exclusiones.csv', REJECTIONS, rejected)
        write_json(stage / 'AG055_I02_resumen_consolidado.json', report)
        lines = [
            '# AG-055 / AGROP-67 — Consolidación del dataset real (I02)', '',
            'Esta evaluación audita datos entregados, sin inventar etiquetas ni certificar origen externo.', '',
            f'- Fotografías inventariadas de AG-036: **{report["vistas_inventariadas"]}**.',
            f'- Piezas con etiqueta reportada por A: **{report["piezas_reportadas_A"]}**.',
            f'- Vistas elegibles con evidencia adicional declarada: **{len(eligible)}**.',
            f'- Piezas elegibles para evaluación experimental: **{report["piezas_elegibles_AG034"]}**.',
            '', '| Producto | E0 grupos | E1 grupos | E2 grupos | Estado |',
            '|---|---:|---:|---:|---|',
        ]
        for p in PRODUCTS:
            rec = report['productos'][p]
            c = rec['grupos_independientes_por_grado']
            lines.append(f'| {p} | {c["E0"]} | {c["E1"]} | {c["E2"]} | {rec["estado_particion"]} |')
        lines += [
            '', '## Interpretación metodológica',
            '- E0/E1/E2 provienen de una sola revisión A: no representan concordancia A/B.',
            '- Una misma pieza con varias vistas cuenta una sola vez; sesiones compartidas no se dividen entre splits.',
            '- Las fotografías MPO no son automáticamente JPG/PNG para AG-034; requieren transformación declarada y nuevo SHA.',
            '- Cada afirmación manual de licencia, ROI, variedad o rúbrica necesita archivo soporte. Su autenticidad no la certifica el script.',
            '- El CSV elegible es únicamente un insumo experimental; ejecutar el entrenador I01 no implica validación para producción.',
            '- No subir fotografías, etiquetas privadas, soportes ni identificadores de revisores a GitHub.',
        ]
        (stage / 'AG055_I02_informe.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        os.rename(stage, output)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='AG-055 Incremento 02: dataset real sin etiquetas inventadas')
    subs = ap.add_subparsers(dest='accion', required=True)
    a = subs.add_parser('inventariar', help='Conserva revisión A y prepara fichas sin marcar ROI verificada')
    a.add_argument('--universo', type=Path, required=True)
    a.add_argument('--imagenes', type=Path, required=True)
    a.add_argument('--devolucion-a', type=Path, required=True)
    a.add_argument('--salida-dir', type=Path, required=True)
    b = subs.add_parser('consolidar', help='Audita fichas completadas y produce CSV elegible AG-034')
    b.add_argument('--preparacion', type=Path, required=True)
    b.add_argument('--salida-dir', type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        if args.accion == 'inventariar':
            report = inventariar(args.universo, args.imagenes, args.devolucion_a, args.salida_dir)
            print('AG055 I02 INVENTARIO OK:', report['vistas_inventario'], 'vistas,',
                  report['piezas_con_etiqueta_A'], 'piezas con etiqueta A (NO elegibles automáticamente).')
        else:
            report = consolidar(args.preparacion, args.salida_dir)
            print('AG055 I02 CONSOLIDACIÓN OK:', report['piezas_elegibles_AG034'],
                  'piezas elegibles; modelo autorizado: NO.')
        return 0
    except (DatasetError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print('AG055 I02 ERROR:', str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
