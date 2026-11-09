"""AG-036 / Incremento 02: preparar dos paquetes CIEGOS de revisión humana.

No asigna etiquetas, no comprueba identidad humana, no ejecuta inferencia y no
sube fotografías a GitHub. Solo empaqueta piezas previamente seleccionadas,
tras verificar fotografías y SHA256 usando el auditor AG-036 existente.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import os
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from .auditar_etiquetado import (
    AuditError, REVIEW_COLS, UNIVERSE_COLS, load_csv, load_universe, safe_file,
    MAX_IMAGE,
)

VERSION = 'ag036-preparacion-ciega-v1'


def _csv_bytes(columns: tuple[str, ...], rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator='\n', extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode('utf-8-sig')


def _image_archive_name(relative: str) -> str:
    if not relative or '\\' in relative or ':' in relative:
        raise AuditError('Ruta inválida para paquete de revisión')
    rel = PurePosixPath(relative)
    if rel.is_absolute() or any(part in ('..', '.', '') for part in rel.parts):
        raise AuditError('Ruta insegura para archivo comprimido')
    return 'imagenes/' + rel.as_posix()


def _viewer(pieces: list[dict], slot: str) -> bytes:
    lines = [
        '<!doctype html><html lang="es"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>AG-036 | Revisión independiente ' + slot + '</title>',
        '<style>body{font:16px system-ui,sans-serif;margin:2rem auto;max-width:900px;padding:0 1rem}',
        '.case{border:1px solid #ccc;border-radius:12px;padding:1rem;margin:1rem 0}',
        '.pics{display:flex;flex-wrap:wrap;gap:1rem}.pics figure{margin:0;max-width:260px}',
        '.pics img{width:260px;max-width:100%;height:210px;object-fit:contain;background:#f4f4f4}',
        'figcaption{font-size:0.75rem;overflow-wrap:anywhere}small{color:#555}</style></head><body>',
        '<h1>AG-036 · Revisión independiente ' + slot + '</h1>',
        '<p>Estas imágenes son evidencia por revisar, NO ejemplos previamente etiquetados. '
        'No se presentan las decisiones de otro revisor. </p>',
        '<p>Complete <code>revision_' + slot + '.csv</code> tras inspeccionar las vistas y la rúbrica. '
        'E0/E1/E2 solo describen condición externa; no representan primera/segunda comercial. '
        'Si la evidencia es insuficiente use <code>no_evaluable</code>.</p>',
    ]
    for n, piece in enumerate(pieces, 1):
        key = html.escape(f"{piece['producto']} · {piece['lote_id']} · {piece['pieza_id']}")
        rubric = html.escape(piece['rubrica_version'])
        lines.append(f'<section class="case"><h2>{n}. {key}</h2><small>Rúbrica: {rubric}</small><div class="pics">')
        for image in piece['imagenes']:
            name = _image_archive_name(image['imagen_relativa'])
            src = html.escape(quote(name, safe="/"), quote=True)
            text = html.escape(image['imagen_relativa'])
            lines.append(f'<figure><img src="{src}" alt="Vista de {key}" loading="lazy"><figcaption>{text}</figcaption></figure>')
        lines.append('</div></section>')
    lines.append('</body></html>')
    return '\n'.join(lines).encode('utf-8')


def _guide(slot: str) -> bytes:
    text = f'''# AG-036: paquete de revisión independiente {slot}

ESTADO: SIN ETIQUETAR. Este paquete contiene imágenes originales comprobadas
mediante SHA256 y filas preparadas, pero no acredita evaluación humana.

1. Descomprima todo el ZIP en una carpeta privada; abra `indice.html` en el navegador.
2. Identifique la rúbrica aplicable a cada producto/version (`kent-ext-*` / `tomato-ext-*`).
   Es una propuesta documental pendiente de aprobación formal. No atribuya defectos
   que no se ven ni infiera madurez interna, inocuidad o categoría comercial.
3. Abra `revision_{slot}.csv`. Complete `revisor_id` (código suyo, NO el de otro
   revisor), `fecha_revision_iso` con zona horaria (p. ej., 2026-11-08T15:00:00-05:00),
   `estado_revision` (`etiquetada`, `no_evaluable` o `pendiente`), `justificacion`.
   Solo si el estado es `etiquetada`, indique E0/E1/E2. Para E1/E2, complete
   `criterios_rxx` (códigos de la rúbrica del producto) y `ubicacion_evidencia`.
4. Para cada dictamen finalizado, incluya evidencia documental propia en `soportes/`
   y ponga su ruta relativa a dicha carpeta en `soporte_relativo`, por ejemplo
   `revision_pieza_001.txt`. La justificación debe expresar observaciones reales.
5. Mantenga el archivo del otro revisor oculto hasta cerrar ambas revisiones.
   No modifique las imágenes, IDs, rúbrica ni el inventario de origen.
6. Devuelva `revision_{slot}.csv` y los soportes al responsable de consolidación;
   las dos hojas se combinan SOLO después de terminar ambas revisiones.

IMPORTANTE: `fecha_revision_iso` es la fecha REAL de cada decisión, no una fecha
predeterminada; el auditor no aceptará filas incompletas como evidencia. Los
resultados deben quedar pendientes cuando no se dispone de imágenes elegibles.
'''
    return text.encode('utf-8')


def prepare(universe_csv: Path, images_root: Path, output_dir: Path) -> dict:
    """Genera dos ZIP autónomos y un acta; no escribe si ya existe destino."""
    # Impide que los paquetes con fotos se creen dentro del repositorio público.
    repo_root = Path(__file__).resolve().parents[3]
    target = output_dir.resolve()
    if target == repo_root or target.is_relative_to(repo_root):
        raise AuditError('Salida dentro del repositorio: use Documents fuera de Git')
    if output_dir.exists():
        raise AuditError('No se sobrescribe un directorio de entrega existente')

    universe, audit_meta = load_universe(universe_csv, images_root)
    rows, _ = load_csv(universe_csv, UNIVERSE_COLS)
    pieces_by_key = {}
    rubric_by_product = defaultdict(set)
    for key, item in sorted(universe.items()):
        if not (item['elegible'] and item['seleccion_doble'] == 'si'):
            continue
        product, lot, piece = key
        rubric_by_product[product].add(item['rubrica_version'])
        pieces_by_key[key] = {
            'producto': product, 'lote_id': lot, 'pieza_id': piece,
            'variedad_declarada': item['variedad_declarada'],
            'rubrica_version': item['rubrica_version'],
            'criterio_seleccion': item['criterio_seleccion'],
            'imagenes': [],
        }
    if not pieces_by_key:
        raise AuditError('No hay piezas elegibles previamente seleccionadas: no emitir paquetes vacíos')
    if any(len(versions) != 1 for versions in rubric_by_product.values()):
        raise AuditError('Una revisión por producto no puede mezclar versiones de rúbrica')

    seen_images = set()
    images = {}
    for row in rows:
        key = row['producto'], row['lote_id'], row['pieza_id']
        if key not in pieces_by_key:
            continue
        rel = row['imagen_relativa']
        name = _image_archive_name(rel)
        if name in seen_images:
            raise AuditError('Dos vistas seleccionadas comparten una ruta relativa: ' + rel)
        seen_images.add(name)
        blob, digest = safe_file(images_root, rel, MAX_IMAGE)
        if digest != row['sha256_imagen'].lower():
            raise AuditError('El contenido cambió durante la preparación: ' + rel)
        images[name] = blob
        pieces_by_key[key]['imagenes'].append({
            'imagen_relativa': rel, 'sha256_imagen': digest,
            'sesion_id': row['sesion_id'],
        })
    pieces = list(pieces_by_key.values())
    for p in pieces:
        p['imagenes'].sort(key=lambda x: x['imagen_relativa'])
    keys = [(p['producto'], p['lote_id'], p['pieza_id']) for p in pieces]
    counts = dict(sorted(Counter(x[0] for x in keys).items()))
    manifest = {
        'version': VERSION, 'estado': 'paquetes_preparados_sin_revision_humana',
        'sha256_universo_csv': audit_meta['sha256'],
        'piezas_seleccionadas': len(pieces), 'piezas_por_producto': counts,
        'fotos_incluidas': len(images), 'fichas': pieces,
        'etiquetas_generadas_automaticamente': 0,
        'autenticidad_revision_humana_verificada': False,
        'cierre_total_AG036_acreditado': False,
    }
    bundle = {}
    for slot in ('A', 'B'):
        review_rows = []
        for piece in pieces:
            r = dict.fromkeys(REVIEW_COLS, '')
            for field in ('producto', 'lote_id', 'pieza_id', 'rubrica_version'):
                r[field] = piece[field]
            review_rows.append(r)
        bundle[slot] = {
            f'revision_{slot}.csv': _csv_bytes(REVIEW_COLS, review_rows),
            'indice.html': _viewer(pieces, slot),
            'GUIA_REVISION.md': _guide(slot),
            'inventario_vistas.json': (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8'),
            'soportes/': b'',
            **images,
        }
    # Crear en un temporal y mover al destino solamente tras escribir ambos ZIP.
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ag036-preparacion-', dir=output_dir.parent) as td:
        temp = Path(td)
        sha_packages = {}
        for slot in ('A', 'B'):
            zipfile_path = temp / f'AG036_Revisor_{slot}.zip'
            with zipfile.ZipFile(zipfile_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for name, content in sorted(bundle[slot].items()):
                    archive.writestr(name, content)
            sha_packages[slot] = hashlib.sha256(zipfile_path.read_bytes()).hexdigest()
        act = {
            **manifest, 'fecha_preparacion_utc': datetime.now(timezone.utc).isoformat(),
            'sha256_zips': sha_packages,
            'advertencia': 'Preparación no acredita selección representativa, etiquetado humano ni aprobación de rúbrica.',
        }
        (temp / 'AG036_acta_preparacion.json').write_text(json.dumps(act, indent=2, ensure_ascii=False)+'\n',encoding='utf-8')
        (temp / 'LEEME_ENTREGA.txt').write_text(
            'Entregue AG036_Revisor_A.zip y AG036_Revisor_B.zip por separado. '\
            'Conserve AG036_acta_preparacion.json sin modificar. No suba fotos a GitHub.\n', encoding='utf-8')
        os.rename(temp, output_dir)
    return {'estado': 'paquetes_preparados_sin_revision_humana',
            'directorio': str(output_dir), 'piezas': len(pieces),
            'vistas': len(images), 'por_producto': counts,
            'acta': str(output_dir / 'AG036_acta_preparacion.json'),
            'cierre_total_AG036_acreditado': False}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--universo', type=Path, required=True)
    ap.add_argument('--raiz-imagenes', type=Path, required=True)
    ap.add_argument('--directorio-salida', type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        result = prepare(args.universo, args.raiz_imagenes, args.directorio_salida)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (AuditError, OSError) as exc:
        print(json.dumps({'estado': 'error_de_preparacion', 'detalle': str(exc)}, ensure_ascii=False),file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
