"""AG-037 / AGROP-45: analisis reproducible de compuertas de deteccion.

NO calcula exactitud, precision, recall, acuerdo entre humanos ni calidad E0/E1/E2.
El ensayo retrospectivo coteja los 97 resultados YOLOE de AG-036 con las
32 decisiones humanas de los casos rechazados por la compuerta original.
Las 65 detecciones originalmente admitidas NO tienen evaluacion humana aqui.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

THRESHOLDS = (0.40, 0.30, 0.25)
SOURCE_FIELDS = (
    'fuente', 'producto_candidato', 'grupo_candidato', 'ruta_relativa',
    'sha256_imagen', 'estado_deteccion', 'candidatos_producto',
    'confianza_mejor_coincidencia', 'mascara_poligono_disponible',
)
REVIEW_FIELDS = ('sha256_imagen', 'producto', 'decision_revisor')
ALLOWED_STATES = {
    'deteccion_lista_para_captura', 'confianza_inferior_a_umbral_captura',
    'deteccion_sin_clase_esperada', 'sin_deteccion',
    'multiples_candidatos_esperados',
}
DECISIONS = {'Bien localizada', 'YOLOE falló'}
PRODUCTS = {'mango', 'tomate'}
SHA_PATTERN = re.compile(r'^[a-f0-9]{64}$')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path, required: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
            raise ValueError(f'Faltan columnas obligatorias en {path.name}')
        rows = list(reader)
    if not rows:
        raise ValueError(f'Archivo sin registros: {path.name}')
    if any(None in row for row in rows):
        raise ValueError('CSV con columnas adicionales o fila mal formada')
    return rows


def _as_int(value: str, name: str) -> int:
    try:
        number = int(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{name} no es entero válido') from exc
    if number < 0 or number > 100:
        raise ValueError(f'{name} fuera de rango')
    return number


def _as_confidence(value: str, required: bool) -> float | None:
    if not value.strip():
        if required:
            raise ValueError('Falta confianza de candidato unico')
        return None
    try:
        n = float(value)
    except ValueError as exc:
        raise ValueError('Confianza inválida') from exc
    if not math.isfinite(n) or not 0 <= n <= 1:
        raise ValueError('Confianza fuera de rango')
    return n


def _ready(row: dict, threshold: float) -> bool:
    return (row['candidatos_producto'] == 1
            and row['mascara']
            and row['confianza'] is not None
            and row['confianza'] >= threshold)


def evaluate(detector_rows: list[dict[str, str]], review_rows: list[dict[str, str]],
             *, verify_baseline: bool = True) -> tuple[dict, list[dict]]:
    if len(detector_rows) != len({r.get('sha256_imagen') for r in detector_rows}):
        raise ValueError('SHA256 duplicado en detecciones')
    if len(review_rows) != len({r.get('sha256_imagen') for r in review_rows}):
        raise ValueError('SHA256 duplicado en revisión')
    records: list[dict] = []
    for row in detector_rows:
        if any(field not in row for field in SOURCE_FIELDS):
            raise ValueError('Columnas incompletas del detector')
        sha = row['sha256_imagen'].strip().lower()
        if not SHA_PATTERN.fullmatch(sha):
            raise ValueError('SHA256 inválido de detección')
        product = row['producto_candidato'].strip().lower()
        state = row['estado_deteccion'].strip()
        mask = row['mascara_poligono_disponible'].strip().lower()
        if product not in PRODUCTS or state not in ALLOWED_STATES:
            raise ValueError('Producto o estado de detección no admitido')
        if mask not in {'si', 'no'}:
            raise ValueError('Máscara no reconocida')
        count = _as_int(row['candidatos_producto'], 'candidatos_producto')
        confidence = _as_confidence(row['confianza_mejor_coincidencia'], count == 1)
        if count == 0 and confidence is not None:
            raise ValueError('Confianza de candidato inexistente')
        if count == 0 and mask == 'si':
            raise ValueError('Máscara sin candidato esperado')
        record = {
            'sha256': sha, 'producto': product, 'fuente': row['fuente'].strip(),
            'grupo': row['grupo_candidato'].strip(),
            'archivo': row['ruta_relativa'].strip(),
            'estado_original': state, 'candidatos_producto': count,
            'confianza': confidence, 'mascara': mask == 'si',
            'revision': None,
        }
        if not record['archivo'] or not record['grupo']:
            raise ValueError('Identificador de grupo o ruta vacío')
        if verify_baseline:
            reported = state == 'deteccion_lista_para_captura'
            if _ready(record, 0.40) != reported:
                raise ValueError('La regla 0,40 no coincide con el estado original: ' + sha[:12])
        records.append(record)
    by_sha = {row['sha256']: row for row in records}
    for row in review_rows:
        if any(field not in row for field in REVIEW_FIELDS):
            raise ValueError('Columnas incompletas de revisión')
        sha = row['sha256_imagen'].strip().lower()
        if sha not in by_sha:
            raise ValueError('Revisión no vinculable a resultados YOLOE')
        item = by_sha[sha]
        if row['producto'].strip().lower() != item['producto']:
            raise ValueError('Producto discordante entre revisión y detector')
        decision = row['decision_revisor'].strip()
        if decision not in DECISIONS:
            raise ValueError('Veredicto de revisión no reconocido')
        if _ready(item, 0.40):
            raise ValueError('El estudio original revisó solo rechazos: hay un aceptado revisado')
        item['revision'] = decision
    if len(review_rows) != sum(r['revision'] is not None for r in records):
        raise ValueError('No todas las revisiones pudieron asociarse')
    if sum(r['revision'] is None for r in records) + len(review_rows) != len(records):
        raise ValueError('Error de cobertura')
    scenarios = []
    previous_accepted: set[str] = set()
    baseline_accepted = {r['sha256'] for r in records if _ready(r, 0.40)}
    for threshold in THRESHOLDS:
        accepted = [r for r in records if _ready(r, threshold)]
        retained = [r for r in records if not _ready(r, threshold)]
        newly_accepted = [r for r in accepted if r['sha256'] not in baseline_accepted]
        reviewed_admitted = [r for r in accepted if r['revision'] is not None]
        reviewed_rejected = [r for r in retained if r['revision'] is not None]
        by_product = {p: {
            'imagenes': sum(r['producto'] == p for r in records),
            'admitidas': sum(r['producto'] == p for r in accepted),
            'retenidas': sum(r['producto'] == p for r in retained),
        } for p in ('mango', 'tomate')}
        scenarios.append({
            'umbral': f'{threshold:.2f}',
            'admitidas': len(accepted), 'retenidas': len(retained),
            'admitidas_sin_revision_humana': sum(r['revision'] is None for r in accepted),
            'admitidas_con_revision_humana': len(reviewed_admitted),
            'admitidas_revisadas_bien_localizadas': sum(r['revision'] == 'Bien localizada' for r in reviewed_admitted),
            'admitidas_revisadas_yoloe_fallo': sum(r['revision'] == 'YOLOE falló' for r in reviewed_admitted),
            'nuevas_admitidas_sobre_040': len(newly_accepted),
            'nuevas_admitidas_bien_localizadas_revisadas': sum(r['revision'] == 'Bien localizada' for r in newly_accepted),
            'nuevas_admitidas_sin_revision': sum(r['revision'] is None for r in newly_accepted),
            'retenidas_revisadas_bien_localizadas': sum(r['revision'] == 'Bien localizada' for r in reviewed_rejected),
            'retenidas_revisadas_yoloe_fallo': sum(r['revision'] == 'YOLOE falló' for r in reviewed_rejected),
            'por_producto': by_product,
            'tasa_falsas_aceptaciones_global': None,
            'precision_del_detector': None,
        })
        if previous_accepted and not previous_accepted.issubset({r['sha256'] for r in accepted}):
            raise AssertionError('La cobertura debe aumentar al bajar el umbral')
        previous_accepted = {r['sha256'] for r in accepted}
    report = {
        'actividad': 'AG-037 / AGROP-45',
        'alcance': 'evaluacion_retroactiva_de_deteccion_no_calibracion',
        'unidad_de_observacion': 'fotografia_no_pieza_fisica',
        'imagenes': len(records),
        'imagenes_unicas_sha256': len(by_sha),
        'revisiones_manuales_selectivas': len(review_rows),
        'revisiones_bien_localizadas': sum(r['revision'] == 'Bien localizada' for r in records),
        'revisiones_yoloe_fallo': sum(r['revision'] == 'YOLOE falló' for r in records),
        'imagenes_sin_revision': sum(r['revision'] is None for r in records),
        'estados': dict(sorted(Counter(r['estado_original'] for r in records).items())),
        'escenarios': scenarios,
        'umbral_productivo': '0.40',
        'umbral_modificado': False,
        'exactitud_detector_estimable': False,
        'clasificacion_visual_e0_e1_e2_evaluada': False,
        'hardware_fisico_probado': False,
        'concordancia_entre_humanos_calculada': False,
        'limitaciones': [
            'Las revisiones son selectivas: proceden de rechazos originales, no de una muestra representativa.',
            '65 admisiones iniciales carecen de verificacion humana de localizacion; la tasa de falsas admisiones global es desconocida.',
            'Una localizacion marcada Bien localizada no acredita exactitud de mascaras, identidad fisica ni calidad E0/E1/E2.',
            'El estudio usa detecciones precalculadas con piso de inferencia 0,25; no reejecuta YOLOE ni prueba ESP32.',
            'La seleccion de umbral es provisional y no existe calibracion independiente por pieza/negativos dificiles.',
        ],
    }
    return report, records


def write_results(detector: Path, revisions: Path, destination: Path) -> dict:
    if destination.exists():
        raise ValueError('La carpeta de salida ya existe; no sobrescribir evidencias')
    # Parse and validate ALL inputs before creating output.
    rows = read_csv(detector, SOURCE_FIELDS)
    review_rows = read_csv(revisions, REVIEW_FIELDS)
    summary, records = evaluate(rows, review_rows)
    summary['fuentes_sha256'] = {'detecciones_csv': digest(detector), 'revision_manual_csv': digest(revisions)}
    destination.mkdir(parents=True)
    (destination / 'resumen_ag037.json').write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    with (destination / 'matriz_umbrales.csv').open('w', encoding='utf-8-sig', newline='') as f:
        keys = ['umbral','admitidas','retenidas','admitidas_sin_revision_humana',
                'admitidas_con_revision_humana','admitidas_revisadas_bien_localizadas',
                'admitidas_revisadas_yoloe_fallo','nuevas_admitidas_sobre_040',
                'nuevas_admitidas_bien_localizadas_revisadas',
                'retenidas_revisadas_bien_localizadas','retenidas_revisadas_yoloe_fallo']
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(summary['escenarios'])
    with (destination / 'casos_trazables.csv').open('w', encoding='utf-8-sig', newline='') as f:
        keys = ['sha256','producto','fuente','grupo','archivo','estado_original','candidatos_producto',
                'confianza','mascara','revision','gate_040','gate_030','gate_025']
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in records:
            out = {k: row.get(k) for k in keys}
            out.update({f'gate_{int(t*100):03d}': 'admitida' if _ready(row,t) else 'retenida' for t in THRESHOLDS})
            writer.writerow(out)
    cases = '\n'.join(f"| {s['umbral']} | {s['admitidas']} | {s['retenidas']} | {s['admitidas_con_revision_humana']} | {s['admitidas_sin_revision_humana']} | {s['admitidas_revisadas_yoloe_fallo']} |" for s in summary['escenarios'])
    report = f'''# AG-037: comparacion retrospectiva del umbral de deteccion

**Alcance:** experimento sobre resultados YOLOE ya calculados; no evaluacion del clasificador E0/E1/E2.
**Universo:** {summary['imagenes']} fotografias con SHA256 unico, {summary['revisiones_manuales_selectivas']} veredictos humanos selectivos ({summary['revisiones_bien_localizadas']} bien localizadas, {summary['revisiones_yoloe_fallo']} fallos) y {summary['imagenes_sin_revision']} fotografias sin veredicto humano.

| Umbral | Admitidas | Retenidas | Admitidas revisadas | Admitidas sin revisar | Fallos humanos admitidos entre los revisados |
|---:|---:|---:|---:|---:|---:|
{cases}

**Hallazgo:** Los tres umbrales retienen los 10 fallos observados por el revisor en el subconjunto selectivo. Esto NO equivale a una tasa global cero de falsas admisiones, porque todas las 65 admisiones originales estan sin revisar.

Se mantiene 0,40 como umbral **operativo provisional**, no calibrado estadisticamente. La diferencia entre deteccion del producto y grado visual de calidad E0/E1/E2 es obligatoria. Tampoco se acredita ensayo fisico con ESP32.

**Trazabilidad de entrada**: detecciones `{summary['fuentes_sha256']['detecciones_csv']}`; revisiones `{summary['fuentes_sha256']['revision_manual_csv']}`.

## Condiciones para una calibracion posterior

Validar una muestra de aceptados originales y negativos dificiles, repartir por pieza fisica/grupo independiente y documentar denominadores de error. No cambiar produccion con solo los casos rechazados selectivamente.
'''
    (destination / 'informe_ag037.md').write_text(report, encoding='utf-8')
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--detecciones', required=True, type=Path)
    p.add_argument('--revisiones', required=True, type=Path)
    p.add_argument('--salida', required=True, type=Path)
    args = p.parse_args(argv)
    try:
        result = write_results(args.detecciones, args.revisiones, args.salida)
    except (ValueError, OSError, UnicodeError) as exc:
        p.exit(2, f'AG-037: no se pudo generar el informe: {exc}\n')
    print(json.dumps({'estado': result['alcance'], 'imagenes': result['imagenes'],
                      'revisadas': result['revisiones_manuales_selectivas'],
                      'salida': str(args.salida)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
