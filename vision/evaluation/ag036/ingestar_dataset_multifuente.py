"""AG-036 incremento 04: ingesta verificable de imágenes de distintas procedencias.

Inventario técnico solamente: NO acredita identificación de piezas, licencias,
variedades o etiquetas E0/E1/E2. No mezcla capturas propias con datasets externos.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

from PIL import Image, UnidentifiedImageError

IMAGES = {'.jpg', '.jpeg', '.png'}
MAX_ENTRY = 12 * 1024 * 1024
MAX_TOTAL = 1500 * 1024 * 1024
MAX_FILES = 15000
INVENTORY_FIELDS = (
    'fuente', 'producto_candidato', 'grupo_candidato', 'ruta_relativa',
    'sha256_imagen', 'ancho_px', 'alto_px', 'advertencia_resolucion',
    'id_captura_en_nombre', 'variedad_tipo_en_nombre', 'identidad_pieza_confirmada',
    'licencia_y_procedencia_verificadas', 'estado_uso', 'etiqueta_e0_e1_e2',
)
GROUP_FIELDS = (
    'fuente', 'producto_candidato', 'grupo_candidato', 'fotografias',
    'codigos_captura_distintos', 'codigos_captura', 'imagenes_con_dimension_menor_224',
    'pieza_fisica_confirmada', 'variedad_o_tipo_confirmado',
    'licencia_y_procedencia_verificadas', 'etiquetado_doble_completado',
    'estado', 'observacion',
)
UNIVERSE_FIELDS = (
    'producto', 'variedad_declarada', 'lote_id', 'pieza_id', 'sesion_id',
    'imagen_relativa', 'sha256_imagen', 'rubrica_version',
    'seleccion_doble', 'criterio_seleccion',
)


class IngestionError(ValueError):
    pass


def _write_csv(path: Path, fields, rows: list[dict]) -> None:
    with path.open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def _safe_path(name: str) -> tuple[str, ...]:
    if ('\\' in name or ':' in name or '\x00' in name or not name):
        raise IngestionError(f'ZIP contiene ruta inválida: {name!r}')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:
        raise IngestionError(f'ZIP contiene ruta insegura: {name!r}')
    return path.parts


def _source(parts: tuple[str, ...]):
    # Strip one container root if the archive is distributed inside a folder.
    if parts and parts[0] == 'AgroScan_Imagenes_Revisadas':
        parts = parts[1:]
    if len(parts) < 4:
        raise IngestionError('Ruta de imagen sin procedencia/grupo identificable')
    folder, subcategory, group = parts[:3]
    if folder == '01_ZIP_Capturas_reales':
        source = 'captura_proyecto_declarada'
        product = 'mango' if subcategory == 'Mango_variedad_pendiente' else ('tomate' if subcategory == 'Tomate_tipo_pendiente' else None)
        variety = ''
    elif folder == '02_Datasets_externos':
        source = 'dataset_externo_declarado'
        product = 'mango' if subcategory == 'Mango_Kent_COFiLAB_dos_vistas' else ('tomate' if subcategory == 'Tomate_Cherry_Rojo_Fruits360' else None)
        variety = 'Kent (solo carpeta)' if product == 'mango' else ('Cherry Red (solo carpeta)' if product == 'tomate' else '')
    else:
        raise IngestionError(f'Procedencia no reconocida: {folder}')
    if product is None:
        raise IngestionError(f'Subcategoría no reconocida: {subcategory}')
    return parts, source, product, group, variety


def ingest(source_zip: Path, output_dir: Path) -> dict:
    if not source_zip.is_file():
        raise IngestionError('ZIP de entrada no encontrado')
    if output_dir.exists():
        raise IngestionError('La carpeta de salida ya existe: no sobrescribir')
    if output_dir.resolve() == source_zip.resolve():
        raise IngestionError('Entrada y salida coinciden')
    # Si este script está dentro del repositorio, impide introducir fotos en Git.
    repo = Path(__file__).resolve().parents[3]
    if (repo / '.git').exists() and output_dir.resolve().is_relative_to(repo):
        raise IngestionError('La carpeta con fotografías debe estar fuera del repositorio')

    inventory, groups = [], defaultdict(list)
    sha_owners = defaultdict(list)
    total = 0
    names = set()
    source_sha = hashlib.sha256(source_zip.read_bytes()).hexdigest()
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(source_zip) as archive, tempfile.TemporaryDirectory(
        prefix='ag036-ingesta-', dir=output_dir.parent
    ) as staging_path:
        staging = Path(staging_path)
        images_root = staging / 'imagenes'
        images_root.mkdir()
        for info in archive.infolist():
            if info.is_dir():
                continue
            parts = _safe_path(info.filename)
            if not parts or PurePosixPath(parts[-1]).suffix.lower() not in IMAGES:
                raise IngestionError(f'ZIP incluye archivo no fotográfico: {info.filename}')
            if len(names) >= MAX_FILES or info.file_size > MAX_ENTRY or info.file_size == 0:
                raise IngestionError('Imagen vacía o límites de volumen excedidos')
            total += info.file_size
            if total > MAX_TOTAL:
                raise IngestionError('Archivo descomprimido excede límite de seguridad')
            parts, source, product, group, variety = _source(parts)
            rel = PurePosixPath(*parts).as_posix()
            if rel.casefold() in names:
                raise IngestionError(f'Ruta duplicada: {rel}')
            names.add(rel.casefold())
            # Rechaza enlaces simbólicos (modo UNIX en ZIP).
            unix_mode = (info.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise IngestionError('ZIP contiene enlace simbólico')
            with archive.open(info) as reader:
                data = reader.read(MAX_ENTRY + 1)
            if len(data) != info.file_size or len(data) > MAX_ENTRY:
                raise IngestionError(f'Volumen real de imagen inválido: {rel}')
            try:
                with Image.open(io.BytesIO(data)) as photo:
                    w, h = photo.size
                    if photo.format not in ('JPEG', 'PNG') or w*h > 16_000_000:
                        raise IngestionError(f'Formato o dimensiones inválidas: {rel}')
                    photo.verify()
            except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
                raise IngestionError(f'Imagen corrupta: {rel}') from exc
            sha = hashlib.sha256(data).hexdigest()
            sha_owners[sha].append(rel)
            dest = images_root.joinpath(*parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            capture = re.match(r'(E-\d+)', parts[-1], re.IGNORECASE)
            row = {
                'fuente': source, 'producto_candidato': product,
                'grupo_candidato': group, 'ruta_relativa': rel,
                'sha256_imagen': sha, 'ancho_px': w, 'alto_px': h,
                'advertencia_resolucion': 'dimension_menor_224' if min(w,h) < 224 else '',
                'id_captura_en_nombre': capture.group(1) if capture else '',
                'variedad_tipo_en_nombre': variety,
                'identidad_pieza_confirmada': 'no',
                'licencia_y_procedencia_verificadas': 'no',
                'estado_uso': 'solo_inventario_y_deteccion_exploratoria',
                'etiqueta_e0_e1_e2': '',
            }
            inventory.append(row)
            groups[(source, product, group)].append(row)

        if not inventory:
            raise IngestionError('ZIP sin fotografías compatibles')
        inventory.sort(key=lambda x: x['ruta_relativa'])
        group_rows = []
        for (source, product, group), items in sorted(groups.items()):
            codes = sorted({i['id_captura_en_nombre'] for i in items if i['id_captura_en_nombre']})
            obs = ('Las capturas con diferentes E-* podrían ser piezas distintas; confirmar identidad.'
                   if len(codes) > 1 else
                   'Carpeta candidata, no equivale necesariamente a pieza física independiente.')
            if source == 'dataset_externo_declarado':
                obs = 'Fuente y licencia del archivo original por verificar; no equivale a ground truth.'
            group_rows.append({
                'fuente': source, 'producto_candidato': product,
                'grupo_candidato': group, 'fotografias': len(items),
                'codigos_captura_distintos': len(codes), 'codigos_captura': ';'.join(codes),
                'imagenes_con_dimension_menor_224': sum(bool(i['advertencia_resolucion']) for i in items),
                'pieza_fisica_confirmada': 'no', 'variedad_o_tipo_confirmado': 'no',
                'licencia_y_procedencia_verificadas': 'no', 'etiquetado_doble_completado': 'no',
                'estado': 'pendiente_validacion_de_grupo_y_procedencia',
                'observacion': obs,
            })
        universe = []
        for row in inventory:
            universe.append(dict(zip(UNIVERSE_FIELDS, (
                row['producto_candidato'], '', '', '', '', row['ruta_relativa'],
                row['sha256_imagen'], '', 'no', '',
            ))))
        _write_csv(staging/'inventario_multifuente.csv', INVENTORY_FIELDS, inventory)
        _write_csv(staging/'grupos_candidatos.csv', GROUP_FIELDS, group_rows)
        _write_csv(staging/'universo_AG036_borrador.csv', UNIVERSE_FIELDS, universe)
        sections = Counter((r['fuente'], r['producto_candidato']) for r in inventory)
        duplicates = {sha: paths for sha, paths in sha_owners.items() if len(paths) > 1}
        report = {
            'actividad': 'AG-036', 'tipo': 'preparacion_multifuente_sin_etiquetas',
            'sha256_zip_original': source_sha, 'fotografias_total': len(inventory),
            'sha256_imagenes_unicos': len(sha_owners),
            'grupos_de_carpetas_candidatos': len(group_rows),
            'fotografias_por_fuente_producto': [
                {'fuente': s, 'producto': p, 'imagenes': n}
                for (s,p),n in sorted(sections.items())],
            'imagenes_con_dimension_menor_224': sum(bool(i['advertencia_resolucion']) for i in inventory),
            'sha256_duplicados': len(duplicates),
            'duplicados_nombres': [paths for paths in duplicates.values()],
            'piezas_fisicas_independientes_acreditadas': 0,
            'etiquetas_e0_e1_e2_acreditadas': 0,
            'aprobado_para_entrenamiento_supervisado': False,
            'cierre_total_AG036_acreditado': False,
            'advertencias': [
                'Los grupos por carpeta son candidatos: una foto no equivale a una pieza independiente.',
                'Las variedades y fuentes que aparecen en las carpetas no acreditan identidad ni licencia.',
                'El universo_AG036_borrador.csv requiere completar manualmente lote, pieza, sesión y rúbrica antes de auditar.',
                'No usar los mismos ejemplares o sesiones en entrenamiento y evaluación final.',
                'No publicar fotografías ni identificadores privados sin verificar autorizaciones.',
            ],
        }
        (staging/'resumen_multifuente.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n',encoding='utf-8')
        (staging/'LEEME_INVENTARIO.md').write_text(
            '# AgroScan | Inventario multifuente\n\n'
            f'Fotografías verificadas: **{len(inventory)}**. Grupos por carpeta: **{len(group_rows)}**. '
            f'Hash repetido: **{len(duplicates)}**.\n\n'
            '1. Revisar `inventario_multifuente.csv` y `grupos_candidatos.csv` SIN borrar fotografías.\n'
            '2. Confirmar que cada `grupo_candidato` corresponde a una pieza física. Si no, separar por lote/pieza real.\n'
            '3. Confirmar identidad de variedad, origen/licencia y versión de rúbrica; no suponer Kent por la carpeta.\n'
            '4. Completar `universo_AG036_borrador.csv` por foto, con misma pieza para sus vistas. '
            'Mantener `seleccion_doble=no` hasta preseleccionar documentalmente.\n'
            '5. Ejecutar el auditor/paquetes de AG-036 solo al contar con el universo verificado.\n'
            '6. Para utilizar todas las fotografías en YOLOE (detección exploratoria), ejecutar '
            '`python -m vision.evaluation.ag036.evaluar_detector_multifuente` sobre este inventario.\n\n'
            'ATENCIÓN: Los resultados de YOLOE no equivalen a E0/E1/E2 ni a precisión validada; '
            'no entrenar un clasificador de calidad con etiquetas faltantes.\n',
            encoding='utf-8',
        )
        os.rename(staging, output_dir)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', dest='source_zip', type=Path, required=True)
    parser.add_argument('--salida-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = ingest(args.source_zip, args.salida_dir)
        print(json.dumps({'estado': 'inventario_generado_sin_etiquetas',
                          'fotografias': report['fotografias_total'],
                          'grupos_candidatos': report['grupos_de_carpetas_candidatos'],
                          'cierre_total_AG036_acreditado': False}, ensure_ascii=False))
        return 0
    except (IngestionError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({'estado': 'error_ingesta', 'detalle': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
