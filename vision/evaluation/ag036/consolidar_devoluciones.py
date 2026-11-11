"""AG-036 / Incremento 03: recepción y auditoría de fichas A/B sin inventar etiquetas.

Consume las entregas originales selladas del Incremento 02 y las carpetas
privadas devueltas por ambos revisores. Conserva CSV originales, separa
soportes por revisor y llama al auditor de concordancia existente.

No demuestra identidad/independencia de revisores ni aprobación de rúbricas.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .auditar_etiquetado import (
    AuditError, MAX_CSV, MAX_IMAGE, REVIEW_COLS, UNIVERSE_COLS, audit, load_csv,
    load_universe, markdown, safe_file,
)

VERSION = 'ag036-recepcion-doble-v1'
LOCKED = ('producto', 'lote_id', 'pieza_id', 'rubrica_version')
EDITABLE = tuple(c for c in REVIEW_COLS if c not in LOCKED)
MAX_JSON = 4 * 1024 * 1024


def _digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _file_digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def _read_json(path: Path) -> dict:
    blob = path.read_bytes()
    if not blob or len(blob) > MAX_JSON:
        raise AuditError('Acta de preparación vacía o excesiva')
    try:
        data = json.loads(blob)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuditError('Acta de preparación ilegible') from exc
    if not isinstance(data, dict):
        raise AuditError('Formato de acta no admitido')
    return data


def _zip_ficha(path: Path, slot: str, hash_esperado: str,
               expected_images: dict[str, str]) -> tuple[dict, list[dict]]:
    if not path.is_file():
        raise AuditError(f'Paquete {slot}: archivo ausente')
    if _file_digest(path) != hash_esperado:
        raise AuditError(f'Paquete {slot}: SHA256 distinto del acta original')
    try:
        with zipfile.ZipFile(path) as archive:
            # Ningún archivo se extrae: se comprueban los hashes de las vistas
            # originales contra el universo, incluso si se alteró el acta.
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise AuditError(f'Paquete {slot}: entradas ZIP duplicadas')
            images_in_zip = {name for name in names if name.startswith('imagenes/') and not name.endswith('/')}
            if images_in_zip != set(expected_images):
                raise AuditError(f'Paquete {slot}: fotografías distintas del universo')
            for name, sha in expected_images.items():
                if archive.getinfo(name).file_size > MAX_IMAGE:
                    raise AuditError(f'Paquete {slot}: foto demasiado grande: {name}')
                digest = hashlib.sha256()
                with archive.open(name) as image:
                    for chunk in iter(lambda: image.read(1024 * 1024), b''):
                        digest.update(chunk)
                if digest.hexdigest() != sha:
                    raise AuditError(f'Paquete {slot}: foto alterada: {name}')
            info_csv = archive.getinfo(f'revision_{slot}.csv')
            info_manifest = archive.getinfo('inventario_vistas.json')
            if info_csv.file_size > MAX_CSV or info_manifest.file_size > MAX_JSON:
                raise AuditError(f'Paquete {slot}: ficha o inventario demasiado grande')
            blob = archive.read(info_csv)
            manifest = json.loads(archive.read(info_manifest))
    except (OSError, KeyError, zipfile.BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError(f'Paquete {slot}: estructura original inválida') from exc
    if not isinstance(manifest, dict):
        raise AuditError(f'Paquete {slot}: inventario inválido')
    try:
        reader = csv.DictReader(io.StringIO(blob.decode('utf-8-sig'), newline=''), strict=True)
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)) or set(reader.fieldnames) != set(REVIEW_COLS):
            raise AuditError(f'Paquete {slot}: encabezados originales inválidos')
        rows = list(reader)
        if any(None in r or any(v is None for v in r.values()) for r in rows):
            raise AuditError(f'Paquete {slot}: CSV original malformado')
        return manifest, [{k: v.strip() for k, v in r.items()} for r in rows]
    except (UnicodeError, csv.Error) as exc:
        raise AuditError(f'Paquete {slot}: CSV original ilegible') from exc


def _key(row: dict) -> tuple[str, str, str]:
    return row['producto'], row['lote_id'], row['pieza_id']


def _expected_manifest(universe: dict) -> dict:
    selected = {}
    for key, data in universe.items():
        if data['elegible'] and data['seleccion_doble'] == 'si':
            selected[key] = data['rubrica_version']
    if not selected:
        raise AuditError('No existe subconjunto elegible seleccionado')
    return selected


def _support_name(value: str) -> str:
    if not value or '\\' in value or ':' in value:
        raise AuditError('Soporte: ruta insegura')
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in ('', '.', '..') for x in p.parts):
        raise AuditError('Soporte: ruta insegura')
    parts = p.parts[1:] if p.parts[0] == 'soportes' else p.parts
    if not parts:
        raise AuditError('Soporte: ruta vacía')
    return '/'.join(parts)


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_COLS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def _consume_return(slot: str, original: list[dict], received: Path, staging: Path) -> dict:
    path = received / f'revision_{slot}.csv'
    if not received.is_dir() or path.is_symlink():
        raise AuditError(f'Revisor {slot}: carpeta o CSV no permitido')
    rows, sha = load_csv(path, REVIEW_COLS)
    expected = {_key(r): r for r in original}
    if len(expected) != len(original):
        raise AuditError(f'Paquete {slot}: piezas duplicadas en la ficha original')
    actual = {_key(r): r for r in rows}
    if len(actual) != len(rows) or set(actual) != set(expected):
        raise AuditError(f'Revisor {slot}: se cambiaron, eliminaron o duplicaron piezas')
    supports_copied: dict[str, str] = {}
    normalized = []
    pending = 0
    for key in sorted(expected):
        row = actual[key]
        if any(row[c] != expected[key][c] for c in LOCKED):
            raise AuditError(f'Revisor {slot}: modificó los campos bloqueados de {key}')
        # La ficha recién creada tiene campos humanos vacíos. No asignar etiquetas
        # ni fechas a las filas que el revisor no llegó a completar.
        if all(not row[c] for c in EDITABLE):
            pending += 1
            continue
        target = dict(row)
        if row['soporte_relativo']:
            sub = _support_name(row['soporte_relativo'])
            blob, digest = safe_file(received / 'soportes', sub, MAX_CSV)
            normalized_name = f'{slot}/{sub}'
            if sub in supports_copied:
                if supports_copied[sub] != digest:
                    raise AuditError(f'Revisor {slot}: soporte con contenido inconsistente')
            else:
                destination = staging / 'soportes' / slot / Path(*PurePosixPath(sub).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(blob)
                supports_copied[sub] = digest
            target['soporte_relativo'] = normalized_name
        normalized.append(target)
    original_dir = staging / 'originales' / slot
    original_dir.mkdir(parents=True, exist_ok=True)
    (original_dir / path.name).write_bytes(path.read_bytes())
    _write_csv(staging / 'normalizados' / path.name, normalized)
    return {'sha256_csv_recibido': sha, 'filas_originales': len(rows),
            'filas_con_registro': len(normalized), 'filas_sin_completar': pending,
            'soportes_sha256': supports_copied}


def consolidate(preparation: Path, universe_csv: Path, images_root: Path,
                return_a: Path, return_b: Path, output_dir: Path) -> dict:
    """Consolida solo si hay integridad verificable, sin sobrescribir resultados."""
    repo = Path(__file__).resolve().parents[3]
    destination = output_dir.resolve()
    if destination == repo or destination.is_relative_to(repo):
        raise AuditError('La salida con datos humanos debe estar fuera de Git')
    if output_dir.exists():
        raise AuditError('El directorio de consolidación ya existe; no sobrescribir')
    if return_a.resolve() == return_b.resolve():
        raise AuditError('Las devoluciones A y B deben ser carpetas diferentes')
    inputs = (preparation, images_root, return_a, return_b)
    if any(destination == p.resolve() or p.resolve().is_relative_to(destination) for p in inputs):
        raise AuditError('La salida no puede contener las entradas')

    act = _read_json(preparation / 'AG036_acta_preparacion.json')
    expected_hashes = act.get('sha256_zips')
    if not isinstance(expected_hashes, dict) or any(not isinstance(expected_hashes.get(s), str) or len(expected_hashes[s]) != 64 for s in ('A', 'B')):
        raise AuditError('Acta sin hashes verificables de ambos paquetes')
    universe, metadata = load_universe(universe_csv, images_root)
    if act.get('sha256_universo_csv') != metadata['sha256']:
        raise AuditError('El universo fue cambiado después de preparar las revisiones')
    selected = _expected_manifest(universe)
    rows, _ = load_csv(universe_csv, UNIVERSE_COLS)
    expected_images = {}
    expected_fichas = {}
    for key, item in sorted(universe.items()):
        if key not in selected:
            continue
        expected_fichas[key] = {
            'producto': key[0], 'lote_id': key[1], 'pieza_id': key[2],
            'variedad_declarada': item['variedad_declarada'],
            'rubrica_version': item['rubrica_version'],
            'criterio_seleccion': item['criterio_seleccion'],
            'imagenes': [],
        }
    for row in rows:
        key = _key(row)
        if key in selected:
            name = 'imagenes/' + row['imagen_relativa']
            if name in expected_images:
                raise AuditError('Rutas de fotografía repetidas en el subconjunto')
            expected_images[name] = row['sha256_imagen'].lower()
            if row['criterio_seleccion'] != expected_fichas[key]['criterio_seleccion']:
                raise AuditError('Criterio de selección contradictorio entre vistas de la pieza')
            expected_fichas[key]['imagenes'].append({
                'imagen_relativa': row['imagen_relativa'],
                'sha256_imagen': row['sha256_imagen'].lower(),
                'sesion_id': row['sesion_id'],
            })
    for ficha in expected_fichas.values():
        ficha['imagenes'].sort(key=lambda x: x['imagen_relativa'])
    if act.get('fichas') != list(expected_fichas.values()):
        raise AuditError('Acta: asociación imagen/pieza o selección distinta del universo')
    if act.get('fotos_incluidas') != len(expected_images):
        raise AuditError('Acta no coincide con las vistas seleccionadas')
    if act.get('piezas_seleccionadas') != len(selected):
        raise AuditError('Acta no coincide con las piezas seleccionadas')
    sealed = {}
    for slot in ('A', 'B'):
        manifest, original = _zip_ficha(
            preparation / f'AG036_Revisor_{slot}.zip', slot, expected_hashes[slot], expected_images)
        if manifest.get('sha256_universo_csv') != metadata['sha256']:
            raise AuditError(f'Paquete {slot}: manifiesto con universo distinto')
        if manifest.get('fichas') != act.get('fichas'):
            raise AuditError(f'Paquete {slot}: manifiesto distinto del acta')
        if manifest.get('piezas_seleccionadas') != len(selected):
            raise AuditError(f'Paquete {slot}: número de piezas inconsistente')
        if {_key(r): r['rubrica_version'] for r in original} != selected or len(original) != len(selected):
            raise AuditError(f'Paquete {slot}: listado de piezas distinto al universo')
        if any(any(r[c] for c in EDITABLE) for r in original):
            raise AuditError(f'Paquete {slot}: plantilla original ya tenía evaluaciones')
        sealed[slot] = original

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ag036-consolidar-', dir=output_dir.parent) as temporary:
        temp = Path(temporary)
        records = {
            'A': _consume_return('A', sealed['A'], return_a, temp),
            'B': _consume_return('B', sealed['B'], return_b, temp),
        }
        report = audit(
            universe_csv, temp / 'normalizados' / 'revision_A.csv',
            temp / 'normalizados' / 'revision_B.csv',
            images_root, temp / 'soportes', None,
        )
        (temp / 'AG036_auditoria.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (temp / 'AG036_auditoria.md').write_text(markdown(report), encoding='utf-8')
        receipt = {
            'version': VERSION,
            'fecha_consolidacion_utc': datetime.now(timezone.utc).isoformat(),
            'sha256_universo_csv': metadata['sha256'],
            'sha256_acta_preparacion': _digest((preparation / 'AG036_acta_preparacion.json').read_bytes()),
            'sha256_paquetes_originales': expected_hashes,
            'devoluciones': records,
            'resultado': {p: {
                'pares_con_dos_grados': d['pares_con_dos_grados'],
                'discrepancias': d['discrepancias'],
                'pares_incompletos': d['pares_incompletos'],
            } for p, d in report['por_producto'].items()},
            'autenticidad_e_independencia_humana_verificadas': False,
            'aprobacion_de_rubricas_verificada': False,
            'cierre_total_AG036_acreditado': False,
            'advertencia': 'Verifica integridad y coherencia declarada, no competencia ni independencia humana.',
        }
        (temp / 'AG036_acta_recepcion.json').write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.rename(temp, output_dir)
    return {'estado': 'devoluciones_consolidadas_cierre_pendiente',
            'salida': str(output_dir), 'filas_A': records['A']['filas_con_registro'],
            'filas_B': records['B']['filas_con_registro'],
            'piezas_sin_revisar_A': records['A']['filas_sin_completar'],
            'piezas_sin_revisar_B': records['B']['filas_sin_completar'],
            'cierre_total_AG036_acreditado': False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('preparacion', 'universo', 'raiz-imagenes', 'devolucion-a', 'devolucion-b', 'directorio-salida'):
        parser.add_argument('--' + arg, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = consolidate(args.preparacion, args.universo, args.raiz_imagenes,
                             args.devolucion_a, args.devolucion_b, args.directorio_salida)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (AuditError, OSError, ValueError) as exc:
        print(json.dumps({'estado': 'error_de_recepcion', 'detalle': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
