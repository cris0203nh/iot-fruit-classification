"""AG-036 incremento 04: ejecutar YOLOE sobre todas las imágenes SIN etiquetas E0/E1/E2.

La confianza del detector no es precisión ni validación de calidad comercial.
Se preservan resultados separados por procedencia y fotografía.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath

from .ingestar_dataset_multifuente import INVENTORY_FIELDS, IngestionError

OUTPUT_FIELDS = ('fuente','producto_candidato','grupo_candidato','ruta_relativa',
                 'sha256_imagen','resolucion_baja','estado_deteccion',
                 'candidatos_totales','candidatos_producto','confianza_mejor_coincidencia',
                 'caja','mascara_poligono_disponible','etiqueta_e0_e1_e2')


def _load_inventory(inventory: Path):
    with inventory.open('r', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if set(reader.fieldnames or []) != set(INVENTORY_FIELDS) or len(reader.fieldnames or []) != len(INVENTORY_FIELDS):
            raise IngestionError('Inventario multifuente con cabeceras inválidas')
        rows = list(reader)
        if any(None in r or None in r.values() for r in rows):
            raise IngestionError('CSV malformado')
    if not rows:
        raise IngestionError('No existen fotografías en el inventario')
    return rows


def _real_detector():
    # Carga perezosa: las pruebas unitarias no requieren torch/YOLOE.
    import numpy as np
    from PIL import Image
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root/'backend'))
    from app.routers.images import get_vision_model
    model = get_vision_model()

    def predict(path: Path):
        with Image.open(path) as image:
            bgr = np.asarray(image.convert('RGB'))[:,:,::-1].copy()
        result = model.predict(source=bgr, imgsz=512, conf=.25,
                               iou=.50, max_det=10, device='cpu', verbose=False)[0]
        detections = []
        for idx, box in enumerate(result.boxes):
            label = str(result.names[int(box.cls[0].item())]).lower()
            confidence = float(box.conf[0].item())
            bbox = [round(float(v),2) for v in box.xyxy[0].tolist()]
            has_mask = bool(result.masks is not None and idx < len(result.masks.xy) and
                            len(result.masks.xy[idx]) >= 3)
            detections.append({'label':label,'confidence':confidence,'box':bbox,'mask':has_mask})
        return detections
    return predict


def evaluate(inventory: Path, images_root: Path, output_dir: Path, predictor=None, limit: int=0):
    if output_dir.exists():
        raise IngestionError('No sobrescribir resultados anteriores')
    repo = Path(__file__).resolve().parents[3]
    if (repo/'.git').exists() and output_dir.resolve().is_relative_to(repo):
        raise IngestionError('Resultados deben guardarse fuera del repositorio')
    if limit < 0:
        raise IngestionError('El límite no puede ser negativo')
    rows = _load_inventory(inventory)
    if limit:
        rows = rows[:limit]
    if predictor is None:
        predictor = _real_detector()
    out, status = [], Counter()
    root = images_root.resolve(strict=True)
    for ix, row in enumerate(rows, 1):
        relative = row['ruta_relativa']
        p = PurePosixPath(relative)
        if ('\\' in relative or ':' in relative or p.is_absolute() or '..' in p.parts):
            raise IngestionError('Ruta inválida del inventario')
        image = root.joinpath(*p.parts)
        if not image.is_file() or not image.resolve().is_relative_to(root):
            raise IngestionError(f'Fotografía ausente/fuera de carpeta: {relative}')
        if image.is_symlink() or image.stat().st_size > 12*1024*1024:
            raise IngestionError(f'Fotografía insegura: {relative}')
        sha = hashlib.sha256(image.read_bytes()).hexdigest()
        if sha != row['sha256_imagen'].lower():
            raise IngestionError(f'SHA256 alterado: {relative}')
        detections = predictor(image)
        if not isinstance(detections, list):
            raise IngestionError('Detector devolvió estructura inválida')
        product = row['producto_candidato'].strip().lower()
        if product not in ('mango','tomate'):
            raise IngestionError('Producto candidato inválido')
        word = 'mango' if product == 'mango' else 'tomato'
        same = [d for d in detections if word in str(d.get('label','')).lower()]
        if product == 'tomate':
            same = [d for d in detections if ('tomato' in str(d.get('label','')).lower() or
                                                   'tomate' in str(d.get('label','')).lower())]
        best = max(same, key=lambda d: d.get('confidence',0)) if same else None
        if not detections:
            state = 'sin_deteccion'
        elif not same:
            state = 'deteccion_sin_clase_esperada'
        elif len(same) > 1:
            state = 'multiples_candidatos_esperados'
        elif best['confidence'] < .40:
            state = 'confianza_inferior_a_umbral_captura'
        elif not best.get('mask'):
            state = 'sin_poligono_de_segmentacion'
        else:
            state = 'deteccion_lista_para_captura'
        status[(row['fuente'], product, state)] += 1
        out.append({
            'fuente':row['fuente'], 'producto_candidato':product,
            'grupo_candidato':row['grupo_candidato'], 'ruta_relativa':relative,
            'sha256_imagen':sha, 'resolucion_baja':row['advertencia_resolucion'],
            'estado_deteccion':state, 'candidatos_totales':len(detections),
            'candidatos_producto':len(same),
            'confianza_mejor_coincidencia':round(best['confidence'],6) if best else '',
            'caja':json.dumps(best.get('box', [])) if best else '',
            'mascara_poligono_disponible':'si' if best and best.get('mask') else 'no',
            'etiqueta_e0_e1_e2':'',
        })
        if ix % 10 == 0:
            print(f'YOLOE: {ix}/{len(rows)} fotografías procesadas',file=sys.stderr)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ag036-deteccion-',dir=output_dir.parent) as td:
        tmp=Path(td)
        with (tmp/'resultados_deteccion.csv').open('x',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=OUTPUT_FIELDS,lineterminator='\n')
            w.writeheader();w.writerows(out)
        report={
            'estado':'deteccion_exploratoria_no_es_calidad_visual',
            'fotografias_procesadas':len(rows),
            'conteos_por_fuente_producto_estado':[
                {'fuente':s,'producto':p,'estado_deteccion':st,'cantidad':n}
                for (s,p,st),n in sorted(status.items())],
            'etiquetas_e0_e1_e2_generadas':0,
            'medicion_exactitud_clasificador':None,
            'aprobado_para_entrenamiento_supervisado':False,
            'cierre_total_AG036_acreditado':False,
            'advertencia':'La detección no demuestra que el producto/variedad en el nombre de la carpeta sea correcto ni confirma el grado E0/E1/E2.'}
        (tmp/'resumen_deteccion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        os.rename(tmp,output_dir)
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventario',type=Path,required=True)
    p.add_argument('--raiz-imagenes',type=Path,required=True)
    p.add_argument('--salida-dir',type=Path,required=True)
    p.add_argument('--limite',type=int,default=0)
    args=p.parse_args(argv)
    try:
        result=evaluate(args.inventario,args.raiz_imagenes,args.salida_dir,limit=args.limite)
        print(json.dumps({'estado':result['estado'],'imagenes':result['fotografias_procesadas'],
                          'etiquetas_generadas':0},ensure_ascii=False))
        return 0
    except (IngestionError,OSError,ValueError) as exc:
        print(json.dumps({'estado':'error_deteccion','detalle':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
