"""AGROP-42 · Incremento 07: ingesta verificable de imágenes de fuentes externas.

La evidencia de origen y el agrupamiento son DECLARADOS por el CSV del ZIP.
El hash, el formato y las dimensiones son comprobaciones reales de bytes.
NO acredita sesiones ni identidades físicas, etiquetas E0/E1/E2, variedad Kent
ni permisos adicionales al texto de licencia declarado.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from PIL import Image, UnidentifiedImageError

from vision.evaluation.agrop42.auditar_revisiones import COLUMNAS as COLUMNAS_AUDITOR, auditar_csv

COLUMNAS_FUENTE = (
    "archivo", "carpeta", "id_ejemplar", "vista", "grupo_original",
    "estado_fuente", "observacion_visual", "archivo_original", "fuente",
    "licencia", "resolucion_px", "sha256",
)
COLUMNAS_INVENTARIO = COLUMNAS_FUENTE + (
    "producto", "archivo_importado", "formato_comprobado", "ancho_comprobado",
    "alto_comprobado", "bytes_comprobados", "sha256_comprobado", "exif_campos_comprobados",
    "es_captura_propia", "trazabilidad_origen_verificada", "revision_visual",
    "clasificacion_e0_e1_e2", "observacion_tecnica",
)
VERSION = "agrop42-externo-v1"
MAX_ZIP_BYTES = 300 * 1024 * 1024
MAX_IMAGEN_BYTES = 50 * 1024 * 1024
MAX_IMAGEN_PIXELES = 40_000_000
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")
RES_RE = re.compile(r"^(\d{1,5})x(\d{1,5})$")


class ErrorFuentesExternas(ValueError):
    """La ingesta debe abortarse sin crear resultados parciales."""


def _ruta_segura(nombre: str) -> bool:
    """Descarta ZIP-slip, drive letters y barras Windows en cualquier host."""
    if not nombre or len(nombre) > 260 or "\\" in nombre or ":" in nombre or "\x00" in nombre:
        return False
    ruta = PurePosixPath(nombre)
    win = PureWindowsPath(nombre)
    return (not ruta.is_absolute() and not win.is_absolute() and not win.drive
            and not nombre.startswith("~") and all(x not in ("", ".", "..") for x in nombre.split("/")))


def _sha_bytes(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def _sha_archivo(ruta: Path) -> str:
    digest = hashlib.sha256()
    with ruta.open("rb") as f:
        for parte in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(parte)
    return digest.hexdigest()


def _escribir_csv(ruta: Path, columnas: tuple[str, ...] | list[str], filas: list[dict[str, Any]]) -> None:
    with ruta.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(filas)


def _entrada_zip(z: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    indice: dict[str, zipfile.ZipInfo] = {}
    colisiones: set[str] = set()
    tamaño_total = 0
    for info in z.infolist():
        nombre = info.filename
        if info.is_dir():
            # Directorios explícitos no contienen datos, pero también deben ser seguros.
            if not _ruta_segura(nombre[:-1]):
                raise ErrorFuentesExternas(f"directorio inseguro dentro de ZIP: {nombre!r}")
            continue
        if not _ruta_segura(nombre):
            raise ErrorFuentesExternas(f"ruta insegura dentro de ZIP: {nombre!r}")
        if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
            raise ErrorFuentesExternas("no se aceptan enlaces simbólicos en ZIP")
        normal = nombre.casefold()
        if normal in colisiones:
            raise ErrorFuentesExternas(f"ruta duplicada / colisión de mayúsculas: {nombre}")
        colisiones.add(normal)
        if info.file_size > MAX_IMAGEN_BYTES and nombre.lower().endswith((".jpg", ".jpeg", ".png")):
            raise ErrorFuentesExternas(f"imagen demasiado grande: {nombre}")
        tamaño_total += info.file_size
        if tamaño_total > MAX_ZIP_BYTES:
            raise ErrorFuentesExternas("el ZIP sobrepasa el límite de tamaño descomprimido")
        indice[nombre] = info
    return indice


def _metadata_jpeg(blob: bytes, nombre: str) -> tuple[int, int, int]:
    if len(blob) > MAX_IMAGEN_BYTES:
        raise ErrorFuentesExternas(f"imagen demasiado grande: {nombre}")
    try:
        with Image.open(io.BytesIO(blob)) as img:
            if img.format != "JPEG" or not nombre.lower().endswith((".jpg", ".jpeg")):
                raise ErrorFuentesExternas(f"solo JPEG original admitido: {nombre}")
            w, h = img.size
            if not (w > 0 and h > 0 and w * h <= MAX_IMAGEN_PIXELES):
                raise ErrorFuentesExternas(f"resolución inválida: {nombre}")
            exif_campos = len(img.getexif())
            img.verify()
        # Fuerza decodificación; verify() solo valida estructura parcial.
        with Image.open(io.BytesIO(blob)) as img:
            img.load()
        return w, h, exif_campos
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ErrorFuentesExternas(f"fotografía inválida {nombre}: {exc}") from exc


def validar_zip(ruta_zip: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Analiza fuente sin modificar el ZIP, devuelve metadatos derivados de bytes."""
    if not ruta_zip.is_file():
        raise ErrorFuentesExternas(f"archivo ZIP no existe: {ruta_zip}")
    with zipfile.ZipFile(ruta_zip) as z:
        indice = _entrada_zip(z)
        if "trazabilidad.csv" not in indice:
            raise ErrorFuentesExternas("falta trazabilidad.csv en la raíz")
        if indice["trazabilidad.csv"].file_size > 5 * 1024 * 1024:
            raise ErrorFuentesExternas("CSV de trazabilidad demasiado grande")
        try:
            raw = z.read("trazabilidad.csv").decode("utf-8-sig")
            lector = csv.DictReader(io.StringIO(raw), restkey="__extra__")
            cols = lector.fieldnames or []
            if len(cols) != len(set(cols)) or not set(COLUMNAS_FUENTE).issubset(cols):
                raise ErrorFuentesExternas("columnas duplicadas o faltantes en trazabilidad.csv")
            filas = list(lector)
        except (UnicodeError, csv.Error) as exc:
            raise ErrorFuentesExternas(f"CSV ilegible: {exc}") from exc
        if not filas:
            raise ErrorFuentesExternas("trazabilidad.csv sin registros")
        nombres_fotos = {p for p in indice if p.lower().endswith((".jpg", ".jpeg", ".png"))}
        vistos: set[str] = set()
        shas: set[str] = set()
        grupos: dict[str, dict[str, Any]] = {}
        salida: list[dict[str, Any]] = []
        for n, fila in enumerate(filas, 2):
            if fila.get("__extra__") is not None or any(not str(fila.get(c) or "").strip() for c in ("archivo", "carpeta", "id_ejemplar", "vista", "grupo_original", "archivo_original", "fuente", "licencia", "resolucion_px", "sha256")):
                raise ErrorFuentesExternas(f"fila {n}: valores obligatorios incompletos o columnas extra")
            # Los inventarios se abren con frecuencia en Excel: rechazar fórmulas en datos externos.
            if any(str(valor or "").lstrip().startswith(("=", "+", "-", "@")) for campo, valor in fila.items() if campo not in ("vista",) and campo != "__extra__"):
                raise ErrorFuentesExternas(f"fila {n}: campo que podría ejecutarse como fórmula CSV")
            path = fila["archivo"].strip()
            if not _ruta_segura(path) or path not in nombres_fotos or path in vistos:
                raise ErrorFuentesExternas(f"fila {n}: fotografía inválida, ausente o repetida: {path}")
            vistos.add(path)
            producto = {"mangos": "mango", "tomates": "tomate"}.get(fila["carpeta"])
            if not producto or not ID_RE.fullmatch(fila["id_ejemplar"]):
                raise ErrorFuentesExternas(f"fila {n}: carpeta o identificador no admitido")
            partes = path.split("/")
            if len(partes) != 3 or partes[:2] != [fila["carpeta"], fila["id_ejemplar"]] or not re.fullmatch(r"vista_\d{2}\.jpg", partes[2], re.IGNORECASE):
                raise ErrorFuentesExternas(f"fila {n}: ruta y pieza declarada no concuerdan")
            vista = str(fila["vista"])
            if not vista.isdecimal() or not 1 <= int(vista) <= 99 or partes[2].lower() != f"vista_{int(vista):02d}.jpg":
                raise ErrorFuentesExternas(f"fila {n}: vista no coincide con archivo")
            if not str(fila["fuente"]).startswith("https://") or not str(fila["licencia"]).startswith("https://"):
                raise ErrorFuentesExternas(f"fila {n}: URL de fuente/licencia inválida")
            sha = fila["sha256"].lower()
            if not SHA_RE.fullmatch(sha):
                raise ErrorFuentesExternas(f"fila {n}: SHA256 malformado")
            blob = z.read(path)
            real_sha = _sha_bytes(blob)
            if sha != real_sha or real_sha in shas:
                raise ErrorFuentesExternas(f"fila {n}: SHA256 incorrecto o fotografía repetida")
            shas.add(real_sha)
            w, h, exif_campos = _metadata_jpeg(blob, path)
            match = RES_RE.fullmatch(fila["resolucion_px"])
            if not match or (int(match[1]), int(match[2])) != (w, h):
                raise ErrorFuentesExternas(f"fila {n}: resolución incorrecta")
            identificador = fila["id_ejemplar"]
            if identificador in grupos and grupos[identificador]["grupo_original"] != fila["grupo_original"]:
                raise ErrorFuentesExternas(f"fila {n}: una pieza declarada cambia de grupo original")
            if identificador not in grupos:
                grupos[identificador] = {"producto": producto, "grupo_original": fila["grupo_original"], "vistas": set()}
            if grupos[identificador]["producto"] != producto or int(vista) in grupos[identificador]["vistas"]:
                raise ErrorFuentesExternas(f"fila {n}: conflicto de producto o vista por identificador")
            grupos[identificador]["vistas"].add(int(vista))
            obs = "baja_resolucion_100x100" if min(w, h) < 224 else ""
            salida.append({**fila,
                           "producto": producto, "archivo_importado": f"originales/{real_sha}.jpg",
                           "formato_comprobado": "JPEG", "ancho_comprobado": w, "alto_comprobado": h,
                           "bytes_comprobados": len(blob), "sha256_comprobado": real_sha,
                           "exif_campos_comprobados": exif_campos,
                           "es_captura_propia": "no", "trazabilidad_origen_verificada": "no",
                           "revision_visual": "pendiente", "clasificacion_e0_e1_e2": "",
                           "observacion_tecnica": obs})
        if nombres_fotos != vistos:
            raise ErrorFuentesExternas("hay imágenes en ZIP sin entrada de trazabilidad")
        archivos_extra = set(indice) - vistos - {"trazabilidad.csv", "LEEME.md"}
        if archivos_extra:
            raise ErrorFuentesExternas("archivos inesperados en ZIP: " + ", ".join(sorted(archivos_extra)[:5]))
        # Este conjunto declara tres vistas por pieza; eso no acredita independencia física.
        for identificador, group in grupos.items():
            if group["vistas"] != {1, 2, 3}:
                raise ErrorFuentesExternas(f"vistas incompletas para {identificador}: {group['vistas']}")
        for fila in salida:
            # Datos de fuentes, no se reinterpretan como etiquetas o inspecciones.
            if fila["producto"] == "mango":
                fila["observacion_tecnica"] = ";".join(x for x in (fila["observacion_tecnica"], "variedad_fuente_Ataulfo_no_Kent") if x)
        conteos = Counter(f["producto"] for f in salida)
        reporte = {
            "version": VERSION,
            "zip_sha256": _sha_archivo(ruta_zip),
            "zip_nombre": ruta_zip.name,
            "fotografias": len(salida), "sha256_correctos": len(salida), "hashes_unicos": len(shas),
            "vistas_por_ejemplar_declaradas": 3,
            "ejemplares_declarados": dict(sorted(Counter(g["producto"] for g in grupos.values()).items())),
            "imagenes_por_producto": dict(sorted(conteos.items())),
            "resolucion_inferior_224px": sum(min(f["ancho_comprobado"], f["alto_comprobado"]) < 224 for f in salida),
            "resolucion_exacta_100x100": sum((f["ancho_comprobado"],f["alto_comprobado"]) == (100,100) for f in salida),
            "imagenes_con_metadatos_exif": sum(f["exif_campos_comprobados"] > 0 for f in salida),
            "procedencia": "externa; no captura propia del proyecto",
            "mango_variedad": "Ataulfo según fuente; no se acredita Kent",
            "metadatos_fotograficos_de_sesion": "no acreditados por manifiesto",
            "comprobaciones_automaticas": "contenido, decodificación, formato, resolución, SHA256, agrupación declarada y rutas",
            "revision_independiente_de_identidad_sesiones_variedad_y_licencias": False,
            "etiquetas_e0_e1_e2": 0, "entrenamiento_autorizado": False,
            "aviso": "No inferir estado fitosanitario ni equivalencia Kent/Ataulfo. CSV fuente solo aporta agrupación declarada y observaciones."
        }
        return salida, reporte


def _fila_revision(fila: dict[str, Any], n: int) -> dict[str, str]:
    out = {col: "" for col in COLUMNAS_AUDITOR}
    out.update({
        "registro_id": f"EXT-{fila['id_ejemplar']}-V{int(fila['vista']):02d}",
        "producto": fila["producto"], "sha256": fila["sha256_comprobado"],
        "archivo": fila["archivo_importado"], "estado_revision": "pendiente",
        "nota_revision": "Origen externo sin revisión humana acreditada. " + str(fila.get("observacion_visual") or ""),
        # Nunca atribuir lote/pieza/sesión/dispositivo físico por nombrar un grupo documental.
        "lote_id": "", "pieza_id": "", "sesion_id": "", "dispositivo_id": "",
        "evidencia_pieza": "", "evidencia_sesion": "",
        "etiqueta_visual": "", "rubrica_version": "", "revisor_id": "",
        "pieza_confirmada": "", "sesion_confirmada": "",
        "calidad_confirmada": "", "cobertura_confirmada": "",
    })
    return out


def atribuciones() -> str:
    return """# AGROP-42 — Atribución y transformaciones de fuentes externas

## Mangos
- Fuente declarada en el paquete: Marianito-Cuahuitic et al. (2026), *Non-Destructive Classification of Ataulfo Mango Ripeness Using Color Images and Machine Learning*, Algorithms 19(8), 691. https://doi.org/10.3390/a19080691
- Dataset declarado: https://github.com/Imanol-24/ataulfo-mango-maturity-dataset/releases/tag/v1.0.0
- Licencia declarada: CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/
- El README suministrado declara **reexportación JPEG y reducción de tamaño hasta 1200 px**. Los SHA-256 corresponden a esos archivos reexportados, no necesariamente a los originales de la fuente.
- Variedad citada: **Ataulfo, no Kent**. No aplicar la rúbrica específica Kent como validación de variedad.

## Tomates
- Fuente declarada: Mihai Oltean, *Fruits-360*, https://github.com/fruits-360
- Licencia declarada: CC BY-SA 4.0 — https://creativecommons.org/licenses/by-sa/4.0/
- Subconjuntos: https://github.com/fruits-360/fruits-360-original-size y https://github.com/fruits-360/fruits-360-100x100
- El README suministrado declara que los JPEG de tomate solo fueron renombrados.
- Distintas categorías/variedades del dataset, no equivalentes a clases E0/E1/E2.

## Controles pendientes
- Verificar la edición/versionado exactos del material y condiciones de licencia aplicables a una futura publicación/redistribución.
- La coincidencia SHA256 con el ZIP **no demuestra** cadena de custodia o identidad física de cada ejemplar.
- Evitar subir imágenes/EXIF o derivados a Git hasta resolver la política de publicación y atribución.
"""


def ingresar_zip(ruta_zip: Path, salida: Path, *, solo_validar: bool = False) -> dict[str, Any]:
    """Realiza ingesta atómica fuera del ZIP; nunca sobrescribe una salida existente."""
    registros, reporte = validar_zip(ruta_zip)
    if solo_validar:
        return reporte
    salida = salida.resolve(strict=False)
    if salida.exists():
        raise ErrorFuentesExternas("la salida ya existe: no se sobrescribe")
    if salida == ruta_zip.resolve(strict=True) or salida == ruta_zip.resolve().parent:
        raise ErrorFuentesExternas("salida inválida")
    salida.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".agrop42_ext_", dir=salida.parent) as tmp:
        stage = Path(tmp)
        (stage / "originales").mkdir()
        with zipfile.ZipFile(ruta_zip) as z:
            for f in registros:
                dest = stage / f["archivo_importado"]
                data = z.read(f["archivo"])
                dest.write_bytes(data)
                if _sha_archivo(dest) != f["sha256_comprobado"]:
                    raise ErrorFuentesExternas("SHA incorrecto al materializar fotografía")
        inventario = stage / "inventario_externo.csv"
        _escribir_csv(inventario, COLUMNAS_INVENTARIO, registros)
        review = stage / "revisiones_pendientes.csv"
        _escribir_csv(review, sorted(COLUMNAS_AUDITOR), [_fila_revision(f, i) for i, f in enumerate(registros)])
        gate = auditar_csv(review)
        if gate["errores_integridad"] or gate["estado_global"] != "bloqueado_por_datos_insuficientes" or gate["evaluacion_ejecutada"]:
            raise ErrorFuentesExternas("revisiones deben permanecer sin etiquetas ni evaluación ejecutada")
        (stage / "ATRIBUCIONES.md").write_text(atribuciones(), encoding="utf-8")
        reporte["gate_incremento05"] = gate["estado_global"]
        reporte["revision_pendiente_csv"] = "revisiones_pendientes.csv"
        reporte["inventario_csv"] = "inventario_externo.csv"
        reporte["inventario_sha256"] = _sha_archivo(inventario)
        reporte["revisiones_sha256"] = _sha_archivo(review)
        reporte["originales"] = [{"archivo": f["archivo_importado"], "sha256": f["sha256_comprobado"]} for f in registros]
        (stage / "control_externo.json").write_text(json.dumps(reporte, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        # El directorio final solo aparece al terminar toda la ingesta.
        os.replace(stage, salida)
    return reporte


def verificar_salida(salida: Path) -> dict[str, Any]:
    """Reverifica SHA-256 y ligaduras de inventario sin convertir en etiquetas."""
    salida = salida.resolve(strict=True)
    control = json.loads((salida / "control_externo.json").read_text(encoding="utf-8"))
    if control.get("version") != VERSION:
        raise ErrorFuentesExternas("control de versión no reconocido")
    inventario = salida / "inventario_externo.csv"
    if not inventario.is_file() or _sha_archivo(inventario) != control.get("inventario_sha256"):
        raise ErrorFuentesExternas("inventario modificado o ausente")
    with inventario.open("r", encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    if len(filas) != control.get("fotografias") or len(filas) != len(control.get("originales", [])):
        raise ErrorFuentesExternas("conteo de fotografías inconsistente")
    for f, item in zip(filas, control["originales"]):
        nombre = item.get("archivo", "")
        if not _ruta_segura(nombre) or not nombre.startswith("originales/"):
            raise ErrorFuentesExternas("ruta insegura en control")
        path = (salida / nombre)
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(salida):
            raise ErrorFuentesExternas("fotografía inexistente o referencia externa")
        if nombre != f["archivo_importado"] or item.get("sha256") != f["sha256_comprobado"]:
            raise ErrorFuentesExternas("inventario y control discrepan")
        if _sha_archivo(path) != item["sha256"]:
            raise ErrorFuentesExternas("imagen alterada: " + nombre)
    revisiones = salida / "revisiones_pendientes.csv"
    if not revisiones.is_file() or _sha_archivo(revisiones) != control.get("revisiones_sha256"):
        raise ErrorFuentesExternas("plantilla de revisiones alterada: crear copia versionada para revisión humana")
    gate = auditar_csv(revisiones)
    if gate["errores_integridad"] or gate["estado_global"] != "bloqueado_por_datos_insuficientes":
        raise ErrorFuentesExternas("gate de revisiones inconsistente")
    return {"estado": "integridad_verificada", "fotografias": len(filas),
            "captura_propia": False, "grupos_elegibles": 0, "entrenamiento_autorizado": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="accion", required=True)
    for accion in ("validar", "importar"):
        sub = subs.add_parser(accion)
        sub.add_argument("--zip", required=True, type=Path)
        if accion == "importar":
            sub.add_argument("--salida", required=True, type=Path)
    check = subs.add_parser("verificar")
    check.add_argument("--salida", required=True, type=Path)
    a = parser.parse_args(argv)
    try:
        if a.accion == "verificar":
            reporte = verificar_salida(a.salida)
        else:
            reporte = ingresar_zip(a.zip, a.salida if a.accion == "importar" else Path("."), solo_validar=(a.accion == "validar"))
        print(json.dumps(reporte, ensure_ascii=False, indent=2))
        return 0
    except (ErrorFuentesExternas, OSError, ValueError, zipfile.BadZipFile, csv.Error, json.JSONDecodeError) as exc:
        print(json.dumps({"estado": "error", "detalle": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
