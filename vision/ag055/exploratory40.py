"""Compare returned human labels with frozen E0/E1/E2 pilots; never accredits independence."""
import argparse
import csv
import io
import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from .experimental import dump, private, safe, score, sha
from .pilot117 import LABELS, predict, validate


def match_reviews(mapping, human):
    """Match immutable blind identifiers, product and SHA, never CSV row order."""
    expected = {m['foto_id']: m for m in mapping}
    actual = {h['foto_id']: h for h in human}
    if len(expected) != len(mapping) or len(actual) != len(human):
        raise ValueError('Duplicate blind IDs')
    if set(actual) != set(expected):
        raise ValueError('Unexpected/missing blind IDs')
    matched = []
    for key, m in expected.items():
        h = actual[key]
        if h['producto'] != m['product'] or h['sha256_imagen'] != m['sha256']:
            raise ValueError('Fixed review columns changed: ' + key)
        if h['grado_humano'] not in (*LABELS, 'no_evaluable'):
            raise ValueError('Invalid/missing human grade: ' + key)
        matched.append((m, h))
    return matched


def metrics(records):
    if not records:
        return None
    return score([LABELS.index(r['humanGrade']) for r in records],
                 [LABELS.index(r['prediction']['label']) for r in records], LABELS)


def evaluate(package_root, pilot_run, reviews, reviewer, review_date, output):
    # Date precision is a day: never invent a review time or timezone.
    review_day = date.fromisoformat(review_date).isoformat()
    if not reviewer.strip():
        raise ValueError('Declared reviewer required')
    output = private(output)
    if output.exists():
        raise FileExistsError('Use a new private output directory')
    custody = package_root / 'custodia'
    inputs = [reviews, custody/'mapping.json', custody/'protocol.json', custody/'audit.json',
              pilot_run/'manifest.json']
    protocol = json.loads(inputs[2].read_text(encoding='utf-8'))
    mapping = json.loads(inputs[1].read_text(encoding='utf-8'))
    if len(mapping) != 40 or Counter(m['product'] for m in mapping) != {'mango': 20, 'tomate': 20}:
        raise ValueError('Expected frozen 40-photo package')
    models = {}
    for product in ('mango', 'tomate'):
        path = pilot_run/'models'/f'ag055_pilot117_{product}.json'
        raw = path.read_bytes()
        if sha(raw) != protocol['modelHashes'][path.name]:
            raise ValueError('Frozen model changed')
        model = json.loads(raw)
        validate(model, product)
        models[product] = (model, sha(raw))
        inputs.append(path)
    # Verify all 117 training originals as well as disjointness of candidate bytes.
    training = json.loads((pilot_run/'manifest.json').read_text(encoding='utf-8'))
    training_hashes = set(protocol['trainingImageHashes'])
    if len(training) != 117 or {r['sha256'] for r in training} != training_hashes:
        raise ValueError('Frozen training inventory changed')
    for row in training:
        path = safe(Path(row['root']), row['relative'])
        if sha(path.read_bytes()) != row['sha256']:
            raise ValueError('Training image changed')
        inputs.append(path)
    raw_csv = reviews.read_bytes()
    human = list(csv.DictReader(io.StringIO(raw_csv.decode('utf-8-sig'), newline='')))
    matched = match_reviews(mapping, human)
    images = {}
    for m, h in matched:
        path = safe(Path(m['root']), m['relative'])
        raw = path.read_bytes()
        if sha(raw) != m['sha256']:
            raise ValueError('Candidate image changed: ' + m['foto_id'])
        if m['sha256'] in training_hashes or m['exactTrainingOverlap']:
            raise ValueError('Known exact training overlap: ' + m['foto_id'])
        if m['sha256'] in images:
            raise ValueError('Duplicate candidate bytes')
        images[m['sha256']] = raw
        inputs.append(path)
    # Protect the original DB/ZIPs/older models listed in the existing baseline.
    baseline = json.loads((pilot_run/'baseline.json').read_text(encoding='utf-8'))
    for name, expected in baseline.items():
        path = Path(name)
        if sha(path.read_bytes()) != expected:
            raise ValueError('Protected baseline changed: ' + name)
        inputs.append(path)
    before = {str(p.resolve()): sha(p.read_bytes()) for p in inputs}
    records = []
    excluded = []
    for m, h in matched:
        if h['grado_humano'] == 'no_evaluable':
            excluded.append({'foto_id': m['foto_id'], 'reason': 'human_no_evaluable'})
            continue
        model, model_sha = models[m['product']]
        prediction = predict(model, images[m['sha256']])
        records.append({'foto_id': m['foto_id'], 'originalId': m['id'], 'product': m['product'],
                        'sha256': m['sha256'], 'humanGrade': h['grado_humano'],
                        'humanOriginalFields': h, 'modelSha256': model_sha,
                        'prediction': prediction, 'correct': h['grado_humano'] == prediction['label'],
                        'perceptualTrainingRelations': m['trainingSimilarityCandidates'],
                        'physicalIndependenceAccredited': False, 'kentAccredited': False})
    per_product = {}
    for product in ('mango', 'tomate'):
        subset = [r for r in records if r['product'] == product]
        unflagged = [r for r in subset if not r['perceptualTrainingRelations']]
        per_product[product] = {
            'metrics': metrics(subset),
            'humanClassCounts': {g: sum(r['humanGrade'] == g for r in subset) for g in LABELS},
            'errors': [r['foto_id'] for r in subset if not r['correct']],
            'descriptiveSensitivityExcludingFlaggedSimilarity': {
                'excludedIds': [r['foto_id'] for r in subset if r['perceptualTrainingRelations']],
                'metrics': metrics(unflagged), 'independenceAccredited': False}}
    report = {
        'status': 'exploratory_photo_level_not_accredited_independent_validation',
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'humanAttribution': {'reviewer': reviewer, 'reviewDate': review_day,
                            'datePrecision': 'day', 'source': 'explicit_user_declaration',
                            'csvReviewerAndDatePreservedUnmodified': True},
        'reviewsSha256': sha(raw_csv), 'nReceived': len(human), 'nEvaluated': len(records),
        'excluded': excluded, 'labels': LABELS, 'confusionOrientation': 'rows human; columns predicted',
        'perProduct': per_product, 'modelHashes': protocol['modelHashes'],
        'trainingImagesVerified': len(training), 'candidateImagesVerified': len(images),
        'exactTrainingOverlaps': 0, 'modelsUnchanged': True, 'trainingPerformed': False,
        'thresholdsAdjusted': False, 'independentPerformanceAccredited': False,
        'physicalFruitCount': None, 'kentAccredited': False,
        'manualVsAssisted': 'not_evaluated_no_paired_real_measurements',
        'AGROP67FinalClosureAuthorized': False,
        'missingHumanFields': {k: sum(not h.get(k, '').strip() for h in human)
                               for k in human[0] if k not in ('foto_id','producto','sha256_imagen','grado_humano')},
        'limitations': [
            'Photo-level convenience sample; physical fruit/session independence unverified.',
            'F014 has an unresolved perceptual relation to a pilot training image; exact hashes differ.',
            'No Kent accreditation; generic mango results only.',
            'CSV lacks rubric/version, Rxx, localized evidence, prior-exposure attestation and timings.',
            'Reviewer/day attributed by user declaration; CSV fields remain blank; no time invented.',
            'One reviewer, small sample, no inter-rater reliability or population inference.',
            'Candidates unused by pilot117 by exact hashes, but not guaranteed unused by older exploratory models.',
            'Scores uncalibrated; no fitting, calibration, model selection or threshold adjustment.',
            'Older original-label models have incompatible label spaces and are not graded against E0/E1/E2.'
        ]}
    after = {name: sha(Path(name).read_bytes()) for name in before}
    if before != after:
        raise RuntimeError('Protected inputs changed during evaluation')
    output.mkdir(parents=True)
    (output/'formulario_completado_original.csv').write_bytes(raw_csv)
    dump(output/'report.json', report)
    dump(output/'predictions.json', records)
    dump(output/'integrity.json', {'before': before, 'after': after, 'allUnchanged': True})
    with (output/'comparacion.csv').open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['foto_id','original_id','producto','sha256','humano','modelo','correcto',
                         'model_sha256','similitud_entrenamiento_pendiente'])
        for r in records:
            writer.writerow([r['foto_id'], r['originalId'], r['product'], r['sha256'], r['humanGrade'],
                             r['prediction']['label'], r['correct'], r['modelSha256'],
                             bool(r['perceptualTrainingRelations'])])
    dump(output/'SHA256SUMS.json', {p.name: sha(p.read_bytes()) for p in sorted(output.iterdir())})
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('package-root', 'pilot-run', 'reviews', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--reviewer', required=True)
    parser.add_argument('--review-date', required=True, help='Declared ISO calendar day; no time fabricated')
    args = parser.parse_args()
    result = evaluate(args.package_root, args.pilot_run, args.reviews, args.reviewer,
                      args.review_date, args.output)
    print(json.dumps({'status': result['status'], 'perProduct': result['perProduct']}, ensure_ascii=False))
