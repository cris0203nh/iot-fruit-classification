"""AGROP-42 / Etapa 01A: registro trazable de imágenes originales.

Importa fotos suministradas localmente, SIN inferir etiquetas ni variedad.
El paquete exporta manifiestos compatibles con auditar.py y nunca entrena.
Las declaraciones de propiedad, variedad y pieza son metadatos aportados,
no hechos verificados por el programa.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

VERSION = "agrop42-dataset-registry-v0.1"
PRODUCTS = {"mango", "tomate"}
ORIGINS = {"captura_propia", "externo_original", "aumentada", "sintetica"}
FIELDNAMES = (
    "archivo", "producto", "tipo_fuente", "fuente_id", "fuente_url", "licencia",
    "derechos_confirmados", "evidencia_derechos", "lote_id", "pieza_id",
    "pieza_confirmada", "dispositivo_id", "sesion_id", "vista",
    "variedad_declarada", "variedad_confirmada", "evidencia_variedad",
    "etiqueta_fuente", "observaciones",
)
MAX_FILE_SIZE = 30 * 1024 * 1024
NEAR_DUPLICATE_DISTANCE = 5  # heurística de revisión, no prueba de duplicación.


class DatasetPreparationError(ValueError):
    """Error explícito, sin crear un dataset parcial."""


def _required(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _boolean(value: object, column: str, line: int) -> bool:
    v = _required(value).lower()
    if v not in {"true", "false"}:
        raise DatasetPreparationError(f"Fila {line}: {column} debe ser true/false, sin inferencias")
    return v == "true"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _dhash(image: Image.Image) -> int:
    """Huella perceptual simple; propone revisión, no confirma duplicación."""
    gray = ImageOps.exif_transpose(image).convert("L").resize(
        (9, 8), Image.Resampling.LANCZOS
    )
    pixels = list(gray.get_flattened_data())
    result = 0
    for row in range(8):
        for col in range(8):
            result = (result << 1) | int(pixels[row * 9 + col] > pixels[row * 9 + col + 1])
    return result


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise DatasetPreparationError("El CSV no tiene encabezados")
            missing = set(FIELDNAMES) - set(reader.fieldnames)
            if missing:
                raise DatasetPreparationError(f"Faltan columnas: {', '.join(sorted(missing))}")
            extra = set(reader.fieldnames) - set(FIELDNAMES)
            if extra:
                raise DatasetPreparationError(f"Columnas desconocidas: {', '.join(sorted(extra))}")
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise DatasetPreparationError("No se puede leer el CSV UTF-8") from exc
    if not rows:
        raise DatasetPreparationError("No hay filas: primero coloca fotos reales y metadatos")
    if any(None in row for row in rows):
        raise DatasetPreparationError("Fila con columnas de más")
    return rows


def _resolve_source(root: Path, relative: str, line: int) -> Path:
    src = Path(relative)
    if not relative or src.is_absolute():
        raise DatasetPreparationError(f"Fila {line}: archivo requiere ruta RELATIVA")
    abs_path = (root / src).resolve()
    if not abs_path.is_relative_to(root.resolve()):
        raise DatasetPreparationError(f"Fila {line}: archivo sale del directorio de entrada")
    if not abs_path.is_file() or abs_path.is_symlink():
        raise DatasetPreparationError(f"Fila {line}: imagen inexistente o no admitida: {relative}")
    return abs_path


def _inspect_file(path: Path, line: int) -> tuple[str, str, int, int, int]:
    size = path.stat().st_size
    if not 0 < size <= MAX_FILE_SIZE:
        raise DatasetPreparationError(f"Fila {line}: imagen vacía o supera 30 MiB")
    try:
        with Image.open(path) as img:
            fmt = img.format
            if fmt not in {"JPEG", "PNG"}:
                raise DatasetPreparationError(f"Fila {line}: formato distinto de PNG/JPEG")
            img.verify()
        with Image.open(path) as img:
            img.load()
            width, height = img.size
            phash = _dhash(img)
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise DatasetPreparationError(f"Fila {line}: imagen no se puede decodificar") from exc
    if width < 128 or height < 128:
        raise DatasetPreparationError(f"Fila {line}: imagen menor que 128 píxeles por lado")
    return _sha256(path), (".jpg" if fmt == "JPEG" else ".png"), width, height, phash


class _BKTree:
    """Búsqueda eficiente de dHash cercanos con distancia de Hamming."""
    def __init__(self):
        self.root = None

    @staticmethod
    def distance(a: int, b: int) -> int:
        return (a ^ b).bit_count()

    def insert(self, value: int, name: str) -> list[tuple[int, str, int]]:
        if self.root is None:
            self.root = [value, name, {}]
            return []
        near = []
        stack = [self.root]
        while stack:
            node = stack.pop()
            dist = self.distance(value, node[0])
            if dist <= NEAR_DUPLICATE_DISTANCE:
                near.append((node[0], node[1], dist))
            stack.extend(child for distance, child in node[2].items()
                         if dist - NEAR_DUPLICATE_DISTANCE <= distance <= dist + NEAR_DUPLICATE_DISTANCE)
        node = self.root
        while True:
            dist = self.distance(value, node[0])
            child = node[2].get(dist)
            if child is None:
                node[2][dist] = [value, name, {}]
                break
            node = child
        return near


def prepare(rows: list[dict[str, str]], image_root: Path, output: Path) -> dict:
    """Validar TODO antes de escribir. Guardar contenido local sin transformación."""
    image_root = image_root.resolve()
    output = output.resolve()
    if output.exists():
        raise DatasetPreparationError("El directorio de salida ya existe: usa otro nombre de versión")
    if not image_root.is_dir():
        raise DatasetPreparationError("El directorio de imágenes de entrada no existe")
    validated = []
    for index, row in enumerate(rows, start=2):
        if any(value is None for value in row.values()):
            raise DatasetPreparationError(f"Fila {index}: campos vacíos inválidos")
        product = _required(row["producto"]).lower()
        origin = _required(row["tipo_fuente"]).lower()
        if product not in PRODUCTS or origin not in ORIGINS:
            raise DatasetPreparationError(f"Fila {index}: producto o tipo_fuente no reconocido")
        source_id = _required(row["fuente_id"])
        if not source_id:
            raise DatasetPreparationError(f"Fila {index}: falta fuente_id")
        rights = _boolean(row["derechos_confirmados"], "derechos_confirmados", index)
        piece_known = _boolean(row["pieza_confirmada"], "pieza_confirmada", index)
        variety_known = _boolean(row["variedad_confirmada"], "variedad_confirmada", index)
        if rights and not _required(row["evidencia_derechos"]):
            raise DatasetPreparationError(f"Fila {index}: falta evidencia_derechos")
        if origin == "externo_original" and not (_required(row["fuente_url"]) and _required(row["licencia"])):
            raise DatasetPreparationError(f"Fila {index}: datos externos exigen URL y licencia declaradas")
        if piece_known and not (_required(row["pieza_id"]) and _required(row["lote_id"])):
            raise DatasetPreparationError(f"Fila {index}: pieza confirmada requiere pieza_id y lote_id")
        if variety_known and not (_required(row["variedad_declarada"]) and _required(row["evidencia_variedad"])):
            raise DatasetPreparationError(f"Fila {index}: variedad confirmada requiere evidencia_variedad")
        if product == "mango" and variety_known and _required(row["variedad_declarada"]) != "Kent":
            # Se permite registrar otras variedades para inventario, no para el experimento Kent.
            pass
        src = _resolve_source(image_root, _required(row["archivo"]), index)
        sha, ext, width, height, dhash = _inspect_file(src, index)
        eligible = (rights and origin in {"captura_propia", "externo_original"}
                    and (product != "mango" or (variety_known and _required(row["variedad_declarada"]) == "Kent")))
        reason = (
            None if eligible else
            "fuente_sintetica_o_aumentada" if origin in {"sintetica", "aumentada"} else
            "derechos_sin_confirmar" if not rights else
            "variedad_kent_no_verificada"
        )
        validated.append({
            "record_id": f"REG-{index - 1:05d}", "source": src, "sha256": sha, "extension": ext,
            "dhash": dhash, "width": width, "height": height, "product": product,
            "origin": origin, "source_id": source_id,
            "source_url": _required(row["fuente_url"]), "license": _required(row["licencia"]),
            "rights_confirmed_declared": rights, "rights_evidence": _required(row["evidencia_derechos"]),
            "lot_id": _required(row["lote_id"]) or None,
            "piece_id": _required(row["pieza_id"]) if piece_known else None,
            "piece_identity_declared": piece_known,
            "device_id": _required(row["dispositivo_id"]) or None,
            "boot_id": _required(row["sesion_id"]) or None,
            "view": _required(row["vista"]) or "vista_sin_identificar",
            "variety_declared": _required(row["variedad_declarada"]) or None,
            "variety_confirmed_declared": variety_known,
            "variety_evidence": _required(row["evidencia_variedad"]),
            "original_label_unverified": _required(row["etiqueta_fuente"]) or None,
            "notes": _required(row["observaciones"]), "visible_to_audit": eligible,
            "excluded_from_audit_reason": reason,
        })
    # No se presupone independencia si varias fotos reutilizan mismo SHA.
    groups = defaultdict(list)
    for r in validated:
        groups[r["sha256"]].append(r["record_id"])
    near_trees = {p: _BKTree() for p in PRODUCTS}
    near_pairs = []
    sha_by_id = {r["record_id"]: r["sha256"] for r in validated}
    for r in validated:
        for _, other, distance in near_trees[r["product"]].insert(r["dhash"], r["record_id"]):
            if r["sha256"] != sha_by_id[other]:
                near_pairs.append({"registro_1": other, "registro_2": r["record_id"],
                                   "distancia_dhash": distance, "solo_sospecha": True})
    # Mantener un solo manifiesto por pieza declarada; sin pieza, uno por registro.
    manifest_groups = defaultdict(list)
    for r in validated:
        if not r["visible_to_audit"]:
            continue
        if r["piece_id"] and r["lot_id"]:
            key = (r["product"], r["lot_id"], r["piece_id"])
        else:
            key = (r["product"], r["record_id"], None)
        manifest_groups[key].append(r)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="agrop42_dataset_stage_", dir=output.parent) as stage_name:
        stage = Path(stage_name)
        (stage / "images").mkdir()
        (stage / "manifests").mkdir()
        for r in validated:
            destination = stage / "images" / (r["sha256"] + r["extension"])
            if not destination.exists():
                shutil.copyfile(r["source"], destination)
                if _sha256(destination) != r["sha256"]:
                    raise DatasetPreparationError("Falló la copia íntegra de fotografías")
        for group_idx, (key, items) in enumerate(sorted(manifest_groups.items()), start=1):
            first = items[0]
            # No propagar una variedad afirmada por otra fotografía de la misma pieza.
            varieties = {r["variety_declared"] for r in items}
            variety = next(iter(varieties)) if len(varieties) == 1 else None
            manifest = {
                "experiment_id": f"AGROP42-DATA-{group_idx:05d}",
                "piece": {
                    "product": first["product"], "lot_id": first["lot_id"],
                    "piece_id": first["piece_id"], "variety_declared": variety,
                },
                "coverage_verified": None,
                "images": [{
                    "image_id": r["record_id"], "view": r["view"],
                    "path": "../images/" + r["sha256"] + r["extension"],
                    "capture": {"device_id": r["device_id"], "boot_id": r["boot_id"]},
                    "quality": {"focus_ok": None, "lighting_ok": None, "unoccluded": None},
                    "roi_xywh": None, "roi_verified": False,
                } for r in items],
                "operator_visual_label": None,
                "source": "agrop42_dataset_registry_not_ground_truth",
            }
            (stage / "manifests" / f"group_{group_idx:05d}.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        inventory = []
        for r in validated:
            record = {k: v for k, v in r.items() if k not in {"source", "dhash", "extension"}}
            record["image_path"] = "images/" + r["sha256"] + r["extension"]
            record["dhash64"] = f"{r['dhash']:016x}"
            inventory.append(record)
        report = {
            "task": "AGROP-42", "stage": "dataset-01A", "version": VERSION,
            "photographic_records": len(validated),
            "unique_files_sha256": len(groups),
            "duplicate_sha_groups": [
                {"sha256": k, "records": v} for k, v in sorted(groups.items()) if len(v) > 1
            ],
            "near_duplicate_candidates_dhash": near_pairs,
            "mango_records": sum(r["product"] == "mango" for r in validated),
            "tomato_records": sum(r["product"] == "tomate" for r in validated),
            "exported_records_to_auditor": sum(r["visible_to_audit"] for r in validated),
            "excluded_from_auditor": sum(not r["visible_to_audit"] for r in validated),
            "manifest_count": len(manifest_groups),
            "annotation_status": "none_reviewed_or_assigned_by_importer",
            "limits": [
                "Los permisos, la variedad y la identidad de pieza son declaraciones del CSV, no verificaciones automáticas.",
                "dHash es heurístico: solo sugiere posibles duplicados; no elimina capturas.",
                "Registros externos requieren identidad física y sesión real para probar independencia.",
                "No se convierten etiquetas originales en E0/E1/E2.",
                "Imágenes generadas, aumentadas, sin permisos o sin verificación Kent quedan fuera de la auditoría supervisada.",
            ],
        }
        (stage / "inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (stage / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (stage / "annotations_to_review.json").write_text('{"annotations": []}\n', encoding="utf-8")
        # Renombrar al final: ninguna importación parcial expuesta como dataset final.
        if output.exists():
            raise DatasetPreparationError("El destino apareció durante la preparación; no se sobrescribe")
        os.rename(stage, output)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AGROP-42: importar fotos y preparar registro trazable, sin etiquetas automáticas")
    parser.add_argument("--csv", type=Path, required=True, help="Planilla CSV de imágenes con procedencia")
    parser.add_argument("--input-dir", type=Path, required=True, help="Raíz local que contiene las fotografías")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directorio NUEVO; debe estar dentro de vision/experiments")
    args = parser.parse_args(argv)
    try:
        # Protección de datos: no crear paquetes versionables accidentalmente.
        repo = Path(__file__).resolve().parents[3]
        allowed = (repo / "vision/experiments").resolve()
        if not args.output_dir.resolve().is_relative_to(allowed) or args.output_dir.resolve() == allowed:
            raise DatasetPreparationError("--output-dir debe ser nuevo y estar dentro de vision/experiments/")
        report = prepare(_read_csv(args.csv), args.input_dir, args.output_dir)
    except (DatasetPreparationError, OSError) as exc:
        parser.error(str(exc))
    print("AGROP-42: dataset inventariado; NO entrenado")
    print(f"  registros={report['photographic_records']} únicos={report['unique_files_sha256']}")
    print(f"  exportados_para_auditar={report['exported_records_to_auditor']} excluidos={report['excluded_from_auditor']}")
    print(f"  posibles_pares_dhash={len(report['near_duplicate_candidates_dhash'])}")
    print(f"  salida={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
