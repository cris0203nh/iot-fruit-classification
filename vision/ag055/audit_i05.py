"""Read-only final audit of frozen AG-055 data, artifacts and routing. No fitting."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

from .experimental import (TASKS, audit_splits, describe, dump, model_scores, private,
                           rows, safe, score, sha, validate_artifact)
from .uncertainty import assess, load_policy


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def audit(run, i04, output):
    records=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
    report=json.loads((run/'report.json').read_text(encoding='utf-8'))
    version=sha(json.dumps([(r['id'],r['sha256'],r['label'],r['group'],r['excluded']) for r in records],sort_keys=True).encode())
    if version!=report['dataVersion']:
        raise ValueError('Manifest data version mismatch')
    audit_splits([r for r in records if r.get('split')])
    for key in ('sha256','pixelSha256'):
        active=[r[key] for r in records if r.get('split')]
        if len(active)!=len(set(active)):
            raise ValueError('Retained exact duplicates')
    for r in records:
        if digest(safe(Path(r['root']),r['relative']))!=r['sha256']:
            raise ValueError('Changed original image: '+r['id'])
    real=Path(next(r['root'] for r in records if r['source']=='TQ'))
    by_id={r['id']:r for r in records}
    relations=rows(real/'metadata/duplicados_y_relaciones.csv')
    if not all(by_id[e['imagen_a']]['group']==by_id[e['imagen_b']]['group'] for e in relations):
        raise ValueError('Known relation split across groups')
    package_files=0
    for root in {Path(r['root']) for r in records}:
        for r in rows(root/'metadata/sha256_archivos.csv'):
            path=safe(root,r['archivo_relativo'])
            if digest(path)!=r['sha256'] or path.stat().st_size!=int(r['bytes']):
                raise ValueError('Package integrity mismatch')
            package_files+=1
    for entry in report['integrity']:
        if digest(entry['archive'])!=entry['zipSha256']:
            raise ValueError('Archive changed')
    policy_path=i04/'uncertainty_policy.json'
    result={'dataVersion':version,'imagesVerified':len(records),'packageFilesVerified':package_files,
        'knownRelationsVerified':len(relations),'retainedExactDuplicates':0,'knownLeakageDetected':False,
        'policySha256':digest(policy_path),'thresholdsModified':False,'modelsTrained':False,
        'physicalIndependenceAccredited':False,'kentAccredited':False,'e0e1e2Accredited':False,
        'exclusions':dict(Counter(r['excluded'].split(':')[0] for r in records if r['excluded'])),'tasks':{}}
    previous=json.loads((i04/'uncertainty_policy_evaluation.json').read_text(encoding='utf-8'))
    for task,(_,labels) in TASKS.items():
        model_path=run/'models'/f'ag055_exploratory_{task}.json'
        artifact=json.loads(model_path.read_text(encoding='utf-8')); validate_artifact(artifact)
        if artifact['dataVersion']!=version:
            raise ValueError('Model data mismatch')
        policy=load_policy(policy_path,task,digest(model_path),version)
        if task!='FG' and not policy:
            raise ValueError('Frozen policy mismatch')
        splits={}
        missed=[]
        for split in ('validation','test'):
            rr=[r for r in records if r['source']==task and r.get('split')==split and not r['excluded']]
            predictions=[]; targets=[]; flags=[]; errors=[]; rotten=[]; fn=[]
            binary_predictions=[]; binary_targets=[]
            for r in rr:
                raw=safe(Path(r['root']),r['relative']).read_bytes()
                features,roi,method,pixels=describe(raw)
                if pixels!=r['pixelSha256'] or roi!=r['roi'] or method!=r['roiMethod']:
                    raise ValueError('Descriptor/ROI drift: '+r['id'])
                scores=model_scores(artifact['model'],features)[0]
                predicted=int(scores.argmax()); actual=labels.index(r['label'])
                prediction={'task':task,'label':labels[predicted],
                    'scoresUncalibrated':dict(zip(labels,map(float,scores)))}
                routing=assess(prediction,policy)
                predictions.append(predicted); targets.append(actual)
                if task=='SEN':
                    binary_predictions.append(int(scores[labels.index('Healthy')]<.5))
                    binary_targets.append(int(r['label']!='Healthy'))
                flags.append(routing['priority']=='priority'); errors.append(actual!=predicted)
                rotten.append(task=='TQ' and r['label']=='Rotten')
                fn.append(task=='TQ' and r['label']=='Rotten' and labels[predicted]=='Fresh')
                if split=='test' and fn[-1] and not flags[-1]:
                    missed.append({'id':r['id'],'sha256':r['sha256'],'originalLabel':r['label'],
                        'prediction':prediction,'routing':routing,'roi':roi,'roiMethod':method,
                        'imagePath':str(safe(Path(r['root']),r['relative'])),
                        'note':'Descriptive audit only; not a human review or agronomic diagnosis'})
            metrics=score(targets,predictions,labels)
            expected=artifact['evaluation'][split][artifact['evaluation']['selectedOnValidation']]
            if metrics['confusionMatrix']!=expected['confusionMatrix'] or not np.isclose(metrics['f1Macro'],expected['f1Macro'],atol=1e-10):
                raise ValueError('Frozen model metrics drift: '+task+' '+split)
            n=len(rr); err=sum(errors); fn_count=sum(fn); rotten_count=sum(rotten)
            prioritized_errors=sum(e and f for e,f in zip(errors,flags))
            prioritized_fn=sum(e and f for e,f in zip(fn,flags))
            splits[split]={'metrics':metrics,'images':n,'priorityImages':sum(flags),
                'priorityFraction':sum(flags)/n,'originalErrors':err,'errorsPrioritized':prioritized_errors,
                'errorCoverage':prioritized_errors/err if err else None,
                'rottenImages':rotten_count,'rottenPrioritized':sum(e and f for e,f in zip(rotten,flags)),
                'falseNegativeRotten':fn_count,'falseNegativeRottenPrioritized':prioritized_fn,
                'falseNegativeCoverage':prioritized_fn/fn_count if fn_count else None,
                'falseNegativeRottenNotPrioritized':fn_count-prioritized_fn,
                'manualTimeSavedMeasured':False,'allPredictionsStillRequireHumanReview':True}
            if task=='SEN':
                binary=score(binary_targets,binary_predictions,['Healthy','ListedDisease'])
                expected_binary=artifact['evaluation']['healthyVsListedDiseases'][split][artifact['evaluation']['selectedOnValidation']]
                if binary['confusionMatrix']!=expected_binary['confusionMatrix']:
                    raise ValueError('Grouped healthy/disease metrics drift')
                splits[split]['healthyVsListedDiseaseMetrics']=binary
            if split=='test' and task!='FG':
                old=previous['tasks'][task]
                if (old['testImages'],old['priorityReviewImages'],old['originalErrors'],old['errorsRoutedToPriority'])!=(n,sum(flags),err,prioritized_errors):
                    raise ValueError('Routing differs from I04')
        result['tasks'][task]={'modelSha256':digest(model_path),'modelVersion':artifact['version'],
            'selectedModel':artifact['evaluation']['selectedOnValidation'],'splits':splits,
            'nonPrioritizedFalseNegatives':missed,'fgradeDiagnosticOnly':task=='FG'}
    dump(private(output),result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--i04',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args()
    result=audit(a.run,a.i04,a.output)
    print(json.dumps({'verifiedImages':result['imagesVerified'],'knownRelations':result['knownRelationsVerified'],
        'nonPrioritizedFalseNegatives':[r['id'] for r in result['tasks']['TQ']['nonPrioritizedFalseNegatives']]}))
