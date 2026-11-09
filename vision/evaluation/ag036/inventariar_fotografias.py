"""AG-036 / Incremento 02: inventario SIN identidad ni etiquetas inferidas.

Registra imágenes JPEG/PNG reales y sus SHA256. Producto, variedad, lote,
pieza, sesión, rúbrica y selección deben documentarse manualmente después.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .auditar_etiquetado import AuditError, UNIVERSE_COLS, MAX_IMAGE, safe_file

SUFFIXES = {'.jpg', '.jpeg', '.png'}


def inventory(images_root: Path, output_csv: Path) -> dict:
    if output_csv.exists():
        raise AuditError('El CSV de salida ya existe; no sobrescribir')
    repo = Path(__file__).resolve().parents[3]
    if output_csv.resolve().is_relative_to(repo):
        raise AuditError('La salida debe estar fuera del repositorio para proteger el inventario')
    if not images_root.is_dir():
        raise AuditError('No existe el directorio de imágenes')
    all_paths = sorted((p for p in images_root.rglob('*') if p.suffix.lower() in SUFFIXES),
                       key=lambda p: p.relative_to(images_root).as_posix())
    if not all_paths:
        raise AuditError('No hay fotografías JPG/PNG para inventariar')
    rows = []
    hashes = set()
    duplicates = 0
    for p in all_paths:
        rel = p.relative_to(images_root).as_posix()
        data, sha = safe_file(images_root, rel, MAX_IMAGE)
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ('JPEG', 'PNG') or image.width * image.height > 16_000_000:
                    raise AuditError('Formato o dimensiones no admitidos: ' + rel)
                image.verify()
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise AuditError('Imagen ilegible: ' + rel) from exc
        row = dict.fromkeys(UNIVERSE_COLS, '')
        row['imagen_relativa'] = rel
        row['sha256_imagen'] = sha
        row['seleccion_doble'] = 'no'  # Por defecto, ninguna pieza está aprobada para selección.
        rows.append(row)
        if sha in hashes:
            duplicates += 1
        hashes.add(sha)
    # Solo escribe una vez superadas todas las verificaciones, sin inventar atributos.
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open('x', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=UNIVERSE_COLS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    return {'estado': 'inventario_sin_atributos_humanos', 'fotografias': len(rows),
            'imagenes_contenido_repetido': duplicates, 'csv': str(output_csv),
            'identidad_producto_variedad_pieza_acreditada': False,
            'seleccion_doble_confirmada': False, 'cierre_total_AG036_acreditado': False}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directorio-imagenes', type=Path, required=True)
    p.add_argument('--salida-csv', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        print(json.dumps(inventory(args.directorio_imagenes, args.salida_csv), ensure_ascii=False, indent=2))
        return 0
    except (AuditError, OSError) as exc:
        print(json.dumps({'estado': 'error_de_inventario', 'detalle': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
