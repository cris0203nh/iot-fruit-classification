"""AGROP-42 / Incremento 01: auditoría de viabilidad supervisada, solo lectura.

No entrena modelos, no produce métricas predictivas y no modifica AGROP-39/40/41.
Los umbrales de viabilidad son mínimos estructurales para intentar tres conjuntos,
NO garantías estadísticas ni validación agronómica.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

VERSION = "agrop42-auditoria-v0.1"
PRODUCTS = ("mango", "tomate")
LABELS = ("E0", "E1", "E2")
MIN_GROUPS = 3
MIN_GROUPS_PER_CLASS = 3
MAX_IMAGE_BYTES = 30 * 1024 * 1024
REPO_ROOT = Path(__file__).resolve().parents[3]


class AuditInputError(ValueError):
    """Archivo de entrada no soportado; no confundir con datos insuficientes."""


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _id(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    return _string(str(value))


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _inspect_image(path_text: str | None, root: Path, allowed_root: Path) -> tuple[str, str | None]:
    """Nunca lee fuera de la raíz permitida; verifica decodificación PNG/JPEG."""
    if not path_text:
        return "ruta_ausente", None
    path = Path(path_text)
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(allowed_root.resolve()):
        return "ruta_fuera_de_raiz_permitida", None
    if not path.is_file():
        return "archivo_ausente", None
    try:
        size = path.stat().st_size
        if size == 0:
            return "archivo_vacio", None
        if size > MAX_IMAGE_BYTES:
            return "archivo_supera_limite_tecnico", None
        with Image.open(path) as image:
            if image.format not in {"PNG", "JPEG"}:
                return "formato_no_admitido", None
            image.verify()
        return "valida", _digest(path)
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return "imagen_invalida", None


def _read_database(db: Path, data_root: Path, allowed_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not db.is_file():
        return [], {"status": "no_disponible", "records": 0}
    query = """
    SELECT i.id AS image_id, i.relative_path, e.id AS evaluation_id,
           e.piece_ref_id, e.piece_id AS piece_legacy, e.device_id,
           e.boot_id, e.visual_category, l.code AS lot_code,
           COALESCE(l.product, e.product) AS product
      FROM images i
      LEFT JOIN evaluations e ON e.id = i.evaluation_id
      LEFT JOIN lots l ON l.id = e.lot_id
      ORDER BY i.id
    """
    try:
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as con:
            con.row_factory = sqlite3.Row
            rows = [dict(row) for row in con.execute(query)]
    except sqlite3.DatabaseError as exc:
        # No exponer ruta, consultas completas ni información privada del usuario.
        raise AuditInputError("La base SQLite no tiene el esquema esperado de AgroScan") from exc
    result = []
    for row in rows:
        status, digest = _inspect_image(row["relative_path"], data_root, allowed_root)
        # Una pieza sin FK normalizada no se trata como independiente por código libre.
        piece_key = f"db:{row['piece_ref_id']}" if row["piece_ref_id"] is not None else None
        dev, boot = _string(row["device_id"]), _string(row["boot_id"])
        result.append({
            "source_id": f"db:image:{row['image_id']}",
            "source": "sqlite", "product": (_string(row["product"]) or "").lower(),
            "piece_key": piece_key,
            "session_key": f"{dev}:{boot}" if dev and boot else None,
            "file_status": status, "sha256": digest,
            "unverified_label": _string(row["visual_category"]),
        })
    return result, {"status": "leida", "records": len(result)}


def _read_manifests(directory: Path | None, allowed_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if directory is None:
        return [], {"status": "no_solicitado", "records": 0, "manifests": 0}
    if not directory.is_dir():
        return [], {"status": "no_disponible", "records": 0, "manifests": 0}
    records = []
    examined, accepted, ignored = 0, 0, 0
    for file in sorted(directory.rglob("*.json")):
        # Impide seguir enlaces fuera del directorio de manifiestos.
        if not file.resolve().is_relative_to(directory.resolve()):
            ignored += 1
            continue
        examined += 1
        try:
            data = json.loads(file.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            ignored += 1
            continue
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("piece"), dict)
            or not isinstance(data.get("images"), list)
            or "criteria" in data
            or "visual_status" in data
            or "pipeline_version" in data
            or any(isinstance(item, dict) and "path" not in item for item in data["images"])
        ):
            ignored += 1  # Los resultados JSON también contienen piece/images; NO son manifiestos.
            continue
        accepted += 1
        piece = data["piece"]
        product = (_string(piece.get("product")) or "").lower()
        lot_id, piece_id = _id(piece.get("lot_id")), _id(piece.get("piece_id"))
        # La identidad no se infiere a partir del nombre de archivo ni del candidato visual.
        piece_key = f"manifest:{product}:{lot_id}:{piece_id}" if lot_id and piece_id else None
        for idx, item in enumerate(data["images"], start=1):
            if not isinstance(item, dict):
                item = {}
            capture = item.get("capture") if isinstance(item.get("capture"), dict) else {}
            dev, boot = _string(capture.get("device_id")), _string(capture.get("boot_id"))
            status, digest = _inspect_image(_string(item.get("path")), file.parent, allowed_root)
            records.append({
                "source_id": f"manifest:{file.name}:{accepted}:{idx}",
                "source": "manifest", "product": product, "piece_key": piece_key,
                "session_key": f"{dev}:{boot}" if dev and boot else None,
                "file_status": status, "sha256": digest,
                "unverified_label": _string(data.get("operator_visual_label")),
            })
    return records, {"status": "leidos", "records": len(records), "manifests": accepted,
                     "files_examined": examined, "non_manifest_or_invalid_files": ignored}


def _read_annotations(path: Path | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if path is None:
        return [], {"status": "no_solicitadas", "count": 0}
    if not path.is_file():
        return [], {"status": "no_disponibles", "count": 0}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditInputError("El JSON de anotaciones no puede leerse") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("annotations"), list):
        raise AuditInputError("Las anotaciones requieren un objeto con lista 'annotations'")
    rows = []
    for i, item in enumerate(payload["annotations"], start=1):
        if not isinstance(item, dict):
            raise AuditInputError(f"Anotación {i}: debe ser un objeto")
        digest, product, label = item.get("sha256"), item.get("product"), item.get("label")
        if (not isinstance(digest, str) or len(digest) != 64 or
                any(c not in "0123456789abcdef" for c in digest) or
                product not in PRODUCTS or label not in LABELS):
            raise AuditInputError(f"Anotación {i}: SHA256, producto o etiqueta inválidos")
        # Requiere respaldo explícito, pero se sigue considerando declaración
        # documental: la auditoría NO certifica credenciales del revisor.
        verified = (item.get("review_verified") is True and
                    bool(_string(item.get("reviewer_id"))) and
                    bool(_string(item.get("rubric_version"))) and
                    bool(_string(item.get("reviewed_at"))))
        rows.append({"sha256": digest, "product": product, "label": label,
                     "review_documented": verified})
    return rows, {"status": "leidas", "count": len(rows),
                  "con_revision_documentada": sum(row["review_documented"] for row in rows)}


class _DSU:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def root(self, key: str) -> str:
        if key not in self.parent:
            self.parent[key] = key
        if self.parent[key] != key:
            self.parent[key] = self.root(self.parent[key])
        return self.parent[key]

    def join(self, a: str, b: str) -> None:
        ra, rb = self.root(a), self.root(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)  # Orden canónico determinista.


def _product_audit(rows: list[dict[str, Any]], annotations: list[dict[str, Any]], product: str,
                   cross_product_sha: set[str]) -> dict[str, Any]:
    own = [r for r in rows if r["product"] == product]
    valid = [r for r in own if r["file_status"] == "valida"]
    valid_shas = {r["sha256"] for r in valid}
    eligible = [r for r in valid if r["piece_key"] and r["session_key"]]
    dsu = _DSU()
    for record in eligible:
        dsu.join(f"piece:{record['piece_key']}", f"session:{record['session_key']}")
        dsu.join(f"piece:{record['piece_key']}", f"hash:{record['sha256']}")
    groups = {dsu.root(f"hash:{r['sha256']}") for r in eligible}
    # Una etiqueta solo cuenta si tiene revisión documentada y SHA existente.
    # Anotaciones contradictorias para un hash bloquean todo ese hash.
    labels_by_hash: dict[str, set[str]] = defaultdict(set)
    for annotation in annotations:
        if (annotation["product"] == product and annotation["sha256"] in valid_shas
                and annotation["review_documented"]):
            labels_by_hash[annotation["sha256"]].add(annotation["label"])
    conflicts = {sha for sha, labels in labels_by_hash.items() if len(labels) > 1}
    label_groups: dict[str, set[str]] = defaultdict(set)
    eligible_sha_roots = {r["sha256"]: dsu.root(f"hash:{r['sha256']}") for r in eligible}
    for sha, label_set in labels_by_hash.items():
        if sha not in conflicts and sha in eligible_sha_roots and sha not in cross_product_sha:
            label_groups[next(iter(label_set))].add(eligible_sha_roots[sha])
    # Un grupo con múltiples clases distintas no puede adjudicarse a ninguna.
    groups_to_classes: dict[str, set[str]] = defaultdict(set)
    for label, roots in label_groups.items():
        for root in roots:
            groups_to_classes[root].add(label)
    ambiguous_groups = {g for g, classes in groups_to_classes.items() if len(classes) > 1}
    usable = {label: roots - ambiguous_groups for label, roots in label_groups.items()}
    classes = [label for label in LABELS if usable.get(label)]
    reasons = []
    if not valid:
        reasons.append("sin_fotografias_validas")
    if len(groups) < MIN_GROUPS:
        reasons.append("menos_de_tres_grupos_independientes")
    if len(classes) < 2:
        reasons.append("menos_de_dos_clases_con_etiquetas_revisadas_y_sesion")
    if len(classes) >= 2 and any(len(usable[label]) < MIN_GROUPS_PER_CLASS for label in classes):
        reasons.append("alguna_clase_tiene_menos_de_tres_grupos_independientes")
    if conflicts or ambiguous_groups:
        reasons.append("anotaciones_contradicen_la_misma_imagen_o_grupo")
    if valid_shas & cross_product_sha:
        reasons.append("mismo_archivo_asignado_a_productos_distintos")
    return {
        "registros": len(own), "imagenes_validas": len(valid),
        "imagenes_unicas_sha256": len(valid_shas),
        "registros_con_pieza_y_sesion": len(eligible),
        "grupos_independientes_verificables": len(groups),
        "etiquetas_no_verificadas_en_origen": sum(bool(r["unverified_label"]) for r in own),
        "imagenes_con_revision_documentada": len(labels_by_hash),
        "clases_revisadas_en_grupos_elegibles": {label: len(usable.get(label, set())) for label in LABELS},
        "imagenes_con_anotaciones_contradictorias": len(conflicts),
        "grupos_con_etiquetas_contradictorias": len(ambiguous_groups),
        "status": "preparado_para_intentar_particion" if not reasons else "bloqueado",
        "motivos": reasons,
        "advertencia": "Revisión documental declarada; no constituye certificación del experto ni prueba de exactitud.",
    }


def audit(records: list[dict[str, Any]], annotations: list[dict[str, Any]],
          sources: dict[str, Any]) -> dict[str, Any]:
    """Evalúa condiciones mínimas por producto; nunca entrena ni particiona."""
    valid = [r for r in records if r["file_status"] == "valida"]
    hash_sources: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in valid:
        hash_sources[record["sha256"]].append(record)
    duplicates = {sha: group for sha, group in hash_sources.items() if len(group) > 1}
    cross_product = {sha for sha, group in hash_sources.items()
                     if len({r["product"] for r in group}) > 1}
    products = {product: _product_audit(records, annotations, product, cross_product)
                for product in PRODUCTS}
    if not records:
        status = "insumos_no_disponibles"
    elif any(x["status"] == "preparado_para_intentar_particion" for x in products.values()):
        status = "potencial_para_particion_por_producto"
    else:
        status = "bloqueado_por_datos_insuficientes"
    return {
        "task": "AGROP-42", "increment": "01", "audit_version": VERSION,
        "status": status, "fuentes": sources,
        "umbrales_estructurales_no_estadisticos": {
            "grupos_independientes_minimos_para_tres_particiones": MIN_GROUPS,
            "clases_revisadas_distintas_minimas": 2,
            "grupos_independientes_por_clase_minimos": MIN_GROUPS_PER_CLASS,
        },
        "totales": {
            "registros_fotograficos": len(records),
            "registros_de_archivos_validos": len(valid),
            "archivos_unicos_sha256": len(hash_sources),
            "registros_con_archivos_ausentes_o_invalidos": len(records) - len(valid),
            "sha256_repetidos": len(duplicates),
            "registros_reutilizados_en_sha256_repetidos": sum(len(group) for group in duplicates.values()),
            "hashes_reutilizados_entre_productos": len(cross_product),
        },
        "evidencia_de_duplicados": [
            {"sha256": sha, "registros": sorted(r["source_id"] for r in group),
             "productos": sorted({r["product"] for r in group})}
            for sha, group in sorted(duplicates.items())
        ],
        "por_producto": products,
        "decision": {
            "entrenamiento_ejecutado": False,
            "metricas_predictivas_calculadas": False,
            "comparacion_de_modelos_ejecutada": False,
            "siguiente_paso": (
                "validar_particion_estratificada_sin_fugas_por_producto_y_confirmar_etiquetas"
                if status == "potencial_para_particion_por_producto" else
                "obtener_fotografias_originales_con_sesion_y_etiquetas_revisadas_por_producto"
            ),
        },
        "advertencias": [
            "Mango y tomate se evalúan por separado; sus rúbricas y etiquetas no se mezclan.",
            "El mismo SHA256 puede representar múltiples registros; no equivale a capturas independientes.",
            "SHA256 no detecta copias modificadas, reescaladas o recortadas; la independencia visual requiere revisión adicional.",
            "Los campos visual_category y operator_visual_label no constituyen verdad-terreno validada.",
            "Los grupos enlazan pieza, sesión y SHA256 para reducir filtración entre particiones.",
            "El mínimo de grupos es un control estructural, no una garantía de tamaño muestral o precisión.",
            "No se entrenan modelos ni se generan métricas simuladas.",
        ],
    }


def run(db: Path, data_root: Path, allowed_root: Path,
        manifests_dir: Path | None = None, annotations_file: Path | None = None) -> dict[str, Any]:
    db_rows, db_info = _read_database(db, data_root, allowed_root)
    manifest_rows, manifest_info = _read_manifests(manifests_dir, allowed_root)
    annotations, ann_info = _read_annotations(annotations_file)
    return audit(db_rows + manifest_rows, annotations, {
        "sqlite": db_info, "manifiestos": manifest_info, "anotaciones": ann_info,
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AGROP-42: auditoría de dataset solo lectura")
    parser.add_argument("--db", type=Path, default=REPO_ROOT / "backend/data/agroscan.db")
    parser.add_argument("--data-root", type=Path, default=REPO_ROOT / "backend/data")
    parser.add_argument("--allowed-root", type=Path, default=REPO_ROOT,
                        help="Raíz de seguridad para archivos de imagen, por defecto repositorio")
    parser.add_argument("--manifests-dir", type=Path,
                        help="Directorio local opcional con manifiestos de AGROP-40/41")
    parser.add_argument("--annotations", type=Path,
                        help="JSON opcional de etiquetas con revisión documentada")
    parser.add_argument("--output", type=Path,
                        default=REPO_ROOT / "vision/experiments/AGROP42/auditoria_viabilidad.json")
    args = parser.parse_args(argv)
    try:
        result = run(args.db, args.data_root, args.allowed_root,
                     args.manifests_dir, args.annotations)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    except (AuditInputError, OSError) as exc:
        parser.error(str(exc))
    print("Auditoría AGROP-42:", result["status"])
    print("Informe:", args.output)
    for product, detail in result["por_producto"].items():
        print(f"  {product}: {detail['status']} | archivos únicos={detail['imagenes_unicas_sha256']} "
              f"| grupos={detail['grupos_independientes_verificables']} "
              f"| motivos={','.join(detail['motivos']) or 'ninguno'}")
    return 0  # Bloqueo por datos insuficientes es un resultado válido de la auditoría.


if __name__ == "__main__":
    raise SystemExit(main())
