from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone
import sqlite3, hashlib, json, csv, time, math, platform, statistics

from PIL import Image

from vision.src.surface_analysis import (
    propose_surface_regions,
    save_candidate_preview
)
from vision.src.surface_masks import (
    describe_surface_masks,
    save_mask_preview
)
from vision.src.tomato_surface import analyze_tomato_surface

ROOT = Path(__file__).resolve().parents[3]
DB = ROOT / "backend/data/agroscan.db"
DATA = DB.parent.resolve()
BASE = ROOT / "vision/experiments/AGROP42"

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()

def p95(values):
    values = sorted(values)
    return round(values[math.ceil(.95 * len(values)) - 1], 4) if values else None

def main():
    if not DB.is_file():
        raise FileNotFoundError(DB)

    out = None
    for n in range(1, 100):
        candidate = BASE / f"procesamiento_sqlite_real_{n:02d}"
        if not candidate.exists():
            out = candidate
            break

    if out is None:
        raise RuntimeError("No hay directorio de salida disponible.")

    previews = out / "previews"
    previews.mkdir(parents=True)

    uri = DB.as_uri() + "?mode=ro"

    with sqlite3.connect(uri, uri=True) as con:
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute("""
            SELECT
                i.id AS image_id,
                i.evaluation_id,
                i.view,
                i.relative_path,
                e.product,
                e.lot_id,
                l.code AS lot_code,
                e.piece_ref_id AS piece_id,
                p.code AS piece_code,
                e.device_id,
                e.boot_id
            FROM images i
            JOIN evaluations e ON e.id = i.evaluation_id
            LEFT JOIN lots l ON l.id = e.lot_id
            LEFT JOIN pieces p ON p.id = e.piece_ref_id
            WHERE LOWER(e.product) IN ('mango', 'tomate')
            ORDER BY i.id
        """)]

    grouped = defaultdict(list)

    for row in rows:
        raw = row["relative_path"]
        if not raw:
            raise ValueError(f"Imagen {row['image_id']} sin ruta.")

        path = (DATA / raw.replace("\\", "/")).resolve()

        if not path.is_relative_to(DATA) or not path.is_file():
            raise FileNotFoundError(f"Imagen no disponible: {row['image_id']}")

        digest = sha256(path)
        grouped[digest].append((row, path))

    results = []
    features = []
    timings = defaultdict(list)
    counts = {
        p: {"imagenes_unicas": 0, "candidatos": 0,
            "estados_superficie": Counter(), "estados_mascara": Counter()}
        for p in ("mango", "tomate")
    }

    for digest, group in sorted(grouped.items()):
        products = {r["product"] for r, _ in group}

        if len(products) != 1:
            raise ValueError("Una misma imagen SHA aparece en productos diferentes.")

        product = products.pop()
        row, path = group[0]

        start = time.perf_counter()

        with Image.open(path) as source:
            image = source.convert("RGB")

        if product == "tomate":
            analysis = analyze_tomato_surface(image)
            proposal = analysis["surface_analysis"]
            mask = analysis["mask_analysis"]
        else:
            proposal = propose_surface_regions(image)
            proposal = dict(proposal)
            proposal["product"] = "mango"
            mask = describe_surface_masks(image, proposal)

        elapsed = (time.perf_counter() - start) * 1000
        timings[product].append(elapsed)

        segments = mask.get("segments", [])
        candidates = proposal.get("candidates", [])

        counts[product]["imagenes_unicas"] += 1
        counts[product]["candidatos"] += len(candidates)
        counts[product]["estados_superficie"][proposal.get("status", "unknown")] += 1
        counts[product]["estados_mascara"][mask.get("status", "unknown")] += 1

        rgb = area = ""

        # Una única propuesta permite extraer descriptores,
        # pero no confirma automáticamente que sea la fruta.
        if len(segments) == 1:
            segment = segments[0]
            values = segment.get("masked_median_rgb")
            if isinstance(values, list) and len(values) == 3:
                rgb = values
                area = segment.get("pixel_fraction_of_processing_image", "")

        evidence = {
            "surface_status": proposal.get("status"),
            "mask_status": mask.get("status"),
            "candidate_count": len(candidates),
            "candidates": candidates,
            "segments": segments,
            "confirmation_required": True
        }

        features.append({
            "registro_id": f"AG42-{digest[:16]}",
            "r_mediana": rgb[0] if rgb else "",
            "g_mediana": rgb[1] if rgb else "",
            "b_mediana": rgb[2] if rgb else "",
            "area_relativa": area,
            "mascara_confirmada": "false",
            "evidencia_mascara": json.dumps(evidence, ensure_ascii=False)
        })

        # Vistas de diagnóstico. Nunca modifican la fotografía original.
        try:
            save_candidate_preview(
                path, proposal, previews / f"{digest[:16]}_candidatos.png"
            )
            save_mask_preview(
                path, proposal, previews / f"{digest[:16]}_mascara.png"
            )
        except Exception as exc:
            evidence["error_preview"] = str(exc)

        results.append({
            "registro_id": f"AG42-{digest[:16]}",
            "producto": product,
            "sha256": digest,
            "archivo": row["relative_path"],
            "image_ids": [r["image_id"] for r, _ in group],
            "evaluation_ids": sorted({r["evaluation_id"] for r, _ in group}),
            "piece_ids": sorted({r["piece_id"] for r, _ in group if r["piece_id"] is not None}),
            "lot_ids": sorted({r["lot_id"] for r, _ in group if r["lot_id"] is not None}),
            "sessions": sorted({
                f"{r['device_id']}:{r['boot_id']}"
                for r, _ in group if r["device_id"] and r["boot_id"]
            }),
            "views": [r["view"] for r, _ in group],
            "surface_analysis": proposal,
            "mask_analysis": mask,
            "processing_ms": round(elapsed, 4)
        })

    csv_path = out / "atributos_extraidos.csv"

    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        fields = [
            "registro_id", "r_mediana", "g_mediana", "b_mediana",
            "area_relativa", "mascara_confirmada", "evidencia_mascara"
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(features)

    summary = {}

    for product in ("mango", "tomate"):
        values = timings[product]
        summary[product] = {
            **counts[product],
            "estados_superficie": dict(counts[product]["estados_superficie"]),
            "estados_mascara": dict(counts[product]["estados_mascara"]),
            "latencia_mediana_ms": round(statistics.median(values), 4) if values else None,
            "latencia_p95_ms": p95(values)
        }

    report = {
        "tarea": "AGROP-42",
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "origen": "SQLite local de AgroScan",
        "base": "backend/data/agroscan.db",
        "fotografias_registradas": len(rows),
        "fotografias_unicas_sha256": len(results),
        "registros_repetidos": len(rows) - len(results),
        "hardware_ejecutor": {
            "sistema": platform.platform(),
            "procesador": platform.processor(),
            "cpu_logicas": __import__("os").cpu_count(),
            "python": platform.python_version(),
            "alcance": "PC de procesamiento visual; no mide ESP32"
        },
        "productos": summary,
        "resultados": results,
        "limitaciones": [
            "Los descriptores RGB no son etiquetas de calidad.",
            "Las mascaras siguen pendientes de confirmacion independiente.",
            "No se generan etiquetas E0/E1/E2 automaticamente.",
            "No se modifica la base SQLite ni las fotografias originales."
        ]
    }

    json_path = out / "resultados_vision_real.json"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("\n===== PROCESAMIENTO REAL AGROP-42 =====")
    print("Fotografias registradas:", len(rows))
    print("Fotografias unicas:", len(results))
    print("Registros repetidos:", len(rows) - len(results))

    for product, data in summary.items():
        print("\n", product.upper())
        print("Imagenes:", data["imagenes_unicas"])
        print("Candidatos:", data["candidatos"])
        print("Estados:", data["estados_superficie"])
        print("Mediana ms:", data["latencia_mediana_ms"])
        print("P95 ms:", data["latencia_p95_ms"])

    print("\nCSV:", csv_path)
    print("JSON:", json_path)
    print("Vistas:", previews)
    print("BASE DE DATOS ORIGINAL: SIN MODIFICACIONES")

if __name__ == "__main__":
    main()
