"""I04: review routing derived ONLY from frozen validation, never test optimization."""
import argparse
import json
from pathlib import Path

import numpy as np

from .experimental import describe, dump, model_scores, private, safe, sha, validate_artifact

VERSION = 'ag055-review-routing-v1'


def fit_policy(scores, truth, labels):
    scores = np.asarray(scores)
    truth = np.asarray(truth)
    if len(scores) < 20 or len(set(truth)) != len(labels):
        raise ValueError('Insufficient validation coverage')
    ordered = np.sort(scores, axis=1)
    margin = ordered[:, -1] - ordered[:, -2]
    errors = scores.argmax(1) != truth
    threshold = float(np.quantile(margin[errors], .95)) if errors.any() else 1.0
    policy = {'marginThreshold':threshold, 'validationCount':len(truth),
              'validationErrors':int(errors.sum()), 'targetValidationErrorReviewRecall':.95}
    if labels == ['Fresh', 'Rotten']:
        rotten = scores[truth == 1, 1]
        # Largest score threshold retaining >=95% of validation Rotten for review.
        candidates = np.unique(np.r_[0, rotten])
        threshold = max(float(t) for t in candidates if np.mean(rotten >= t) >= .95)
        flagged = (scores[:, 1] >= threshold) | (margin <= policy['marginThreshold'])
        policy.update(rottenReviewThreshold=threshold, validationRottenCount=len(rotten),
            validationRottenReviewRecall=float(flagged[truth == 1].mean()),
            validationReviewFraction=float(flagged.mean()))
    return policy


def assess(prediction, policy=None):
    scores = prediction['scoresUncalibrated']
    values = sorted(scores.values(), reverse=True)
    margin = float(values[0]-values[1])
    reasons = ['confidence_not_calibrated']
    priority = 'normal'
    task = prediction['task']
    if task == 'FG':
        reasons.append('fgrade_diagnostic_only_no_operational_decisions')
        priority = 'diagnostic_only'
    elif not policy:
        reasons.append('no_defensible_validation_policy')
        priority = 'priority'
    else:
        if margin <= policy['marginThreshold']:
            reasons.append('ambiguous_class_margin'); priority = 'priority'
        if task == 'TQ' and (prediction['label']=='Rotten' or scores['Rotten'] >= policy['rottenReviewThreshold']):
            reasons.append('potential_rotten_prioritize_review'); priority = 'priority'
        if task == 'SEN' and prediction['label'] != 'Healthy':
            reasons.append('visible_disease_category_requires_review'); priority = 'priority'
    return {'version':VERSION, 'margin':margin, 'priority':priority, 'reasons':reasons,
            'humanReviewRequired':True, 'confidenceCalibrated':False,
            'operationalUseAllowed':False, 'thresholdSource':'validation_only' if policy else 'unavailable',
            'policy':policy}


def derive(run, output):
    run=private(run); output=private(output)
    records=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
    policies={}
    for task in ('TQ','SEN'):
        path=run/'models'/f'ag055_exploratory_{task}.json'
        raw=path.read_bytes(); model=json.loads(raw); validate_artifact(model)
        validation=[r for r in records if r['source']==task and r.get('split')=='validation' and not r['excluded']]
        features=[]
        for r in validation:
            image=safe(Path(r['root']),r['relative']).read_bytes()
            if sha(image)!=r['sha256']:
                raise ValueError('Changed validation image')
            features.append(describe(image)[0])
        scores=model_scores(model['model'],np.stack(features))
        truth=[model['labels'].index(r['label']) for r in validation]
        policies[task]={'modelSha256':sha(raw), 'dataVersion':model['dataVersion'],
            'validationIdsSha256':sha(json.dumps([r['id'] for r in validation]).encode()),
            'split':'validation', **fit_policy(scores,truth,model['labels'])}
    payload={'version':VERSION,'calibrated':False,'thresholdSelectionSplit':'validation',
             'testUsedForThresholdSelection':False,'tasks':policies}
    dump(output,payload)
    return payload


def load_policy(path, task, model_hash, data_version):
    if not path:
        return None
    try:
        raw=Path(path).read_bytes()
        if len(raw)>65536:
            return None
        payload=json.loads(raw)
        p=payload['tasks'][task]
        if (payload['version']!=VERSION or payload['testUsedForThresholdSelection'] is not False
                or payload['thresholdSelectionSplit']!='validation' or p['split']!='validation'
                or p['modelSha256']!=model_hash or p['dataVersion']!=data_version
                or not 0<=p['marginThreshold']<=1
                or (task=='TQ' and not 0<=p['rottenReviewThreshold']<=1)):
            return None
        return p
    except (OSError,ValueError,KeyError,TypeError):
        return None


def evaluate_frozen_policy(run, policy_path, output):
    """Descriptive held-out evaluation AFTER policy freeze; no threshold fitting here."""
    run=private(run); records=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
    report={'policySha256':sha(Path(policy_path).read_bytes()),'thresholdsModified':False,'tasks':{}}
    for task in ('TQ','SEN'):
        raw=(run/'models'/f'ag055_exploratory_{task}.json').read_bytes(); model=json.loads(raw)
        policy=load_policy(policy_path,task,sha(raw),model['dataVersion'])
        if not policy:
            raise ValueError('Frozen policy does not match model')
        test=[r for r in records if r['source']==task and r.get('split')=='test' and not r['excluded']]
        results=[]
        for r in test:
            image=safe(Path(r['root']),r['relative']).read_bytes()
            if sha(image)!=r['sha256']:
                raise ValueError('Changed test photo')
            scores=model_scores(model['model'],describe(image)[0])[0]
            pred={'task':task,'label':model['labels'][int(scores.argmax())],
                  'scoresUncalibrated':dict(zip(model['labels'],map(float,scores)))}
            results.append({'error':pred['label']!=r['label'],
                'falseNegativeRotten':task=='TQ' and r['label']=='Rotten' and pred['label']=='Fresh',
                'priority':assess(pred,policy)['priority']=='priority'})
        report['tasks'][task]={'testImages':len(results),
            'priorityReviewImages':sum(r['priority'] for r in results),
            'originalErrors':sum(r['error'] for r in results),
            'errorsRoutedToPriority':sum(r['error'] and r['priority'] for r in results),
            'falseNegativeRotten':sum(r['falseNegativeRotten'] for r in results),
            'falseNegativeRottenRoutedToPriority':sum(r['falseNegativeRotten'] and r['priority'] for r in results)}
    dump(private(output),report)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--evaluate-policy',type=Path)
    a=ap.parse_args()
    result=evaluate_frozen_policy(a.run,a.evaluate_policy,a.output) if a.evaluate_policy else derive(a.run,a.output)
    print(json.dumps(result,indent=2))
