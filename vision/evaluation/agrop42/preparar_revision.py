from pathlib import Path
from collections import defaultdict
import sqlite3
import hashlib
import csv
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
DB = ROOT / "backend/data/agroscan.db"
DATA = ROOT / "backend/data"
OUT = Path(__file__).with_name("atributos_validados.template.csv")

CAMPOS = [
    "registro_id", "producto", "sha256", "archivo",
    "estado_revision", "etiqueta_visual", "revisor_id",
    "revisado_en", "rubrica_version", "calidad_confirmada",
    "cobertura_confirmada", "pieza_confirmada",
    "sesion_confirmada", "lote_id", "pieza_id",
    "sesion_id", "dispositivo_id", "evidencia_pieza",
    "evidencia_sesion", "justificacion_etiqueta",
    "nota_revision"
]

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

sql = """
SELECT i.id AS image_id, i.evaluation_id, i.view,
       i.relative_path, LOWER(COALESCE(l.product,e.product,'')) AS product,
       e.lot_id, l.code AS lot_code,
       e.piece_ref_id, p.code AS piece_code,
       e.device_id, e.boot_id
FROM images i
LEFT JOIN evaluations e ON e.id = i.evaluation_id
LEFT JOIN lots l ON l.id = e.lot_id
LEFT JOIN pieces p ON p.id = e.piece_ref_id
ORDER BY i.id
"""

with sqlite3.connect(DB) as con:
    con.row_factory = sqlite3.Row
    registros = [dict(r) for r in con.execute(sql)]

por_hash = defaultdict(list)
invalidas = []

for r in registros:
    producto = r["product"]
    raw = r["relative_path"]

    if producto not in ("mango", "tomate") or not raw:
        invalidas.append(r["image_id"])
        continue

    ruta = (DATA / raw).resolve()

    if not ruta.is_relative_to(DATA.resolve()) or not ruta.is_file():
        invalidas.append(r["image_id"])
        continue

    try:
        with Image.open(ruta) as img:
            img.verify()

        sha = digest(ruta)
        r["_sha"] = sha
        r["_ruta"] = ruta
        por_hash[sha].append(r)

    except Exception:
        invalidas.append(r["image_id"])

filas = []

for sha, grupo in sorted(por_hash.items()):
    productos = {r["product"] for r in grupo}

    if len(productos) != 1:
        raise ValueError(f"SHA compartido entre productos: {sha}")

    piezas = {str(r["piece_ref_id"]) for r in grupo
              if r["piece_ref_id"] is not None}
    lotes = {str(r["lot_id"]) for r in grupo
             if r["lot_id"] is not None}
    sesiones = {
        (r["device_id"], r["boot_id"])
        for r in grupo
        if r["device_id"] and r["boot_id"]
    }

    pieza_completa = (
        all(r["piece_ref_id"] is not None for r in grupo)
        and len(piezas) == 1
    )

    sesion_completa = (
        all(r["device_id"] and r["boot_id"] for r in grupo)
        and len(sesiones) == 1
    )

    evidencia_pieza = "; ".join(sorted({
        f"pieza={r['piece_ref_id']} codigo={r['piece_code']}"
        for r in grupo if r["piece_ref_id"] is not None
    }))

    evidencia_sesion = "; ".join(sorted({
        f"device={r['device_id']} boot={r['boot_id']}"
        for r in grupo if r["device_id"] and r["boot_id"]
    }))

    notas = ["Pendiente de revisión humana; no inferir E0/E1/E2."]

    if len(grupo) > 1:
        notas.append(
            f"SHA repetido en {len(grupo)} registros; no contar como muestras independientes."
        )

    if not pieza_completa:
        notas.append("Identidad de pieza pendiente de confirmar.")

    if not sesion_completa:
        notas.append("Identidad de sesión pendiente de confirmar.")

    primero = grupo[0]

    filas.append({
        "registro_id": f"AG42-{sha[:16]}",
        "producto": primero["product"],
        "sha256": sha,
        "archivo": primero["relative_path"].replace("\\", "/"),
        "estado_revision": "pendiente",
        "etiqueta_visual": "",
        "revisor_id": "",
        "revisado_en": "",
        "rubrica_version": "",
        "calidad_confirmada": "",
        "cobertura_confirmada": "",
        "pieza_confirmada": "",
        "sesion_confirmada": "",
        "lote_id": next(iter(lotes)) if len(lotes) == 1 else "",
        "pieza_id": next(iter(piezas)) if pieza_completa else "",
        "sesion_id": (
            f"{next(iter(sesiones))[0]}:{next(iter(sesiones))[1]}"
            if sesion_completa else ""
        ),
        "dispositivo_id": (
            next(iter(sesiones))[0] if sesion_completa else ""
        ),
        "evidencia_pieza": evidencia_pieza,
        "evidencia_sesion": evidencia_sesion,
        "justificacion_etiqueta": "",
        "nota_revision": " ".join(notas)
    })

OUT.parent.mkdir(parents=True, exist_ok=True)

with OUT.open("w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=CAMPOS)
    writer.writeheader()
    writer.writerows(filas)

print("\n===== AGROP-42: DATASET PREPARADO =====")
print("Registros originales:", len(registros))
print("Fotografías únicas:", len(filas))
print("Registros repetidos:", len(registros) - len(filas))
print("Archivos inválidos o ausentes:", len(invalidas))

for producto in ("mango", "tomate"):
    print(producto, sum(x["producto"] == producto for x in filas))

print("Archivo generado:", OUT)
