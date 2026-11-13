"""Inference-only JSON adapter for the supplied 117-photo SVC pilot. No fitting/pickle."""
import io
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from .experimental import sha

VERSION='ag055-pilot117-svc-rbf-v1'
FEATURE_VERSION='pilot117-global-676-opencv-v1'
LABELS=['E0','E1','E2']


def features(raw):
    # Exact audited descriptor from the supplied train_pilot.py. Whole image,
    # including background: no automatic fruit ROI or human verification claimed.
    with Image.open(io.BytesIO(raw)) as original:
        img=ImageOps.exif_transpose(original).convert('RGB')
    if min(img.size)<32 or img.width*img.height>40_000_000:
        raise ValueError('Unsupported image dimensions')
    a=np.asarray(img.resize((96,96)),dtype=np.uint8)
    bgr=cv2.cvtColor(a,cv2.COLOR_RGB2BGR)
    gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)
    hsv=cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV)
    coarse=cv2.resize(gray,(24,24),interpolation=cv2.INTER_AREA).astype(np.float32).ravel()/255.
    color=[]
    for array in (a,hsv):
        for ch in range(3):
            h=cv2.calcHist([array],[ch],None,[16],[0,180 if array is hsv and ch==0 else 256]).ravel()
            color.extend((h/max(h.sum(),1)).tolist())
    stats=np.array([gray.mean()/255.,gray.std()/255.,cv2.Laplacian(gray,cv2.CV_64F).var()/10000.,
                    np.count_nonzero(cv2.Canny(gray,50,150))/gray.size],dtype=np.float32)
    return np.concatenate((coarse,np.array(color,dtype=np.float32),stats)).astype(np.float32),[0,0,img.width,img.height]


def validate(artifact,product=None):
    if (artifact.get('version')!=VERSION or artifact.get('featureVersion')!=FEATURE_VERSION
        or artifact.get('labels')!=LABELS or artifact.get('labelSpace')!='pilot_declared_e0e1e2'
        or artifact.get('product') not in ('mango','tomate') or (product and artifact['product']!=product)
        or artifact.get('deploymentAuthorized') is not False or artifact.get('humanReviewRequired') is not True
        or artifact.get('independentTestMetrics') is not None or artifact.get('kentAccredited') is not False):
        raise ValueError('Incompatible pilot artifact')
    model=artifact['model']; count=sum(model['supportCounts'])
    if len(model['supportCounts'])!=3 or not 3<=count<=117 or any(type(n) is not int or n<1 for n in model['supportCounts']):
        raise ValueError('Invalid support counts')
    for key,shape in [('mean',(676,)),('scale',(676,)),('supportVectors',(count,676)),('dualCoef',(2,count)),('intercept',(3,))]:
        a=np.asarray(model[key],dtype=np.float64)
        if a.shape!=shape or not np.isfinite(a).all() or (key=='scale' and np.any(a<=0)):
            raise ValueError('Invalid pilot parameters')
    if not isinstance(model['gamma'],(float,int)) or not np.isfinite(model['gamma']) or model['gamma']<=0:
        raise ValueError('Invalid kernel gamma')
    if not isinstance(artifact['trainingImageHashes'],list) or len(artifact['trainingImageHashes']) not in (56,61):
        raise ValueError('Missing training provenance')


def decision(artifact,vector):
    model=artifact['model']
    # StandardScaler preserves float32 and rounds after each in-place operation.
    x=np.asarray(vector,dtype=np.float32).copy()
    np.subtract(x,np.asarray(model['mean']),out=x,casting='unsafe')
    np.divide(x,np.asarray(model['scale']),out=x,casting='unsafe')
    sv=np.asarray(model['supportVectors'],dtype=np.float64)
    kernel=np.exp(-model['gamma']*((sv-x.astype(np.float64))**2).sum(1))
    dual=np.asarray(model['dualCoef']); counts=model['supportCounts']; starts=np.r_[0,np.cumsum(counts)]
    votes=np.zeros(3,dtype=int); confidences=np.zeros(3); pair_scores=[]
    pair=0
    for i in range(3):
        for j in range(i+1,3):
            a,b=slice(starts[i],starts[i+1]),slice(starts[j],starts[j+1])
            value=float(dual[j-1,a]@kernel[a]+dual[i,b]@kernel[b]+model['intercept'][pair]); pair+=1
            votes[i if value>0 else j]+=1
            confidences[i]+=value; confidences[j]-=value; pair_scores.append(value)
    ovr=votes+confidences/(3*(np.abs(confidences)+1))
    return LABELS[int(votes.argmax())],ovr,pair_scores


def predict(artifact,raw):
    validate(artifact)
    x,roi=features(raw); label,ovr,pairs=decision(artifact,x)
    scores=np.exp(ovr-ovr.max()); scores/=scores.sum()
    return {'label':label,'confidence':float(scores[LABELS.index(label)]),
        'scoresUncalibrated':dict(zip(LABELS,map(float,scores))),
        'decisionScores':dict(zip(LABELS,map(float,ovr))),'ovoDecisionScores':pairs,
        'scoreMethod':'softmax_of_ovr_decision_scores_not_probability',
        'confidenceCalibrated':False,'experimental':True,'proposedGrade':None,
        'modelVersion':VERSION,'task':'PILOT117','roi':roi,'roiMethod':'whole_image_training_descriptor',
        'roiHumanVerified':False,'kentVerified':False,'independentPerformanceEvaluated':False,
        'sampleUse':'training_photo' if sha(raw) in artifact['trainingImageHashes'] else 'unseen_photo_independence_unverified',
        'uncertainty':{'margin':float(np.sort(scores)[-1]-np.sort(scores)[-2]),'priority':'priority',
            'reasons':['confidence_not_calibrated','pilot_independent_performance_unevaluated'],
            'thresholdSource':'unavailable','humanReviewRequired':True,'operationalUseAllowed':False}}


def load_models(directory,product):
    if not directory:
        return []
    base=Path(directory).resolve(); path=base/f'ag055_pilot117_{product}.json'
    if not path.is_file():
        return []
    if not path.resolve().is_relative_to(base) or path.stat().st_size>4*1024*1024:
        raise ValueError('Invalid pilot model path/size')
    raw=path.read_bytes(); model=json.loads(raw);validate(model,product)
    return [(model,sha(raw))]
