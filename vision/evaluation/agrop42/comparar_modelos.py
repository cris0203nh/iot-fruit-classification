"""Comparación reproducible AGROP-42: reglas clásicas vs modelo ligero."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import statistics
import time
import os
from collections import Counter, defaultdict
from pathlib import Path

from .auditar_revisiones import (
    ETIQUETAS, FRUTAS, _fila_elegible, asignar_grupos, auditar_csv,
)

VERSION = "agrop42-comparacion-v1"
ATRIBUTOS = ("r_mediana", "g_mediana", "b_mediana", "area_relativa")
VERDADEROS = {"true", "si", "sí", "1", "yes"}


class ErrorComparacion(ValueError):
    pass


def _texto(row, key):
    return str(row.get(key) or "").strip()


def _sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _leer_csv(path, name):
    if not path.is_file():
        raise ErrorComparacion(f"No existe {name}: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ErrorComparacion(f"{name}: CSV sin encabezado")
        return list(reader)


def _num(value, field):
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        raise ErrorComparacion(f"{field}: se requiere número") from None
    if not math.isfinite(result):
        raise ErrorComparacion(f"{field}: número no finito")
    return result


def _cargar_atributos(path, annotations, eligible):
    rows = _leer_csv(path, "atributos validados")
    required = {
        "registro_id", *ATRIBUTOS,
        "mascara_confirmada", "evidencia_mascara"
    }
    missing = required - set(rows[0])
    if missing:
        raise ErrorComparacion(
            "Faltan columnas en atributos: " + ", ".join(sorted(missing))
        )

    annotation_ids = {_texto(r, "registro_id") for r in annotations}
    by_id = {}

    for n, row in enumerate(rows, 2):
        rid = _texto(row, "registro_id")
        if not rid or rid in by_id or rid not in annotation_ids:
            raise ErrorComparacion(
                f"Atributos, fila {n}: registro_id vacío, duplicado o desconocido"
            )
        by_id[rid] = row

    result = {}

    for annotation in eligible:
        rid = _texto(annotation, "registro_id")
        row = by_id.get(rid)

        if row is None:
            raise ErrorComparacion(f"{rid}: faltan atributos de máscara confirmada")

        if _texto(row, "mascara_confirmada").lower() not in VERDADEROS:
            raise ErrorComparacion(f"{rid}: máscara no confirmada")

        if not _texto(row, "evidencia_mascara"):
            raise ErrorComparacion(f"{rid}: falta evidencia de máscara")

        values = [_num(row[k], f"{rid}/{k}") for k in ATRIBUTOS]

        if any(v < 0 or v > 255 for v in values[:3]):
            raise ErrorComparacion(f"{rid}: RGB fuera de rango")

        if not 0 <= values[3] <= 1:
            raise ErrorComparacion(f"{rid}: área relativa fuera de rango")

        result[rid] = values

    return result


def _validar_regla(rule, product):
    if not isinstance(rule, dict):
        raise ErrorComparacion(f"{product}: regla no válida")

    rid = str(rule.get("id") or "").strip()
    label = rule.get("etiqueta")
    conditions = rule.get("condiciones")

    if not rid or label not in ETIQUETAS:
        raise ErrorComparacion(f"{product}: regla incompleta")

    if not isinstance(conditions, list) or not conditions:
        raise ErrorComparacion(f"{product}/{rid}: faltan condiciones")

    normalized = []

    for cond in conditions:
        if not isinstance(cond, dict) or cond.get("atributo") not in ATRIBUTOS:
            raise ErrorComparacion(f"{product}/{rid}: atributo no válido")

        op = cond.get("operador")
        value = cond.get("valor")

        if op not in {"lt", "lte", "gt", "gte", "eq", "between"}:
            raise ErrorComparacion(f"{product}/{rid}: operador no válido")

        if op == "between":
            if not isinstance(value, list) or len(value) != 2:
                raise ErrorComparacion(
                    f"{product}/{rid}: between requiere [mínimo,máximo]"
                )

            value = [_num(value[0], rid), _num(value[1], rid)]

            if value[0] > value[1]:
                raise ErrorComparacion(f"{product}/{rid}: intervalo invertido")
        else:
            value = _num(value, rid)

        maximum = 1.0 if cond["atributo"] == "area_relativa" else 255.0
        values = value if isinstance(value, list) else [value]

        if any(v < 0 or v > maximum for v in values):
            raise ErrorComparacion(f"{product}/{rid}: umbral fuera de rango")

        normalized.append({
            "atributo": cond["atributo"],
            "operador": op,
            "valor": value,
        })

    return {
        "id": rid,
        "etiqueta": label,
        "condiciones": normalized,
    }


def _cargar_reglas(path, products, eligible):
    if not path.is_file():
        raise ErrorComparacion(f"No existe configuración de reglas: {path}")

    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErrorComparacion(f"JSON de reglas ilegible: {exc}") from exc

    if not isinstance(config, dict):
        raise ErrorComparacion("Configuración de reglas no válida")

    if config.get("version") != "agrop42-reglas-clasicas-v1":
        raise ErrorComparacion("Versión de reglas no compatible")

    product_specs = config.get("productos")

    if not isinstance(product_specs, dict):
        raise ErrorComparacion("Falta el objeto productos")

    output = {}

    for product in products:
        spec = product_specs.get(product)

        if not isinstance(spec, dict):
            raise ErrorComparacion(f"Faltan reglas para {product}")

        rubric_versions = {
            _texto(r, "rubrica_version")
            for r in eligible
            if _texto(r, "producto").lower() == product
        }

        if len(rubric_versions) != 1:
            raise ErrorComparacion(
                f"{product}: versiones de rúbrica inconsistentes"
            )

        if spec.get("rubrica_version") != next(iter(rubric_versions)):
            raise ErrorComparacion(
                f"{product}: versión de rúbrica distinta"
            )

        default = spec.get("clase_por_defecto")
        rules = spec.get("reglas")

        if default not in ETIQUETAS or not isinstance(rules, list) or not rules:
            raise ErrorComparacion(
                f"{product}: falta clase por defecto o reglas aprobadas"
            )

        validated = [_validar_regla(rule, product) for rule in rules]

        if len({r["id"] for r in validated}) != len(validated):
            raise ErrorComparacion(f"{product}: IDs de reglas repetidos")

        output[product] = {
            "clase_por_defecto": default,
            "reglas": validated,
        }

    return output


def _cumple(value, condition):
    op = condition["operador"]
    threshold = condition["valor"]

    if op == "lt":
        return value < threshold
    if op == "lte":
        return value <= threshold
    if op == "gt":
        return value > threshold
    if op == "gte":
        return value >= threshold
    if op == "eq":
        return value == threshold

    return threshold[0] <= value <= threshold[1]


def predecir_reglas(x, config):
    predictions = []

    for values in x:
        features = dict(zip(ATRIBUTOS, values))
        label = config["clase_por_defecto"]

        for rule in config["reglas"]:
            if all(
                _cumple(features[c["atributo"]], c)
                for c in rule["condiciones"]
            ):
                label = rule["etiqueta"]
                break

        predictions.append(label)

    return predictions


def _agrupar_piezas(rows, features):
    buckets = defaultdict(list)
    group_by_record = asignar_grupos(rows)

    for row in rows:
        key = (_texto(row, "lote_id"), _texto(row, "pieza_id"))
        buckets[key].append(row)

    samples = []

    for (lot, piece), views in sorted(buckets.items()):
        labels = {_texto(r, "etiqueta_visual") for r in views}
        groups = {
            group_by_record[_texto(r, "registro_id")]
            for r in views
        }

        if len(labels) != 1 or len(groups) != 1:
            raise ErrorComparacion(
                f"{lot}/{piece}: etiqueta o grupo inconsistente entre vistas"
            )

        ids = sorted(_texto(r, "registro_id") for r in views)

        vector = [
            float(statistics.median(features[rid][i] for rid in ids))
            for i in range(len(ATRIBUTOS))
        ]

        samples.append({
            "pieza": f"{lot}/{piece}",
            "grupo": next(iter(groups)),
            "etiqueta": next(iter(labels)),
            "registro_ids": ids,
            "cantidad_vistas": len(ids),
            "x": vector,
        })

    return samples


def _metricas(y_true, y_pred):
    from sklearn.metrics import (
        accuracy_score,
        balanced_accuracy_score,
        confusion_matrix,
        precision_recall_fscore_support,
    )

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=["E0", "E1", "E2"],
        average="macro",
        zero_division=0,
    )

    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision),
        "recall_macro": float(recall),
        "f1_macro": float(f1),
        "matriz_confusion": confusion_matrix(
            y_true, y_pred, labels=["E0", "E1", "E2"]
        ).tolist(),
        "orden_clases": ["E0", "E1", "E2"],
    }


def _tiempo(predict, x, repeats):
    durations = []

    for _ in range(repeats):
        start = time.perf_counter_ns()
        predict(x)
        elapsed = time.perf_counter_ns() - start
        durations.append(elapsed / max(1, len(x)) / 1_000_000)

    ordered = sorted(durations)

    return {
        "mediana_ms_por_muestra": float(statistics.median(ordered)),
        "p95_ms_por_muestra": float(
            ordered[min(len(ordered)-1, math.ceil(.95 * len(ordered))-1)]
        ),
        "repeticiones": repeats,
        "alcance": "Atributos en memoria; excluye cámara, lectura y segmentación",
    }


def _resumen(folds):
    metrics = (
        "accuracy", "balanced_accuracy",
        "precision_macro", "recall_macro", "f1_macro",
    )
    summary = {}

    for method in ("reglas_clasicas", "modelo_ligero"):
        summary[method] = {}

        for metric in metrics:
            values = [
                fold[method]["metricas"][metric]
                for fold in folds
            ]

            summary[method][metric] = {
                "media": float(statistics.mean(values)),
                "desviacion_estandar": (
                    float(statistics.stdev(values))
                    if len(values) > 1 else 0.0
                ),
            }

        summary[method]["p95_inferencia_ms_mediana"] = float(
            statistics.median(
                fold[method]["inferencia"]["p95_ms_por_muestra"]
                for fold in folds
            )
        )

        if method == "modelo_ligero":
            summary[method]["entrenamiento_ms_mediana"] = float(
                statistics.median(
                    fold[method]["entrenamiento_ms"]
                    for fold in folds
                )
            )

    summary["diferencia_f1_modelo_menos_reglas"] = (
        summary["modelo_ligero"]["f1_macro"]["media"]
        - summary["reglas_clasicas"]["f1_macro"]["media"]
    )

    return summary


def comparar(
    anotaciones,
    atributos,
    reglas,
    *,
    splits=20,
    test_size=.33,
    semilla=42,
    repeticiones=30,
):
    if splits < 1 or repeticiones < 1 or not 0 < test_size < 1:
        raise ErrorComparacion("Parámetros fuera de rango")

    audit = auditar_csv(anotaciones)
    annotation_rows = _leer_csv(anotaciones, "anotaciones")

    report = {
        "version": VERSION,
        "tarea": "AGROP-42",
        "estado": "bloqueado_por_datos_insuficientes",
        "auditoria": audit,
        "configuracion": {
            "splits_solicitados": splits,
            "test_size": test_size,
            "semilla": semilla,
            "repeticiones_inferencia": repeticiones,
        },
        "hardware_ejecucion": {
            "sistema": platform.platform(),
            "procesador": platform.processor(),
            "cpu_logicas": os.cpu_count(),
            "python": platform.python_version(),
        },
        "huellas_sha256": {
            "anotaciones": _sha256(anotaciones),
            "atributos": None,
            "reglas": None,
        },
        "productos": {},
        "comparacion_mismo_conjunto_prueba": False,
        "limitacion_rendimiento": (
            "La latencia corresponde a atributos en memoria. "
            "RSS y flujo completo se miden con el perfilador AG-034 existente."
        ),
    }

    eligible_by_product = {}

    for product in FRUTAS:
        gate = audit["productos"][product]

        rows = [
            r for r in annotation_rows
            if _texto(r, "producto").lower() == product
            and _fila_elegible(r)
        ]

        eligible_by_product[product] = rows

        report["productos"][product] = {
            "estado": "bloqueado",
            "fotografias": gate["fotografias"],
            "etiquetas_elegibles": gate["etiquetas_elegibles"],
            "grupos_independientes": gate["grupos_independientes"],
            "clases": gate["clases_elegibles"],
            "motivos": list(gate["motivos"]),
            "splits_validos": 0,
            "resultados": [],
            "resumen": None,
        }

    if audit["errores_integridad"]:
        report["estado"] = "bloqueado_por_integridad"
        return report

    eligible_products = {
        p for p in FRUTAS
        if audit["productos"][p]["estado"] == "apto_para_diseno_experimental"
    }

    if not eligible_products:
        return report

    if atributos is None or reglas is None:
        for p in eligible_products:
            report["productos"][p]["motivos"].append(
                "faltan_atributos_confirmados_o_reglas_aprobadas"
            )
        return report

    try:
        eligible_rows = [
            r for p in eligible_products
            for r in eligible_by_product[p]
        ]

        feature_map = _cargar_atributos(
            atributos, annotation_rows, eligible_rows
        )

        rule_map = _cargar_reglas(
            reglas, eligible_products, eligible_rows
        )

    except (ErrorComparacion, OSError, ValueError) as exc:
        report["estado"] = "bloqueado_por_insumos_invalidos"
        report["errores_insumos"] = [str(exc)]
        return report

    report["huellas_sha256"]["atributos"] = _sha256(atributos)
    report["huellas_sha256"]["reglas"] = _sha256(reglas)

    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import GroupShuffleSplit
    except ImportError as exc:
        raise ErrorComparacion(
            "Instala scikit-learn desde vision/requirements-experiment.txt"
        ) from exc

    for product in sorted(eligible_products):
        rows = eligible_by_product[product]
        samples = _agrupar_piezas(rows, feature_map)

        x = [s["x"] for s in samples]
        y = [s["etiqueta"] for s in samples]
        groups = [s["grupo"] for s in samples]

        item = report["productos"][product]
        item["piezas_utilizadas"] = len(samples)
        item["fotografias_utilizadas"] = len(rows)
        item["distribucion_clases"] = dict(sorted(Counter(y).items()))

        splitter = GroupShuffleSplit(
            n_splits=splits,
            test_size=test_size,
            random_state=semilla,
        )

        seen_tests = set()
        folds = []

        for number, (train_idx, test_idx) in enumerate(
            splitter.split(x, y, groups), 1
        ):
            y_train = [y[i] for i in train_idx]
            y_test = [y[i] for i in test_idx]

            if len(set(y_train)) < 2 or len(set(y_test)) < 2:
                continue

            train_groups = {groups[i] for i in train_idx}
            test_groups = {groups[i] for i in test_idx}

            if train_groups & test_groups:
                raise AssertionError("Fuga de grupos entre entrenamiento y prueba")

            key = tuple(sorted(test_groups))

            if key in seen_tests:
                continue

            seen_tests.add(key)

            x_train = [x[i] for i in train_idx]
            x_test = [x[i] for i in test_idx]

            predict_rules = lambda values, cfg=rule_map[product]: (
                predecir_reglas(values, cfg)
            )

            pred_rules = predict_rules(x_test)
            metrics_rules = _metricas(y_test, pred_rules)
            timing_rules = _tiempo(
                predict_rules, x_test, repeticiones
            )

            model = RandomForestClassifier(
                n_estimators=100,
                max_depth=4,
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=semilla,
            )

            start = time.perf_counter_ns()
            model.fit(x_train, y_train)
            training_ms = (
                time.perf_counter_ns() - start
            ) / 1_000_000

            predict_model = lambda values, fitted=model: (
                fitted.predict(values).tolist()
            )

            pred_model = predict_model(x_test)
            metrics_model = _metricas(y_test, pred_model)
            timing_model = _tiempo(
                predict_model, x_test, repeticiones
            )

            folds.append({
                "split": number,
                "train_piezas": [
                    samples[i]["pieza"] for i in train_idx
                ],
                "test_piezas": [
                    samples[i]["pieza"] for i in test_idx
                ],
                "train_grupos": sorted(train_groups),
                "test_grupos": sorted(test_groups),
                "train_registros": sorted(
                    rid for i in train_idx
                    for rid in samples[i]["registro_ids"]
                ),
                "test_registros": sorted(
                    rid for i in test_idx
                    for rid in samples[i]["registro_ids"]
                ),
                "reglas_clasicas": {
                    "metricas": metrics_rules,
                    "inferencia": timing_rules,
                    "predicciones": pred_rules,
                },
                "modelo_ligero": {
                    "metricas": metrics_model,
                    "inferencia": timing_model,
                    "entrenamiento_ms": training_ms,
                    "predicciones": pred_model,
                },
            })

        item["splits_validos"] = len(folds)
        item["resultados"] = folds

        if folds:
            item["resumen"] = _resumen(folds)
            item["decision_final"] = (
                "pendiente_validacion_RSS_y_limites_aprobados_en_PC_objetivo"
            )
            item["estado"] = "comparacion_ejecutada"
        else:
            item["motivos"].append(
                "sin_split_con_dos_clases_en_train_y_test"
            )

    evaluated = [
        p for p in sorted(eligible_products)
        if report["productos"][p]["estado"] == "comparacion_ejecutada"
    ]

    report["productos_evaluados"] = evaluated
    report["comparacion_mismo_conjunto_prueba"] = bool(evaluated)

    if len(evaluated) == len(FRUTAS):
        report["estado"] = "comparacion_ejecutada"
    elif evaluated:
        report["estado"] = "comparacion_parcial"
    else:
        report["estado"] = "bloqueado_sin_split_valido"

    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("--anotaciones", type=Path, required=True)
    parser.add_argument("--atributos", type=Path)
    parser.add_argument("--reglas", type=Path)
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--splits", type=int, default=20)
    parser.add_argument("--test-size", type=float, default=.33)
    parser.add_argument("--semilla", type=int, default=42)
    parser.add_argument("--repeticiones-inferencia", type=int, default=30)

    args = parser.parse_args(argv)

    try:
        if args.salida.exists():
            raise ErrorComparacion(
                "La salida ya existe; no se sobrescribe"
            )

        result = comparar(
            args.anotaciones,
            args.atributos,
            args.reglas,
            splits=args.splits,
            test_size=args.test_size,
            semilla=args.semilla,
            repeticiones=args.repeticiones_inferencia,
        )

        args.salida.parent.mkdir(parents=True, exist_ok=True)

        args.salida.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    except (ErrorComparacion, OSError, ValueError) as exc:
        parser.error(str(exc))

    print(json.dumps({
        "estado": result["estado"],
        "productos_evaluados": result.get("productos_evaluados", []),
        "salida": str(args.salida),
    }, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())