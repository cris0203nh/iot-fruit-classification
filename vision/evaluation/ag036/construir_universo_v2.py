"""AG-036 incremento 08: preparar universo DECLARADO de carpeta v2.

No verifica variedad, identidad física, licencia o sesión real. Selección para
revisión exploratoria, no autoriza entrenamiento ni demuestra independencia.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

from .auditar_etiquetado import UNIVERSE_COLS, load_universe
from .ingestar_dataset_multifuente import INVENTORY_FIELDS, IngestionError

EXTERNAL_TYPES = {
    'Mango_Kent_COFiLAB_dos_vistas': ('mango', 'EXT_COFILAB', 'Kent', 'kent-ext-v0.4'),
    'Tomate_Rojo_Hohenheim_3_vistas': ('tomate', 'EXT_HOHENHEIM', 'rojo_tipo_no_acreditado', 'tomato-ext-v0.2'),
}
PROJECT_TYPES = {
    'Mango_variedad': ('mango', 'CAP_MANGO', 'variedad_no_acreditada', 'kent-ext-v0.4'),
    'Tomate': ('tomate', 'CAP_TOMATE', 'tipo_no_acreditado', 'tomato-ext-v0.2'),
}


def _classify(r: dict[str, str]) -> tuple[str, str, str, str, str, bool]:
    path = PurePosixPath(r['ruta_relativa'])
    if '\\' in r['ruta_relativa'] or ':' in r['ruta_relativa'] or path.is_absolute() or '..' in path.parts or len(path.parts) != 4:
        raise IngestionError('Ruta de imagen no coincide con la estructura v2: ' + r['ruta_relativa'])
    section, subcategory, group, _ = path.parts
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,89}', group):
        raise IngestionError('Grupo no admite identificador documental seguro: ' + group)
    if section == '02_Datasets_externos' and subcategory in EXTERNAL_TYPES:
        p, lot, variety, rubric = EXTERNAL_TYPES[subcategory]
        selected = True
    elif section == '01_ZIP_Capturas_reales' and subcategory in PROJECT_TYPES:
        p, lot, variety, rubric = PROJECT_TYPES[subcategory]
        selected = False
    else:
        raise IngestionError('Carpeta no reconocida para v2: ' + r['ruta_relativa'])
    if p != r['producto_candidato'] or selected != (r['fuente'] == 'dataset_externo_declarado'):
        raise IngestionError('Producto o fuente contradictorios en el inventario')
    if r['grupo_candidato'] != group:
        raise IngestionError('El grupo no coincide con la ruta de imagen')
    return p, lot, group, variety, rubric, selected


def build(inventory_csv: Path, images_root: Path, output_dir: Path) -> dict:
    repo = Path(__file__).resolve().parents[3]
    if output_dir.exists():
        raise IngestionError('Salida existente: no sobrescribir inventario')
    if (repo / '.git').exists() and output_dir.resolve().is_relative_to(repo):
        raise IngestionError('El universo y los datos deben mantenerse fuera de Git')
    root = images_root.resolve(strict=True)
    if not inventory_csv.is_file():
        raise IngestionError('No existe el inventario multifuente')
    with inventory_csv.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)) or set(reader.fieldnames) != set(INVENTORY_FIELDS):
            raise IngestionError('Cabeceras de inventario inválidas')
        inventory = list(reader)
    if not inventory or any(None in row or any(v is None for v in row.values()) for row in inventory):
        raise IngestionError('Inventario vacío o malformado')
    universe = []
    seen_path, seen_sha = set(), set()
    groups = defaultdict(list)
    for r in inventory:
        product, lot, group, variety, rubric, selected = _classify(r)
        relative = r['ruta_relativa']
        p = PurePosixPath(relative)
        dest = root.joinpath(*p.parts)
        if not dest.is_file() or not dest.resolve().is_relative_to(root) or dest.is_symlink():
            raise IngestionError('Imagen insegura o ausente: ' + relative)
        sha = hashlib.sha256(dest.read_bytes()).hexdigest()
        if sha != r['sha256_imagen'].lower() or sha in seen_sha or relative in seen_path:
            raise IngestionError('SHA256 divergente, imagen o ruta duplicada: ' + relative)
        seen_sha.add(sha)
        seen_path.add(relative)
        # sesion_id = identificador TECNICO de agrupacion; NO fecha o sesión documentada.
        session_id = 'GRP_' + group
        universe.append(dict(zip(UNIVERSE_COLS, (
            product, variety, lot, group, session_id, relative, sha, rubric,
            'si' if selected else 'no',
            'muestra_exploratoria_grupo_declarado_v2' if selected else '',
        ))))
        groups[(product,lot,group,selected)].append(relative)
    universe.sort(key=lambda x: (x['producto'],x['lote_id'],x['pieza_id'],x['imagen_relativa']))
    selected_groups = [k for k in groups if k[3]]
    by_product = Counter(k[0] for k in selected_groups)
    by_photos = Counter(x['producto'] for x in universe if x['seleccion_doble']=='si')
    excluded = Counter(x['producto'] for x in universe if x['seleccion_doble']=='no')
    report = {
        'estado': 'universo_v2_preparado_para_revision_exploratoria_sin_etiquetas',
        'fotografias': len(universe),
        'grupos_totales': len(groups),
        'grupos_seleccionados_declarados': len(selected_groups),
        'fotografias_seleccionadas': sum(by_photos.values()),
        'grupos_por_producto': dict(sorted(by_product.items())),
        'fotos_por_producto': dict(sorted(by_photos.items())),
        'fotografias_no_seleccionadas': dict(sorted(excluded.items())),
        'etiquetas_e0_e1_e2_asignadas': 0,
        'identidad_fisica_y_sesiones_autenticadas': False,
        'procedencia_y_licencias_acreditadas': False,
        'rubricas_aprobadas': False,
        'entrenamiento_autorizado': False,
        'advertencia': ('Los grupos son unidades DECLARADAS por el archivo v2. Los campos lote_id y sesion_id '
                        'son claves técnicas, NO registros reales. La variedad Kent es declarada en la carpeta externa '
                        'pero NO verificada por certificación. No redistribuir fotos externas sin revisar su licencia.'),
    }
    output_dir.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ag036-08-',dir=output_dir.parent) as td:
        temp=Path(td)
        with (temp/'universo_AG036_v2.csv').open('x',encoding='utf-8-sig',newline='') as f:
            wr=csv.DictWriter(f,fieldnames=UNIVERSE_COLS,lineterminator='\n')
            wr.writeheader();wr.writerows(universe)
        (temp/'resumen_universo.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        with (temp/'grupos_revision.csv').open('x',encoding='utf-8-sig',newline='') as f:
            fields=['producto','lote_tecnico','grupo_declarado','vistas','seleccion_doble','identidad_fisica_verificada','origen_licencia_verificados']
            wr=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');wr.writeheader()
            for (p,lot,g,sel),photos in sorted(groups.items()):
                wr.writerow(dict(producto=p,lote_tecnico=lot,grupo_declarado=g,vistas=len(photos),seleccion_doble='si' if sel else 'no',identidad_fisica_verificada='no',origen_licencia_verificados='no'))
        # Comprueba exactamente el formato que consume el empaquetador heredado.
        _,checked = load_universe(temp/'universo_AG036_v2.csv',root)
        if checked['filas_vistas']!=len(universe) or checked['piezas']!=len(groups):
            raise IngestionError('El validador de AG-036 devolvió conteos inconsistentes')
        os.rename(temp,output_dir)
    return report


def main(argv=None)->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--inventario',type=Path,required=True)
    ap.add_argument('--raiz-imagenes',type=Path,required=True)
    ap.add_argument('--directorio-salida',type=Path,required=True)
    a=ap.parse_args(argv)
    try:
        result=build(a.inventario,a.raiz_imagenes,a.directorio_salida)
        print(json.dumps(result,ensure_ascii=False))
        return 0
    except (IngestionError, OSError, ValueError) as ex:
        print(json.dumps({'estado':'error_universo_v2','detalle':str(ex)},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
