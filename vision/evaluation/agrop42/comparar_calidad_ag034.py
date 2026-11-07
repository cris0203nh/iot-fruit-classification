"""AG-034 / Incremento 14: comparación experimental E0/E1/E2, por producto.

Una declaración en CSV y sus soportes NO prueban por sí solos validación humana.
Bloquea el benchmark cuando no hay tres clases y suficientes grupos independientes.
Nunca integra una clasificación comercial automática a los pipelines ni a FastAPI.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath

from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError

VERSION = 'ag034-comparacion-calidad-v1'
LABELS = ('E0', 'E1', 'E2')
PRODUCTS = ('mango', 'tomate')
FEATURES = ('rojo_medio', 'verde_medio', 'azul_medio', 'rojo_desv', 'verde_desv',
            'azul_desv', 'rojo_sobre_verde', 'verde_sobre_rojo', 'aspecto_roi',
            'contraste_luma', 'fraccion_bordes', 'fraccion_zonas_oscuras')
COLUMNS = (
    'producto', 'variedad_declarada', 'pieza_id', 'sesion_id',
    'imagen_relativa', 'sha256_imagen', 'roi_xywh', 'roi_verificada',
    'estado_revision', 'etiqueta_e0_e1_e2', 'revisor_id', 'fecha_revision_iso',
    'rubrica_version', 'soporte_revision_relativo',
    'soporte_identidad_sesion_relativo',
)
VALID_STATES = {'pendiente', 'no_evaluable', 'revisada_sin_etiqueta', 'etiquetada'}
SHA_RE = re.compile(r'[0-9a-fA-F]{64}\Z')
ID_RE = re.compile(r'[A-Za-z0-9_-]{1,90}\Z')
MAX_CSV_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 12 * 1024 * 1024


class QualityError(ValueError):
    """Datos faltantes, ilegibles, inconsistentes o no íntegros."""


def safe_path(root: Path, relative: str) -> Path:
    """Limita todo archivo de evidencia al directorio permitido, sin symlinks."""
    if not relative or '\\' in relative or ':' in relative:
        raise QualityError('Ruta relativa insegura o vacía')
    p = PurePosixPath(relative)
    if p.is_absolute() or any(segment in ('', '.', '..') for segment in p.parts):
        raise QualityError('Ruta relativa insegura: ' + relative)
    root = root.resolve(strict=True)
    target = root.joinpath(*p.parts)
    if any(part.is_symlink() for part in [target, *target.parents] if part != root):
        raise QualityError('Enlace simbólico no permitido: ' + relative)
    if not target.is_file() or not target.resolve().is_relative_to(root):
        raise QualityError('No existe evidencia en raíz permitida: ' + relative)
    return target


def read_csv(path: Path) -> tuple[list[dict[str, str]], str]:
    data = path.read_bytes()
    if len(data) > MAX_CSV_BYTES:
        raise QualityError('CSV supera el límite permitido')
    try:
        rd = csv.DictReader(io.StringIO(data.decode('utf-8-sig'), newline=''), strict=True)
        if rd.fieldnames is None or len(rd.fieldnames) != len(set(rd.fieldnames)):
            raise QualityError('Encabezados ausentes o duplicados')
        if set(rd.fieldnames) != set(COLUMNS):
            raise QualityError('Encabezados distintos de la plantilla oficial AG-034')
        rows = list(rd)
        if any(None in row or any(v is None for v in row.values()) for row in rows):
            raise QualityError('CSV malformado')
        return rows, hashlib.sha256(data).hexdigest()
    except (UnicodeError, csv.Error) as e:
        raise QualityError('CSV inválido') from e


def _time_with_zone(s: str) -> bool:
    try:
        t = datetime.fromisoformat(s.replace('Z', '+00:00'))
        return t.tzinfo is not None and t.utcoffset() is not None
    except ValueError:
        return False


def _read_blob(root: Path, filename: str, *, max_bytes: int) -> tuple[bytes, str]:
    path = safe_path(root, filename)
    if path.stat().st_size > max_bytes:
        raise QualityError('Archivo supera límite: ' + filename)
    blob = path.read_bytes()
    if not blob:
        raise QualityError('Archivo vacío: ' + filename)
    return blob, hashlib.sha256(blob).hexdigest()


def _features(blob: bytes, roi_json: str) -> list[float]:
    try:
        roi = json.loads(roi_json)
        if not isinstance(roi, list) or len(roi) != 4 or any(type(n) is not int for n in roi):
            raise QualityError('ROI requiere [x,y,ancho,alto] en píxeles enteros')
        x, y, w, h = roi
        if min(x, y) < 0 or min(w, h) <= 0:
            raise QualityError('ROI fuera de rango')
        with Image.open(io.BytesIO(blob)) as original:
            if original.format not in {'JPEG', 'PNG'}:
                raise QualityError('Formato de imagen no permitido')
            if original.width * original.height > 16_000_000:
                raise QualityError('Imagen superior a 16 millones de píxeles')
            image = ImageOps.exif_transpose(original).convert('RGB')
        if x + w > image.width or y + h > image.height:
            raise QualityError('ROI fuera de la fotografía')
        crop = image.crop((x, y, x + w, y + h))
        crop.thumbnail((96, 96), Image.Resampling.BILINEAR)
        stats = ImageStat.Stat(crop)
        means = [v / 255 for v in stats.mean]
        stds = [v / 255 for v in stats.stddev]
        gray = crop.convert('L')
        pix = gray.tobytes()  # 8 bits: sin API Pillow obsoleta
        cw, ch = gray.size
        mean_luma = statistics.fmean(pix)
        contrast = ImageStat.Stat(gray).stddev[0] / 255.
        dark_fraction = sum(v < mean_luma - 25 for v in pix) / len(pix)
        border_edges = 0
        pairs = 0
        for yy in range(ch):
            for xx in range(cw):
                v = pix[yy * cw + xx]
                if xx + 1 < cw:
                    border_edges += abs(v - pix[yy*cw + xx+1]) >= 30
                    pairs += 1
                if yy + 1 < ch:
                    border_edges += abs(v - pix[(yy+1)*cw + xx]) >= 30
                    pairs += 1
        edge_fraction = border_edges / max(1, pairs)
        return [*means, *stds, means[0] / max(means[1], .01),
                means[1] / max(means[0], .01), w / h, contrast,
                edge_fraction, dark_fraction]
    except (OSError, ValueError, TypeError, json.JSONDecodeError,
            UnidentifiedImageError, Image.DecompressionBombError) as e:
        if isinstance(e, QualityError):
            raise
        raise QualityError('No se pudo extraer ROI de imagen: ' + str(e)) from e


def load_eligible(csv_path: Path, images_root: Path, supports_root: Path) -> tuple[list[dict], dict]:
    rows, csv_sha = read_csv(csv_path)
    eligible = []
    states = Counter()
    seen_views = set()
    images_sha_owner = {}
    piece_labels = {}
    support_hashes = {}
    errors = []
    for line, row in enumerate(rows, 2):
        try:
            r = {k: v.strip() for k, v in row.items()}
            p, piece, session = r['producto'], r['pieza_id'], r['sesion_id']
            if p not in PRODUCTS or not ID_RE.fullmatch(piece) or not ID_RE.fullmatch(session):
                raise QualityError('Producto, pieza_id o sesion_id inválidos')
            state, label = r['estado_revision'], r['etiqueta_e0_e1_e2']
            if state not in VALID_STATES:
                raise QualityError('Estado de revisión no admitido')
            if (state == 'etiquetada') != bool(label) or label and label not in LABELS:
                raise QualityError('Etiqueta incompatible con estado de revisión')
            view_key = (p, piece, r['imagen_relativa'])
            if view_key in seen_views:
                raise QualityError('Vista repetida')
            seen_views.add(view_key)
            if state == 'etiquetada':
                if p == 'mango' and r['variedad_declarada'].casefold() != 'kent':
                    raise QualityError('Solo mango Kent declarado es elegible para su rúbrica')
                if r['roi_verificada'] != 'si':
                    raise QualityError('ROI no confirmada por operador')
                if not r['revisor_id'] or re.search(r'chatgpt|asistente.?ia|inteligencia artificial', r['revisor_id'], re.I):
                    raise QualityError('Falta identificador de revisor humano')
                if not _time_with_zone(r['fecha_revision_iso']):
                    raise QualityError('Fecha de revisión sin zona horaria')
                if not r['rubrica_version'] or (p == 'mango' and not r['rubrica_version'].startswith('kent-ext-')) or (p == 'tomate' and not r['rubrica_version'].startswith('tomato-ext-')):
                    raise QualityError('Rúbrica del producto ausente/inconsistente')
                if not SHA_RE.fullmatch(r['sha256_imagen']):
                    raise QualityError('SHA de imagen inválido')
                if not r['soporte_revision_relativo'] or not r['soporte_identidad_sesion_relativo']:
                    raise QualityError('Faltan soportes de revisión o sesión')
                for name in ('soporte_revision_relativo', 'soporte_identidad_sesion_relativo'):
                    ref = r[name]
                    if ref not in support_hashes:
                        _, support_hashes[ref] = _read_blob(supports_root, ref, max_bytes=MAX_CSV_BYTES)
                data, digest = _read_blob(images_root, r['imagen_relativa'], max_bytes=MAX_IMAGE_BYTES)
                if digest != r['sha256_imagen'].lower():
                    raise QualityError('SHA256 imagen no coincide: ' + r['imagen_relativa'])
                if digest in images_sha_owner and images_sha_owner[digest] != (p, piece):
                    raise QualityError('Misma imagen atribuida a otra pieza')
                images_sha_owner[digest] = (p, piece)
                old_label = piece_labels.setdefault((p, piece), label)
                if old_label != label:
                    raise QualityError('Etiquetas contradictorias para una pieza')
                feature = _features(data, r['roi_xywh'])
                eligible.append({'producto': p, 'pieza_id': piece, 'sesion_id': session,
                                 'y': label, 'x': feature, 'sha256': digest})
            elif label:
                raise QualityError('Etiqueta en vista no etiquetada')
            states[(p, state)] += 1
        except (OSError, QualityError) as exc:
            errors.append(f'fila {line}: {exc}')
    if errors:
        raise QualityError('; '.join(errors[:12]) + ('; ...' if len(errors) > 12 else ''))
    return eligible, {'sha256_csv': csv_sha, 'filas_csv': len(rows),
                      'vistas_elegibles': len(eligible),
                      'estado_por_producto': {p: {s: states[(p, s)] for s in sorted(VALID_STATES)}
                                              for p in PRODUCTS},
                      'sha256_soportes': support_hashes,
                      'acreditacion_externa_independiente_automaticamente_verificada': False}


def aggregate_pieces(rows: list[dict]) -> list[dict]:
    by_piece = defaultdict(list)
    for r in rows:
        by_piece[(r['producto'], r['pieza_id'])].append(r)
    pieces = []
    for (product, piece), views in sorted(by_piece.items()):
        values = {r['y'] for r in views}
        if len(values) != 1:
            raise QualityError('Etiquetas discrepantes para una pieza')
        n = len(views)
        pieces.append({'producto': product, 'pieza_id': piece, 'y': views[0]['y'],
                       'sesiones': set(r['sesion_id'] for r in views),
                       'x': [sum(r['x'][i] for r in views) / n for i in range(len(FEATURES))],
                       'vistas': n})
    return pieces


def connected_groups(pieces: list[dict]) -> list[list[dict]]:
    """Una sesión compartida o la misma pieza jamás se divide entre splits."""
    parent = list(range(len(pieces)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    session_owners = {}
    for i, row in enumerate(pieces):
        for session in row['sesiones']:
            if session in session_owners:
                a, b = root(i), root(session_owners[session])
                parent[a] = b
            else:
                session_owners[session] = i
    groups = defaultdict(list)
    for i, row in enumerate(pieces):
        groups[root(i)].append(row)
    return list(groups.values())


def split_groups(groups: list[list[dict]], seed: int = 34) -> tuple[dict, str | None]:
    """Split por componentes pieza/sesión; estratificación por clase sin fuga."""
    counts = Counter(y for group in groups for y in {r['y'] for r in group})
    if any(counts[c] < 5 for c in LABELS):
        return {}, 'Se requieren >=5 componentes independientes por cada E0/E1/E2'
    if len(groups) < 15:
        return {}, 'Se requieren al menos 15 componentes independientes'
    rng = random.Random(seed)
    indices = list(range(len(groups)))
    for _ in range(1000):
        rng.shuffle(indices)
        # Aproximación 60/20/20 por grupo independiente (sin recalibrar con test).
        n = len(indices)
        ntest = max(3, round(.2 * n))
        nval = max(3, round(.2 * n))
        mapping = {i: 'prueba' if j < ntest else 'validacion' if j < ntest+nval else 'entrenamiento'
                   for j, i in enumerate(indices)}
        per_split = {s: Counter(r['y'] for i, group in enumerate(groups) if mapping[i] == s for r in group)
                     for s in ('entrenamiento', 'validacion', 'prueba')}
        if all(per_split[s][y] >= (3 if s == 'entrenamiento' else 1)
               for s in per_split for y in LABELS):
            return mapping, None
    return {}, 'No hay partición estratificada disjunta viable con estas piezas y sesiones'


def fit_rule(train: list[dict]) -> dict:
    """Regla clásica: un descriptor RGB, centroide por grado calculado en train."""
    choices = []
    for f in range(len(FEATURES)):
        centers = {c: statistics.fmean(r['x'][f] for r in train if r['y'] == c)
                   for c in LABELS}
        def pred(row):
            return min(LABELS, key=lambda c: (abs(row['x'][f] - centers[c]), c))
        score = sum(pred(row) == row['y'] for row in train)
        choices.append((-score, f, centers))
    _, f, centers = min(choices, key=lambda a: (a[0], a[1]))
    return {'feature': FEATURES[f], 'indice': f, 'centros_entrenamiento': centers}


def predict_rule(model: dict, x: list[float]) -> str:
    f = model['indice']
    return min(LABELS, key=lambda c: (abs(x[f] - model['centros_entrenamiento'][c]), c))


def fit_light(train: list[dict]) -> dict:
    """Regresión softmax multicategoría L2, implementada sin sklearn ni datos externos."""
    dim = len(FEATURES)
    mean = [statistics.fmean(r['x'][i] for r in train) for i in range(dim)]
    scale = [max(statistics.pstdev(r['x'][i] for r in train), .05) for i in range(dim)]
    samples = [([(r['x'][j] - mean[j]) / scale[j] for j in range(dim)], LABELS.index(r['y']))
               for r in train]
    weights = [[0.] * (dim + 1) for _ in LABELS]
    for _ in range(450):
        gradients = [[0.] * (dim+1) for _ in LABELS]
        for x, label in samples:
            xx = x + [1.]
            logits = [sum(a*b for a, b in zip(w, xx)) for w in weights]
            shift = max(logits)
            exps = [math.exp(min(0., z-shift)) for z in logits]
            denom = sum(exps)
            for k in range(len(LABELS)):
                error = exps[k]/denom - int(k == label)
                for j in range(dim+1):
                    gradients[k][j] += error * xx[j]
        for k in range(len(LABELS)):
            for j in range(dim+1):
                penalty = .04 * weights[k][j] if j < dim else 0.
                weights[k][j] -= .07 * (gradients[k][j]/len(samples) + penalty)
    return {'algoritmo': 'softmax_l2_python', 'clases': list(LABELS), 'pesos': weights,
            'medias_train': mean, 'escalas_train': scale,
            'parametros': len(LABELS)*(dim+1)}


def predict_light(model: dict, x: list[float]) -> str:
    xx = [(x[j]-model['medias_train'][j])/model['escalas_train'][j]
          for j in range(len(FEATURES))] + [1.]
    logits = [sum(a*b for a, b in zip(w, xx)) for w in model['pesos']]
    return LABELS[max(range(len(LABELS)), key=lambda k: (logits[k], -k))]


def metrics(rows: list[dict], predict) -> dict:
    matrix = {y: {p: 0 for p in LABELS} for y in LABELS}
    for r in rows:
        matrix[r['y']][predict(r['x'])] += 1
    per_class = {}
    for c in LABELS:
        tp = matrix[c][c]
        fn = sum(matrix[c].values())-tp
        fp = sum(matrix[y][c] for y in LABELS if y != c)
        precision = tp/(tp+fp) if tp+fp else 0.
        recall = tp/(tp+fn) if tp+fn else 0.
        f1 = 2*precision*recall/(precision+recall) if precision+recall else 0.
        per_class[c] = {'precision': precision, 'recall': recall, 'f1': f1,
                        'n_piezas': sum(matrix[c].values())}
    total = len(rows)
    return {'n_piezas': total, 'accuracy': sum(matrix[c][c] for c in LABELS)/total if total else None,
            'f1_macro': sum(per_class[c]['f1'] for c in LABELS)/3,
            'por_clase': per_class, 'matriz_confusion': matrix}


def benchmark(csv_path: Path, images_root: Path, supports_root: Path, seed: int=34) -> dict:
    eligible, evidence = load_eligible(csv_path, images_root, supports_root)
    pieces = aggregate_pieces(eligible)
    result = {'version': VERSION, 'actividad': 'AG-034',
              'alcance': 'Comparación experimental de grados externos E0/E1/E2 por producto',
              'dataset': evidence, 'piezas_elegibles': len(pieces),
              'por_producto': {}, 'validacion_humana_independiente_acreditada_por_software': False,
              'integracion_productiva_autorizada': False, 'cierre_total_AG034_acreditado': False}
    for product in PRODUCTS:
        prod = [r for r in pieces if r['producto'] == product]
        groups = connected_groups(prod)
        assignment, block = split_groups(groups, seed=seed)
        entry = {'piezas': len(prod), 'componentes_pieza_sesion': len(groups),
                 'componentes_por_etiqueta': {c: sum(any(r['y']==c for r in group) for group in groups)
                                             for c in LABELS}}
        if block:
            result['por_producto'][product] = {**entry, 'estado': 'bloqueado_por_datos_insuficientes',
                                               'motivo': block, 'metricas': None}
            continue
        splits = {s: [] for s in ('entrenamiento', 'validacion', 'prueba')}
        membership = {s: [] for s in splits}
        for i, group in enumerate(groups):
            s = assignment[i]
            splits[s].extend(group)
            membership[s].extend(r['pieza_id'] for r in group)
        if any(set(membership[a]) & set(membership[b]) for a in splits for b in splits if a != b):
            raise QualityError('Error: fuga de piezas entre particiones')
        rule, light = fit_rule(splits['entrenamiento']), fit_light(splits['entrenamiento'])
        preds = {'reglas': lambda x: predict_rule(rule, x),
                 'modelo_ligero': lambda x: predict_light(light, x)}
        val = {name: metrics(splits['validacion'], fn) for name, fn in preds.items()}
        test = {name: metrics(splits['prueba'], fn) for name, fn in preds.items()}
        winner = max(preds, key=lambda name: (val[name]['f1_macro'], -list(preds).index(name)))
        result['por_producto'][product] = {
            **entry, 'estado': 'comparacion_experimental_provisional',
            'reparto_por_pieza': {s: len(rows) for s, rows in splits.items()},
            'ids_por_particion': {s: sorted(membership[s]) for s in splits},
            'regla_clasica': rule, 'modelo_ligero': {'algoritmo': light['algoritmo'],
                                                     'parametros': light['parametros']},
            'validacion_comun': val, 'prueba_comun': test,
            'alternativa_provisional_por_validacion': winner,
            'metricas': test,
        }
    result['advertencias'] = [
        'Solo se usan etiquetas declaradas por revisor con archivos de soporte presentes; su autenticidad y competencia NO son certificadas por el software.',
        'Las clases E0/E1/E2 requieren rúbricas formalmente aprobadas y referencias de campo antes de una conclusión comercial.',
        'Las máscaras o ROI se dan por revisadas según declaración del CSV, no por una medición independiente de segmentación.',
        'La regla y el modelo ven las mismas piezas, descriptores y conjunto de prueba por producto.',
        'Las métricas son por pieza. Una partición pequeña no demuestra generalización estadística.',
        'No se mide hardware físico ni se ejecuta clasificación automática en FastAPI/React.',
        'No equivale a finalizar AG-034: aún requiere revisión humana independiente y evidencia de hardware.',
    ]
    return result


def main(argv: list[str] | None=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--csv', type=Path, required=True)
    ap.add_argument('--raiz-imagenes', type=Path, required=True)
    ap.add_argument('--raiz-soportes', type=Path, required=True)
    ap.add_argument('--salida', type=Path, required=True)
    ap.add_argument('--semilla', type=int, default=34)
    args = ap.parse_args(argv)
    try:
        if args.salida.exists():
            raise QualityError('No se sobrescriben resultados previos; cambie --salida')
        report = benchmark(args.csv, args.raiz_imagenes, args.raiz_soportes, args.semilla)
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'archivo': str(args.salida), 'piezas': report['piezas_elegibles'],
                          'estado_por_producto': {p: v['estado'] for p, v in report['por_producto'].items()},
                          'cierre_total_AG034_acreditado': False}, ensure_ascii=False))
        return 0
    except (OSError, QualityError) as exc:
        print(json.dumps({'estado': 'error_de_integridad', 'detalle': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
