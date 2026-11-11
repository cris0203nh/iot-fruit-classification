"""AG-036 incremento 06: sensibilidad de umbrales con auditoría humana de localización.

No reejecuta YOLOE ni modifica su umbral de producción. Los resultados de
conf=.25 solo permiten simulaciones retrospectivas para umbrales >= .25.
Este informe NO calcula exactitud, precisión ni etiquetas de calidad E0/E1/E2.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

PRED_FIELDS = (
    'fuente', 'producto_candidato', 'grupo_candidato', 'ruta_relativa',
    'sha256_imagen', 'estado_deteccion', 'candidatos_producto',
    'confianza_mejor_coincidencia', 'mascara_poligono_disponible',
    'etiqueta_e0_e1_e2',
)
REVIEW_FIELDS = (
    'fuente', 'producto', 'grupo', 'ruta_relativa', 'sha256_imagen',
    'estado_yoloe', 'decision_revisor', 'observacion_revisor',
)
THRESHOLDS = (Decimal('0.40'), Decimal('0.30'), Decimal('0.25'))
AUTOMATIC_READY = 'deteccion_lista_para_captura'
VERDICTS = {'Bien localizada', 'YOLOE falló', 'Caja incorrecta',
            'Foto no evaluable', 'Duda'}
STATES = {
    AUTOMATIC_READY, 'confianza_inferior_a_umbral_captura',
    'deteccion_sin_clase_esperada', 'sin_deteccion',
    'multiples_candidatos_esperados', 'sin_poligono_de_segmentacion',
}
OUTPUT_FIELDS = (
    'producto', 'fuente', 'grupo', 'ruta_relativa', 'sha256_imagen',
    'estado_original', 'confianza', 'decision_revisor', 'observacion_revisor',
    'captura_0_40', 'captura_0_30', 'captura_0_25',
    'nuevo_candidato_0_30', 'nuevo_candidato_0_25', 'motivo_bloqueo',
)


class AuditError(ValueError):
    """Entrada o correspondencia de evidencias inválida."""


def _load_csv(path: Path, required: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.is_file():
        raise AuditError(f'Archivo de entrada no encontrado: {path}')
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        if len(header) != len(set(header)) or not set(required).issubset(header):
            raise AuditError(f'Cabeceras inválidas en {path.name}')
        data = list(reader)
    if not data or any(None in row or None in row.values() for row in data):
        raise AuditError(f'CSV vacío o malformado: {path.name}')
    return data


def _identity(row: dict) -> str:
    sha = row['sha256_imagen'].strip().lower()
    if len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
        raise AuditError('SHA256 inválido')
    route = row['ruta_relativa']
    if (not route or '\\' in route or ':' in route or route.startswith('/')
            or any(p in ('', '.', '..') for p in route.split('/'))):
        raise AuditError('Ruta de imagen inválida')
    return sha


def _decimal(value: str, field: str) -> Decimal | None:
    if value == '':
        return None
    try:
        num = Decimal(value)
        if not num.is_finite() or not Decimal('0') <= num <= Decimal('1'):
            raise InvalidOperation()
        return num
    except InvalidOperation as exc:
        raise AuditError(f'Confianza inválida en {field}') from exc


def _ready(pred: dict, threshold: Decimal) -> bool:
    """Misma regla de 1 candidato + máscara del detector, variando solo umbral."""
    return (pred['_count'] == 1 and pred['mascara_poligono_disponible'] == 'si'
            and pred['_conf'] is not None and pred['_conf'] >= threshold)


def _block_reason(pred: dict) -> str:
    if pred['_count'] > 1:
        return 'multiples_candidatos'
    if pred['_count'] == 0:
        return ('sin_deteccion' if pred['estado_deteccion'] == 'sin_deteccion'
                else 'sin_clase_esperada')
    if pred['mascara_poligono_disponible'] != 'si':
        return 'sin_mascara'
    if pred['_conf'] is None:
        return 'sin_confianza'
    if pred['_conf'] < Decimal('0.25'):
        return 'por_debajo_del_limite_de_inferencia'
    return ''


def _read_predictions(path: Path):
    predictions = _load_csv(path, PRED_FIELDS)
    by_sha = {}
    for p in predictions:
        sha = _identity(p)
        if sha in by_sha:
            raise AuditError('SHA256 repetido en resultados de YOLOE')
        if p['estado_deteccion'] not in STATES:
            raise AuditError('Estado de detector no reconocido')
        if p['producto_candidato'] not in ('mango', 'tomate'):
            raise AuditError('Producto de detector no reconocido')
        try:
            count = int(p['candidatos_producto'])
        except ValueError as exc:
            raise AuditError('Conteo de candidatos inválido') from exc
        if count < 0 or p['mascara_poligono_disponible'] not in ('si', 'no'):
            raise AuditError('Candidatos o máscara inválidos')
        p['_count'] = count
        p['_conf'] = _decimal(p['confianza_mejor_coincidencia'],sha)
        if p['_conf'] is not None and count == 0:
            raise AuditError('Confianza presente sin candidatos de clase esperada')
        if count == 1 and p['_conf'] is None:
            raise AuditError('Candidato esperado sin confianza registrada')
        if p['etiqueta_e0_e1_e2'].strip():
            raise AuditError('Los resultados del detector no deben contener E0/E1/E2')
        if (p['estado_deteccion'] == AUTOMATIC_READY) != _ready(p,Decimal('0.40')):
            raise AuditError('Estado original incompatible con la regla 0.40')
        by_sha[sha] = p
    return by_sha


def _read_reviews(path: Path, predictions: dict):
    rows = _load_csv(path, REVIEW_FIELDS)
    reviews = {}
    for r in rows:
        sha = _identity(r)
        if sha in reviews:
            raise AuditError('Revisión humana duplicada')
        if sha not in predictions:
            raise AuditError('Revisión sin correspondencia SHA256 en el detector')
        p = predictions[sha]
        pairs = (('fuente','fuente'),('producto','producto_candidato'),
                 ('grupo','grupo_candidato'),('ruta_relativa','ruta_relativa'),
                 ('estado_yoloe','estado_deteccion'))
        if any(r[left] != p[right] for left,right in pairs):
            raise AuditError('La revisión no coincide con fuente/producto/grupo/ruta/estado')
        if p['estado_deteccion'] == AUTOMATIC_READY:
            raise AuditError('Esta herramienta espera revisiones solo de no listos')
        if r['decision_revisor'] not in VERDICTS:
            raise AuditError('Decisión de revisión humana inválida o vacía')
        reviews[sha] = r
    expected = {sha for sha,p in predictions.items() if p['estado_deteccion'] != AUTOMATIC_READY}
    if reviews.keys() != expected:
        missing = len(expected - reviews.keys())
        raise AuditError(f'Revisión incompleta o sobrante: faltan {missing} registros no listos')
    return reviews


def _safe_output(output: Path, inputs: tuple[Path, ...]):
    if output.exists():
        raise AuditError('La salida ya existe; no se sobrescriben evidencias')
    output_resolved = output.resolve()
    if any(output_resolved == p.resolve() for p in inputs):
        raise AuditError('Salida coincide con entrada')
    repo = Path(__file__).resolve().parents[3]
    if (repo / '.git').exists() and output_resolved.is_relative_to(repo):
        raise AuditError('Guardar los reportes fuera del repositorio')


def analyze(resultados: Path, revisiones: Path, salida_dir: Path) -> dict:
    """Reproduce escenarios, sin extrapolar veredictos a capturas no revisadas."""
    _safe_output(salida_dir, (resultados, revisiones))
    preds = _read_predictions(resultados)
    reviews = _read_reviews(revisiones, preds)
    original = sum(_ready(p,Decimal('0.40')) for p in preds.values())
    totals = {str(t): sum(_ready(p,t) for p in preds.values()) for t in THRESHOLDS}
    status = Counter(p['estado_deteccion'] for p in preds.values())
    verdicts = Counter(r['decision_revisor'] for r in reviews.values())
    by_product = Counter((p['producto_candidato'],p['estado_deteccion']) for p in preds.values())
    detail = []
    new_good = {}
    for t in (Decimal('0.30'),Decimal('0.25')):
        gained = [sha for sha,p in preds.items()
                  if _ready(p,t) and not _ready(p,Decimal('0.40'))]
        new_good[str(t)] = {
            'nuevos_candidatos':len(gained),
            'revision_bien_localizada':sum(reviews.get(sha,{}).get('decision_revisor') == 'Bien localizada' for sha in gained),
            'revision_no_concluyente_o_fallo':sum(reviews.get(sha,{}).get('decision_revisor') != 'Bien localizada' for sha in gained),
        }
    for sha,p in sorted(preds.items(), key=lambda kv:kv[1]['ruta_relativa']):
        rev = reviews.get(sha, {})
        eligible = [_ready(p,t) for t in THRESHOLDS]
        detail.append({
            'producto':p['producto_candidato'], 'fuente':p['fuente'],
            'grupo':p['grupo_candidato'], 'ruta_relativa':p['ruta_relativa'],
            'sha256_imagen':sha, 'estado_original':p['estado_deteccion'],
            'confianza':str(p['_conf']) if p['_conf'] is not None else '',
            'decision_revisor':rev.get('decision_revisor','SIN_REVISION'),
            'observacion_revisor':rev.get('observacion_revisor',''),
            'captura_0_40':'si' if eligible[0] else 'no',
            'captura_0_30':'si' if eligible[1] else 'no',
            'captura_0_25':'si' if eligible[2] else 'no',
            'nuevo_candidato_0_30':'si' if eligible[1] and not eligible[0] else 'no',
            'nuevo_candidato_0_25':'si' if eligible[2] and not eligible[0] else 'no',
            'motivo_bloqueo':_block_reason(p),
        })
    failures = [r for r in detail if r['decision_revisor'] == 'YOLOE falló'
                or r['decision_revisor'] == 'Caja incorrecta']
    reviewed_ready = sum(1 for r in reviews.values() if r['decision_revisor'] == 'Bien localizada')
    summary = {
        'estado':'analisis_retroactivo_no_calibracion_produccion',
        'fotografias':len(preds), 'sin_revision_humana':len(preds)-len(reviews),
        'revisiones_humanas':len(reviews),
        'veredictos_revisados':dict(sorted(verdicts.items())),
        'estados_originales':dict(sorted(status.items())),
        'escenarios_candidatos_captura':totals,
        'nuevos_candidatos_revisados':new_good,
        'fallos_confirmados_revision':len(failures),
        'grupos_con_fallos':dict(sorted(Counter(r['grupo'] for r in failures).items())),
        'detecciones_originales_listos_sin_revision':original,
        'bien_localizadas_en_no_listos':reviewed_ready,
        'comparacion_por_producto_estado':[
            {'producto':product,'estado':state,'cantidad':count}
            for (product,state),count in sorted(by_product.items())],
        'detector_inferencia_conf_minima':0.25,
        'etiquetas_e0_e1_e2':0,
        'exactitud_detector':None,
        'umbral_de_produccion_modificado':False,
        'aprobado_para_entrenamiento_calidad':False,
        'cierre_total_AG036_acreditado':False,
        'limitaciones':[
            'Los 65 casos listos originalmente carecen de revisión humana en este conjunto.',
            'El conjunto revisado se seleccionó por rechazo automático, no al azar.',
            'No es una medición de falsos positivos ni de precisión/recall.',
            'No puede recuperar predicciones descartadas por conf=0.25 durante inferencia.',
            'Las detecciones múltiples siguen bloqueadas en todos los umbrales.',
            'No hay doble etiquetado independiente ni grados E0/E1/E2.'
        ],
        'entradas_sha256':{
            'resultados':hashlib.sha256(resultados.read_bytes()).hexdigest(),
            'revisiones':hashlib.sha256(revisiones.read_bytes()).hexdigest(),
        }
    }
    markdown = [
        '# AG-036 — Incremento 06: sensibilidad retrospectiva de confianza', '',
        f"Fotografías: **{len(preds)}**. Revisión humana de casos no listos: **{len(reviews)}**; "
        f"casos originalmente listos sin revisión: **{len(preds)-len(reviews)}**.", '',
        '| Umbral | Candidatos para captura | Nuevos respecto a 0,40 | Nuevos bien localizados según revisión |',
        '|---:|---:|---:|---:|',
    ]
    for t in THRESHOLDS:
        cnt=totals[str(t)]
        good=0 if t == Decimal('0.40') else new_good[str(t)]['revision_bien_localizada']
        markdown.append(f'| {str(t).replace(".",",")} | {cnt}/{len(preds)} | {cnt-original} | {good} |')
    markdown.extend([
        '',f"Fallos confirmados por revisión: **{len(failures)}**. "
        f"Casos de baja confianza marcados «Bien localizada»: **{sum(1 for sha,r in reviews.items() if r['decision_revisor']=='Bien localizada' and preds[sha]['estado_deteccion']=='confianza_inferior_a_umbral_captura')}** "
        '(consultar CSV de revisiones).','',
        '## Decisión técnica',
        '- **Conservar 0,40 en producción**: este experimento solo compara reglas sobre detecciones ya guardadas.',
        '- Los 10 fallos de clase/ausencia no se solucionan variando exclusivamente este umbral.',
        '- Revisar los 65 casos listos y añadir negativos difíciles antes de estimar falsos positivos o calibrar un umbral.',
        '- Conservar la regla de un único candidato y polígono de máscara obligatorio.',
        '- Analizar por separado los casos de clase equivocada y sin detección, incluyendo distancia/encuadre como hipótesis.',
        '- AG-036 E0/E1/E2 continúa pendiente de doble etiquetado humano independiente por pieza.', '',
        '## Limitaciones',
    ])
    markdown.extend(f'- {item}' for item in summary['limitaciones'])
    salida_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ag036-umbral-', dir=salida_dir.parent) as folder:
        tmp=Path(folder)
        with (tmp/'escenarios_97.csv').open('x', encoding='utf-8-sig', newline='') as file:
            writer=csv.DictWriter(file, fieldnames=OUTPUT_FIELDS, lineterminator='\n')
            writer.writeheader();writer.writerows(detail)
        with (tmp/'fallos_confirmados.csv').open('x', encoding='utf-8-sig', newline='') as file:
            writer=csv.DictWriter(file, fieldnames=OUTPUT_FIELDS, lineterminator='\n')
            writer.writeheader();writer.writerows(failures)
        (tmp/'resumen_umbrales.json').write_text(
            json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (tmp/'informe_umbrales.md').write_text('\n'.join(markdown)+'\n',encoding='utf-8')
        os.rename(tmp,salida_dir)
    return summary


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resultados',type=Path,required=True,help='resultados_deteccion.csv de YOLOE v2')
    parser.add_argument('--revisiones',type=Path,required=True,help='CSV consolidado de revisión manual de 32 casos')
    parser.add_argument('--salida-dir',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        report=analyze(args.resultados,args.revisiones,args.salida_dir)
    except (AuditError,OSError,ValueError) as exc:
        print(json.dumps({'estado':'error_auditoria','detalle':str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2
    print(json.dumps({'estado':report['estado'],
                      'fotografias':report['fotografias'],
                      'escenarios':report['escenarios_candidatos_captura'],
                      'fallos_confirmados':report['fallos_confirmados_revision']},ensure_ascii=False))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
