"""Train reproducible V2 ONLY on the 117 development photos; never consumes 40 labels/photos."""
import argparse
import json
import platform
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import sklearn
from PIL import Image
from sklearn.model_selection import GroupKFold
from sklearn.svm import SVC

from .experimental import dump,private,safe,sha,score
from .v2 import VERSION,FEATURE_VERSION,LABELS,features,predict


def robust_fit(x):
    center=np.median(x,axis=0)
    scale=np.maximum(np.percentile(x,75,axis=0)-np.percentile(x,25,axis=0),.05)
    return center,scale


def transform(x,center,scale):
    z=np.asarray(x,dtype=np.float32).copy()
    np.subtract(z,center,out=z,casting='unsafe');np.divide(z,scale,out=z,casting='unsafe')
    return z


def grouping(records,similarity):
    parent=list(range(len(records)))
    def root(i):
        while i!=parent[i]:parent[i]=parent[parent[i]];i=parent[i]
        return i
    def union(a,b):parent[root(b)]=root(a)
    for i,r in enumerate(records):
        for j,s in enumerate(records[:i]):
            if r['product']==s['product'] and any(r.get(k) and r.get(k)==s.get(k) for k in ('group','previousGroup','sha256','pixelSha256')):
                union(i,j)
    paths={r['relative']:i for i,r in enumerate(records)}
    for edge in similarity['newHeuristicPairs']:
        if edge['a'] in paths and edge['b'] in paths:union(paths[edge['a']],paths[edge['b']])
    return [str(root(i)) for i in range(len(records))]


def train(pilot,output):
    output=private(output)
    if output.exists():raise FileExistsError('Fresh private output required')
    manifest=json.loads((pilot/'manifest.json').read_text(encoding='utf-8'))
    if len(manifest)!=117:raise ValueError('Only original pilot117 development is authorized')
    if len({r['sha256'] for r in manifest})!=117 or len({r['pixelSha256'] for r in manifest})!=117:
        raise ValueError('Duplicate development bytes/pixels require explicit audit before training')
    # Deny-list hashes only, NOT images, labels, predictions or metrics of the 40.
    denied={r['sha256'] for r in json.loads((pilot/'independent_evaluation_candidates.json').read_text(encoding='utf-8'))['candidates']}
    if denied & {r['sha256'] for r in manifest}:raise ValueError('Forbidden exploratory photo in development')
    similarity=json.loads((pilot/'similarity_audit.json').read_text(encoding='utf-8'))
    protected=json.loads((pilot/'baseline.json').read_text(encoding='utf-8'))
    for p in [pilot/'manifest.json',pilot/'similarity_audit.json',*sorted((pilot/'models').glob('*.json'))]:
        protected[str(p)]=sha(p.read_bytes())
    raws={}
    for r in manifest:
        raw=safe(Path(r['root']),r['relative']).read_bytes()
        if sha(raw)!=r['sha256']:raise ValueError('Development image changed')
        raws[r['id']]=raw;protected[str(safe(Path(r['root']),r['relative']))]=r['sha256']
    if any(sha(Path(p).read_bytes())!=h for p,h in protected.items()):raise ValueError('Protected input changed')
    groups=grouping(manifest,similarity)
    output.mkdir(parents=True);(output/'models').mkdir();(output/'masks').mkdir()
    rows=[];vectors=[]
    from .v2 import segment
    for r,g in zip(manifest,groups):
        x,seg=features(raws[r['id']]);rows.append({**r,'v2Group':g,'segmentation':seg,'evaluable':x is not None})
        vectors.append(x)
        rgb,mask,_=segment(raws[r['id']])
        if mask is not None:
            display=rgb.copy();display[~mask]=128
            Image.fromarray(display).save(output/'masks'/f"{r['sourceImageId']}.png")
    dump(output/'manifest.json',rows)
    report={'version':VERSION,'featureVersion':FEATURE_VERSION,'developmentOnly':True,
            'exactByteDuplicates':0,'pixelDuplicates':0,'rubricAudit':'tomato-ext-v0.1 documentary R05/R07/R09; no accredited mango rubric found; labels unchanged, expert approval pending',
            'exploratory40UsedForSelection':False,'physicalIndependenceAccredited':False,
            'kentAccredited':False,'perProduct':{},'seed':5502,
            'selectionProtocol':'GroupKFold 3, whole known components; C in [0.5,3], gamma=scale; train-only median/IQR floor .05; max pooled macro F1, ties smaller C; missing-training-class folds blocked',
            'runtime':{'python':platform.python_version(),'numpy':np.__version__,'sklearn':sklearn.__version__,'opencv':cv2.__version__},
            'limitations':['Provisional original labels, missing approved rubric/reviewer metadata',
                           'Internal selection metrics are optimistic, NOT external performance',
                           'Heuristic segmentation not human verified; masks may fail',
                           'Technical groups do not establish physical fruit identity']}
    ambiguity=[]
    for e in similarity['newHeuristicPairs']:
        if e.get('crossLabel'):
            ambiguity.append({'kind':'perceptually_similar_cross_grade','images':[e['a'],e['b']],
                              'hamming63':e['hamming63'],'decision':'human rubric decision needed; unchanged'})
    report['shortAmbiguityList']=ambiguity[:3]+[
        {'kind':'tomato_grade_boundary','scope':'E1/E2 Rotten: shrivelling vs localized damage; decide with approved rubric, labels unchanged'},
        {'kind':'rubric_not_accredited','scope':'All 117 lack rubric/reviewer/date; E0 is not automatically Healthy/Fresh; no semantic coherence certification'}]
    for product in ('mango','tomate'):
        ids=[i for i,r in enumerate(rows) if r['product']==product and r['evaluable']]
        if set(rows[i]['label'] for i in ids)!=set(LABELS):raise ValueError('Segmentation left a product without three classes: '+product)
        x=np.array([vectors[i] for i in ids],dtype=np.float32);y=np.array([LABELS.index(rows[i]['label']) for i in ids])
        gg=np.array([groups[i] for i in ids]);folds=[];blocked=[]
        if len(set(gg))>=2:
            for k,(tr,va) in enumerate(GroupKFold(n_splits=min(3,len(set(gg)))).split(x,y,gg)):
                assert not(set(gg[tr])&set(gg[va]))
                if len(set(y[tr]))<3:
                    blocked.append({'fold':k,'reason':'training_class_missing','validationIds':[rows[ids[i]]['id'] for i in va]});continue
                folds.append((k,tr,va))
        candidates=[]
        for c in (.5,3.):
            truth=[];pred=[];fold_results=[]
            for k,tr,va in folds:
                center,scale=robust_fit(x[tr]);model=SVC(C=c,kernel='rbf',gamma='scale',class_weight='balanced',random_state=5502)
                model.fit(transform(x[tr],center,scale),y[tr]);p=model.predict(transform(x[va],center,scale))
                truth.extend(y[va].tolist());pred.extend(p.tolist())
                fold_results.append({'fold':k,'trainIds':[rows[ids[i]]['id'] for i in tr],
                    'validationIds':[rows[ids[i]]['id'] for i in va],
                    'metrics':score(y[va],p,LABELS),'centerSha256':sha(np.asarray(center).tobytes()),'scaleMinimum':float(scale.min())})
            candidates.append({'C':c,'metrics':score(truth,pred,LABELS) if truth else None,'folds':fold_results})
        best=max(candidates,key=lambda a:((a['metrics']['f1Macro'] if a['metrics'] else -1),-a['C']))
        center,scale=robust_fit(x);z=transform(x,center,scale)
        model=SVC(C=best['C'],kernel='rbf',gamma='scale',class_weight='balanced',random_state=5502).fit(z,y)
        artifact={'version':VERSION,'featureVersion':FEATURE_VERSION,'product':product,'task':'PILOT117_V2',
                  'labels':LABELS,'labelSpace':'pilot_declared_e0e1e2_v2','deploymentAuthorized':False,
                  'humanReviewRequired':True,'independentTestMetrics':None,'kentAccredited':False,
                  'trainingImageHashes':[rows[i]['sha256'] for i in ids],
                  'dataVersion':sha((pilot/'manifest.json').read_bytes()),'limitations':report['limitations'],
                  'selectedC':best['C'],'scaler':'train_only_median_IQR_floor005',
                  'model':{'mean':center.tolist(),'scale':scale.tolist(),'gamma':float(model._gamma),
                      'supportVectors':model.support_vectors_.tolist(),'dualCoef':model.dual_coef_.tolist(),
                      'intercept':model.intercept_.tolist(),'supportCounts':model.n_support_.tolist()}}
        # Runtime parity on ALL accepted development images, without fitting again.
        predicted=model.predict(z);parity=[]
        for i,index in enumerate(ids):
            p=predict(artifact,raws[rows[index]['id']]);assert p['evaluable'] and p['label']==LABELS[int(predicted[i])]
            parity.append({'id':rows[index]['id'],'label':p['label']})
        dump(output/'models'/f'ag055_v2_{product}.json',artifact)
        report['perProduct'][product]={'nOriginal':sum(r['product']==product for r in rows),'nEvaluable':len(ids),
             'nonEvaluableReasons':dict(Counter(r['segmentation']['reason'] for r in rows if r['product']==product and not r['evaluable'])),
             'acceptedClassCounts':dict(Counter(rows[i]['label'] for i in ids)),'technicalGroups':len(set(gg)),
             'blockedFolds':blocked,'candidates':candidates,'selectedC':best['C'],
             'selectedInternalMetrics':best['metrics'],'missingInternalValidationClasses':[g for g in LABELS if best['metrics'] is None or best['metrics']['perClass'][g]['support']==0],
             'resubstitution_notValidation':score(y,predicted,LABELS),'jsonRuntimeParityCount':len(parity),
             'goldenDevelopmentPredictions':parity}
    if any(sha(Path(p).read_bytes())!=h for p,h in protected.items()):raise RuntimeError('Original input changed')
    dump(output/'report.json',report);dump(output/'protected.json',protected)
    dump(output/'SHA256SUMS.json',{p.relative_to(output).as_posix():sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()})
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pilot',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=train(a.pilot,a.output)
    print(json.dumps({p:{k:v for k,v in r['perProduct'][p].items() if k not in ('candidates','goldenDevelopmentPredictions')} for p in r['perProduct']},indent=2))
