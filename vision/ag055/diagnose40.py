"""Read-only descriptive error audit. Perturbations are diagnostics, never tuning data."""
import argparse
import io
import json
from collections import Counter
from pathlib import Path

import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from .experimental import dump, private, safe, sha
from .pilot117 import decision, features, predict


def png(img):
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def variants(img):
    w, h = img.size
    yield 'brightness_075', ImageEnhance.Brightness(img).enhance(.75)
    yield 'brightness_125', ImageEnhance.Brightness(img).enhance(1.25)
    yield 'grayscale', ImageOps.grayscale(img).convert('RGB')
    # Border is NOT an accredited background segmentation; may overlap fruit.
    box = (int(w*.15), int(h*.15), int(w*.85), int(h*.85))
    border = Image.new('RGB', img.size, (128,128,128))
    border.paste(img.crop(box), box[:2])
    yield 'border15_gray', border
    periphery = img.copy()
    ImageDraw.Draw(periphery).rectangle(box, fill=(128,128,128))
    yield 'center70_gray_periphery_retained', periphery
    pad = Image.new('RGB', (w+2*int(w*.2),h+2*int(h*.2)), (128,128,128))
    pad.paste(img, (int(w*.2),int(h*.2)))
    yield 'pad20_gray_all_pixels_retained', pad


def sheet(rows, path, columns=5, size=(200,205)):
    canvas = Image.new('RGB', (columns*size[0], ((len(rows)+columns-1)//columns)*size[1]), 'white')
    draw = ImageDraw.Draw(canvas)
    for i, (raw, caption) in enumerate(rows):
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert('RGB')
        img.thumbnail((size[0]-8, size[1]-50))
        x, y = (i%columns)*size[0], (i//columns)*size[1]
        canvas.paste(img, (x+(size[0]-img.width)//2,y))
        draw.multiline_text((x+4,y+size[1]-48), caption, fill='black')
    canvas.save(path)


def run(evaluation, pilot, package, output):
    output = private(output)
    if output.exists():
        raise FileExistsError('Fresh output required')
    records = json.loads((evaluation/'predictions.json').read_text(encoding='utf-8'))
    training = json.loads((pilot/'manifest.json').read_text(encoding='utf-8'))
    mapping = json.loads((package/'custodia/mapping.json').read_text(encoding='utf-8'))
    protocol = json.loads((package/'custodia/protocol.json').read_text(encoding='utf-8'))
    protected = dict(json.loads((evaluation/'integrity.json').read_text(encoding='utf-8'))['before'])
    for p in evaluation.iterdir():
        if p.is_file(): protected[str(p.resolve())] = sha(p.read_bytes())
    for name, digest in protected.items():
        if sha(Path(name).read_bytes()) != digest: raise ValueError('Protected input changed')
    models = {}
    for p in ('mango','tomate'):
        path = pilot/'models'/f'ag055_pilot117_{p}.json'
        if sha(path.read_bytes()) != protocol['modelHashes'][path.name]: raise ValueError('Frozen model changed')
        models[p] = json.loads(path.read_text(encoding='utf-8'))
    train_raw = {r['id']:safe(Path(r['root']),r['relative']).read_bytes() for r in training}
    train_features = {key:features(raw)[0] for key,raw in train_raw.items()}
    output.mkdir(parents=True)
    details = []
    contact = []
    hue_examples = []
    for r in records:
        m = next(m for m in mapping if m['foto_id']==r['foto_id'])
        raw = safe(Path(m['root']),m['relative']).read_bytes()
        if sha(raw)!=r['sha256']: raise ValueError('Image changed')
        model = models[r['product']]
        assert predict(model,raw)['label']==r['prediction']['label']
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert('RGB')
        assert np.array_equal(features(raw)[0],features(png(img))[0])
        changes = {name:predict(model,png(im))['label'] for name,im in variants(img)}
        vector = features(raw)[0]
        block_changes = {}
        for name,a,b in [('coarse_gray_576',0,576),('color_hist_96',576,672),('global_stats_4',672,676)]:
            modified = vector.copy()
            modified[a:b] = model['model']['mean'][a:b]
            block_changes[name] = decision(model,modified)[0]
        subset = [t for t in training if t['product']==r['product']]
        scale = np.array(model['model']['scale']);mean=np.array(model['model']['mean'])
        delta = np.array([(train_features[t['id']]-vector)/scale for t in subset])
        distance = (delta**2).sum(1);nn=int(distance.argmin());t=subset[nn]
        standardized = vector.copy()
        np.subtract(standardized,mean,out=standardized,casting='unsafe')
        np.divide(standardized,scale,out=standardized,casting='unsafe')
        sv_squared=(np.array(model['model']['supportVectors'])-standardized.astype(float))**2
        sv_distance=sv_squared.sum(1)
        max_kernel=float(np.exp(-model['model']['gamma']*sv_distance).max())
        nearest_sv=sv_squared[int(sv_distance.argmin())]
        sv_total=float(nearest_sv.sum())
        sv_info={'distance':sv_total,
                 'blockFractions':[float(nearest_sv[a:b].sum()/sv_total) if sv_total else 0
                                   for a,b in [(0,576),(576,672),(672,676)]],
                 'topDimensions':[(int(i),float(nearest_sv[i]/sv_total)) if sv_total else (int(i),0)
                                  for i in nearest_sv.argsort()[-5:][::-1]]}
        hue_info=None
        if r['product']=='tomate':
            rgb=np.asarray(img.resize((96,96)))
            hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
            # Exact integer pixels in descriptor H bins 11 and 12, width 180/16.
            mask=(hsv[:,:,0]>=124)&(hsv[:,:,0]<147)
            count=int(mask.sum())
            hue_info={'hueBins11_12PixelCount':count,'of9216':9216,
                      'fractionSaturationBelow32':float(((hsv[:,:,1]<32)&mask).sum()/count) if count else None}
            if r['foto_id'] in ('F006','F014','F031'):
                overlay=rgb.copy();overlay[mask]=[0,255,0]
                hue_examples.extend([(png(Image.fromarray(rgb).resize((384,384))),r['foto_id']+' original resized'),
                                     (png(Image.fromarray(overlay).resize((384,384))),r['foto_id']+' green = HSV H bins11/12')])
        nn_info={'id':t['id'],'sourceImageId':t['sourceImageId'],'grade':t['humanGrade'],
                 'sourceLabel':t['sourceLabel'],'standardizedSquaredDistance':float(distance[nn]),
                 'blockDistanceFraction':{name:float((delta[nn,a:b]**2).sum()/distance[nn])
                     for name,a,b in [('coarse_gray_576',0,576),('color_hist_96',576,672),('global_stats_4',672,676)]}}
        details.append({'foto_id':r['foto_id'],'product':r['product'],'humanGrade':r['humanGrade'],
                        'prediction':r['prediction']['label'],'correct':r['correct'],
                        'justification':r['humanOriginalFields']['justificacion'],
                        'sourceClass':m['sourceClass'],'perturbedPredictions':changes,
                        'meanBlockAblationPredictions':block_changes,'nearestTrainingDescriptor':nn_info,
                        'maximumRbfSupportSimilarity':max_kernel,'nearestSupportDistance':sv_info,
                        'lowSaturationHueDiagnostic':hue_info})
        contact.append((raw,f"{r['foto_id']} {r['product']} H:{r['humanGrade']} P:{r['prediction']['label']}\nsource:{m['sourceClass']}"))
    sheet(contact,output/'evaluation40.png')
    sheet(hue_examples,output/'hue_background.png',columns=2,size=(400,430))
    for product in ('mango','tomate'):
        subset=[t for t in training if t['product']==product]
        for start in range(0,len(subset),25):
            sheet([(train_raw[t['id']], f"{t['sourceImageId']} H:{t['humanGrade']}\n{t['sourceLabel']}")
                   for t in subset[start:start+25]],output/f'train_{product}_{start//25+1}.png')
    f014=next(m for m in mapping if m['foto_id']=='F014')
    related=next(t for t in training if t['id']==f014['trainingSimilarityCandidates'][0]['otherId'])
    sheet([(safe(Path(f014['root']),f014['relative']).read_bytes(),'F014 eval H:E0 P:E0'),
           (train_raw[related['id']],f"train {related['sourceImageId']} H:{related['humanGrade']}")],
          output/'F014_pair.png',columns=2,size=(600,550))
    summary={}
    for product in ('mango','tomate'):
        subset=[d for d in details if d['product']==product];t=[t for t in training if t['product']==product]
        summary[product]={
            'trainingGradeSource':dict(Counter(f"{r['humanGrade']}|{r['sourceLabel']}" for r in t)),
            'technicalGroups':len({r['group'] for r in t}),
            'evaluationHumanSource':dict(Counter(f"{d['humanGrade']}|{d['sourceClass']}" for d in subset)),
            'predictionCounts':dict(Counter(d['prediction'] for d in subset)),
            'perturbationChangedLabels':{key:sum(d['perturbedPredictions'][key]!=d['prediction'] for d in subset)
                for key in subset[0]['perturbedPredictions']},
            'meanBlockAblationChangedLabels':{key:sum(d['meanBlockAblationPredictions'][key]!=d['prediction'] for d in subset)
                for key in subset[0]['meanBlockAblationPredictions']},
            'trainingResubstitutionCorrect_notValidation':sum(decision(models[product],train_features[r['id']])[0]==r['humanGrade'] for r in t),
            'trainingN':len(t),
            'rbfKernelMaxMedian':float(np.median([d['maximumRbfSupportSimilarity'] for d in subset])),
            'rbfKernelMaxBelow1eMinus6':sum(d['maximumRbfSupportSimilarity']<1e-6 for d in subset),
            'intercepts':models[product]['model']['intercept']}
    assert all(sha(Path(p).read_bytes())==digest for p,digest in protected.items())
    dump(output/'diagnosis.json',{'perProduct':summary,'perPhoto':details,
        'F014TrainingRelation':related,'protectedInputsUnchanged':True,
        'protectedInputHashes':protected,'modelHashes':protocol['modelHashes'],
        'tomatoScalerSelectedDimensions':{i:{'mean':models['tomate']['model']['mean'][i],
                                             'scale':models['tomate']['model']['scale'][i]}
                                          for i in (635,636,671)},
        'warning':'Perturbations and ablations may be out of distribution; border is not segmented background. No tuning or performance improvement claim.'})
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('evaluation','pilot','package','output'):parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args()
    print(json.dumps(run(a.evaluation,a.pilot,a.package,a.output),indent=2))
