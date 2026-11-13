"""Frozen blind review package and deferred, eligibility-gated evaluation. Never trains."""
import argparse
import csv
import hashlib
import io
import json
import random
import re
import zipfile
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image,ImageOps

from .experimental import dump,private,safe,sha,score

FIELDS=['foto_id','producto','sha256_imagen','grado_humano','justificacion','criterios_Rxx',
    'ubicacion_evidencia_visible','rubrica_version','revisor_id','fecha_revision_iso',
    'exposicion_previa_a_predicciones_o_clases','soporte_revision_relativo','duracion_manual_segundos','observaciones']
IDENTITY_FIELDS=['foto_id','fruta_fisica_id','sesion_id','independencia_confirmada','responsable_verificacion',
    'fecha_verificacion_iso','soporte_identidad_relativo','soporte_independencia_entrenamiento_relativo',
    'relaciones_perceptuales_resueltas','soporte_resolucion_relativo','derechos_uso_confirmados']
README='''# AG-055: revisión humana ciega de 40 fotografías

Este paquete NO contiene predicciones, puntuaciones ni categorías sugeridas.
Solo contiene imágenes numeradas de mango genérico y tomate. Kent no está acreditado.
Las imágenes mantienen los bytes originales; no son capturas nuevas de estación.

1. Extraer el ZIP completo. Abrir formulario.html sin conexión, o completar formulario.csv.
2. Examinar cada original de imagenes/F001.jpg a imagenes/F040.jpg y aplicar la rúbrica
   real correspondiente al producto. Registrar su versión y adjuntar su soporte.
3. Elegir explícitamente E0, E1, E2 o no_evaluable. E0: sin defecto externo relevante
   visible; E1: defecto visible que requiere valoración; E2: indicio grave que requiere
   revisión prioritaria. Estas definiciones NO sustituyen una rúbrica aprobada.
4. Escribir justificación, criterio Rxx para E1/E2, localización visible de evidencia,
   identificación real del revisor y fecha REAL con zona horaria (ISO 8601).
   No usar fecha de archivo/importación como fecha de revisión ni inventar soportes.
5. Declarar si ya se conocían predicciones o clases de fuente: no/si/no_sabe.
   No consultar modelos, mapas originales, fuentes con clases ni resultados durante
   la anotación. Si ya los conoce, indicarlo: no se considerará revisión ciega elegible.
6. Guardar el CSV descargado sin alterar foto_id, producto ni SHA. Añadir los soportes
   reales dentro de soportes/. Soporte puede ser un acta auténtica identificando las
   fotografías y la rúbrica; no se exige inventar un archivo firmado por cada vista.
7. Devolver SOLO el formulario completado y sus soportes, preservando el ZIP recibido.
   Corregir guardando una nueva versión; conservar las versiones anteriores.

Para medir duración manual, usar un cronómetro real y registrar segundos observados,
incluidas pausas según protocolo. Dejar vacío si no se midió. No estimar duración con
fechas de archivos. La comparación asistida se realiza después de cerrar esta revisión,
con protocolo aprobado y mediciones reales; este paquete no muestra asistencia.

El custodio conserva fuera de este ZIP los identificadores originales, procedencia,
similitudes y formulario de identidad física. El revisor NO tiene que adivinar identidad,
sesión o variedad a partir de la imagen. Tener SHA diferente NO prueba fruta distinta.
Las etiquetas solas no habilitan evaluación independiente: debe aprobarse también
independencia respecto al entrenamiento y entre muestras de prueba.

No se cerrará AGROP-67 hasta obtener las evidencias experimentales necesarias.
'''


def csv_bytes(records,fields):
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n')
    writer.writeheader();writer.writerows(records)
    return stream.getvalue().encode('utf-8-sig')


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))


def fingerprint(raw):
    with Image.open(io.BytesIO(raw)) as source:
        im=ImageOps.exif_transpose(source).convert('RGB');im.load()
        a=np.array(im.convert('L').resize((32,32)),dtype=np.float32)
        variants=[]
        for mirrored in (a,np.fliplr(a)):
            for turns in range(4):
                d=cv2.dct(np.ascontiguousarray(np.rot90(mirrored,turns)))[:8,:8].ravel()[1:]
                variants.append(d>np.median(d))
        return {'pixels':sha(np.asarray(im).tobytes()+str(im.size).encode()),'bits':np.stack(variants),
            'size':list(im.size),'metadataKeys':sorted(source.info),'rgb32':np.array(im.resize((32,32)),dtype=float)}


def distance(a,b):
    # Transform candidate only; covers D4 rotations/reflections without selecting grades.
    return int(np.count_nonzero(a['bits']!=b['bits'][0],axis=1).min())


def html_form(records):
    # No source names, original classes, model outputs, prior grades or default grades.
    rows=json.dumps([{k:r[k] for k in ('foto_id','producto','sha256_imagen')} for r in records],ensure_ascii=False)
    return r'''<!doctype html><html lang="es"><meta charset="utf-8"><title>AG-055 revisión ciega</title>
<style>body{font:17px system-ui;max-width:950px;margin:auto;padding:16px}img{max-width:100%;max-height:600px}label{display:block;margin:10px 0}input,textarea,select{display:block;width:100%;box-sizing:border-box;padding:10px}button{padding:12px;margin:8px}textarea{min-height:80px}</style>
<h1>Revisión ciega AG-055</h1><p>Leer INSTRUCCIONES.md. No se sugiere ninguna categoría. Guardar el CSV antes de cerrar o recargar; no se transmiten datos a servidores.</p>
<label>Fotografía<select id="selection"></select></label><p id="info"></p><img id="photo" alt="Original numerado">
<div id="fields"></div><button id="previous">Anterior</button><button id="next">Siguiente</button><button id="download">Descargar formulario completo</button><p id="message" role="status"></p>
<script>
const records=ROWS,fields=FIELDS;let index=0;const el=id=>document.getElementById(id);
for(const r of records)for(const k of fields)if(!(k in r))r[k]='';
el('selection').replaceChildren(...records.map((r,i)=>{let o=document.createElement('option');o.value=i;o.textContent=r.foto_id+' · '+r.producto;return o}));
const captions={grado_humano:'Grado humano (obligatorio)',justificacion:'Justificación',criterios_Rxx:'Criterios Rxx aplicados',ubicacion_evidencia_visible:'Ubicación visible de la evidencia',rubrica_version:'Versión de rúbrica',revisor_id:'Revisor real',fecha_revision_iso:'Fecha REAL ISO con zona horaria',exposicion_previa_a_predicciones_o_clases:'¿Conocía predicciones o clases originales?',soporte_revision_relativo:'Soporte real, relativo a soportes/',duracion_manual_segundos:'Duración manual medida (segundos; vacío si no se midió)',observaciones:'Observaciones'};
for(const k of fields.slice(3)){const label=document.createElement('label');label.textContent=captions[k];let input;
 if(k==='grado_humano'||k==='exposicion_previa_a_predicciones_o_clases'){input=document.createElement('select');for(const s of (k==='grado_humano'?['','E0','E1','E2','no_evaluable']:['','no','si','no_sabe'])){let o=document.createElement('option');o.value=s;o.textContent=s||'Seleccionar…';input.append(o)}}else{input=document.createElement(k==='justificacion'||k==='observaciones'?'textarea':'input')}
 input.id=k;input.oninput=()=>records[index][k]=input.value;label.append(input);el('fields').append(label)}
function show(){const r=records[index];el('selection').value=index;el('photo').src='imagenes/'+r.foto_id+'.jpg';el('info').textContent=r.foto_id+' · '+r.producto+' · SHA-256 '+r.sha256_imagen;for(const k of fields.slice(3))el(k).value=r[k]}
el('selection').onchange=e=>{index=+e.target.value;show()};el('previous').onclick=()=>{index=Math.max(0,index-1);show()};el('next').onclick=()=>{index=Math.min(records.length-1,index+1);show()};
el('download').onclick=()=>{const quote=s=>{let t=String(s??'');if('=+-@'.includes(t.charAt(0))&&t.length||t.charCodeAt(0)<32)t="'"+t;return '"'+t.replaceAll('"','""')+'"'};const csv='\uFEFF'+[fields,...records.map(r=>fields.map(k=>r[k]))].map(a=>a.map(quote).join(',')).join('\r\n');const u=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=u;a.download='formulario_completado.csv';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);el('message').textContent='CSV descargado. Revisar y conservar sus soportes.'};show();
</script></html>'''.replace('ROWS',rows).replace('FIELDS',json.dumps(FIELDS))


def prepare(pilot_run,output):
    output=private(output);output.mkdir()
    candidates=json.loads((pilot_run/'independent_evaluation_candidates.json').read_text(encoding='utf-8'))['candidates']
    training=json.loads((pilot_run/'manifest.json').read_text(encoding='utf-8'))
    if len(candidates)!=40 or Counter(r['product'] for r in candidates)!={'mango':20,'tomate':20}:
        raise ValueError('Expected exactly 20 mango and 20 tomato candidates')
    all_rows=[('candidate',r) for r in candidates]+[('training',r) for r in training]
    fingerprints={};raw_images={}
    for scope,r in all_rows:
        raw=safe(Path(r['root']),r['relative']).read_bytes()
        if sha(raw)!=r['sha256']:raise ValueError('Original SHA mismatch: '+r['id'])
        key=(scope,r['id']);fingerprints[key]=fingerprint(raw)
        if scope=='candidate':raw_images[r['id']]=raw
    relationships=[];training_relations=[]
    for i,a in enumerate(candidates):
        fa=fingerprints['candidate',a['id']]
        for scope,b in [('candidate',r) for r in candidates[i+1:]]+[('training',r) for r in training]:
            fb=fingerprints[scope,b['id']];h=distance(fa,fb)
            exact=a['sha256']==b['sha256'];pixels=fa['pixels']==fb['pixels']
            if h<=8 or exact or pixels:
                edge={'candidateId':a['id'],'otherId':b['id'],'otherScope':scope,'minimumHamming63D4':h,
                    'exactBytes':exact,'exactPixels':pixels,'physicalRelationship':'unverified_requires_documentary_resolution'}
                relationships.append(edge)
                if scope=='training':training_relations.append(edge)
    original_root=Path(candidates[0]['root'])
    # Preserve source declarations, but never infer fruit identity or Kent from them.
    import_source={r['imagen_id']:r for r in read_csv(original_root/'metadata/inventario_imagenes.csv')}
    shuffled=list(candidates);random.Random(55040).shuffle(shuffled)
    forms=[];mapping=[]
    for number,r in enumerate(shuffled,1):
        blind_id=f'F{number:03d}';form={k:'' for k in FIELDS}
        form.update(foto_id=blind_id,producto=r['product'],sha256_imagen=r['sha256']);forms.append(form)
        source=import_source[r['id']]
        flags=[e for e in training_relations if e['candidateId']==r['id']]
        mapping.append({**r,'foto_id':blind_id,'sourceDataset':source['dataset'],'sourceAuthor':source['autor'],
            'sourceUrl':source['url_origen'],'license':source['licencia'],'sourceClass':source['clase_original'],
            'trainingSimilarityCandidates':flags,
            'candidateSimilarityCandidates':[e for e in relationships if e['otherScope']=='candidate' and r['id'] in (e['candidateId'],e['otherId'])],
            'imageMetadataKeys':fingerprints['candidate',r['id']]['metadataKeys'],
            'exactTrainingOverlap':any(e['exactBytes'] or e['exactPixels'] for e in flags),
            'physicalIdentityAccredited':False,'pixelSha256':fingerprints['candidate',r['id']]['pixels']})
    model_hashes={p.name:sha(p.read_bytes()) for p in (pilot_run/'models').glob('*.json')}
    protocol={'version':'ag055-independent-blind-v1','modelHashes':model_hashes,'trainingImageHashes':[r['sha256'] for r in training],
        'blindedCandidateCount':40,'classSampleSizeApproved':False,'minimumPerClassPlanningOnly':5,
        'independentPerformanceMetrics':None,'manualAssistedTimingMeasured':False,
        'physicalIdentityAccredited':0,'doNotCloseAGROP67':True}
    audit={'imagesShaVerified':40,'trainingImagesShaVerified':len(training),'exactDuplicateCandidates':40-len({r['sha256'] for r in candidates}),
        'pixelDuplicateCandidates':40-len({fingerprints['candidate',r['id']]['pixels'] for r in candidates}),
        'exactTrainingOverlaps':sum(r['exactTrainingOverlap'] for r in mapping),
        'perceptualPairs':relationships,'candidateTrainingPairs':len(training_relations),
        'candidatesWithPerceptualTrainingRelations':len({r['candidateId'] for r in training_relations}),
        'method':'PIL oriented L bicubic32, OpenCV DCT8x8 excluding DC; median63; min over 8 D4 candidate transforms; Hamming<=8',
        'actualPhysicalFruitCount':None,'accreditedPhysicalFruits':{'mango':0,'tomate':0},
        'categoriesNotYetHumanAssigned':True,'independentMetrics':None,
        'deficitVsLegacyPlanningFloor5':{p:{g:5 for g in ('E0','E1','E2')} for p in ('mango','tomate')},
        'note':'Five is an existing technical planning floor, not approval or sufficient sample size for final scientific acceptance; exact new-capture deficit awaits labels, identity supports and approved target.'}
    (output/'custodia').mkdir();dump(output/'custodia/mapping.json',mapping);dump(output/'custodia/protocol.json',protocol)
    dump(output/'custodia/audit.json',audit)
    identity=[{**{k:'' for k in IDENTITY_FIELDS},'foto_id':r['foto_id']} for r in mapping]
    (output/'custodia/identidad_independencia.csv').write_bytes(csv_bytes(identity,IDENTITY_FIELDS))
    (output/'custodia/INSTRUCCIONES_CUSTODIA.md').write_text('''# Solo custodio: NO enviar al revisor ciego
Mantener mapping.json, audit.json y protocol.json separados del ZIP de revisión.
El mapa preserva ID, ruta original, SHA y procedencia/licencia de cada imagen.
No ejecutar modelos ni revelar clases de fuente/predicciones durante la anotación ciega.
No asignar un ID de fruta diferente por foto para aparentar independencia. Confirmar
con registros originales y soportes reales fruta, sesión y separación del entrenamiento.
Las similitudes son indicios, no pruebas de identidad; documentar su resolución.
Los campos de identidad, fecha, responsable y soportes se dejan vacíos hasta verificarlos.
Copiar soportes auténticos bajo una raíz local; usar rutas relativas sin .. ni absolutos.
Los campos completados son declaraciones documentales y no autentican por sí solos evidencia.
Congelar las etiquetas ciegas antes de abrir modelos o comparar predicciones.
No cerrar AGROP-67 ni calcular métricas independientes con datos no elegibles.
''',encoding='utf-8')
    # Neither original IDs/names/classes nor relationship flags enter the reviewer ZIP.
    contents={'INSTRUCCIONES.md':README.encode(),'formulario.csv':csv_bytes(forms,FIELDS),
        'formulario.html':html_form(forms).encode(),
        'LICENCIAS.md':('Fuentes: MangoFruitDDS, Demba Faye, Idy Diop, Nalla Mbaye, MariusMintu Diedhiou y Doudou Dione; CC BY-NC 3.0, https://creativecommons.org/licenses/by-nc/3.0/. Investigación no comercial.\n'
        'Tomato Quality Grading, Tania Khatun, Abdur Razzak, Md. Shofiul Islam y Mohammad Shorif Uddin; espejo Project-AgML; CC BY 4.0, https://creativecommons.org/licenses/by/4.0/.\n'
        'Imágenes sin recodificar ni modificar. La asociación individual fuente/foto queda con el custodio para preservar cegamiento.\n').encode()}
    for r in mapping:contents[f'imagenes/{r["foto_id"]}.jpg']=raw_images[r['id']]
    contents['SHA256SUMS.json']=json.dumps({p:sha(raw) for p,raw in contents.items()},indent=2).encode()
    package=output/'AG055_Revision_Ciega_40.zip'
    with zipfile.ZipFile(package,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name,raw in contents.items():z.writestr(name,raw)
    with zipfile.ZipFile(output/'AG055_Custodia_NO_ENVIAR_AL_REVISOR.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted((output/'custodia').iterdir()):z.write(p,p.name)
    dump(output/'delivery.json',{'blindZipSha256':sha(package.read_bytes()),'blindImages':40,
        'noPredictionsInBlindPackage':True,'originalIdentifiersPreservedSeparately':True,
        'accreditedIndependentFruits':0,'independentMetrics':None})
    return audit


def date_valid(value):
    try:return datetime.fromisoformat(value.replace('Z','+00:00')).utcoffset() is not None
    except (ValueError,AttributeError):return False


def evaluate(package_root,pilot_run,reviews,identity,supports,output):
    """Called ONLY after return of real reviews and documentary independence support.

    Completed fields/support hashes are documentary attestations, not software proof
    of authenticity, reviewer competence or true physical independence.
    """
    custody=package_root/'custodia';mapping=json.loads((custody/'mapping.json').read_text(encoding='utf-8'))
    protocol=json.loads((custody/'protocol.json').read_text(encoding='utf-8'))
    for name,expected in protocol['modelHashes'].items():
        if sha((pilot_run/'models'/name).read_bytes())!=expected:raise ValueError('Frozen model changed')
    human=read_csv(reviews);physical=read_csv(identity)
    if len({r['foto_id'] for r in human})!=len(human) or len({r['foto_id'] for r in physical})!=len(physical):
        raise ValueError('Duplicate review/identity IDs')
    hh={r['foto_id']:r for r in human};ii={r['foto_id']:r for r in physical}
    if set(hh)!={r['foto_id'] for r in mapping} or not set(ii).issubset(hh):raise ValueError('Unexpected/missing blind IDs')
    eligible=[];exclusions=[];fruit_owners={};session_grades={};support_hashes={}
    for m in mapping:
        h=hh[m['foto_id']];p=ii.get(m['foto_id'],{});reasons=[]
        if h['producto']!=m['product'] or h['sha256_imagen']!=m['sha256']:raise ValueError('Fixed review columns changed')
        if h['grado_humano'] not in ('E0','E1','E2','no_evaluable'):reasons.append('human_grade_missing')
        if h['grado_humano']=='no_evaluable':reasons.append('human_no_evaluable')
        if not h['revisor_id'].strip() or not date_valid(h['fecha_revision_iso']):reasons.append('reviewer_or_real_date_missing')
        if not h['rubrica_version'].strip() or len(h['justificacion'].strip())<20 or not h['ubicacion_evidencia_visible'].strip():reasons.append('rubric_or_evidence_missing')
        if h['grado_humano'] in ('E1','E2') and not re.search(r'\bR\d{2}\b',h['criterios_Rxx']):reasons.append('Rxx_required')
        if h['exposicion_previa_a_predicciones_o_clases']!='no':reasons.append('blinding_not_attested')
        if (not p.get('fruta_fisica_id','').strip() or not p.get('sesion_id','').strip()
            or p.get('independencia_confirmada')!='si' or not p.get('responsable_verificacion','').strip()
            or not date_valid(p.get('fecha_verificacion_iso',''))):reasons.append('physical_independence_not_documented')
        if p.get('derechos_uso_confirmados')!='si':reasons.append('use_rights_not_confirmed')
        proofs=[h['soporte_revision_relativo'],p.get('soporte_identidad_relativo',''),p.get('soporte_independencia_entrenamiento_relativo','')]
        if m['trainingSimilarityCandidates'] or m['candidateSimilarityCandidates']:
            if p.get('relaciones_perceptuales_resueltas')!='si':reasons.append('training_similarity_unresolved')
            proofs.append(p.get('soporte_resolucion_relativo',''))
        for proof in proofs:
            try:support_hashes[proof]=sha(safe(supports,proof).read_bytes())
            except (OSError,ValueError):reasons.append('support_missing_or_unsafe')
        raw=safe(Path(m['root']),m['relative']).read_bytes()
        if sha(raw)!=m['sha256']:raise ValueError('Candidate image changed')
        if m['sha256'] in protocol['trainingImageHashes'] or m['exactTrainingOverlap']:reasons.append('training_photo_overlap')
        fruit=(m['product'],p.get('fruta_fisica_id'));session=(m['product'],p.get('sesion_id'))
        if not reasons:
            if fruit in fruit_owners:reasons.append('additional_view_of_same_physical_fruit')
            else:fruit_owners[fruit]=m['foto_id']
        if reasons:exclusions.append({'foto_id':m['foto_id'],'reasons':sorted(set(reasons))})
        else:eligible.append((m,h,p));session_grades.setdefault(session,[]).append(m['foto_id'])
    report={'modelsUnchanged':True,'eligiblePhysicalFruitCounts':{},'exclusions':exclusions,'perProduct':{},
        'supportHashes':support_hashes,'basis':'Documentary independence attestations; authenticity not proven by software',
        'manualVsAssisted':'not_evaluated_no_paired_real_measurements','AGROP67FinalClosureAuthorized':False}
    for product in ('mango','tomate'):
        subset=[(m,h,p) for m,h,p in eligible if m['product']==product]
        counts=Counter(h['grado_humano'] for m,h,p in subset)
        report['eligiblePhysicalFruitCounts'][product]={g:counts[g] for g in ('E0','E1','E2')}
        # Conservative gate: no evaluation promoted when a class lacks the existing
        # planning floor. This floor is NOT final scientific/statistical approval.
        if any(counts[g]<protocol['minimumPerClassPlanningOnly'] for g in ('E0','E1','E2')):
            report['perProduct'][product]={'status':'blocked_insufficient_documented_independent_reviews','metrics':None,'n':len(subset)};continue
        from .pilot117 import predict,validate
        model=json.loads((pilot_run/'models'/f'ag055_pilot117_{product}.json').read_text(encoding='utf-8'));validate(model,product)
        labels=['E0','E1','E2'];truth=[];predicted=[]
        for m,h,p in subset:
            truth.append(labels.index(h['grado_humano']))
            predicted.append(labels.index(predict(model,safe(Path(m['root']),m['relative']).read_bytes())['label']))
        report['perProduct'][product]={'status':'documentary_independent_evaluation_not_automatic_accreditation',
            'n':len(subset),'sessions':len({p['sesion_id'] for m,h,p in subset}),'metrics':score(truth,predicted,labels),
            'limitations':['Independence/support authenticity remains a human responsibility','Small-sample uncertainty and clustered sessions',
                'Kent not accredited','No calibration or threshold tuning performed','Final sample-size approval still pending']}
    dump(private(output),report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--pilot-run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('evaluate');p.add_argument('--package-root',type=Path,required=True);p.add_argument('--pilot-run',type=Path,required=True)
    p.add_argument('--reviews',type=Path,required=True);p.add_argument('--identity',type=Path,required=True)
    p.add_argument('--supports',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='prepare':r=prepare(args.pilot_run,args.output);print(json.dumps({k:v for k,v in r.items() if k!='perceptualPairs'}))
    else:
        r=evaluate(args.package_root,args.pilot_run,args.reviews,args.identity,args.supports,args.output)
        print(json.dumps({'perProduct':r['perProduct'],'eligible':r['eligiblePhysicalFruitCounts']}))
