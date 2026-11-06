"""AGROP-42 / Incremento 04: revisión documental trazable de imágenes.

No genera etiquetas ni acredita inspecciones automáticamente. El CSV es una
DECLARACIÓN del operador y la evidencia de pieza/sesión debe provenir de una
fuente identificable, nunca del nombre del archivo o su apariencia.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

VERSION = "agrop42-revision-v0.1"
RUBRICS = {"mango": "kent-ext-v0.5", "tomate": "tomato-ext-v0.1"}
STATES = {"pendiente", "revisada", "no_evaluable", "excluida"}
LABELS = {"E0", "E1", "E2"}
YES_NO = {"", "si", "no", "pendiente"}
SHA = re.compile(r"^[0-9a-f]{64}$")
MAX_FILE_BYTES = 30 * 1024 * 1024
READONLY = (
    "registro_id", "producto", "sha256", "archivo", "tipo_fuente",
    "fuente_url", "licencia", "variedad_declarada",
)
EDITABLE = (
    "estado_revision", "revisor_id", "revisado_en", "rubrica_version",
    "calidad_confirmada", "cobertura_confirmada", "variedad_verificada",
    "evidencia_variedad", "etiqueta_visual", "etiqueta_documentada",
    "justificacion_etiqueta", "motivo_no_evaluable",
    "observacion_r03", "observacion_r04", "observacion_r05",
    "observacion_r06", "observacion_r07", "observacion_r08",
    "observacion_r09", "pieza_confirmada", "lote_id", "pieza_id",
    "evidencia_pieza", "sesion_confirmada", "dispositivo_id", "sesion_id",
    "evidencia_sesion", "revision_similitud", "evidencia_similitud", "nota_revision",
)
FIELDS = READONLY + EDITABLE


class ReviewInputError(ValueError):
    """Datos de revisión incompletos o incompatibles con el inventario."""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewInputError("No se pudo leer un JSON de entrada válido") from exc


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_inventory(dataset_dir: Path) -> list[dict[str, Any]]:
    """Comprueba el paquete 01A sin confiar únicamente en sus metadatos."""
    root = dataset_dir.resolve()
    inventory = _read_json(root / "inventory.json")
    if not isinstance(inventory, list) or not inventory:
        raise ReviewInputError("El inventario debe contener al menos una fotografía")
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for n, item in enumerate(inventory, 1):
        if not isinstance(item, dict):
            raise ReviewInputError(f"Inventario {n}: registro inválido")
        rid, product, digest = item.get("record_id"), item.get("product"), item.get("sha256")
        path_txt = item.get("image_path")
        if (not isinstance(rid, str) or not rid or rid in seen
                or product not in RUBRICS or not isinstance(digest, str)
                or not SHA.fullmatch(digest) or not isinstance(path_txt, str)):
            raise ReviewInputError(f"Inventario {n}: identidad, producto o SHA256 inválidos")
        # Solo rutas generadas por preparar_dataset.py: images/<sha>.jpg|.png.
        if path_txt not in (f"images/{digest}.jpg", f"images/{digest}.png"):
            raise ReviewInputError(f"Inventario {rid}: ruta no coincide con su SHA256")
        image_dir = root / "images"
        image_path = root / path_txt
        if (image_dir.is_symlink() or image_path.is_symlink()
                or not image_path.resolve().is_relative_to(image_dir.resolve())
                or not image_path.is_file()):
            raise ReviewInputError(f"Inventario {rid}: imagen inexistente o ruta insegura")
        if not 0 < image_path.stat().st_size <= MAX_FILE_BYTES:
            raise ReviewInputError(f"Inventario {rid}: tamaño de imagen no admitido")
        try:
            with Image.open(image_path) as image:
                if image.format not in ("PNG", "JPEG"):
                    raise ReviewInputError(f"Inventario {rid}: formato no admitido")
                image.verify()
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError, ValueError) as exc:
            raise ReviewInputError(f"Inventario {rid}: imagen inválida") from exc
        if _sha256(image_path) != digest:
            raise ReviewInputError(f"Inventario {rid}: imagen modificada desde su importación")
        seen.add(rid)
        rows.append(item)
    return sorted(rows, key=lambda r: r["record_id"])


def _readonly(item: dict[str, Any]) -> dict[str, str]:
    return {
        "registro_id": item["record_id"], "producto": item["product"],
        "sha256": item["sha256"], "archivo": item["image_path"],
        "tipo_fuente": item.get("origin") or "",
        "fuente_url": item.get("source_url") or "",
        "licencia": item.get("license") or "",
        "variedad_declarada": item.get("variety_declared") or "",
    }


def template_rows(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Cada celda editable queda vacía: ninguna verificación se presupone."""
    return [{**_readonly(item), **{k: ("pendiente" if k == "estado_revision" else "")
                                  for k in EDITABLE}} for item in items]


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if path.exists():
        raise ReviewInputError("El archivo de salida ya existe; no se sobrescribe")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def create_template(dataset_dir: Path, output_csv: Path) -> dict[str, int]:
    if output_csv.resolve().is_relative_to(dataset_dir.resolve()):
        raise ReviewInputError("La plantilla debe quedar fuera del dataset inmutable")
    items = load_inventory(dataset_dir)
    _write_csv(output_csv, template_rows(items))
    return {"registros": len(items), "sin_etiquetas_asignadas": len(items)}


def read_reviews(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or list(reader.fieldnames) != list(FIELDS):
                raise ReviewInputError("El CSV de revisión debe conservar exactamente las columnas de la plantilla")
            data = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ReviewInputError("No se pudo leer el CSV de revisión UTF-8") from exc
    if any(None in row or any(value is None for value in row.values()) for row in data):
        raise ReviewInputError("CSV con columnas faltantes o sobrantes")
    return [{k: v.strip() for k, v in row.items()} for row in data]


def _time(value: str, record_id: str) -> None:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewInputError(f"{record_id}: revisado_en requiere fecha ISO 8601") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ReviewInputError(f"{record_id}: revisado_en requiere zona horaria explícita")


def _yes_no(row: dict[str, str], record_id: str) -> None:
    for col in ("calidad_confirmada", "cobertura_confirmada", "variedad_verificada",
                "etiqueta_documentada", "pieza_confirmada", "sesion_confirmada"):
        if row[col] not in YES_NO:
            raise ReviewInputError(f"{record_id}: {col} requiere si/no/pendiente o vacío")


def _validate_entry(row: dict[str, str], source: dict[str, Any]) -> dict[str, Any]:
    rid, product = source["record_id"], source["product"]
    if any(row[key] != value for key, value in _readonly(source).items()):
        raise ReviewInputError(f"{rid}: cambiaste un campo del inventario de solo lectura")
    status = row["estado_revision"]
    if status not in STATES:
        raise ReviewInputError(f"{rid}: estado_revision no reconocido")
    _yes_no(row, rid)
    label = row["etiqueta_visual"]
    if label and label not in LABELS:
        raise ReviewInputError(f"{rid}: etiqueta_visual solo admite E0, E1 o E2")

    if status == "pendiente":
        if any(row[k] for k in EDITABLE if k not in ("estado_revision", "nota_revision")):
            raise ReviewInputError(f"{rid}: un registro pendiente no puede declarar revisión o identidad")
    else:
        for key in ("revisor_id", "revisado_en", "rubrica_version", "nota_revision"):
            if not row[key]:
                raise ReviewInputError(f"{rid}: {key} es obligatorio al cerrar una revisión")
        _time(row["revisado_en"], rid)
        if row["rubrica_version"] != RUBRICS[product]:
            raise ReviewInputError(f"{rid}: rúbrica incompatible con {product}")

    if status == "revisada" and row["motivo_no_evaluable"]:
        raise ReviewInputError(f"{rid}: revisión no debe tener motivo de exclusión")

    if status in ("no_evaluable", "excluida"):
        if not row["motivo_no_evaluable"]:
            raise ReviewInputError(f"{rid}: indica el motivo de no evaluación o exclusión")
        if label or row["etiqueta_documentada"] == "si":
            raise ReviewInputError(f"{rid}: una imagen no evaluable/excluida no puede etiquetarse")

    if label:
        if status != "revisada" or row["etiqueta_documentada"] != "si":
            raise ReviewInputError(f"{rid}: etiqueta necesita revisión explícita y etiqueta_documentada=si")
        if not source.get("visible_to_audit") or not source.get("rights_confirmed_declared"):
            raise ReviewInputError(f"{rid}: fuente excluida o derechos no declarados")
        if row["calidad_confirmada"] != "si" or row["cobertura_confirmada"] != "si":
            raise ReviewInputError(f"{rid}: etiqueta requiere calidad y cobertura revisadas")
        if product == "mango" and (row["variedad_verificada"] != "si" or not row["evidencia_variedad"]):
            raise ReviewInputError(f"{rid}: mango Kent requiere verificación documental de variedad")
        if not row["justificacion_etiqueta"]:
            raise ReviewInputError(f"{rid}: justificación de la etiqueta obligatoria")
        applicable = range(3, 8) if product == "mango" else range(3, 10)
        if not any(row[f"observacion_r{i:02d}"] for i in applicable):
            raise ReviewInputError(f"{rid}: etiqueta requiere observación de un criterio de su rúbrica")
    elif row["etiqueta_documentada"] == "si":
        raise ReviewInputError(f"{rid}: etiqueta_documentada=si sin etiqueta")
    elif row["justificacion_etiqueta"]:
        raise ReviewInputError(f"{rid}: existe justificación sin etiqueta")

    # Campos de identidad/Sesión nunca se infieren de registro_id, filename o fuente.
    piece_fields = ("lote_id", "pieza_id", "evidencia_pieza")
    if row["pieza_confirmada"] == "si":
        if status != "revisada" or not all(row[k] for k in piece_fields):
            raise ReviewInputError(f"{rid}: pieza_confirmada=si requiere revisión, lote, pieza y evidencia")
        if not source.get("visible_to_audit"):
            raise ReviewInputError(f"{rid}: pieza de fuente excluida")
    elif any(row[k] for k in piece_fields):
        raise ReviewInputError(f"{rid}: no declares lote/pieza sin verificación y evidencia")
    session_fields = ("dispositivo_id", "sesion_id", "evidencia_sesion")
    if row["sesion_confirmada"] == "si":
        if row["pieza_confirmada"] != "si" or not all(row[k] for k in session_fields):
            raise ReviewInputError(f"{rid}: sesión requiere pieza confirmada y evidencia de captura")
    elif any(row[k] for k in session_fields):
        raise ReviewInputError(f"{rid}: no declares dispositivo/sesión sin evidencia")

    if row["revision_similitud"] not in ("", "pendiente", "misma_pieza", "distintas_piezas"):
        raise ReviewInputError(f"{rid}: revision_similitud fuera de opciones")
    if row["revision_similitud"] in ("misma_pieza", "distintas_piezas") and (
            status == "pendiente" or not row["evidencia_similitud"]):
        raise ReviewInputError(f"{rid}: similitud revisada requiere nota y revisor")
    if row["evidencia_similitud"] and row["revision_similitud"] not in ("misma_pieza", "distintas_piezas"):
        raise ReviewInputError(f"{rid}: evidencia de similitud sin decisión registrada")
    if product == "mango" and row["observacion_r09"]:
        raise ReviewInputError(f"{rid}: R09 no pertenece a la rúbrica Kent R01-R08")

    return {
        "record_id": rid, "product": product, "sha256": source["sha256"],
        "estado_revision": status, "revisor_id": row["revisor_id"] or None,
        "revisado_en": row["revisado_en"] or None, "rubrica_version": row["rubrica_version"] or None,
        "calidad_confirmada_por_operador": row["calidad_confirmada"] == "si",
        "cobertura_confirmada_por_operador": row["cobertura_confirmada"] == "si",
        "variedad_verificada_declarada": row["variedad_verificada"] == "si",
        "evidencia_variedad": row["evidencia_variedad"] or None,
        "etiqueta_documentada": label or None,
        "justificacion_etiqueta": row["justificacion_etiqueta"] or None,
        "motivo_no_evaluable": row["motivo_no_evaluable"] or None,
        "observaciones_rubrica": {f"R{i:02d}": row[f"observacion_r{i:02d}"]
                                for i in range(3, 10) if row[f"observacion_r{i:02d}"]},
        "pieza_confirmada_por_operador": row["pieza_confirmada"] == "si",
        "lote_id": row["lote_id"] or None,
        "pieza_id": row["pieza_id"] or None,
        "evidencia_pieza": row["evidencia_pieza"] or None,
        "sesion_confirmada_por_operador": row["sesion_confirmada"] == "si",
        "dispositivo_id": row["dispositivo_id"] or None,
        "sesion_id": row["sesion_id"] or None,
        "evidencia_sesion": row["evidencia_sesion"] or None,
        "revision_similitud": row["revision_similitud"] or "pendiente",
        "evidencia_similitud": row["evidencia_similitud"] or None,
        "nota_revision": row["nota_revision"] or None,
        "procedencia": {
            "tipo_fuente": source.get("origin"), "fuente_id": source.get("source_id"),
            "fuente_url": source.get("source_url"), "licencia": source.get("license"),
            "derechos_declarados": source.get("rights_confirmed_declared"),
        },
        "revision_humana_declarada_no_certificacion_experta": True,
    }


def _manifest_dict(group: list[tuple[dict[str, Any], dict[str, Any]]], output_dir: Path,
                   dataset_dir: Path, number: int) -> dict[str, Any]:
    first = group[0][1]
    product = first["product"]
    piece_verified = all(r["pieza_confirmada_por_operador"] for _, r in group)
    known_piece = first["pieza_id"] if piece_verified else None
    known_lot = first["lote_id"] if piece_verified else None
    source_varieties = {i.get("variety_declared") for i, _ in group}
    variety = next(iter(source_varieties)) if len(source_varieties) == 1 else None
    images = []
    for source, reviewed in group:
        image_path = (dataset_dir / source["image_path"]).resolve()
        path_rel = Path(os.path.relpath(image_path, output_dir / "manifests")).as_posix()
        session = reviewed["sesion_confirmada_por_operador"]
        images.append({
            "image_id": source["record_id"], "view": source.get("view") or "vista_sin_identificar",
            "path": path_rel,
            "capture": {"device_id": reviewed["dispositivo_id"] if session else None,
                        "boot_id": reviewed["sesion_id"] if session else None},
            # Estos datos se REVISARON en la ficha, pero el pipeline no los midió.
            "quality": {"focus_ok": None, "lighting_ok": None, "unoccluded": None},
            "roi_xywh": None, "roi_verified": False,
        })
    return {
        "experiment_id": f"AGROP42-REV-{number:05d}",
        "piece": {"product": product, "lot_id": known_lot,
                  "piece_id": known_piece, "variety_declared": variety},
        "coverage_verified": None,
        "images": images, "operator_visual_label": None,
        "source": "agrop42_documented_review_not_automatic_classification",
    }


def finalize(dataset_dir: Path, reviews_csv: Path, output_dir: Path) -> dict[str, Any]:
    """Produce un NUEVO paquete revisado; no toca fotos, CSV ni SQLite."""
    dataset_dir = dataset_dir.resolve()
    output_dir = output_dir.resolve()
    if output_dir.is_relative_to(dataset_dir):
        raise ReviewInputError("El paquete de revisión debe crearse fuera del dataset original")
    if output_dir.exists():
        raise ReviewInputError("El directorio de salida ya existe; elige una nueva versión")
    items = load_inventory(dataset_dir)
    rows = read_reviews(reviews_csv)
    by_id = {r["record_id"]: r for r in items}
    if len(rows) != len(items) or len({r["registro_id"] for r in rows}) != len(items) or set(r["registro_id"] for r in rows) != set(by_id):
        raise ReviewInputError("El CSV no corresponde exactamente al inventario: filas faltantes, extra o duplicadas")
    reviewed: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for row in sorted(rows, key=lambda r: r["registro_id"]):
        item = by_id[row["registro_id"]]
        reviewed.append((item, _validate_entry(row, item)))

    # No permitir etiquetas o identidades incompatibles para la MISMA imagen.
    labels_per_sha: dict[str, set[str]] = defaultdict(set)
    pieces_per_sha: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    piece_labels: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    products_per_sha: dict[str, set[str]] = defaultdict(set)
    for item, r in reviewed:
        products_per_sha[r["sha256"]].add(r["product"])
        if r["etiqueta_documentada"]:
            labels_per_sha[r["sha256"]].add(r["etiqueta_documentada"])
        if r["pieza_confirmada_por_operador"]:
            key = (r["product"], r["lote_id"], r["pieza_id"])
            pieces_per_sha[r["sha256"]].add(key)
            if r["etiqueta_documentada"]:
                piece_labels[key].add(r["etiqueta_documentada"])
    if any(len(v) > 1 for v in labels_per_sha.values()):
        raise ReviewInputError("Etiquetas contradictorias asociadas a un mismo SHA256")
    if any(len(v) > 1 for v in pieces_per_sha.values()):
        raise ReviewInputError("Una misma fotografía fue adjudicada a piezas físicas diferentes")
    if any(len(v) > 1 for v in piece_labels.values()):
        raise ReviewInputError("Una misma pieza tiene etiquetas contradictorias entre vistas")
    conflict_shas = {sha for sha, p in products_per_sha.items() if len(p) > 1}
    if any(r["sha256"] in conflict_shas and
           (r["etiqueta_documentada"] or r["pieza_confirmada_por_operador"])
           for _, r in reviewed):
        raise ReviewInputError("Una imagen atribuida a productos diferentes no puede validar etiquetas ni identidad")

    # El dHash propone similitud, NO identifica fruto: documentar la resolución antes
    # de afirmar que son piezas físicas distintas en una partición supervisada.
    near_pairs = []
    registry_report = dataset_dir / "report.json"
    if registry_report.is_file():
        meta = _read_json(registry_report)
        if not isinstance(meta, dict) or not isinstance(meta.get("near_duplicate_candidates_dhash"), list):
            raise ReviewInputError("Reporte 01A: pares dHash inválidos")
        near_pairs = meta["near_duplicate_candidates_dhash"]
    by_review = {r["record_id"]: r for _, r in reviewed}
    unresolved_pairs = []
    for pair in near_pairs:
        if not isinstance(pair, dict):
            raise ReviewInputError("Reporte 01A: par de similitud malformado")
        aid, bid = pair.get("registro_1"), pair.get("registro_2")
        if aid not in by_review or bid not in by_review or aid == bid:
            raise ReviewInputError("Reporte 01A: referencias dHash no corresponden a registros distintos")
        a, b = by_review[aid], by_review[bid]
        a_piece = (a["product"], a["lote_id"], a["pieza_id"])
        b_piece = (b["product"], b["lote_id"], b["pieza_id"])
        two_confirmed = a["pieza_confirmada_por_operador"] and b["pieza_confirmada_por_operador"]
        if two_confirmed and a_piece != b_piece:
            if not all(r["revision_similitud"] == "distintas_piezas" and r["evidencia_similitud"]
                       for r in (a, b)):
                raise ReviewInputError("Posible duplicado visual: no declarar piezas distintas sin revisión documentada")
        else:
            unresolved_pairs.append([aid, bid])

    annotations = [{
        "sha256": r["sha256"], "product": r["product"], "label": r["etiqueta_documentada"],
        "review_verified": True, "reviewer_id": r["revisor_id"],
        "reviewed_at": r["revisado_en"], "rubric_version": r["rubrica_version"],
    } for _, r in reviewed if r["etiqueta_documentada"]]
    # Una anotación por hash/producto/etiqueta; no multiplicar votos por reuso.
    annotations = list({(a["sha256"], a["product"], a["label"]): a
                        for a in annotations}.values())
    annotations.sort(key=lambda a: (a["product"], a["sha256"]))

    groups: dict[tuple[str, ...], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for item, r in reviewed:
        if not item.get("visible_to_audit") or r["estado_revision"] in ("no_evaluable", "excluida"):
            continue
        if r["pieza_confirmada_por_operador"]:
            group_key = (r["product"], "pieza", r["lote_id"], r["pieza_id"])
        else:
            group_key = (r["product"], "registro", r["record_id"])
        groups[group_key].append((item, r))
    counts = Counter(r["estado_revision"] for _, r in reviewed)
    per_product = {p: {
        "registros": sum(r["product"] == p for _, r in reviewed),
        "anotaciones_con_revision_documentada": sum(a["product"] == p for a in annotations),
        "piezas_con_identidad_declarada": len({(r["lote_id"], r["pieza_id"])
                                             for _, r in reviewed if r["product"] == p and r["pieza_confirmada_por_operador"]}),
        "sesiones_con_evidencia_declarada": sum(r["product"] == p and r["sesion_confirmada_por_operador"]
                                               for _, r in reviewed),
    } for p in RUBRICS}
    review_status = (
        "sin_revisiones_efectuadas" if counts["pendiente"] == len(reviewed) else
        "revision_documental_parcial" if counts["pendiente"] else "revision_documental_completa"
    )
    report = {
        "task": "AGROP-42", "increment": "04", "version": VERSION,
        "status": review_status,
        "registros": len(reviewed), "estados_revision": {state: counts[state] for state in sorted(STATES)},
        "anotaciones_exportadas_para_auditoria": len(annotations),
        "manifiestos_generados": len(groups), "por_producto": per_product,
        "registros_fuera_de_manifiestos": sum(not item.get("visible_to_audit") or r["estado_revision"] in ("no_evaluable", "excluida") for item, r in reviewed),
        "pares_dhash_sospechosos": len(near_pairs),
        "pares_dhash_sin_independencia_confirmada": len(unresolved_pairs),
        "modelo_entrenado": False, "clasificacion_automatica": False,
        "limitations": [
            "El CSV recoge declaraciones de un revisor, no una certificación experta externa.",
            "Las etiquetas y observaciones no son predicciones automáticas del pipeline.",
            "La fotografía sin pieza y sesión verificadas no es un grupo independiente para partición.",
            "La rúbrica mango kent-ext-v0.5 no está acreditada como versión experta final.",
            "Los manifiestos no prueban por sí solos la variedad, procedencia, calidad ni cobertura real.",
            "Las métricas predictivas requieren una prueba independiente y anotaciones válidas.",
        ],
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="agrop42_revision_stage_", dir=output_dir.parent) as tmp:
        stage = Path(tmp)
        (stage / "manifests").mkdir()
        for i, (_, group) in enumerate(sorted(groups.items()), 1):
            manifest = _manifest_dict(group, output_dir, dataset_dir, i)
            (stage / "manifests" / f"review_{i:05d}.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        for fname, payload in (
            ("annotations_to_review.json", {"annotations": annotations}),
            ("revisiones_documentadas.json", {"reviews": [r for _, r in reviewed]}),
            ("summary.json", report),
        ):
            (stage / fname).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        if output_dir.exists():
            raise ReviewInputError("El destino apareció durante la generación; no se sobrescribe")
        os.rename(stage, output_dir)
    return report


def _safe_destination(path: Path) -> None:
    # Seguridad del proyecto: las salidas operativas deben permanecer sin versionar.
    project = Path(__file__).resolve().parents[3]
    allowed = (project / "vision/experiments").resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(allowed) or resolved == allowed:
        raise ReviewInputError("Las salidas deben estar dentro de vision/experiments/")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AGROP-42: ficha documental de anotaciones, sin clases automáticas")
    sub = parser.add_subparsers(dest="action", required=True)
    init = sub.add_parser("iniciar", help="Crear CSV editable sin revisiones ni etiquetas")
    init.add_argument("--dataset-dir", type=Path, required=True)
    init.add_argument("--output", type=Path, required=True)
    finish = sub.add_parser("validar", help="Validar CSV del revisor y exportar evidencias")
    finish.add_argument("--dataset-dir", type=Path, required=True)
    finish.add_argument("--revisiones", type=Path, required=True)
    finish.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        dest = args.output if args.action == "iniciar" else args.output_dir
        _safe_destination(dest)
        if args.action == "iniciar":
            result = create_template(args.dataset_dir, args.output)
            print(f"AGROP-42: plantilla creada con {result['registros']} registros; etiquetas=0")
            print("CSV:", args.output)
        else:
            result = finalize(args.dataset_dir, args.revisiones, args.output_dir)
            print("AGROP-42 revisión:", result["status"])
            print("  registros=", result["registros"], "etiquetas_documentadas=", result["anotaciones_exportadas_para_auditoria"])
            print("  estados=", result["estados_revision"])
            print("Salida:", args.output_dir)
    except (ReviewInputError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
