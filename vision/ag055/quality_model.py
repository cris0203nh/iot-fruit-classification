"""AG-055: modelo experimental E0/E1/E2 a partir de etiquetas humanas acreditables.

La auditoría estructural NO prueba independencia, competencia del revisor ni
validez agronómica. No autoriza decisiones automáticas de producción.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from vision.evaluation.agrop42.comparar_calidad_ag034 import (
    FEATURES, LABELS, QualityError, _features, aggregate_pieces,
    connected_groups, fit_light, fit_rule, load_eligible, metrics,
    predict_light, predict_rule, split_groups, read_csv,
)

VERSION = 'ag055-quality-experimental-v1'
PRODUCTS = ('mango', 'tomate')


def probabilities(model: dict, features: list[float]) -> dict[str, float]:
    """Softmax de regresión; puntuaciones NO son probabilidades calibradas."""
    if len(features) != len(FEATURES):
        raise QualityError('Dimensión de características incompatible')
    if model.get('algoritmo') != 'softmax_l2_python' or model.get('clases') != list(LABELS):
        raise QualityError('Modelo no compatible')
    weights, means, scales = model['pesos'], model['medias_train'], model['escalas_train']
    if (len(weights) != 3 or any(len(w) != len(FEATURES)+1 for w in weights)
            or len(means) != len(FEATURES) or len(scales) != len(FEATURES)
            or any(not math.isfinite(v) or v <= 0 for v in scales)):
        raise QualityError('Parámetros incompatibles')
    x = [(v - m)/s for v, m, s in zip(features, means, scales)] + [1.0]
    logits = [sum(a*b for a,b in zip(w,x)) for w in weights]
    if not all(math.isfinite(v) for v in logits):
        raise QualityError('Valores numéricos inválidos')
    maxi=max(logits)
    exps=[math.exp(v-maxi) for v in logits]
    den=sum(exps)
    return {c: round(v/den, 8) for c,v in zip(LABELS,exps)}


def predict_artifact(artifact: dict, image_bytes: bytes, roi: list[int]) -> dict:
    if artifact.get('version') != VERSION or artifact.get('deploymentAuthorized') is not False:
        raise QualityError('Artefacto no experimental o incompatible')
    if artifact.get('product') not in PRODUCTS or artifact.get('features') != list(FEATURES):
        raise QualityError('Producto/descriptor no compatible')
    roi_json=json.dumps(roi)
    x=_features(image_bytes,roi_json)
    model=artifact['model']
    if model.get('algoritmo') == 'softmax_l2_python':
        scores=probabilities(model,x)
        grade=max(LABELS,key=lambda c:(scores[c],-LABELS.index(c)))
        return {'proposedGrade':grade,'scoresUncalibrated':scores,'confidenceCalibrated':False}
    if model.get('algoritmo') == 'centroides_rgb':
        grade=predict_rule(model['payload'],x)
        return {'proposedGrade':grade,'scoresUncalibrated':None,'confidenceCalibrated':False}
    raise QualityError('Algoritmo no admitido')


def prepare(csv: Path, images: Path, supports: Path, seed: int=55) -> tuple[dict,dict]:
    rows, evidence=load_eligible(csv,images,supports)
    pieces=aggregate_pieces(rows)
    csv_rows,_=read_csv(csv)
    rubric_by_product={p:{r['rubrica_version'].strip() for r in csv_rows
        if r['producto'].strip()==p and r['estado_revision'].strip()=='etiquetada'}
        for p in PRODUCTS}
    report={'version':VERSION,'sourceCsvSha256':evidence['sha256_csv'],
            'accreditationVerifiedBySoftware':False,
            'deploymentAuthorized':False,'perProduct':{}}
    prepared={}
    for product in PRODUCTS:
        pp=[x for x in pieces if x['producto']==product]
        groups=connected_groups(pp)
        group_counts={label:sum(any(r['y']==label for r in group) for group in groups) for label in LABELS}
        assignment,reason=split_groups(groups,seed=seed)
        row={'pieces':len(pp),'independentComponents':len(groups),
             'componentsPerGrade':group_counts}
        if len(rubric_by_product[product]) > 1:
            reason='Rúbricas distintas para un mismo producto; no mezclar etiquetas'
        if reason:
            report['perProduct'][product]={**row,'status':'blocked_insufficient_data','reason':reason,'metrics':None}
            continue
        splits={k:[] for k in ('entrenamiento','validacion','prueba')}
        for index, group in enumerate(groups):
            splits[assignment[index]].extend(group)
        if any(not splits[k] for k in splits):
            raise QualityError('Partición incompleta')
        # NO se reentrena sobre prueba; selección exclusiva por validación.
        models={'reglas':fit_rule(splits['entrenamiento']),
                'modelo_ligero':fit_light(splits['entrenamiento'])}
        candidates={'reglas':lambda x:predict_rule(models['reglas'],x),
                    'modelo_ligero':lambda x:predict_light(models['modelo_ligero'],x)}
        validation={k:metrics(splits['validacion'],f) for k,f in candidates.items()}
        winner=max(candidates,key=lambda k:(validation[k]['f1_macro'], -list(candidates).index(k)))
        test=metrics(splits['prueba'],candidates[winner])
        prepared[product]={'rubricVersion':next(iter(rubric_by_product[product])),
                           'algorithm':winner,'model':models[winner],
                           'metrics':test,'validation':validation,
                           'splits':{k:len(v) for k,v in splits.items()}}
        report['perProduct'][product]={**row,'status':'experimental_candidate',
            'selectedOnValidation':winner,'splitCounts':prepared[product]['splits'],
            'validationMetrics':validation,'testMetrics':test,
            'limitations':['Etiquetas solo comprobadas estructuralmente',
                'ROI manual de entrenamiento frente a ROI YOLOE en inferencia',
                'Sin validación física ni aprobación de despliegue']}
    return prepared,report


def build_artifact(product: str, candidate: dict, report: dict) -> dict:
    model=candidate['model']
    if candidate['algorithm']=='reglas':
        model={'algoritmo':'centroides_rgb','payload':model}
    payload={'version':VERSION,'product':product,'features':list(FEATURES),
        'model':model,'rubricVersion':candidate['rubricVersion'],
        'sourceCsvSha256':report['sourceCsvSha256'],
        'testMetrics':candidate['metrics'],'validationMetrics':candidate['validation'],
        'trainedAt':datetime.now(timezone.utc).isoformat(),
        'deploymentAuthorized':False,'humanReviewRequired':True,
        'featureAcquisition':'ROI_manual_train_bbox_yoloe_runtime_experimental',
        'verifiedIndependentExternalEvidence':False}
    return payload


def write_new(path: Path, data: dict) -> None:
    if path.exists():
        raise QualityError(f'No se sobrescribe el archivo: {path}')
    if not path.parent.is_dir():
        raise QualityError('El directorio de salida debe existir')
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def main(argv=None) -> int:
    ap=argparse.ArgumentParser(description='AG-055: auditoría y modelos experimentales E0/E1/E2')
    ap.add_argument('--csv',type=Path,required=True)
    ap.add_argument('--imagenes',type=Path,required=True)
    ap.add_argument('--soportes',type=Path,required=True)
    ap.add_argument('--salida-informe',type=Path,required=True)
    ap.add_argument('--exportar-modelos',type=Path,help='Carpeta existente; exporta candidatos SOLO si hay datos elegibles')
    ap.add_argument('--semilla',type=int,default=55)
    args=ap.parse_args(argv)
    try:
        trained,report=prepare(args.csv,args.imagenes,args.soportes,args.semilla)
        write_new(args.salida_informe,report)
        if args.exportar_modelos is not None:
            for product,candidate in trained.items():
                write_new(args.exportar_modelos/f'ag055_quality_{product}.json',
                          build_artifact(product,candidate,report))
    except (QualityError,OSError,ValueError) as e:
        ap.error(str(e))
    print('AG-055 auditoría: '+', '.join(f'{p}={v["status"]}' for p,v in report['perProduct'].items()))
    print('Despliegue autorizado: NO. Revisión humana: SÍ.')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
