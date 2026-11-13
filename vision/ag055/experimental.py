"""AG-055 I02B/I03. Original-label experiments; never imputes E0/E1/E2.

Only Pillow and NumPy are needed. Originals, manifests and models stay outside Git.
Known visual relations and filename acquisition families are joined BEFORE splitting.
These components do not establish physical independence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import platform
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, __version__ as PIL_VERSION

VERSION = 'ag055-original-labels-v1'
FEATURE_VERSION = 'rgb-hsv-hist-grid-v1'
FEATURE_COUNT = 57
TASKS = {'TQ': ('tomate', ['Fresh', 'Rotten']),
         'SEN': ('mango', ['Alternaria', 'Anthracnose', 'Black Mould Rot', 'Healthy', 'Stem end Rot']),
         'FG': ('tomate', [str(i) for i in range(10)])}
LIMITATIONS = [
    'Physical fruit/session independence is NOT verified; grouped internal experiment only.',
    'Automatic color ROI is a proposal, not human verification or fruit segmentation.',
    'Background, embedded writing and acquisition shortcuts may influence predictions.',
    'Original labels are NOT E0/E1/E2; mango variety Kent is NOT accredited.',
    'Scores are uncalibrated; no production deployment or agronomic accreditation.',
]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)


def private(path):
    path = Path(path).resolve()
    if path.is_relative_to(Path(__file__).resolve().parents[2]):
        raise ValueError('Private data/models must remain outside the repository')
    return path


def safe(root, relative):
    if not relative or '\\' in relative or ':' in relative:
        raise ValueError('Unsafe relative path')
    p = (root / relative).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise ValueError('Missing or unsafe evidence: ' + relative)
    return p


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def extract_verified(archive, destination):
    """No overwrite, no symlinks/traversal. Check every supplied checksum."""
    destination = private(destination)
    destination.mkdir()  # fail rather than overwrite previous work
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            p = (destination / info.filename).resolve()
            if (not p.is_relative_to(destination) or '\\' in info.filename
                    or ':' in info.filename or (info.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('Unsafe ZIP entry')
            if info.is_dir():
                p.mkdir(parents=True, exist_ok=True)
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open('xb') as f:
                    f.write(z.read(info))
    manifests = list(destination.glob('*/metadata/sha256_archivos.csv'))
    if len(manifests) != 1:
        raise ValueError('Expected a single checksum manifest')
    root = manifests[0].parents[1]
    checked = rows(manifests[0])
    for r in checked:
        raw = safe(root, r['archivo_relativo']).read_bytes()
        if sha(raw) != r['sha256'] or len(raw) != int(r['bytes']):
            raise ValueError('Package checksum mismatch: ' + r['archivo_relativo'])
    return root, {'archive': str(Path(archive).resolve()), 'zipSha256': sha(Path(archive).read_bytes()),
                  'verifiedFiles': len(checked)}


def describe(raw, roi=None):
    """Same EXIF orientation and ROI/descriptor at training and inference."""
    with Image.open(io.BytesIO(raw)) as original:
        image = ImageOps.exif_transpose(original).convert('RGB')
    w, h = image.size
    if min(w, h) < 32 or w * h > 40_000_000:
        raise ValueError('Unsupported image dimensions')
    if roi is None:
        small = np.asarray(image.resize((128, 128)), dtype=float) / 255
        saturation = small.max(2) - small.min(2)
        mask = (saturation > .18) & (small.max(2) > .18)
        yy, xx = np.where(mask)
        # Broad color bounding box, conservative fallback explicitly recorded.
        if len(xx) >= 128:
            x1 = max(0, int((xx.min() - 3) * w / 128))
            y1 = max(0, int((yy.min() - 3) * h / 128))
            x2 = min(w, int((xx.max() + 4) * w / 128))
            y2 = min(h, int((yy.max() + 4) * h / 128))
            roi, method = [x1, y1, x2-x1, y2-y1], 'color_bbox_proposal'
        else:
            roi, method = [0, 0, w, h], 'full_image_fallback_no_localization'
    else:
        method = 'human_roi'
    if (len(roi) != 4 or any(type(v) is not int for v in roi)
            or min(roi[:2]) < 0 or min(roi[2:]) <= 0
            or roi[0]+roi[2] > w or roi[1]+roi[3] > h):
        raise ValueError('ROI outside oriented image')
    x, y, rw, rh = roi
    crop = image.crop((x, y, x+rw, y+rh)).resize((64, 64))
    rgb = np.asarray(crop, dtype=float) / 255
    hsv = np.asarray(crop.convert('HSV'), dtype=float) / 255
    f = [*rgb.mean((0, 1)), *rgb.std((0, 1)), rw/rh]
    for c in range(3):
        f.extend(np.histogram(hsv[:, :, c], bins=12, range=(0, 1))[0] / 4096)
    for a in range(2):
        for b in range(2):
            f.extend(rgb[a*32:(a+1)*32, b*32:(b+1)*32].mean((0, 1)))
    gray = rgb.mean(2)
    f.extend([np.abs(np.diff(gray, axis=0)).mean(), np.abs(np.diff(gray, axis=1)).mean()])
    pixels = sha(np.asarray(image).tobytes() + str(image.size).encode())
    return np.asarray(f), roi, method, pixels


class Union:
    def __init__(self, ids):
        self.parent = {x: x for x in ids}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def join(self, a, b):
        if a not in self.parent or b not in self.parent:
            raise ValueError('Unknown relationship image')
        a, b = self.find(a), self.find(b)
        self.parent[max(a, b)] = min(a, b)


def group_records(records, relations):
    u = Union(r['id'] for r in records)
    for edge in relations:
        u.join(edge['imagen_a'], edge['imagen_b'])
    seen = {}
    for r in records:
        keys = [('sha', r['sha256']), ('pixel', r['pixelSha256'])]
        if r.get('visualGroup'):
            keys.append(('visual', r['source'], r['visualGroup']))
        name = Path(r['relative']).stem
        if r['source'] == 'TQ':
            date = re.search(r'(20\d{6})', name)
            # Date is only a conservative acquisition proxy, never a verified session.
            keys.append(('date', 'TQ', date[1] if date else 'unknown-date'))
        if r['source'] == 'FG':
            keys.append(('filename-family', 'FG', re.sub(r'\d+$', '', name).lower()))
        if r.get('parent'):
            keys.append(('parent', r['source'], r['parent']))
        for key in keys:
            if key in seen:
                u.join(r['id'], seen[key])
            else:
                seen[key] = r['id']
    seen_bytes, seen_pixels = {}, {}
    for r in records:
        r['group'] = u.find(r['id'])
        previous = seen_bytes.get(r['sha256']) or seen_pixels.get(r['pixelSha256'])
        r['excluded'] = 'duplicate_of:' + previous if previous else r.get('excluded', '')
        seen_bytes.setdefault(r['sha256'], r['id'])
        seen_pixels.setdefault(r['pixelSha256'], r['id'])
    # Do not arbitrarily keep the first label of a contradictory exact duplicate.
    label_sets = defaultdict(set)
    for r in records:
        label_sets[r['pixelSha256']].add((r['source'],r.get('label','')))
    for r in records:
        if len(label_sets[r['pixelSha256']]) > 1:
            r['excluded'] = 'conflicting_original_labels_exact_pixels'
    return records


def split(records, labels, seed=55):
    groups = sorted({r['group'] for r in records})
    counts = np.array([[sum(r['group'] == g and r['label'] == c for r in records)
                        for c in labels] for g in groups], dtype=float)
    if len(groups) < 5 or np.any((counts > 0).sum(0) < 3):
        raise ValueError('Insufficient connected groups for all classes in train/val/test')
    rng = np.random.default_rng(seed)
    target = np.array([.6, .2, .2])[:, None]
    best = None
    # Optimize class COUNTS only, never pixels/features/predictions or test metrics.
    for _ in range(400):
        allocation = rng.choice(3, len(groups), p=[.6, .2, .2])
        totals = np.array([counts[allocation == i].sum(0) for i in range(3)])
        if np.any(totals == 0):
            continue
        loss = float(((totals / counts.sum(0) - target)**2).sum())
        if best is None or loss < best[0]:
            best = loss, allocation.copy()
    if best is None:
        raise ValueError('No complete grouped partition found')
    assignment = {g: ['train', 'validation', 'test'][int(a)] for g, a in zip(groups, best[1])}
    for r in records:
        r['split'] = assignment[r['group']]
    audit_splits(records)


def audit_splits(records):
    for key in ('group', 'sha256', 'pixelSha256'):
        seen = {}
        for r in records:
            if r[key] in seen and seen[r[key]] != r['split']:
                raise ValueError('Leakage detected: ' + key)
            seen[r[key]] = r['split']


def score(y, predicted, labels):
    cm = np.zeros((len(labels), len(labels)), dtype=int)
    for a, b in zip(y, predicted):
        cm[int(a), int(b)] += 1
    precision = np.divide(cm.diagonal(), cm.sum(0), out=np.zeros(len(labels)), where=cm.sum(0)>0)
    recall = np.divide(cm.diagonal(), cm.sum(1), out=np.zeros(len(labels)), where=cm.sum(1)>0)
    f1 = np.divide(2*precision*recall, precision+recall, out=np.zeros(len(labels)), where=precision+recall>0)
    return {'n': len(y), 'accuracy': float(cm.trace()/cm.sum()),
            'precisionMacro': float(precision.mean()), 'recallMacro': float(recall.mean()),
            'f1Macro': float(f1.mean()), 'confusionMatrix': cm.tolist(), 'labels': labels,
            'perClass': {c: {'precision': float(precision[i]), 'recall': float(recall[i]),
                              'f1': float(f1[i]), 'support': int(cm[i].sum())} for i,c in enumerate(labels)}}


def model_scores(model, x):
    x = (np.atleast_2d(x)-np.array(model['mean']))/np.array(model['scale'])
    if model['algorithm'] == 'nearest_centroid':
        logits = -((x[:, None, :] - np.array(model['centroids'])[None, :, :])**2).mean(2)
    elif model['algorithm'] == 'softmax_l2':
        logits = x @ np.array(model['weights']) + np.array(model['bias'])
    else:
        raise ValueError('Unsupported model algorithm')
    logits -= logits.max(1, keepdims=True)
    p = np.exp(logits)
    return p/p.sum(1, keepdims=True)


def train_task(records, labels, feature_map, seed):
    split(records, labels, seed)
    arrays = {}
    for s in ('train', 'validation', 'test'):
        rr = [r for r in records if r['split'] == s]
        arrays[s] = (np.stack([feature_map[r['id']] for r in rr]), np.array([labels.index(r['label']) for r in rr]))
    x, y = arrays['train']
    mean, scale = x.mean(0), x.std(0)
    scale[scale < 1e-6] = 1
    xx = (x-mean)/scale
    common = {'mean': mean.tolist(), 'scale': scale.tolist()}
    candidates = {'nearest_centroid': {**common, 'algorithm': 'nearest_centroid',
                    'centroids': [xx[y == i].mean(0).tolist() for i in range(len(labels))]}}
    # Small linear softmax model, CPU/NumPy; no synthetic data or external weights.
    for l2 in (.001, .01):
        weights = np.zeros((x.shape[1], len(labels)))
        bias = np.zeros(len(labels))
        onehot = np.eye(len(labels))[y]
        for _ in range(500):
            logits = xx @ weights + bias
            logits -= logits.max(1, keepdims=True)
            p = np.exp(logits); p /= p.sum(1, keepdims=True)
            error = (p-onehot)/len(y)
            weights -= .05 * (xx.T @ error + l2*weights)
            bias -= .05 * error.sum(0)
        candidates[f'softmax_l2_{l2}'] = {**common, 'algorithm': 'softmax_l2', 'l2': l2,
            'epochs': 500, 'learningRate': .05, 'weights': weights.tolist(), 'bias': bias.tolist()}
    validation = {k: score(arrays['validation'][1], model_scores(m, arrays['validation'][0]).argmax(1), labels)
                  for k,m in candidates.items()}
    winner = max(candidates, key=lambda k: validation[k]['f1Macro'])
    test = {k: score(arrays['test'][1], model_scores(m, arrays['test'][0]).argmax(1), labels)
            for k,m in candidates.items()}
    result = {'selectedOnValidation': winner, 'validation': validation, 'test': test,
        'splitCounts': {s: len(a[1]) for s,a in arrays.items()},
        'groupCounts': {s: len({r['group'] for r in records if r['split']==s}) for s in arrays}}
    if 'Healthy' in labels and len(labels) == 5:
        healthy = labels.index('Healthy')
        result['healthyVsListedDiseases'] = {
            'mapping': {'Healthy':'Healthy', **{c:'ListedDisease' for c in labels if c!='Healthy'}},
            'method':'Sum uncalibrated scores of four original disease categories; no E0/E1/E2 mapping',
            **{s: {k: score((y != healthy).astype(int),
                (model_scores(m,x)[:,healthy] < .5).astype(int), ['Healthy','ListedDisease'])
                for k,m in candidates.items()} for s,(x,y) in arrays.items() if s!='train'}}
    return candidates[winner], result


def validate_artifact(artifact, product=None):
    if (artifact.get('version') != VERSION or artifact.get('featureVersion') != FEATURE_VERSION
            or artifact.get('deploymentAuthorized') is not False
            or artifact.get('humanReviewRequired') is not True
            or artifact.get('labelSpace') != 'original_source_labels'
            or artifact.get('task') not in TASKS
            or artifact.get('labels') != TASKS[artifact['task']][1]
            or artifact.get('product') != TASKS[artifact['task']][0]
            or (product and artifact['product'] != product)):
        raise ValueError('Incompatible exploratory artifact')
    model = artifact['model']
    for key in ('mean', 'scale'):
        a = np.asarray(model[key], dtype=float)
        if a.shape != (FEATURE_COUNT,) or not np.isfinite(a).all() or (key=='scale' and np.any(a<=0)):
            raise ValueError('Invalid normalization')
    if model['algorithm'] == 'softmax_l2':
        parameters = [('weights',(FEATURE_COUNT,len(artifact['labels']))), ('bias',(len(artifact['labels']),))]
    elif model['algorithm'] == 'nearest_centroid':
        parameters = [('centroids',(len(artifact['labels']),FEATURE_COUNT))]
    else:
        raise ValueError('Invalid algorithm')
    for key,shape in parameters:
        a = np.asarray(model[key],dtype=float)
        if a.shape != shape or not np.isfinite(a).all():
            raise ValueError('Invalid model parameters')
    if not isinstance(artifact.get('dataVersion'),str) or not isinstance(artifact.get('limitations'),list):
        raise ValueError('Missing model provenance')


def predict(artifact, raw):
    validate_artifact(artifact)
    features, roi, method, _ = describe(raw)
    scores = model_scores(artifact['model'], features)[0]
    if scores.shape != (len(artifact['labels']),) or not np.isfinite(scores).all():
        raise ValueError('Invalid model scores')
    result = {'label': artifact['labels'][int(scores.argmax())], 'confidence': float(scores.max()),
            'scoresUncalibrated': dict(zip(artifact['labels'], map(float, scores))),
            'confidenceCalibrated': False, 'roi': roi, 'roiMethod': method,
            'roiHumanVerified': False, 'modelVersion': VERSION, 'task': artifact['task'],
            'experimental': True, 'proposedGrade': None, 'kentVerified': False}
    if artifact['task']=='SEN':
        healthy = float(scores[artifact['labels'].index('Healthy')])
        result['healthyVsListedDiseases'] = {'label':'Healthy' if healthy>=.5 else 'ListedDisease',
            'scoresUncalibrated':{'Healthy':healthy,'ListedDisease':1-healthy}}
    return result


def run(real_zip, selective_zip, output, seed=55):
    output = private(output); output.mkdir()
    real, integrity_real = extract_verified(real_zip, output/'real')
    selective, integrity_selective = extract_verified(selective_zip, output/'selective')
    originals = {r['imagen_id']: r for r in rows(real/'metadata/etiquetas_originales.csv')}
    sources = {r['fuente_id']: r for r in rows(real/'metadata/fuentes.csv')}
    records, feature_map = [], {}
    for r in rows(real/'metadata/inventario_imagenes.csv'):
        original = originals[r['imagen_id']]
        if any(original[k] != r[k] for k in ('imagen_relativa', 'clase_original', 'fuente_id')):
            raise ValueError('Original label metadata mismatch')
        source = r['fuente_id']
        allowed = source in TASKS and sources[source]['licencia'] == {'TQ':'CC BY 4.0','FG':'MIT','SEN':'CC BY-NC 3.0'}[source]
        rec = {'id': r['imagen_id'], 'source': source, 'product': r['producto'],
               'label': original['clase_original'], 'relative': r['imagen_relativa'],
               'sha256': r['sha256_imagen'], 'visualGroup': r['grupo_relacion_propuesta'],
               'excluded': '' if allowed else 'unverified_source_license', 'root': str(real),
               'license': sources[source]['licencia'], 'originalPath': r['ruta_original']}
        raw = safe(real, rec['relative']).read_bytes()
        if sha(raw) != rec['sha256']:
            raise ValueError('Image SHA mismatch')
        features, roi, method, pixel = describe(raw)
        rec.update(roi=roi, roiMethod=method, roiHumanVerified=False, pixelSha256=pixel,
                   humanGrade=None, reviewer=None, reviewedAt=None)
        feature_map[rec['id']] = features; records.append(rec)
    for r in rows(selective/'metadata/inventario.csv'):
        raw = safe(selective, r['ruta_imagen']).read_bytes()
        if sha(raw) != r['sha256']:
            raise ValueError('Selective image SHA mismatch')
        _, roi, method, pixel = describe(raw)
        records.append({'id':r['imagen_id'], 'source':'selective', 'product':r['producto'],
            'label':r['clase_original'], 'relative':r['ruta_imagen'], 'root':str(selective),
            'sha256':sha(raw), 'pixelSha256':pixel, 'roi':roi, 'roiMethod':method,
            'roiHumanVerified':False, 'humanGrade':None, 'reviewer':None, 'reviewedAt':None,
            'parent':r['archivo_padre_relativo'] or r['grupo_origen_conservador'],
            'license':r['licencia'], 'excluded':'no_original_quality_training_label'})
    group_records(records, rows(real/'metadata/duplicados_y_relaciones.csv'))
    return fit_prepared(records, feature_map, sources, [integrity_real,integrity_selective], output, seed)


def fit_prepared(records, feature_map, sources, integrity, output, seed):
    (output/'models').mkdir()
    report = {'version':VERSION, 'seed':seed, 'createdAt':datetime.now(timezone.utc).isoformat(),
        'integrity':integrity, 'images':len(records),
        'excluded':dict(Counter(r['excluded'].split(':')[0] for r in records if r['excluded'])),
        'featureVersion':FEATURE_VERSION, 'runtime':{'python':sys.version, 'numpy':np.__version__,
        'pillow':PIL_VERSION, 'platform':platform.platform()}, 'limitations':LIMITATIONS,
        'deploymentAuthorized':False, 'physicalIndependenceVerified':False, 'tasks':{},
        'sources':sources}
    data_version = sha(json.dumps([(r['id'], r['sha256'], r['label'], r['group'], r['excluded']) for r in records], sort_keys=True).encode())
    report['dataVersion'] = data_version
    for task,(product,labels) in TASKS.items():
        rr = [r for r in records if r['source']==task and not r['excluded']]
        try:
            model, result = train_task(rr, labels, feature_map, seed)
        except ValueError as e:
            report['tasks'][task] = {'status':'blocked', 'reason':str(e)}
            continue
        artifact = {'version':VERSION, 'featureVersion':FEATURE_VERSION, 'task':task, 'product':product,
            'labels':labels, 'labelSpace':'original_source_labels', 'model':model, 'seed':seed,
            'dataVersion':data_version, 'deploymentAuthorized':False, 'humanReviewRequired':True,
            'limitations':LIMITATIONS, 'evaluation':result, 'license':sources[task],
            'trainedAt':report['createdAt']}
        dump(output/'models'/f'ag055_exploratory_{task}.json', artifact)
        report['tasks'][task] = {'status':'exploratory_only', **result}
        sample = next(r for r in rr if r['split']=='test')
        report['tasks'][task]['realImageInference'] = {'imageId':sample['id'], 'sha256':sample['sha256'],
            'originalLabel':sample['label'], **predict(artifact, safe(Path(sample['root']),sample['relative']).read_bytes())}
    # Re-audit across all tasks, including duplicate exclusions and joined relations.
    audit_splits([r for r in records if r.get('split')])
    dump(output/'manifest.json', records)
    dump(output/'report.json', report)
    return report


def retrain(prepared_run, output, seed=55):
    """Recheck prepared originals and retrain without making more photo copies."""
    output = private(output); output.mkdir()
    prepared_run = private(prepared_run)
    records = json.loads((prepared_run/'manifest.json').read_text(encoding='utf-8'))
    previous = json.loads((prepared_run/'report.json').read_text(encoding='utf-8'))
    real = Path(next(r['root'] for r in records if r['source']=='TQ'))
    for entry in previous['integrity']:
        if sha(Path(entry['archive']).read_bytes()) != entry['zipSha256']:
            raise ValueError('Original archive changed')
    for root in {Path(r['root']) for r in records}:
        for r in rows(root/'metadata/sha256_archivos.csv'):
            raw = safe(root,r['archivo_relativo']).read_bytes()
            if sha(raw) != r['sha256'] or len(raw) != int(r['bytes']):
                raise ValueError('Prepared package changed')
    labels = {r['imagen_id']:r for r in rows(real/'metadata/etiquetas_originales.csv')}
    feature_map = {}
    for r in records:
        if r['source'] in TASKS:
            original=labels[r['id']]
            if (r['label'],r['relative'],r['source']) != (original['clase_original'],original['imagen_relativa'],original['fuente_id']):
                raise ValueError('Original labels changed')
        raw = safe(Path(r['root']),r['relative']).read_bytes()
        if sha(raw) != r['sha256']:
            raise ValueError('Prepared image changed')
        f,roi,method,pixel = describe(raw)
        r.update(roi=roi,roiMethod=method,pixelSha256=pixel,
                 excluded='' if r['source'] in TASKS else 'no_original_quality_training_label')
        r.pop('split',None)
        feature_map[r['id']]=f
    group_records(records,rows(real/'metadata/duplicados_y_relaciones.csv'))
    return fit_prepared(records, feature_map, previous['sources'], previous['integrity'],output,seed)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--real-zip', type=Path)
    ap.add_argument('--selective-zip', type=Path)
    ap.add_argument('--prepared-run', type=Path, help='Recheck/retrain prepared originals without copying photos')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--seed', type=int, default=55)
    a = ap.parse_args()
    if a.prepared_run:
        report = retrain(a.prepared_run,a.output,a.seed)
    elif a.real_zip and a.selective_zip:
        report = run(a.real_zip,a.selective_zip,a.output,a.seed)
    else:
        ap.error('Provide both ZIPs or --prepared-run')
    print(json.dumps({k:{'status':v['status'], 'selected':v.get('selectedOnValidation')} for k,v in report['tasks'].items()}))


if __name__ == '__main__':
    main()
