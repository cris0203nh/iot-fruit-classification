"""AG-034: contraste exploratorio de identificación visible de producto.

**NO** evalúa defectos E0/E1/E2 ni sustituye comparación de atributos externos.
Compara regla clásica univariada y regresión logística mínima, entrenadas
exclusivamente con el conjunto de entrenamiento. Agrupa por id_ejemplar.
Dependencias: Python estándar y Pillow; no guarda modelos con pickle.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math,random,statistics,time,tracemalloc
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile
from PIL import Image

FEATURES = ('fraccion_cromatica','fraccion_roja','fraccion_naranja','fraccion_amarilla',
            'fraccion_verde','fraccion_azulada','r_normalizada','g_normalizada',
            'b_normalizada','centro_y','aspecto_bbox')

def split_groups(rows, seed=34):
    """Grupos fuente disjuntos; ninguna de tres vistas del mismo ID cruza splits."""
    groups=defaultdict(set)
    for r in rows:
        product=r['producto']
        key=(product,r['id_ejemplar'])
        groups[product].add(key)
    rng=random.Random(seed)
    mapping={}
    for product, keys in sorted(groups.items()):
        keys=sorted(keys)
        if len(keys)<5: raise ValueError('Se requieren >=5 grupos por producto para este protocolo')
        rng.shuffle(keys)
        # 15 ids -> 9 train + 3 val + 3 test. For small n, leave >=1 in each split.
        n=len(keys); test=max(1,round(.2*n)); val=max(1,round(.2*n))
        if n-test-val<2: raise ValueError('Conjunto de entrenamiento insuficiente')
        for i,key in enumerate(keys):
            mapping[key]= 'prueba' if i<test else 'validacion' if i<test+val else 'entrenamiento'
    return mapping

def get_features(image):
    im=image.convert('RGB');im.thumbnail((112,112),Image.Resampling.BILINEAR)
    w,h=im.size
    chrom=[];positions=[];counts=[0,0,0,0,0]
    for index,(r,g,b) in enumerate(im.get_flattened_data()):
        high=max(r,g,b);low=min(r,g,b)
        s=(high-low)/high if high else 0
        if s<.19 or high<35: continue
        vals=(r/255,g/255,b/255)
        chrom.append(vals)
        x=index%w;y=index//w;positions.append((x,y))
        # hues in RGB -> HSV; no background colors used as labels.
        if high==low: hue=0
        elif high==r: hue=((g-b)/(high-low))%6/6
        elif high==g: hue=((b-r)/(high-low)+2)/6
        else: hue=((r-g)/(high-low)+4)/6
        if hue<.055 or hue>=.945: counts[0]+=1
        elif hue<.115: counts[1]+=1
        elif hue<.20: counts[2]+=1
        elif hue<.51: counts[3]+=1
        else: counts[4]+=1
    n=max(len(chrom),1)
    if chrom:
        mean=[sum(p[c] for p in chrom)/n for c in range(3)]
        xs=[v[0] for v in positions];ys=[v[1] for v in positions]
        aspect=(max(xs)-min(xs)+1)/(max(ys)-min(ys)+1)
        cy=sum(ys)/n/max(1,h-1)
    else: mean=[0,0,0];aspect=0;cy=.5
    return [len(chrom)/(w*h),*[v/n for v in counts],*mean,cy,aspect]

def choose_classical(train):
    """Selecciona UNA característica + umbral únicamente en train."""
    candidates=[]
    for k in range(len(FEATURES)):
        vs=sorted(set(row['features'][k] for row in train))
        cutpoints=[vs[0]-.000001]+[(a+b)/2 for a,b in zip(vs,vs[1:])]+[vs[-1]+.000001]
        for orientation in [1,-1]:
            for cut in cutpoints:
                score=sum((1 if orientation*(row['features'][k]-cut)>=0 else 0)==row['y'] for row in train)
                candidates.append((-score,k,orientation,cut))
    _,k,orientation,cut=min(candidates)
    return {'indice':k,'feature':FEATURES[k],'orientacion':orientation,'umbral':cut}

def rule_predict(model,x):
    return int(model['orientacion']*(x[model['indice']]-model['umbral'])>=0)

def fit_linear(train):
    mean=[statistics.fmean(r['features'][i] for r in train) for i in range(len(FEATURES))]
    scale=[max(statistics.pstdev(r['features'][i] for r in train),.035) for i in range(len(FEATURES))]
    dim=len(FEATURES);w=[0.0]*dim;b=0.0
    x=[[(r['features'][i]-mean[i])/scale[i] for i in range(dim)] for r in train]
    labels=[r['y'] for r in train]
    for _ in range(850):
        grads=[0.0]*dim;gb=0.0
        for xx,y in zip(x,labels):
            z=max(-40,min(40,sum(a*v for a,v in zip(w,xx))+b)); p=1/(1+math.exp(-z));err=p-y
            gb+=err
            for i in range(dim):grads[i]+=err*xx[i]
        rate=.1/len(x)
        for i in range(dim):w[i]-=rate*(grads[i]+len(x)*.035*w[i])
        b-=rate*gb
    return {'pesos':w,'bias':b,'media_train':mean,'escala_train':scale,'algoritmo':'regresion_logistica_l2_python'}

def linear_predict(model,features):
    z=model['bias']+sum(w*(x-m)/s for w,x,m,s in zip(model['pesos'],features,model['media_train'],model['escala_train']))
    return int(z>=0)

def metrics(rows,predictor):
    classes={0:'mango',1:'tomate'}
    correct=sum(int(predictor(row['features'])==row['y']) for row in rows)
    recalls={}
    conf={'mango':{'mango':0,'tomate':0},'tomate':{'mango':0,'tomate':0}}
    for r in rows:
        truth=classes[r['y']];pred=classes[predictor(r['features'])]
        conf[truth][pred]+=1
    for k in conf:
        n=sum(conf[k].values());recalls[k]=conf[k][k]/n if n else None
    return {'n_vistas':len(rows),'accuracy_vistas':correct/len(rows) if rows else None,
        'recall_por_producto':recalls,'balanced_accuracy_vistas':sum(v for v in recalls.values() if v is not None)/len(recalls),
        'matriz_confusion_fuente':conf}

def run(zip_path,output):
    rows=[];tracemalloc.start();tstart=time.perf_counter()
    with ZipFile(zip_path) as z:
        if 'trazabilidad.csv' not in z.namelist():raise ValueError('Falta trazabilidad.csv')
        listing={i.filename for i in z.infolist()}
        csvrows=list(csv.DictReader(io.StringIO(z.read('trazabilidad.csv').decode('utf-8-sig'))))
        seen=set()
        for r in csvrows:
            path=r['archivo'];prod='mango' if path.startswith('mangos/') else 'tomate' if path.startswith('tomates/') else None
            if not prod or path not in listing or path in seen or '..' in Path(path).parts:raise ValueError('Inventario inválido')
            if r['id_ejemplar'] in ('',None):raise ValueError('id_ejemplar no declarado')
            data=z.read(path);sha=hashlib.sha256(data).hexdigest()
            if sha!=r['sha256'].lower():raise ValueError('SHA-256 no coincide: '+path)
            seen.add(path)
            with Image.open(io.BytesIO(data)) as im:
                tic=time.perf_counter();feat=get_features(im);duration_ms=(time.perf_counter()-tic)*1000
            rows.append({'path':path,'producto':prod,'id_ejemplar':r['id_ejemplar'],'y':int(prod=='tomate'),
                'features':feat,'t_extraccion_ms':duration_ms})
    groups=split_groups(rows)
    for row in rows:row['split']=groups[(row['producto'],row['id_ejemplar'])]
    tr=[r for r in rows if r['split']=='entrenamiento']
    va=[r for r in rows if r['split']=='validacion']
    te=[r for r in rows if r['split']=='prueba']
    rule=choose_classical(tr)
    model=fit_linear(tr)
    rules_pred=lambda x:rule_predict(rule,x)
    linear_pred=lambda x:linear_predict(model,x)
    def latency(predict):
        data=[r['features'] for r in te]
        tic=time.perf_counter()
        for _ in range(1000):
            for xx in data:predict(xx)
        return (time.perf_counter()-tic)*1000/(1000*len(data))
    checks={'reglas':metrics(te,rules_pred),'modelo_ligero':metrics(te,linear_pred)}
    valchecks={'reglas':metrics(va,rules_pred),'modelo_ligero':metrics(va,linear_pred)}
    # Un mismo ID fuente nunca cuenta como grupos separados.
    for x,y in [('entrenamiento','prueba'),('entrenamiento','validacion'),('prueba','validacion')]:
        assert not {(r['producto'],r['id_ejemplar']) for r in rows if r['split']==x}&{(r['producto'],r['id_ejemplar']) for r in rows if r['split']==y}
    sample_prediction=[]
    for r in te:
        sample_prediction.append({'archivo':r['path'],'id_ejemplar':r['id_ejemplar'],'producto_fuente':r['producto'],
            'reglas': ['mango','tomate'][rules_pred(r['features'])], 'modelo_ligero':['mango','tomate'][linear_pred(r['features'])]})
    _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    result={
      'id':'AG-034','alcance':'CONTROL AUXILIAR identificacion mango/tomate por imagen, NO estado E0/E1/E2',
      'origen':'90 imagenes externas; mango Ataulfo vs tomate Fruits-360; fuente ligada al producto',
      'criterio_de_particion':'por (producto,id_ejemplar), 9/3/3 grupos por producto, semilla=34',
      'totales':{'vistas':len(rows),'grupos_fuente':len(groups),'vistas_train':len(tr),'vistas_val':len(va),'vistas_test':len(te)},
      'regla_clasica_ajustada_solo_train':rule,
      'modelo_ligero':{'nombre':model['algoritmo'],'numero_parametros':len(model['pesos'])+1,'serializacion_sin_pickle_bytes':len(json.dumps(model).encode())},
      'evaluacion_prueba_comun':checks,'evaluacion_validacion':valchecks,
      'predicciones_test':sample_prediction,
      'tiempo_ms_por_vista_cpu':{'extraccion_mediana':statistics.median(r['t_extraccion_ms'] for r in rows),
          'reglas_inferencia':latency(rules_pred),'modelo_inferencia':latency(linear_pred)},
      'pico_tracemalloc_mib_py':round(peak/(1024*1024),2),
      'advertencias':[
       'Los identificadores fuente no equivalen a sesiones físicas verificadas; prueba de ausencia de fuga por ID, no por instalación/cámara.',
       'La separación de fuentes coincide con las clases (Ataulfo vs Fruits-360), por lo que puede existir fuga por dominio/fondo/encuadre.',
       'Las etiquetas de producto no son etiquetas de atributos externos ni grados E0/E1/E2.',
       'El pico tracemalloc mide asignaciones Python; NO es medición integral de RAM nativa ni benchmark ESP32.',
       'Los tiempos dependen de CPU y entorno; no extrapolar a estación final.',
       'Una exactitud alta en esta tarea auxiliar no demuestra segmentación correcta ni clasificación de defectos.'
      ],
      'AG034_cierre_total_acreditado':False,
      'proximo': 'Revisar y etiquetar por rúbrica los defectos, capturar Kent y formar prueba independiente para comparación real de atributos.'
    }
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--zip',required=True,type=Path);p.add_argument('--salida',required=True,type=Path);a=p.parse_args()
    out=run(a.zip,a.salida)
    print(json.dumps({k:out[k] for k in ('totales','evaluacion_prueba_comun','AG034_cierre_total_acreditado')},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
