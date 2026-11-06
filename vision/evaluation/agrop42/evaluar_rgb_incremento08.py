"""AGROP-42 / Incremento 08 — banco técnico RGB de fuentes externas.

Reutiliza el baseline experimental existente de AGROP-40 y AGROP-41;
no infiere identidad de ejemplar, defectos E0/E1/E2, Kent ni ground truth.
La evaluación es descriptiva; imágenes y métricas comerciales no se validan.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import statistics
import tempfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image, UnidentifiedImageError

from vision.src.surface_analysis import propose_surface_regions, save_candidate_preview
from vision.src.surface_masks import describe_surface_masks, save_mask_preview
from vision.src.tomato_surface import analyze_tomato_surface

VERSION = "agrop42-rgb-benchmark-provisional-v0.1"
COLUMNS = ("archivo", "archivo_importado", "id_ejemplar", "vista", "producto", "sha256")
VALID_PRODUCTS = {"mango", "tomate"}
HEX64 = re.compile(r"^[a-f0-9]{64}$")
WARNINGS = [
    "La fuente es externa: los identificadores no demuestran identidad física independiente ni sesión de captura AgroScan.",
    "Las propuestas cromáticas son heurísticas de fondo aproximadamente neutro, no máscaras de fruto confirmadas.",
    "Una máscara provisional no permite diagnosticar defectos, enfermedades, madurez, firmeza ni estado comercial E0/E1/E2.",
    "La mediana RGB depende de iluminación, fondo, cámara, transformación JPEG y regiones detectadas.",
    "Los mangos de esta muestra figuran como Ataulfo en la fuente y no validan la rúbrica Kent.",
    "Las tres vistas de un identificador declarado nunca se cuentan como tres frutos independientes.",
]


class IngestaInvalida(ValueError):
    """Se rechaza entrada inconsistente sin crear resultados parciales."""


def _relative_path(raw: object) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\\" in raw or ":" in raw or "\x00" in raw:
        raise IngestaInvalida("Ruta importada no POSIX o potencialmente insegura.")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in ("", ".", "..") for part in raw.split("/")):
        raise IngestaInvalida("Ruta relativa inválida.")
    if path.parts[0] != "originales" or len(path.parts) != 2:
        raise IngestaInvalida("La fotografía debe ubicarse en originales/.")
    return path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(128 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_inside(root: Path, relative: PurePosixPath) -> Path:
    path = (root / str(relative)).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise IngestaInvalida(f"Fotografía ausente o fuera de la ingesta: {relative}")
    return path


def _validate_inventory(root: Path) -> list[dict[str, str]]:
    inventory = root / "inventario_externo.csv"
    control = root / "control_externo.json"
    if not inventory.is_file() or not control.is_file():
        raise IngestaInvalida("Falta inventario_externo.csv o control_externo.json del Incremento 07.")
    try:
        metadata = json.loads(control.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        raise IngestaInvalida("Control JSON ilegible.") from exc
    if not isinstance(metadata, dict) or metadata.get("entrenamiento_autorizado") is not False or metadata.get("procedencia") != "externa; no captura propia del proyecto":
        raise IngestaInvalida("Solo se procesa la ingesta externa no autorizada para entrenamiento.")
    with inventory.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or any(column not in reader.fieldnames for column in COLUMNS):
            raise IngestaInvalida("Faltan columnas obligatorias del inventario.")
        records = list(reader)
    if not records:
        raise IngestaInvalida("El inventario está vacío.")
    if metadata.get("fotografias") != len(records):
        raise IngestaInvalida("Cantidad distinta al control del Incremento 07.")
    seen_images: set[str] = set()
    seen_views: set[tuple[str, str, str]] = set()
    seen_piece_products: dict[str, str] = {}
    for row in records:
        sha = row["sha256"].strip().lower()
        if not HEX64.fullmatch(sha) or sha != (row.get("sha256_comprobado") or "").lower():
            raise IngestaInvalida("SHA-256 inválido o no coincide con verificación de ingesta.")
        if row["producto"] not in VALID_PRODUCTS:
            raise IngestaInvalida("Producto no reconocido.")
        if row.get("es_captura_propia") != "no" or row.get("clasificacion_e0_e1_e2"):
            raise IngestaInvalida("El inventario contiene captura propia o etiqueta no acreditada.")
        p = _relative_path(row["archivo_importado"])
        if not p.name.startswith(sha + ".") or p.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            raise IngestaInvalida("El nombre del original no corresponde al SHA-256.")
        source = _resolve_inside(root, p)
        if _sha256(source) != sha:
            raise IngestaInvalida("Original alterado desde la ingesta.")
        if sha in seen_images:
            raise IngestaInvalida("El mismo archivo aparece más de una vez en el inventario.")
        seen_images.add(sha)
        product, piece, view = row["producto"], row["id_ejemplar"], row["vista"]
        if not piece or not re.fullmatch(r"[1-9][0-9]{0,2}", view) or not re.fullmatch(r"[\w-]{1,60}", piece, re.ASCII):
            raise IngestaInvalida("Identificador o vista ilegible.")
        if (product, piece, view) in seen_views:
            raise IngestaInvalida("Vista repetida para identificador de la fuente.")
        seen_views.add((product, piece, view))
        if piece in seen_piece_products and seen_piece_products[piece] != product:
            raise IngestaInvalida("Identificador mezclado entre productos.")
        seen_piece_products[piece] = product
        try:
            with Image.open(source) as original:
                if original.format not in {"JPEG", "PNG"}:
                    raise IngestaInvalida("Formato de imagen no permitido.")
                if original.width * original.height > 16_000_000:
                    raise IngestaInvalida("Imagen excesivamente grande para procesamiento batch.")
                original.load()
                if (original.width != int(row["ancho_comprobado"]) or
                        original.height != int(row["alto_comprobado"])):
                    raise IngestaInvalida("Dimensiones distintas al control de ingesta.")
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            if isinstance(exc, IngestaInvalida):
                raise
            raise IngestaInvalida("Fotografía inválida o dimensiones no numéricas.") from exc
    return sorted(records, key=lambda r: (r["producto"], r["id_ejemplar"], int(r["vista"]) if r["vista"].isdigit() else r["vista"], r["sha256"]))


def _best_segment(masks: dict[str, Any]) -> dict[str, Any] | None:
    segments = masks.get("segments") or []
    return max(segments, key=lambda item: (item["pixel_count_processing"], -item["candidate_index"])) if segments else None


def _process_one(root: Path, row: dict[str, str], stage: Path, preview: bool) -> dict[str, Any]:
    source = _resolve_inside(root, _relative_path(row["archivo_importado"]))
    with Image.open(source) as original:
        rgb = original.convert("RGB")
        rgb.load()
    if row["producto"] == "tomate":
        result = analyze_tomato_surface(rgb)
        proposal, masks = result["surface_analysis"], result["mask_analysis"]
    else:
        proposal = propose_surface_regions(rgb)
        masks = describe_surface_masks(rgb, proposal)
    best = _best_segment(masks)
    sha = row["sha256"]
    preview_box = ""
    preview_mask = ""
    if preview:
        base = PurePosixPath("previews") / row["producto"] / row["id_ejemplar"]
        box = base / f"{sha}_cajas.png"
        mask = base / f"{sha}_mascara.png"
        save_candidate_preview(source, proposal, stage / str(box))
        save_mask_preview(source, proposal, stage / str(mask))
        preview_box, preview_mask = str(box), str(mask)
    return {
        "producto": row["producto"], "id_ejemplar_fuente": row["id_ejemplar"],
        "vista": row["vista"], "archivo_importado": row["archivo_importado"],
        "sha256": sha, "ancho_px": rgb.width, "alto_px": rgb.height,
        "resolucion_menor_128": min(rgb.size) < 128,
        "propuesta_estado": proposal["status"], "propuesta_metodo": proposal["method"],
        "candidatos": proposal["candidate_count"],
        "mascara_estado": masks["status"], "mascara_metodo": masks["method"],
        "mascara_candidatos": len(masks.get("segments", [])),
        "candidato_principal": best["candidate_index"] if best else None,
        "pixeles_mascara_principal": best["pixel_count_processing"] if best else None,
        "fraccion_imagen_mascara_principal": best["pixel_fraction_of_processing_image"] if best else None,
        "mediana_rgb_mascara": best["masked_median_rgb"] if best else None,
        "p10_rgb_mascara": best["masked_rgb_p10"] if best else None,
        "p90_rgb_mascara": best["masked_rgb_p90"] if best else None,
        "operador_confirmo_region": False,
        "etiqueta_e0_e1_e2": None, "vista_independiente": False,
        "revisar_caja": preview_box, "revisar_mascara": preview_mask,
    }


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "si" if value else "no"
    if isinstance(value, (list, dict)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return str(value)


def _write_csv(path: Path, records: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in records:
            writer.writerow({key: _csv_value(row.get(key)) for key in columns})


def _summaries(records: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    product_counts: dict[str, Any] = {}
    pieces: list[dict[str, Any]] = []
    by_piece: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_piece[(row["producto"], row["id_ejemplar_fuente"])].append(row)
    for (product, piece), views in sorted(by_piece.items()):
        candidates = [v["mediana_rgb_mascara"] for v in views if v["mediana_rgb_mascara"] is not None]
        pieces.append({
            "producto": product, "id_ejemplar_fuente": piece, "vistas_fuente": len(views),
            "vistas_con_mascara_candidata": len(candidates),
            "mediana_de_medianas_rgb_provisionales": [round(statistics.median(c[i] for c in candidates)) for i in range(3)] if candidates else None,
            "pieza_fisica_verificada": False,
            "independencia_de_sesion_verificada": False,
            "revisar_diferencias_entre_vistas": True,
        })
    for product in sorted(VALID_PRODUCTS):
        group = [r for r in records if r["producto"] == product]
        product_counts[product] = {
            "fotografias": len(group),
            "ejemplares_declarados_por_fuente": len({r["id_ejemplar_fuente"] for r in group}),
            "fotografias_menor_128px": sum(r["resolucion_menor_128"] for r in group),
            "estados_propuesta": dict(sorted(Counter(r["propuesta_estado"] for r in group).items())),
            "estados_mascara": dict(sorted(Counter(r["mascara_estado"] for r in group).items())),
            "fotos_con_mascara_candidata": sum(r["candidato_principal"] is not None for r in group),
            "etiquetas_validadas": 0,
            "grupos_independientes_verificados": 0,
        }
    return product_counts, pieces


def _write_output_checksums(stage: Path) -> dict[str, str]:
    return {
        p.relative_to(stage).as_posix(): _sha256(p)
        for p in sorted(stage.rglob("*")) if p.is_file() and p.name != "informe_tecnico.json"
    }


def evaluate(ingesta: Path, salida: Path, previews_per_piece: int = 1) -> dict[str, Any]:
    if type(previews_per_piece) is not int or previews_per_piece not in (0, 1, 2, 3):
        raise ValueError("previews_per_piece debe estar entre 0 y 3.")
    root, output = ingesta.resolve(), salida.resolve()
    if not root.is_dir():
        raise IngestaInvalida("La carpeta de ingesta no existe.")
    if output.exists():
        raise FileExistsError("La salida ya existe; nunca se sobrescribe.")
    if output.is_relative_to(root) or root.is_relative_to(output):
        raise IngestaInvalida("La salida debe estar separada de la ingesta.")
    records = _validate_inventory(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".agrop42_incremento08_", dir=output.parent) as scratch:
        stage = Path(scratch)
        views: list[dict[str, Any]] = []
        indexed: dict[tuple[str, str], int] = defaultdict(int)
        for row in records:
            key = (row["producto"], row["id_ejemplar"])
            indexed[key] += 1
            views.append(_process_one(root, row, stage, indexed[key] <= previews_per_piece))
        product_counts, pieces = _summaries(views)
        _write_csv(stage / "resultados_por_vista.csv", views, list(views[0]))
        _write_csv(stage / "resultados_por_ejemplar.csv", pieces, list(pieces[0]))
        reviews = [{
            "producto": r["producto"], "id_ejemplar_fuente": r["id_ejemplar_fuente"],
            "vista": r["vista"], "sha256": r["sha256"],
            "estado_propuesta": r["propuesta_estado"],
            "estado_mascara": r["mascara_estado"],
            "previsualizacion_cajas": r["revisar_caja"],
            "previsualizacion_mascara": r["revisar_mascara"],
            "region_confirmada_por_operador": "", "motivo_revision_region": "",
            "fondo_adecuado_confirmado": "", "calidad_confirmada": "",
            "etiqueta_visual_revisada": "", "revisor_id": "", "fecha_revision": "",
        } for r in views]
        _write_csv(stage / "revision_mascaras_pendiente.csv", reviews, list(reviews[0]))
        report = {
            "version": VERSION,
            "estado": "procesamiento_tecnico_completado_sin_validacion_de_mascaras",
            "origen": "fuentes_externas_incremento07",
            "fotografias_procesadas": len(views),
            "conteo_por_producto": product_counts,
            "identificadores_de_fuente": len(pieces),
            "previews_por_identificador": previews_per_piece,
            "regiones_confirmadas_por_operador": 0,
            "etiquetas_e0_e1_e2_verificadas": 0,
            "clasificacion_comercial_automatica": False,
            "modelo_entrenado": False,
            "precision_o_metricas_de_clasificacion": None,
            "entrenamiento_autorizado": False,
            "comparacion_de_exactitud_autorizada": False,
            "advertencias": WARNINGS,
            "sha256_salidas": _write_output_checksums(stage),
        }
        (stage / "informe_tecnico.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        # Copia únicamente artefactos derivados; los originales quedan en la ingesta.
        # Check previo también al mover: no reemplazar ningún directorio existente.
        if output.exists():
            raise FileExistsError("Se creó una salida concurrente; no se reemplaza.")
        os.rename(stage, output)
        return report


def verify(salida: Path) -> dict[str, Any]:
    root = salida.resolve()
    info = root / "informe_tecnico.json"
    if not info.is_file():
        raise IngestaInvalida("No existe el informe técnico del Incremento 08.")
    data = json.loads(info.read_text(encoding="utf-8-sig"))
    if data.get("version") != VERSION or not isinstance(data.get("sha256_salidas"), dict):
        raise IngestaInvalida("Esquema de informe no compatible.")
    for relative, expected in data["sha256_salidas"].items():
        path = _resolve_inside(root, _relative_output(relative))
        if _sha256(path) != expected:
            raise IngestaInvalida(f"Resultado modificado: {relative}")
    return {"estado": "integridad_resultados_verificada", "fotografias_procesadas": data["fotografias_procesadas"],
            "archivos_derivados_verificados": len(data["sha256_salidas"]),
            "entrenamiento_autorizado": False}


def _relative_output(raw: str) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\\" in raw or ":" in raw or "\x00" in raw:
        raise IngestaInvalida("Ruta de resultado malformada.")
    p = PurePosixPath(raw)
    if p.is_absolute() or any(x in ("", ".", "..") for x in raw.split("/")):
        raise IngestaInvalida("Resultado con ruta insegura.")
    if p.parts[0] not in {"previews", "resultados_por_vista.csv", "resultados_por_ejemplar.csv", "revision_mascaras_pendiente.csv"}:
        raise IngestaInvalida("Ruta de resultado no permitida.")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AGROP-42: segmentación, máscaras y RGB técnicos, sin etiquetas E0/E1/E2")
    sub = parser.add_subparsers(dest="accion", required=True)
    run = sub.add_parser("evaluar", help="Procesa una ingesta externa íntegra del Incremento 07")
    run.add_argument("--ingesta", type=Path, required=True)
    run.add_argument("--salida", type=Path, required=True)
    run.add_argument("--previews-por-ejemplar", type=int, choices=(0, 1, 2, 3), default=1)
    check = sub.add_parser("verificar", help="Verifica los archivos derivados mediante SHA-256")
    check.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        data = evaluate(args.ingesta, args.salida, args.previews_por_ejemplar) if args.accion == "evaluar" else verify(args.salida)
        print(json.dumps({k: v for k, v in data.items() if k != "sha256_salidas"}, ensure_ascii=False, indent=2))
    except (IngestaInvalida, FileExistsError, OSError, ValueError) as exc:
        parser.exit(2, f"ERROR AGROP-42: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
