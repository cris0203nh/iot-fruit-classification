"""AG-036 incremento 07: diagnostico pareado de fallos YOLOE sin cambiar produccion.

Usa 10 fallos de revision humana y controles deterministas anteriormente aptos.
Ejecuta el MISMO modelo/prompts por defecto con imgsz 512/640/768, conf .25,
iou .50, max_det 10 y CPU. No evalua calidad E0/E1/E2 ni estima precision.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

ESTADOS = {
    'sin_deteccion', 'deteccion_sin_clase_esperada',
    'multiples_candidatos_esperados', 'confianza_inferior_a_umbral_captura',
    'sin_poligono_de_segmentacion', 'deteccion_lista_para_captura',
}
FALLOS = {'sin_deteccion', 'deteccion_sin_clase_esperada'}
CAMPOS_FALLOS = {
    'producto','fuente','grupo','ruta_relativa','sha256_imagen',
    'estado_original','decision_revisor',
}
CAMPOS_DETECTOR = {
    'fuente','producto_candidato','grupo_candidato','ruta_relativa',
    'sha256_imagen','estado_deteccion',
}
CAMPOS_CASOS = [
    'tipo_caso','fuente','producto','grupo','ruta_relativa','sha256_imagen',
    'estado_original','decision_revisor','observacion_revisor','hipotesis',
]
CAMPOS_RESULTADOS = CAMPOS_CASOS + [
    'imgsz','estado_nuevo','candidatos_totales','candidatos_producto',
    'clase_top','confianza_top','mejor_confianza_producto',
    'caja_producto','mascara_producto','cambio_operativo','revision_visual_requerida',
]


class DiagnosticoError(ValueError):
    """Entradas invalidas / condicion que impide informe verificable."""


def _csv(path: Path, required: set[str]) -> list[dict]:
    if not path.is_file():
        raise DiagnosticoError(f'Archivo inexistente: {path}')
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or not required.issubset(headers):
            raise DiagnosticoError(f'Cabeceras invalidas: {path.name}')
        rows = list(reader)
    if not rows or any(None in row or any(value is None for value in row.values()) for row in rows):
        raise DiagnosticoError(f'CSV vacio o malformado: {path.name}')
    return rows


def _validate_sha(value: str) -> bool:
    return len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _validate_relative(relative: str) -> PurePosixPath:
    path = PurePosixPath(relative)
    if (not relative or '\\' in relative or ':' in relative or path.is_absolute()
            or '..' in path.parts):
        raise DiagnosticoError(f'Ruta de imagen insegura: {relative}')
    return path


def _hypothesis(row: dict) -> str:
    state = row['estado_original']
    if state == 'sin_deteccion':
        return 'no_hay_candidatos_a_conf_0_25_verificar_escala_angulo_e_iluminacion'
    if state == 'deteccion_sin_clase_esperada':
        return 'hay_candidatos_de_otra_clase_inspeccionar_clase_y_caja_sin_reetiquetar'
    return 'control_aceptado_comprobar_que_no_haya_regresion'


def _require_consistent(detector_rows: list[dict], fail_rows: list[dict], controls: int):
    indexed = {}
    by_hash = set()
    for row in detector_rows:
        sha = row['sha256_imagen'].strip().lower()
        route = row['ruta_relativa']
        _validate_relative(route)
        if not _validate_sha(sha) or sha in by_hash or route in indexed:
            raise DiagnosticoError('Hashes duplicados/invalidos o rutas repetidas en detector')
        if row['producto_candidato'] not in ('mango','tomate'):
            raise DiagnosticoError('Producto inesperado en detector')
        if row['estado_deteccion'] not in ESTADOS:
            raise DiagnosticoError('Estado del detector no reconocido')
        by_hash.add(sha)
        indexed[route] = row

    selected, seen = [], set()
    for row in fail_rows:
        route = row['ruta_relativa']
        sha = row['sha256_imagen'].lower()
        _validate_relative(route)
        original = indexed.get(route)
        if route in seen or not original or original['sha256_imagen'].lower() != sha:
            raise DiagnosticoError('Fallo duplicado o no corresponde al CSV original por ruta/SHA256')
        if (row['estado_original'] not in FALLOS or
                row['estado_original'] != original['estado_deteccion'] or
                row['producto'] != original['producto_candidato'] or
                row['fuente'] != original['fuente'] or
                row['grupo'] != original['grupo_candidato'] or
                row['decision_revisor'].strip().casefold() != 'yoloe fallo' and
                row['decision_revisor'].strip().casefold() != 'yoloe falló'):
            raise DiagnosticoError('Fallo sin revision acreditada o metadatos incompatibles')
        seen.add(route)
        selected.append({
            'tipo_caso':'fallo_confirmado', 'fuente':row['fuente'],
            'producto':row['producto'], 'grupo':row['grupo'],
            'ruta_relativa':route, 'sha256_imagen':sha,
            'estado_original':row['estado_original'],
            'decision_revisor':row['decision_revisor'],
            'observacion_revisor':row.get('observacion_revisor',''),
            'hipotesis':_hypothesis(row),
        })
    if len(selected) != 10:
        raise DiagnosticoError(f'Se esperan exactamente 10 fallos confirmados; recibidos {len(selected)}')
    if controls < 0 or controls > 65:
        raise DiagnosticoError('Numero de controles fuera del rango 0..65')
    candidates = defaultdict(list)
    for row in detector_rows:
        if row['estado_deteccion'] != 'deteccion_lista_para_captura' or row['ruta_relativa'] in seen:
            continue
        key = (row['fuente'],row['producto_candidato'])
        candidates[key].append(row)
    # Orden estable independiente del orden de filas y de las rutas.
    for values in candidates.values():
        values.sort(key=lambda r: (r['sha256_imagen'],r['ruta_relativa']))
    pool, chosen = [], []
    for key in sorted(candidates):
        chosen.extend(candidates[key][:min(3,len(candidates[key]),controls)])
        pool.extend(candidates[key][min(3,len(candidates[key]),controls):])
    if len(chosen) < controls:
        pool.sort(key=lambda r:(r['sha256_imagen'],r['ruta_relativa']))
        chosen.extend(pool[:controls-len(chosen)])
    chosen = chosen[:controls]
    for row in chosen:
        selected.append({
            'tipo_caso':'control_sin_revision_humana', 'fuente':row['fuente'],
            'producto':row['producto_candidato'], 'grupo':row['grupo_candidato'],
            'ruta_relativa':row['ruta_relativa'],
            'sha256_imagen':row['sha256_imagen'].lower(),
            'estado_original':row['estado_deteccion'],
            'decision_revisor':'no_revisado',
            'observacion_revisor':'Control automatico, falta verificar resultado visualmente',
            'hipotesis':_hypothesis({'estado_original':row['estado_deteccion']}),
        })
    if len(selected) != 10 + controls:
        raise DiagnosticoError('No hay suficientes controles candidatos')
    return selected


def _check_image(root: Path, row: dict) -> Path:
    rel = _validate_relative(row['ruta_relativa'])
    image = root.joinpath(*rel.parts)
    if (not image.is_file() or image.is_symlink() or
            not image.resolve().is_relative_to(root) or image.stat().st_size > 12*1024*1024):
        raise DiagnosticoError(f'Imagen ausente o insegura: {rel}')
    if hashlib.sha256(image.read_bytes()).hexdigest() != row['sha256_imagen']:
        raise DiagnosticoError(f'SHA256 diferente al inventario: {rel}')
    return image


def classify(detections: list[dict], product: str, threshold: float = .40) -> dict:
    """Reproduce el orden de reglas del evaluador de YOLOE sin alterar producción."""
    if not isinstance(detections,list):
        raise DiagnosticoError('Salida del detector invalida')
    if product not in ('mango','tomate'):
        raise DiagnosticoError('Producto invalido')
    expected = 'mango' if product == 'mango' else 'tomate'
    normalized = []
    for d in detections:
        label = str(d.get('label','')).lower()
        conf = float(d.get('confidence',0))
        if not (0 <= conf <= 1):
            raise DiagnosticoError('Confianza invalida')
        match = (expected in label if product == 'mango' else
                 'tomato' in label or 'tomate' in label)
        normalized.append((d, label, conf, match))
    matching = [x for x in normalized if x[3]]
    top = max(normalized,key=lambda x:x[2]) if normalized else None
    best = max(matching,key=lambda x:x[2]) if matching else None
    if not detections:
        state = 'sin_deteccion'
    elif not matching:
        state = 'deteccion_sin_clase_esperada'
    elif len(matching)>1:
        state = 'multiples_candidatos_esperados'
    elif best[2] < threshold:
        state = 'confianza_inferior_a_umbral_captura'
    elif not best[0].get('mask'):
        state = 'sin_poligono_de_segmentacion'
    else:
        state = 'deteccion_lista_para_captura'
    return {'estado_nuevo':state,'candidatos_totales':len(normalized),
            'candidatos_producto':len(matching),
            'clase_top':top[1] if top else '',
            'confianza_top':round(top[2],6) if top else '',
            'mejor_confianza_producto':round(best[2],6) if best else '',
            'caja_producto':json.dumps(best[0].get('box',[])) if best else '',
            'mascara_producto':'si' if best and best[0].get('mask') else 'no'}


def _real_predictor():
    # Se reutilizan los pesos y prompts de la aplicacion; no cambia su configuracion.
    import numpy as np
    from PIL import Image
    repo = Path(__file__).resolve().parents[3]
    sys.path.insert(0,str(repo/'backend'))
    from app.routers.images import get_vision_model
    model = get_vision_model()

    def predict(path: Path, size: int) -> list[dict]:
        with Image.open(path) as picture:
            bgr = np.asarray(picture.convert('RGB'))[:,:,::-1].copy()
        result = model.predict(source=bgr,imgsz=size,conf=.25,iou=.50,
                               max_det=10,device='cpu',verbose=False)[0]
        detections = []
        if result.boxes is None:
            return detections
        polygons = result.masks.xy if result.masks is not None else []
        for i,box in enumerate(result.boxes):
            class_id = int(box.cls[0].item())
            name = result.names.get(class_id,'') if isinstance(result.names,dict) else result.names[class_id]
            points_available = i < len(polygons) and len(polygons[i]) >= 3
            detections.append({
                'label':str(name).lower(),
                'confidence':float(box.conf[0].item()),
                'box':[round(float(v),2) for v in box.xyxy[0].tolist()],
                'mask':bool(points_available),
            })
        return detections
    return predict


def _writer(path:Path,fields:list[str],rows:list[dict]):
    with path.open('x',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=fields,lineterminator='\n')
        writer.writeheader();writer.writerows(rows)


def evaluate(detector:Path,failures:Path,images_root:Path,output:Path,
             mode:str='inferir',predictor=None,controls:int=12,sizes=(512,640,768)) -> dict:
    if mode not in ('preparar','inferir'):
        raise DiagnosticoError('Modo invalido')
    if not sizes or 512 not in sizes or any(s < 320 or s > 1024 or s%32 for s in sizes) or len(set(sizes))!=len(sizes):
        raise DiagnosticoError('Resoluciones invalidas: incluir 512 y usar multiplos de 32, 320..1024')
    if output.exists():
        raise DiagnosticoError('La salida ya existe: no se sobrescriben evidencias')
    repo = Path(__file__).resolve().parents[3]
    if (repo/'.git').exists() and output.resolve().is_relative_to(repo):
        raise DiagnosticoError('Salida debe estar fuera del repositorio')
    root = images_root.resolve(strict=True)
    items = _require_consistent(_csv(detector,CAMPOS_DETECTOR),_csv(failures,CAMPOS_FALLOS),controls)
    # Comprobacion de integridad ANTES de iniciar inferencias costosas.
    paths = {row['sha256_imagen']:_check_image(root,row) for row in items}
    result_rows, raw = [], []
    if mode == 'inferir':
        predict = predictor or _real_predictor()
        for i,row in enumerate(items,1):
            for size in sizes:
                candidates=predict(paths[row['sha256_imagen']],size)
                classified=classify(candidates,row['producto'])
                after=classified['estado_nuevo']
                if row['tipo_caso']=='fallo_confirmado':
                    delta='candidato_recuperado' if after=='deteccion_lista_para_captura' else 'fallo_persistente'
                else:
                    delta='control_sigue_apto' if after=='deteccion_lista_para_captura' else 'regresion_operativa'
                result_rows.append({**row,'imgsz':size,**classified,
                                    'cambio_operativo':delta,
                                    'revision_visual_requerida':'si'})
                raw.append({'ruta_relativa':row['ruta_relativa'],'sha256_imagen':row['sha256_imagen'],
                            'imgsz':size,'detecciones':candidates})
            print(f'AG036-07: {i}/{len(items)} imagenes, {len(sizes)} resoluciones',file=sys.stderr)
    summaries=[]
    if mode=='inferir':
        for size in sizes:
            rows=[x for x in result_rows if x['imgsz']==size]
            failed=[x for x in rows if x['tipo_caso']=='fallo_confirmado']
            control=[x for x in rows if x['tipo_caso']!='fallo_confirmado']
            summaries.append({'imgsz':size,'fallos_evaluados':len(failed),
                'fallos_candidatos_recuperados':sum(r['cambio_operativo']=='candidato_recuperado' for r in failed),
                'controles_evaluados':len(control),
                'regresiones_operativas_controles':sum(r['cambio_operativo']=='regresion_operativa' for r in control),
                'desacuerdos_con_estado_original_en_512':sum(r['estado_nuevo']!=r['estado_original'] for r in rows) if size==512 else None})
    report={
      'estado':'diagnostico_preliminar' if mode=='preparar' else 'ensayo_pareado_no_aprueba_despliegue',
      'foto_dataset_produccion_modificado':False,
      'modelo_produccion_modificado':False,
      'umbral_produccion_modificado':False,
      'fallos_humanamente_confirmados':10,
      'fallos_por_producto':dict(Counter(r['producto'] for r in items if r['tipo_caso']=='fallo_confirmado')),
      'fallos_por_estado':dict(Counter(r['estado_original'] for r in items if r['tipo_caso']=='fallo_confirmado')),
      'controles_automaticos_sin_revision_humana':controls,
      'resoluciones':list(sizes), 'comparacion_por_resolucion':summaries,
      'predicciones_e0_e1_e2_generadas':0,
      'despliegue_autorizado':False,
      'limites':'Los controles no son ground truth humano. Candidato recuperado = regla automatica satisfecha, NO exactitud; requiere revisar cajas/clases y confirmar no regresiones en el universo completo.',
    }
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ag036-07-',dir=output.parent) as workspace:
        tmp=Path(workspace)
        _writer(tmp/'casos_seleccionados.csv',CAMPOS_CASOS,items)
        if mode=='inferir':
            _writer(tmp/'resultados_variantes.csv',CAMPOS_RESULTADOS,result_rows)
            with (tmp/'detecciones_completas.jsonl').open('x',encoding='utf-8') as f:
                for record in raw:
                    f.write(json.dumps(record,ensure_ascii=False)+'\n')
        (tmp/'resumen_diagnostico.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        lines=['# AG-036 · Incremento 07 — Diagnostico de diez fallos YOLOE','',
           '## Alcance confirmado',
           f"- 10 fallos revisados: {Counter(r['producto'] for r in items if r['tipo_caso']=='fallo_confirmado').get('mango',0)} mango y {Counter(r['producto'] for r in items if r['tipo_caso']=='fallo_confirmado').get('tomate',0)} tomate.",
           f"- Estados iniciales: {dict(Counter(r['estado_original'] for r in items if r['tipo_caso']=='fallo_confirmado'))}.",
           f'- {controls} controles originalmente aptos, **no revisados por una persona**.',
           '- Configuracion de produccion no modificada. La referencia sigue siendo imgsz=512, conf=0.25, iou=0.50.',
           '- El ensayo usa los mismos pesos y prompts; variantes exclusivamente de resolucion.',
           '', '## Resultados',
        ]
        if mode=='preparar':
            lines.append('Solo inventario. Repetir con --modo inferir en el equipo con YOLOE instalado.')
        else:
            lines += ['| Resolucion | Fallos candidatos recuperados / 10 | Regresiones de control |',
                      '|---|---:|---:|']
            for s in summaries:
                lines.append(f"| {s['imgsz']} | {s['fallos_candidatos_recuperados']} | {s['regresiones_operativas_controles']} / {s['controles_evaluados']} |")
            baseline = next(s for s in summaries if s['imgsz']==512)
            if baseline['desacuerdos_con_estado_original_en_512']:
                lines.append(f"\n**Atencion:** {baseline['desacuerdos_con_estado_original_en_512']} divergencias entre reproduccion 512 y resultados historicos. Verificar ambiente/pesos/prompts antes de comparar variantes.")
        lines += ['','## Decision tecnica','- No aplicar ajustes automaticamente.',
          '- Revisar visualmente los casos que cambian de estado y eventuales regresiones.',
          '- No usar esta prueba como precision, recall, clasificacion E0/E1/E2 o validacion de variedad.',
          '- Si hay mejoras consistentes, solicitar una validacion completa de 97 imagenes con referencia humana.',
          '']
        (tmp/'informe_diagnostico.md').write_text('\n'.join(lines),encoding='utf-8')
        os.rename(tmp,output)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resultados',required=True,type=Path)
    parser.add_argument('--fallos',required=True,type=Path)
    parser.add_argument('--raiz-imagenes',required=True,type=Path)
    parser.add_argument('--salida-dir',required=True,type=Path)
    parser.add_argument('--modo',choices=['preparar','inferir'],default='inferir')
    parser.add_argument('--controles',type=int,default=12)
    parser.add_argument('--resoluciones',default='512,640,768')
    args=parser.parse_args(argv)
    try:
        sizes=tuple(int(x.strip()) for x in args.resoluciones.split(','))
        report=evaluate(args.resultados,args.fallos,args.raiz_imagenes,args.salida_dir,
                        mode=args.modo,controls=args.controles,sizes=sizes)
        print(json.dumps({'estado':report['estado'],'fallos':10,
                          'controles':report['controles_automaticos_sin_revision_humana'],
                          'escenarios':report['comparacion_por_resolucion']},ensure_ascii=False))
        return 0
    except (DiagnosticoError,OSError,ValueError) as exc:
        print(json.dumps({'estado':'error_diagnostico','detalle':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
