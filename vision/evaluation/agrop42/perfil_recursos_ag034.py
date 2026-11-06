"""AG-034 / Incremento 10: perfiles comparables de CPU y memoria.

Experimento AUXILIAR mango/tomate, no etiquetas comerciales E0/E1/E2.
Ejecuta los dos enfoques sobre los mismos IDs fuente de prueba; no acredita
independencia física de los frutos ni rendimiento del hardware definitivo.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import platform
import re
import statistics
import sys
import time
import tracemalloc
from collections import Counter
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from PIL import Image, __version__ as pillow_version

from .benchmark_producto_ag034 import (
    FEATURES,
    choose_classical,
    fit_linear,
    get_features,
    linear_predict,
    metrics,
    rule_predict,
    split_groups,
)

VERSION = 'ag034-perfil-recursos-v1'
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_ZIP_FILES = 1000
MAX_TOTAL_BYTES = 500 * 1024 * 1024
PRODUCTS = {'mangos': 'mango', 'tomates': 'tomate'}


def _validar_archivo(nombre: str) -> tuple[str, str]:
    """Solo rutas POSIX regulares en subdirectorios por producto/ID."""
    if not isinstance(nombre, str) or '\\' in nombre or '\x00' in nombre:
        raise ValueError('Ruta de imagen insegura')
    p = PurePosixPath(nombre)
    if (p.is_absolute() or len(p.parts) != 3 or '.' in p.parts
            or '..' in p.parts or p.parts[0] not in PRODUCTS
            or p.suffix.lower() not in {'.jpg', '.jpeg', '.png'}
            or ':' in nombre or nombre.startswith('//')):
        raise ValueError('Ruta de imagen fuera de la estructura admitida: ' + nombre)
    return PRODUCTS[p.parts[0]], p.parts[1]


def _cargar_muestras(zip_path: Path) -> list[dict]:
    """Verifica inventario, SHA e integridad antes del experimento."""
    if not zip_path.is_file():
        raise FileNotFoundError('No existe el ZIP de entrada')
    rows = []
    try:
        with ZipFile(zip_path) as z:
            info = z.infolist()
            if len(info) > MAX_ZIP_FILES or sum(i.file_size for i in info) > MAX_TOTAL_BYTES:
                raise ValueError('ZIP excede límites de tamaño o cantidad')
            names = [i.filename for i in info]
            if len(names) != len(set(names)) or 'trazabilidad.csv' not in names:
                raise ValueError('ZIP duplicado o sin trazabilidad.csv')
            file_info = {i.filename: i for i in info}
            csv_raw = z.read('trazabilidad.csv')
            if len(csv_raw) > 4 * 1024 * 1024:
                raise ValueError('CSV demasiado grande')
            reader = csv.DictReader(io.StringIO(csv_raw.decode('utf-8-sig')))
            # Producto se deriva exclusivamente de la carpeta, no de una etiqueta E0/E1/E2.
            required = {'archivo', 'id_ejemplar', 'sha256'}
            if not required.issubset(set(reader.fieldnames or [])):
                raise ValueError('Esquema de trazabilidad incompleto')
            records = list(reader)
            if not records:
                raise ValueError('No hay fotografías en el inventario')
            seen_paths, seen_shas = set(), set()
            groups_by_source = {}
            for rec in records:
                nombre = (rec.get('archivo') or '').strip()
                producto, id_path = _validar_archivo(nombre)
                id_ejemplar = (rec.get('id_ejemplar') or '').strip()
                if id_path != id_ejemplar or nombre in seen_paths:
                    raise ValueError('ID de ejemplar o ruta duplicada/inconsistente: ' + nombre)
                if nombre not in file_info or file_info[nombre].is_dir():
                    raise ValueError('Fotografía ausente: ' + nombre)
                if file_info[nombre].file_size > MAX_FILE_BYTES:
                    raise ValueError('Fotografía demasiado grande: ' + nombre)
                sha_declarado = (rec.get('sha256') or '').strip().lower()
                if not re.fullmatch(r'[0-9a-f]{64}', sha_declarado):
                    raise ValueError('SHA declarado inválido: ' + nombre)
                original_group = (rec.get('grupo_original') or '').strip()
                if original_group:
                    source_group = (producto, original_group)
                    if source_group in groups_by_source and groups_by_source[source_group] != id_ejemplar:
                        raise ValueError('Grupo original compartido entre ejemplares: ' + original_group)
                    groups_by_source[source_group] = id_ejemplar
                payload = z.read(nombre)
                if hashlib.sha256(payload).hexdigest() != sha_declarado:
                    raise ValueError('SHA-256 no coincide: ' + nombre)
                if sha_declarado in seen_shas:
                    raise ValueError('Foto duplicada por SHA-256: ' + nombre)
                seen_paths.add(nombre)
                seen_shas.add(sha_declarado)
                try:
                    t0 = time.perf_counter_ns()
                    with Image.open(io.BytesIO(payload)) as image:
                        if image.format not in ('JPEG', 'PNG'):
                            raise ValueError('Formato incompatible')
                        features = get_features(image)
                    t_preproc = (time.perf_counter_ns() - t0) / 1_000_000
                except (OSError, ValueError, Image.DecompressionBombError) as exc:
                    raise ValueError('Imagen no procesable: ' + nombre) from exc
                rows.append({
                    'path': nombre, 'producto': producto, 'id_ejemplar': id_ejemplar,
                    'grupo_original': original_group, 'sha256': sha_declarado,
                    'fuente': rec.get('fuente') or '', 'bytes': payload,
                    'features': features, 'y': int(producto == 'tomate'),
                    'preprocesamiento_ms': t_preproc,
                })
            extras = [i for i in info if i.filename.startswith(('mangos/', 'tomates/'))
                      and not i.is_dir() and i.filename.lower().endswith(('.jpg','.jpeg','.png'))
                      and i.filename not in seen_paths]
            if extras:
                raise ValueError('Existen fotografías fuera de trazabilidad.csv')
    except (BadZipFile, UnicodeError, KeyError) as exc:
        raise ValueError('ZIP o manifiesto no legible') from exc
    return rows


def _percentil(vals: list[float], p: float) -> float:
    data = sorted(vals)
    if not data:
        raise ValueError('No hay observaciones para calcular percentil')
    index = (len(data) - 1) * p
    lower = int(index)
    upper = min(lower + 1, len(data) - 1)
    return data[lower] + (data[upper] - data[lower]) * (index - lower)


def _resumen_ms(vals: list[float]) -> dict:
    return {
        'n': len(vals), 'mediana_ms': round(statistics.median(vals), 6),
        'p95_ms': round(_percentil(vals, .95), 6),
        'min_ms': round(min(vals), 6), 'max_ms': round(max(vals), 6),
    }


def _medir_inferencia(predictor, test: list[dict], repeticiones: int, bucles: int) -> dict:
    """Misma entrada precalculada; promedia un lote para reducir ruido de reloj."""
    features = [r['features'] for r in test]
    for _ in range(2):
        for x in features:
            predictor(x)
    medidas = []
    for _ in range(repeticiones):
        start = time.perf_counter_ns()
        for _loop in range(bucles):
            for x in features:
                predictor(x)
        medidas.append((time.perf_counter_ns() - start) / (1_000_000 * bucles * len(features)))
    return _resumen_ms(medidas)


def _medir_extremo_a_extremo(predictor, test: list[dict], repeticiones: int) -> dict:
    """Decodificación + 11 features + predicción; mide cada vista por separado."""
    datos = []
    for vuelta in range(repeticiones):
        orden = test if vuelta % 2 == 0 else list(reversed(test))
        for row in orden:
            start = time.perf_counter_ns()
            with Image.open(io.BytesIO(row['bytes'])) as image:
                feature = get_features(image)
            predictor(feature)
            datos.append((time.perf_counter_ns() - start) / 1_000_000)
    return _resumen_ms(datos)


def _pico_python(predictor, test: list[dict]) -> float:
    """Memoria de asignaciones rastreada por Python; no RSS nativa ni GPU."""
    tracemalloc.start()
    try:
        for row in test:
            with Image.open(io.BytesIO(row['bytes'])) as image:
                predictor(get_features(image))
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return round(peak / (1024**2), 5)


def _datos_maquina() -> dict:
    return {
        'sistema': platform.system(), 'version_sistema': platform.release(),
        'arquitectura': platform.machine(), 'procesador_declarado': platform.processor() or 'no_disponible',
        'cpus_logicas': os.cpu_count(), 'python': platform.python_version(),
        'implementacion_python': platform.python_implementation(), 'pillow': pillow_version,
        'tipo_de_equipo': 'equipo_que_ejecuta_el_comando_no_hardware_final_acreditado',
    }


def ejecutar(zip_path: Path, salida: Path, *, repeticiones: int = 5, bucles: int = 250,
            repeticiones_pipeline: int = 2) -> dict:
    if not (2 <= repeticiones <= 30 and 10 <= bucles <= 10000
            and 1 <= repeticiones_pipeline <= 10):
        raise ValueError('Parámetros de medición fuera de rango permitido')
    zip_path = Path(zip_path).resolve()
    salida = Path(salida).resolve()
    if salida.exists():
        raise FileExistsError('Carpeta de salida ya existe: ' + str(salida))
    rows = _cargar_muestras(zip_path)
    mapping = split_groups(rows, seed=34)
    for row in rows:
        row['split'] = mapping[(row['producto'], row['id_ejemplar'])]
    sets = {name: [r for r in rows if r['split'] == name]
            for name in ('entrenamiento', 'validacion', 'prueba')}
    train, val, test = (sets[k] for k in ('entrenamiento', 'validacion', 'prueba'))
    if len({r['producto'] for r in test}) != 2:
        raise ValueError('El test necesita las dos especies')

    t0 = time.perf_counter_ns()
    rule = choose_classical(train)
    t_rule = (time.perf_counter_ns() - t0) / 1_000_000
    t0 = time.perf_counter_ns()
    light = fit_linear(train)
    t_light = (time.perf_counter_ns() - t0) / 1_000_000
    approaches = {
        'reglas': (lambda x: rule_predict(rule, x), rule, t_rule),
        'modelo_ligero': (lambda x: linear_predict(light, x), light, t_light),
    }
    results = {}
    for key, (predictor, model, t_train) in approaches.items():
        results[key] = {
            'n_vistas_test': len(test),
            'metricas_test': metrics(test, predictor),
            'metricas_validacion': metrics(val, predictor),
            'entrenamiento_ms': round(t_train, 4),
            'inferencia_sin_extraccion': _medir_inferencia(predictor, test, repeticiones, bucles),
            'pipeline_completo_en_equipo_local': _medir_extremo_a_extremo(predictor, test, repeticiones_pipeline),
            'tracemalloc_pico_mib_en_test': _pico_python(predictor, test),
            'modelo_json_bytes': len(json.dumps(model, sort_keys=True).encode('utf-8')),
            'parametros_aprendidos': 3 if key == 'reglas' else len(light['pesos']) + 1,
        }
    # No afirmar que tres vistas son tres frutos independientes.
    parts = {k: {(r['producto'], r['id_ejemplar']) for r in sample} for k, sample in sets.items()}
    if any(parts[a] & parts[b] for a, b in (
        ('entrenamiento','validacion'),('entrenamiento','prueba'),('validacion','prueba')
    )):
        raise AssertionError('Filtración de IDs entre particiones')

    same_accuracy = (results['reglas']['metricas_test']['accuracy_vistas'] ==
                     results['modelo_ligero']['metricas_test']['accuracy_vistas'])
    rule_latency = results['reglas']['inferencia_sin_extraccion']['mediana_ms']
    light_latency = results['modelo_ligero']['inferencia_sin_extraccion']['mediana_ms']
    rule_size = results['reglas']['modelo_json_bytes']
    light_size = results['modelo_ligero']['modelo_json_bytes']
    baseline_recommendation = (same_accuracy and rule_latency <= light_latency and rule_size < light_size)
    decision = {
        'alternativa_preferida_experimento_auxiliar': ('reglas' if baseline_recommendation else 'sin_seleccion_automatica'),
        'criterio': ('misma exactitud de prueba, menor mediana de inferencia y menor JSON'
                     if baseline_recommendation else 'diferencias requieren revisión manual; no imponer selección'),
        'despliegue_autorizado': False,
        'cierre_total_AG034_acreditado': False,
        'hardware_objetivo_validado': False,
        'clasificacion_e0_e1_e2_evaluada': False,
    }
    result = {
        'version': VERSION, 'actividad': 'AG-034 / AGROP-42',
        'tipo': 'benchmark_auxiliar_identificacion_mango_tomate_no_defectos',
        'origen_zip': zip_path.name, 'zip_sha256': hashlib.sha256(zip_path.read_bytes()).hexdigest(),
        'dataset': {
            'vistas': len(rows), 'grupos_fuente_declarados': len(mapping),
            'por_producto': dict(Counter(r['producto'] for r in rows)),
            'particion_vistas': {k: len(v) for k, v in sets.items()},
            'particion_ids_fuente': {k: len(v) for k, v in parts.items()},
            'criterio_particion': 'producto + id_ejemplar declarado, semilla 34',
            'vistas_de_un_id_en_una_sola_particion': True,
            'independencia_fisica_de_piezas_acreditada': False,
            'procedencia_fotografias': 'fuentes_externas_no_adquisicion_propia',
        },
        'entorno': _datos_maquina(),
        'medicion': {
            'repeticiones_inferencia_por_lote': repeticiones,
            'bucles_por_lote': bucles,
            'repeticiones_pipeline': repeticiones_pipeline,
            'preprocesamiento_inicial': _resumen_ms([r['preprocesamiento_ms'] for r in rows]),
            'latencias': 'mediciones locales no son reproducibles bit a bit; medianas y p95 dependen de la maquina',
            'memoria': 'tracemalloc: asignaciones Python; excluye memoria nativa, CUDA y RSS total',
        },
        'enfoques': results,
        'decision': decision,
        'limitaciones': [
            'Mango del dataset externo Ataulfo, NO Kent; variedades y sesiones no acreditadas.',
            'Las clases coinciden con fuentes fotográficas distintas: posible aprendizaje de fondo o dominio.',
            'La tarea auxiliar distingue mango/tomate; no evalúa atributos externos ni etiquetas E0/E1/E2.',
            'El conjunto de prueba contiene IDs agrupados, no captura independiente en la instalación real.',
            'Mediciones efectuadas en este equipo; no se validan RAM total ni latencias del hardware final.',
            'No se calcula IoU/Dice ni exactitud de defectos porque no hay ground truth aprobado.',
        ],
    }
    salida.mkdir(parents=True, exist_ok=False)
    (salida / 'AG034_perfil_recursos.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    _guardar_csv(salida / 'AG034_cuadro_comparativo.csv', results)
    (salida / 'AG034_informe_rendimiento.md').write_text(_informe(result), encoding='utf-8')
    return result


def _guardar_csv(path: Path, results: dict) -> None:
    campos = ['enfoque','vistas_test','accuracy_producto','entrenamiento_ms',
              'inferencia_mediana_ms','inferencia_p95_ms','pipeline_mediana_ms',
              'pipeline_p95_ms','tracemalloc_pico_mib','modelo_json_bytes']
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        for name, datos in results.items():
            writer.writerow({
                'enfoque': name, 'vistas_test': datos['n_vistas_test'],
                'accuracy_producto': datos['metricas_test']['accuracy_vistas'],
                'entrenamiento_ms': datos['entrenamiento_ms'],
                'inferencia_mediana_ms': datos['inferencia_sin_extraccion']['mediana_ms'],
                'inferencia_p95_ms': datos['inferencia_sin_extraccion']['p95_ms'],
                'pipeline_mediana_ms': datos['pipeline_completo_en_equipo_local']['mediana_ms'],
                'pipeline_p95_ms': datos['pipeline_completo_en_equipo_local']['p95_ms'],
                'tracemalloc_pico_mib': datos['tracemalloc_pico_mib_en_test'],
                'modelo_json_bytes': datos['modelo_json_bytes'],
            })


def _informe(result: dict) -> str:
    data = result['dataset']; methods = result['enfoques']; machine = result['entorno']
    rows = []
    for name in ('reglas', 'modelo_ligero'):
        x = methods[name]
        rows.append('| {} | {:.1%} | {:.4f} | {:.4f} | {:.4f} | {:.3f} | {} |'.format(
            name, x['metricas_test']['accuracy_vistas'],
            x['inferencia_sin_extraccion']['mediana_ms'],
            x['pipeline_completo_en_equipo_local']['mediana_ms'],
            x['entrenamiento_ms'], x['tracemalloc_pico_mib_en_test'],
            x['modelo_json_bytes'],
        ))
    return (
        '# AG-034 — Comparación de recursos y decisión técnica (Incremento 10)\n\n'
        '**Alcance:** control auxiliar mango/tomate, NO clasificación de defectos E0/E1/E2.\n\n'
        f'**Evidencia:** ZIP SHA-256 `{result["zip_sha256"]}`, {data["vistas"]} vistas '
        f'y {data["grupos_fuente_declarados"]} IDs de fuente declarados. '
        f'Separación por ID: {data["particion_vistas"]}.\n\n'
        f'**Entorno ejecutor:** {machine["sistema"]} {machine["version_sistema"]}, '
        f'arquitectura {machine["arquitectura"]}, Python {machine["python"]}, '
        f'Pillow {machine["pillow"]}, CPU lógicas {machine["cpus_logicas"]}. '
        '**No** constituye prueba del hardware final de AgroScan ni ESP32.\n\n'
        '## Comparación sobre el mismo conjunto de prueba\n\n'
        '| Método | Exactitud producto | Inferencia mediana ms/vista | '
        'Pipeline completo mediana ms/vista | Ajuste ms | Pico tracemalloc MiB | JSON bytes |\n'
        '|---|---:|---:|---:|---:|---:|---:|\n' + '\n'.join(rows) + '\n\n'
        f'Preprocesamiento inicial: mediana {result["medicion"]["preprocesamiento_inicial"]["mediana_ms"]:.3f} '
        'ms/vista. Tanto regla como modelo reciben exactamente los mismos 11 atributos. '
        'La inferencia cronometrada excluye extracción; el pipeline completo incluye apertura JPEG, '
        'extracción y predicción, medidas locales en la prueba agrupada.\n\n'
        'El pico de `tracemalloc` **solo mide asignaciones Python** durante el recorrido '
        'del conjunto de prueba: no estima RAM total del dispositivo. '
        'Se incluyen p95 y repeticiones en JSON/CSV. No se fijaron presupuestos de latencia/RAM '
        'porque no existe un umbral validado del hardware final.\n\n'
        '## Decisión provisional\n\n'
        f'**Alternativa auxiliar:** `{result["decision"]["alternativa_preferida_experimento_auxiliar"]}`. '
        f'Criterio: {result["decision"]["criterio"]}. '
        'Esta decisión no autoriza despliegue o clasificación comercial.\n\n'
        '## Cierre de AG-034\n\n'
        '**No acreditado íntegramente.** Falta comparación de atributos externos/E0–E2 '
        'con anotaciones verificadas y pruebas en el hardware objetivo. El benchmark actual '
        'puede adjuntarse a Jira como evidencia parcial reproducible, no como cierre.\n\n'
        'Limitaciones: fuente mango Ataulfo (no Kent); confusión de clase y dominio fotográfico; '
        'IDs declarados no garantizan identidad física; prueba no independiente por proveedor.\n'
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='AG-034: perfil local CPU y memoria del benchmark auxiliar')
    parser.add_argument('--zip', type=Path, required=True)
    parser.add_argument('--salida', type=Path, required=True, help='Carpeta nueva de tres informes; no sobrescribe')
    parser.add_argument('--repeticiones', type=int, default=5)
    parser.add_argument('--bucles', type=int, default=250)
    parser.add_argument('--repeticiones-pipeline', type=int, default=2)
    args = parser.parse_args(argv)
    try:
        result = ejecutar(args.zip, args.salida, repeticiones=args.repeticiones,
                          bucles=args.bucles, repeticiones_pipeline=args.repeticiones_pipeline)
    except (ValueError, OSError) as exc:
        print(json.dumps({'estado':'error','detalle':str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({
        'estado': 'perfil_auxiliar_generado', 'vistas': result['dataset']['vistas'],
        'vistas_test': result['dataset']['particion_vistas']['prueba'],
        'entorno': result['entorno']['sistema'],
        'metodos': {k: {
            'accuracy_producto':v['metricas_test']['accuracy_vistas'],
            'inferencia_mediana_ms':v['inferencia_sin_extraccion']['mediana_ms'],
            'pipeline_mediana_ms':v['pipeline_completo_en_equipo_local']['mediana_ms'],
        } for k,v in result['enfoques'].items()},
        'decision': result['decision'], 'salida': str(Path(args.salida).resolve()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
