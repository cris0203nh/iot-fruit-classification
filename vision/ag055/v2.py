"""AG-055 V2: deterministic heuristic fruit ROI, masked descriptor, JSON SVC inference.

No training dependencies at serving time. Segmentation checks are technical guards,
not human verification of fruit identity, lesions, physical independence or Kent.
"""
import io
import json
import threading
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from .experimental import sha
from .pilot117 import LABELS, decision

VERSION = 'ag055-v2-masked-svc-v1'
FEATURE_VERSION = 'fruit-mask-s40-solidity094-128-hsv-s32-robust-floor005-v1'
DIMENSIONS = 128
_lock = threading.Lock()


def segment(raw):
    with Image.open(io.BytesIO(raw)) as source:
        image = ImageOps.exif_transpose(source).convert('RGB')
    w, h = image.size
    if min(w,h)<32 or w*h>40_000_000:
        raise ValueError('Unsupported image size')
    image.thumbnail((320,320),Image.Resampling.LANCZOS)
    rgb=np.asarray(image).copy(); hh,ww=rgb.shape[:2]
    mask=np.zeros((hh,ww),np.uint8)
    mx,my=1,1
    with _lock:
        cv2.setRNGSeed(5502)
        try:
            cv2.grabCut(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),mask,(mx,my,ww-2*mx,hh-2*my),
                        np.zeros((1,65),np.float64),np.zeros((1,65),np.float64),4,cv2.GC_INIT_WITH_RECT)
        except cv2.error:
            return rgb,None,{'reason':'segmentation_failed','roi':[0,0,w,h]}
    binary=np.isin(mask,[cv2.GC_FGD,cv2.GC_PR_FGD]).astype(np.uint8)
    # Conservative chromatic core removes neutral paper/wood and shadows which
    # GrabCut sometimes attaches. Filling its contour below preserves dark lesions
    # and highlights enclosed INSIDE the fruit, rather than erasing those defects.
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    binary &= ((hsv[:,:,1]>=40)&(hsv[:,:,2]>=20)).astype(np.uint8)
    binary=cv2.morphologyEx(binary,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    count,components,stats,_=cv2.connectedComponentsWithStats(binary,8)
    sizes=stats[1:,cv2.CC_STAT_AREA]
    if not len(sizes) or sizes.max()<ww*hh*.08:
        return rgb,None,{'reason':'fruit_not_separated','roi':[0,0,w,h]}
    largest=int(sizes.argmax())+1
    if sum(s>sizes.max()*.15 for s in sizes)>1:
        return rgb,None,{'reason':'multiple_objects_or_uncertain_mask','roi':[0,0,w,h]}
    contours,_=cv2.findContours((components==largest).astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    contour=max(contours,key=cv2.contourArea)
    foreground=np.zeros((hh,ww),np.uint8);cv2.drawContours(foreground,[contour],-1,1,cv2.FILLED)
    area=float(foreground.mean());hull_area=cv2.contourArea(cv2.convexHull(contour))
    solidity=float(cv2.contourArea(contour)/hull_area) if hull_area else 0
    x,y,bw,bh=cv2.boundingRect(contour)
    clipped = x<=mx+1 or y<=my+1 or x+bw>=ww-mx-1 or y+bh>=hh-my-1
    # Shared review contract is x,y,width,height, NOT x1,y1,x2,y2.
    rx,ry=round(x*w/ww),round(y*h/hh)
    info={'roi':[rx,ry,round((x+bw)*w/ww)-rx,round((y+bh)*h/hh)-ry],
          'foregroundFraction':area,'solidity':solidity,'roiMethod':'grabcut_chromatic_core_filled_contour_geometric_guards',
          'roiHumanVerified':False,'segmentationAccredited':False,'partialCoverage':clipped}
    if area>.85 or solidity<.94:
        return rgb,None,{**info,'reason':'excessive_or_irregular_foreground'}
    return rgb,foreground.astype(bool),{**info,'reason':None}


def features(raw):
    rgb,mask,info=segment(raw)
    if mask is None:
        return None,info
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    chromatic=mask & (hsv[:,:,1]>=32)
    if chromatic.sum()<max(32,mask.sum()*.05):
        return None,{**info,'reason':'insufficient_chromatic_fruit'}
    vector=[]
    for data in (rgb,hsv):
        for ch in range(3):
            selected=chromatic if data is hsv and ch==0 else mask
            values=data[:,:,ch][selected]
            hist=np.histogram(values,bins=16,range=(0,180 if data is hsv and ch==0 else 256))[0]
            vector.extend(hist/max(hist.sum(),1))
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    hist=np.histogram(gray[mask],bins=16,range=(0,256))[0]
    vector.extend(hist/max(hist.sum(),1))
    # Gradients only where the complete neighbourhood is inside fruit: no mask edge.
    interior=cv2.erode(mask.astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
    if interior.sum()<32:
        return None,{**info,'reason':'insufficient_fruit_interior'}
    dx=cv2.Sobel(gray,cv2.CV_32F,1,0);dy=cv2.Sobel(gray,cv2.CV_32F,0,1)
    mag,angle=cv2.cartToPolar(dx,dy,angleInDegrees=True)
    orientation=np.histogram(angle[interior],bins=8,range=(0,360),weights=mag[interior])[0]
    vector.extend(orientation/max(orientation.sum(),1))
    for a in (rgb[:,:,0],rgb[:,:,1],rgb[:,:,2],gray):
        vector.extend([float(np.median(a[mask]))/255,float(np.subtract(*np.percentile(a[mask],[75,25])))/255])
    vector=np.asarray(vector,dtype=np.float32)
    assert vector.shape==(DIMENSIONS,) and np.isfinite(vector).all()
    return vector,{**info,'chromaticFruitFraction':float(chromatic.sum()/mask.sum())}


def validate(artifact,product=None):
    if (artifact.get('version')!=VERSION or artifact.get('featureVersion')!=FEATURE_VERSION
        or artifact.get('labels')!=LABELS or artifact.get('product') not in ('mango','tomate')
        or (product and artifact['product']!=product)
        or artifact.get('labelSpace')!='pilot_declared_e0e1e2_v2'
        or artifact.get('deploymentAuthorized') is not False or artifact.get('humanReviewRequired') is not True
        or artifact.get('kentAccredited') is not False or artifact.get('independentTestMetrics') is not None):
        raise ValueError('Incompatible V2 artifact')
    model=artifact['model'];counts=model['supportCounts']
    if len(counts)!=3 or any(type(c) is not int or c<1 for c in counts) or not 3<=sum(counts)<=117:
        raise ValueError('Invalid V2 support counts')
    for name,shape in [('mean',(DIMENSIONS,)),('scale',(DIMENSIONS,)),('supportVectors',(sum(counts),DIMENSIONS)),
                       ('dualCoef',(2,sum(counts))),('intercept',(3,))]:
        a=np.asarray(model[name],dtype=float)
        if a.shape!=shape or not np.isfinite(a).all() or (name=='scale' and (a<.05).any()):
            raise ValueError('Invalid V2 numeric parameters')
    if not isinstance(model['gamma'],(int,float)) or not np.isfinite(model['gamma']) or model['gamma']<=0:
        raise ValueError('Invalid V2 gamma')
    hashes=artifact['trainingImageHashes']
    if not isinstance(hashes,list) or not hashes or len(hashes)>117 or any(not isinstance(h,str) or len(h)!=64 for h in hashes):
        raise ValueError('Invalid V2 provenance')


def predict(artifact,raw):
    validate(artifact)
    vector,roi=features(raw)
    result={'experimental':True,'proposedGrade':None,'confidenceCalibrated':False,
            'modelVersion':VERSION,'featureVersion':FEATURE_VERSION,'task':'PILOT117_V2',
            'roi':roi['roi'],'roiMethod':roi.get('roiMethod','segmentation_failed'),
            'roiHumanVerified':False,'segmentation':roi,'kentVerified':False,
            'independentPerformanceEvaluated':False,
            'sampleUse':'training_photo' if sha(raw) in artifact['trainingImageHashes'] else 'unseen_photo_independence_unverified',
            'uncertainty':{'priority':'priority','reasons':['experimental_v2_no_external_validation'],
                           'humanReviewRequired':True,'operationalUseAllowed':False}}
    if vector is None:
        return {**result,'label':None,'confidence':None,'scoresUncalibrated':{},'evaluable':False,
                'status':'no_evaluable','reason':roi['reason']}
    label,ovr,pairs=decision(artifact,vector)
    scores=np.exp(ovr-ovr.max());scores/=scores.sum()
    return {**result,'label':label,'evaluable':True,'status':'experimental_proposal','reason':None,
            'confidence':float(scores[LABELS.index(label)]),'scoresUncalibrated':dict(zip(LABELS,map(float,scores))),
            'decisionScores':list(map(float,ovr)),'ovoDecisionScores':pairs,
            'scoreMethod':'softmax_of_ovr_decision_scores_not_probability'}


def load_models(directory,product):
    if not directory:return []
    if product not in ('mango','tomate'):raise ValueError('Unsupported product')
    base=Path(directory).resolve();target=(base/f'ag055_v2_{product}.json').resolve()
    if not target.is_relative_to(base):raise ValueError('Unsafe V2 model path')
    if not target.is_file():return []
    raw=target.read_bytes()
    if not 0<len(raw)<=4*1024*1024:raise ValueError('Excessive V2 artifact')
    checksums=json.loads((base.parent/'SHA256SUMS.json').read_text(encoding='utf-8'))
    expected=checksums.get('models/'+target.name,checksums.get(str(Path('models')/target.name)))
    if expected!=sha(raw):raise ValueError('V2 SHA-256 mismatch')
    model=json.loads(raw);validate(model,product)
    return [(model,sha(raw))]
