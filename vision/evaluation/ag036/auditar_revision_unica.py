"""AG-036: auditar una devolucion humana A SIN simular un segundo revisor.

Entradas privadas: universo verificado, imagenes y AG036_Devolucion_A.zip.
Salida: informe de cobertura de UN revisor y observaciones; nunca calcula kappa.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import os
import json
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

from .auditar_etiquetado import AuditError, REVIEW_COLS, load_universe, load_reviews

MAX_CSV = 4 * 1024 * 1024
MAX_SUPPORT = 4 * 1024 * 1024
MAX_ARCHIVE = 50 * 1024 * 1024


def _valid_zip_name(name: str) -> bool:
    p = PurePosixPath(name)
    return (name and not name.startswith('/') and ':' not in name
            and '\\' not in name and '//' not in name and '/./' not in name and all(part not in ('.', '..', '') for part in p.parts))


def _load_return(archive_path: Path, supports: Path) -> tuple[list[dict], str]:
    if not archive_path.is_file():
        raise AuditError('Devolucion A inexistente')
    with zipfile.ZipFile(archive_path) as archive:
        names, total = set(), 0
        for info in archive.infolist():
            name = info.filename
            if not _valid_zip_name(name) or name in names:
                raise AuditError('ZIP de devolucion: ruta insegura o repetida')
            names.add(name)
            if info.is_dir():
                continue
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise AuditError('ZIP de devolucion: enlace simbolico prohibido')
            if name != 'revision_A.csv' and not name.startswith('soportes/'):
                raise AuditError('ZIP de devolucion: archivo no esperado')
            limit = MAX_CSV if name == 'revision_A.csv' else MAX_SUPPORT
            if info.file_size > limit:
                raise AuditError('ZIP de devolucion: soporte o CSV demasiado grande')
            total += info.file_size
            if total > MAX_ARCHIVE:
                raise AuditError('ZIP de devolucion: volumen excedido')
        if 'revision_A.csv' not in names:
            raise AuditError('Falta revision_A.csv')
        blob = archive.read('revision_A.csv')
        try:
            reader = csv.DictReader(io.StringIO(blob.decode('utf-8-sig'), newline=''), strict=True)
            fields = reader.fieldnames or []
            if len(fields) != len(set(fields)) or set(fields) != set(REVIEW_COLS):
                raise AuditError('Encabezados invalidos en revision_A.csv')
            rows = list(reader)
            if not rows or any(None in r or any(v is None for v in r.values()) for r in rows):
                raise AuditError('Filas vacias o CSV malformado')
        except (UnicodeError, csv.Error) as exc:
            raise AuditError('CSV ilegible') from exc
        for name in sorted(names):
            if name.startswith('soportes/') and not name.endswith('/'):
                dest = supports.joinpath(*PurePosixPath(name).parts[1:])
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(archive.read(name))
    return rows, hashlib.sha256(archive_path.read_bytes()).hexdigest()


def _observations(rows: list[dict]) -> list[dict]:
    notes = []
    for row in rows:
        note = []
        desc = row['justificacion'].lower()
        if row['etiqueta_e0_e1_e2'] == 'E0' and any(token in desc for token in ('manchas', 'aplastad', 'golpe', 'lesion', 'podrid')):
            note.append('E0_con_mencion_de_posible_defecto_verificar_gravedad')
        if row['producto'] == 'tomate' and row['etiqueta_e0_e1_e2'] == 'E0':
            note.append('grupo_tomate_solo_E0_no_validar_tres_clases')
        notes.append({
            'producto':row['producto'], 'pieza_id':row['pieza_id'],
            'etiqueta_original':row['etiqueta_e0_e1_e2'],
            'justificacion_original':row['justificacion'],
            'banderas_de_revision':'|'.join(note),
            'etiqueta_modificada':'no',
            'evaluacion_ia_es_revisor_B':'no',
        })
    return notes


def audit_single(universe_csv: Path, images_root: Path, return_zip: Path,
                 output_dir: Path) -> dict:
    if output_dir.exists():
        raise AuditError('La carpeta de salida ya existe; no se sobrescriben evidencias')
    repo = Path(__file__).resolve().parents[3]
    if (repo / '.git').exists() and output_dir.resolve().is_relative_to(repo):
        raise AuditError('No se guardan datos privados dentro del repositorio')
    universe, umeta = load_universe(universe_csv, images_root)
    selected = {key: data for key, data in universe.items()
                if data['elegible'] and data['seleccion_doble'] == 'si'}
    if not selected:
        raise AuditError('Universo sin piezas seleccionadas')
    with tempfile.TemporaryDirectory(prefix='ag036-una-revision-') as staging:
        root = Path(staging)
        (root/'soportes').mkdir()
        raw_rows, zip_sha = _load_return(return_zip, root/'soportes')
        # Valida identidad, fechas, rubricas, soporte e integridad usando el auditor original.
        normalized = root/'revision_A.csv'
        with normalized.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=REVIEW_COLS,lineterminator='\n')
            w.writeheader();w.writerows(raw_rows)
        reviewed, review_meta = load_reviews(normalized,universe,root/'soportes','A')
        if set(reviewed) != set(selected):
            raise AuditError('Devolucion A no cubre exactamente las piezas seleccionadas')
        if any(item['estado_revision'] != 'etiquetada' for item in reviewed.values()):
            raise AuditError('Existen piezas sin etiqueta final del revisor unico')
        distribution = defaultdict(Counter)
        for key,row in reviewed.items():
            distribution[key[0]][row['etiqueta_e0_e1_e2']] += 1
        flags = _observations(raw_rows)
        repetitions = defaultdict(list)
        for row in raw_rows:
            repetitions[(row['producto'],row['justificacion'].strip().casefold())].append(row['pieza_id'])
        repeated = [{'producto':p,'justificacion':desc,'piezas':ps,'cantidad':len(ps)}
                    for (p,desc),ps in repetitions.items() if len(ps)>1]
        report = {
            'estado':'revision_unica_validada_documentalmente_no_cierra_concordancia',
            'revision_humana_reportada':review_meta['revisor_id'],
            'sha256_devolucion_A_zip':zip_sha,
            'sha256_universo':umeta['sha256'],
            'fotografias_inventariadas':umeta['filas_vistas'],
            'grupos_de_universo':umeta['piezas'],
            'piezas_seleccionadas':len(selected),
            'piezas_etiquetadas_por_A':len(reviewed),
            'cobertura_de_A_sobre_subconjunto':round(len(reviewed)/len(selected),6),
            'distribucion':{p:{k:distribution[p][k] for k in ('E0','E1','E2')}
                            for p in ('mango','tomate')},
            'alertas_de_revision_documental':sum(bool(n['banderas_de_revision']) and n['producto']=='mango' for n in flags),
            'justificaciones_repetidas':repeated,
            'doble_revision_humana_realizada':False,
            'acuerdo_entre_humanos':None,
            'kappa_entre_humanos':None,
            'clasificador_e0_e1_e2_validado':False,
            'independencia_fisica_y_licencia_externa_verificadas':False,
            'rubricas_aprobadas_por_especialista_verificadas':False,
            'cierre_tecnico_revision_unica':True,
            'cierre_del_criterio_original_doble_concordancia':False,
            'aviso':'IA no constituye un segundo revisor humano; las etiquetas de A se conservan intactas.'
        }
        output_dir.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='ag036-single-out-',dir=output_dir.parent) as td:
            dest=Path(td)
            (dest/'auditoria_revision_unica.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            with (dest/'alertas_revision.csv').open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(flags[0]))
                w.writeheader();w.writerows(flags)
            lines=[
                '# AG-036 — Acta tecnica de revision unica (sin concordancia A/B)',
                '',f"- Devolucion: `{return_zip.name}` (SHA256 `{zip_sha}`).",
                f"- Revisor declarado: **{review_meta['revisor_id']}**; etiquetas: **{len(reviewed)}/{len(selected)}** piezas seleccionadas.",
                f"- Vistas inventariadas: {umeta['filas_vistas']}; las etiquetas son por pieza, no por fotografia.",
                '', '| Producto | E0 | E1 | E2 |', '|---|---:|---:|---:|',
                *[f"| {p} | {distribution[p]['E0']} | {distribution[p]['E1']} | {distribution[p]['E2']} |" for p in ('mango','tomate')],
                '', f"- Alertas de lectura en justificaciones E0 de mango: **{report['alertas_de_revision_documental']}**; revisar `alertas_revision.csv`.",
                '- Tomate no contiene ejemplos E1 ni E2: no se puede validar el clasificador de tres clases.',
                '- La muestra de mango E1/E2 (2/3) es insuficiente para particiones independientes de entrenamiento/validacion/prueba.',
                '', '## Interpretacion del sprint',
                '', '**Completado:** ingesta v2, deteccion YOLOE, diagnostico y registro humano unico con integridad verificable.',
                '**No completado:** criterio de dos revisores, concordancia y kappa; validacion externa de origen/licencias, rubricas y modelo de calidad.',
                'Si el Product Owner/docente acepta un cambio de alcance, registrar "piloto de revision unica" como criterio adaptado, sin afirmar concordancia.',
                '', '**Prohibido:** copiar A como B, usar decisiones de una IA como firma humana o generar cifras de kappa sin pares.',
            ]
            (dest/'informe_revision_unica.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
            os.rename(dest,output_dir)
        return report


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--universo',type=Path,required=True)
    p.add_argument('--raiz-imagenes',type=Path,required=True)
    p.add_argument('--devolucion-a',type=Path,required=True)
    p.add_argument('--directorio-salida',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        out=audit_single(args.universo,args.raiz_imagenes,args.devolucion_a,args.directorio_salida)
        print(json.dumps({'estado':out['estado'],'piezas':out['piezas_etiquetadas_por_A'],
                          'acuerdo_AB':None,'kappa_AB':None},ensure_ascii=False))
        return 0
    except (AuditError,OSError,ValueError,zipfile.BadZipFile) as exc:
        print(json.dumps({'estado':'error_revision_unica','detalle':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
