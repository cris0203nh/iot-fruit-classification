"""AGROP-42 · Incremento 06: ingesta local de fotografías propias con trazabilidad.

No clasifica defectos ni confirma variedad, pieza, sesión, calidad o licencias.
Los identificadores y la procedencia son DECLARACIONES del capturador; los
SHA-256 y dimensiones se verifican leyendo los archivos originales.
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
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from PIL import Image, ImageFilter, ImageStat, UnidentifiedImageError

from vision.evaluation.agrop42.auditar_revisiones import COLUMNAS as COLUMNAS_AUDITOR, auditar_csv

COLUMNAS_ENTRADA = (
    "registro_id", "producto", "variedad_declarada", "lote_id", "pieza_id",
    "sesion_id", "dispositivo_id", "operador_id", "capturado_en", "vista",
    "archivo_relativo", "procedencia", "autorizacion_ref",
    "referencia_identidad_pieza", "referencia_identidad_sesion", "observaciones",
)
COLUMNAS_SALIDA = COLUMNAS_ENTRADA + (
    "sha256", "archivo_importado", "formato", "ancho_px", "alto_px",
    "tamano_bytes", "luminosidad_indicativa", "bordes_indicativos",
    "alerta_resolucion", "confirmacion_visual", "confirmacion_identidad",
)
# Identificadores sin rutas, espacios ni contenido con significado especial.
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
VISTAS = {
    "frontal", "posterior", "lateral_izquierda", "lateral_derecha",
    "superior", "inferior", "oblicua", "otra",
}
FORMATOS = {"JPEG": {".jpg", ".jpeg"}, "PNG": {".png"}}
MAX_BYTES = 50 * 1024 * 1024
MAX_PIXELS = 40_000_000
VERSION = "agrop42-capturas-v1"


class ErrorCapturas(ValueError):
    """Error de datos en lote; nunca habilita una importación parcial."""


def _valor(fila: dict, nombre: str) -> str:
    return str(fila.get(nombre) or "").strip()


def _ruta_relativa_segura(valor: str) -> bool:
    if not valor or "\\" in valor or ":" in valor or "\x00" in valor:
        return False
    p = PurePosixPath(valor)
    win = PureWindowsPath(valor)
    return (
        not p.is_absolute() and not win.is_absolute() and not win.drive
        and bool(p.parts) and all(s not in {"", ".", ".."} for s in valor.split("/"))
        and not valor.startswith("~")
    )


def _en_directorio(path: Path, directorio: Path) -> bool:
    try:
        path.relative_to(directorio)
        return True
    except ValueError:
        return False


def _fecha_con_zona(valor: str) -> bool:
    try:
        fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        return fecha.tzinfo is not None and fecha.utcoffset() is not None
    except ValueError:
        return False


def _csv_filas(csv_path: Path) -> list[dict[str, str]]:
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            cabecera = reader.fieldnames or []
            if len(cabecera) != len(set(cabecera)):
                raise ErrorCapturas("CSV de captura con nombres de columna duplicados")
            faltantes = set(COLUMNAS_ENTRADA) - set(cabecera)
            if faltantes:
                raise ErrorCapturas("CSV de captura: faltan columnas " + ", ".join(sorted(faltantes)))
            filas = list(reader)
    except (UnicodeError, csv.Error) as exc:
        raise ErrorCapturas(f"CSV no legible: {exc}") from exc
    if not filas:
        raise ErrorCapturas("CSV vacío: registrar capturas propias antes de importar")
    for i, fila in enumerate(filas, 2):
        if None in fila:
            raise ErrorCapturas(f"fila {i}: sobran columnas respecto a la cabecera")
    return filas


def _huella_archivo(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for fragmento in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(fragmento)
    return h.hexdigest()


def _datos_imagen(path: Path) -> dict[str, Any]:
    try:
        with Image.open(path) as imagen:
            formato = imagen.format
            ancho, alto = imagen.size
            if formato not in FORMATOS or path.suffix.lower() not in FORMATOS[formato]:
                raise ErrorCapturas(f"{path.name}: solo JPEG/PNG con extensión correcta")
            if ancho * alto > MAX_PIXELS:
                raise ErrorCapturas(f"{path.name}: supera {MAX_PIXELS} píxeles")
            imagen.verify()
        with Image.open(path) as imagen:
            imagen.load()  # No basta leer la cabecera; exigir decodificación.
            muestra = imagen.convert("L")
            muestra.thumbnail((256, 256))
            brillo = round(ImageStat.Stat(muestra).mean[0], 2)
            borde = round(ImageStat.Stat(muestra.filter(ImageFilter.FIND_EDGES)).var[0], 2)
        return {
            "formato": formato, "ancho_px": ancho, "alto_px": alto,
            "luminosidad_indicativa": brillo,
            "bordes_indicativos": borde,
            "alerta_resolucion": "revisar_resolucion" if min(ancho, alto) < 600 else "",
        }
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        if isinstance(exc, ErrorCapturas):
            raise
        raise ErrorCapturas(f"imagen ilegible/corrupta: {path.name}: {exc}") from exc


def validar_capturas(csv_path: Path, entrada: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Validación de estructura, trazabilidad declarada y bytes originales."""
    entrada = entrada.resolve(strict=True)
    csv_path = csv_path.resolve(strict=True)
    if not entrada.is_dir():
        raise ErrorCapturas("--entrada debe ser un directorio de capturas originales")
    registros = []
    errores = []
    ids: set[str] = set()
    sha_vistos: dict[str, str] = {}
    pieza_a_lote: dict[tuple[str, str], str] = {}
    sesion_a_equipo: dict[str, tuple[str, str]] = {}
    vistas_por_pieza: set[tuple[str, str, str, str]] = set()
    for i, fila in enumerate(_csv_filas(csv_path), 2):
        try:
            datos: dict[str, Any] = {k: _valor(fila, k) for k in COLUMNAS_ENTRADA}
            rid = datos["registro_id"]
            for campo in ("registro_id", "lote_id", "pieza_id", "sesion_id", "dispositivo_id", "operador_id"):
                if not ID_RE.fullmatch(datos[campo]):
                    raise ErrorCapturas(f"{campo} vacío o contiene caracteres prohibidos")
            if rid in ids:
                raise ErrorCapturas(f"registro_id repetido: {rid}")
            if datos["producto"] not in {"mango", "tomate"}:
                raise ErrorCapturas("producto debe ser mango o tomate")
            if datos["producto"] == "mango" and not datos["variedad_declarada"]:
                raise ErrorCapturas("mango requiere variedad declarada (no verificada automáticamente)")
            if not _fecha_con_zona(datos["capturado_en"]):
                raise ErrorCapturas("capturado_en requiere ISO 8601 con hora y zona horaria")
            if datos["vista"] not in VISTAS:
                raise ErrorCapturas("vista no admitida")
            if datos["procedencia"] != "captura_propia":
                raise ErrorCapturas("solo se admiten capturas propias; no archivos externos/reutilizados")
            if not datos["autorizacion_ref"]:
                raise ErrorCapturas("falta referencia documental de autorización/uso")
            if not datos["referencia_identidad_pieza"] or not datos["referencia_identidad_sesion"]:
                raise ErrorCapturas("faltan referencias de identidad de pieza o de sesión")
            for campo in ("autorizacion_ref", "referencia_identidad_pieza", "referencia_identidad_sesion", "observaciones", "variedad_declarada"):
                if len(datos[campo]) > 600 or (datos[campo] and datos[campo][0] in "=+@\t\r"):
                    raise ErrorCapturas(f"{campo}: valor demasiado largo o no seguro para CSV")
            relativo = datos["archivo_relativo"]
            if not _ruta_relativa_segura(relativo):
                raise ErrorCapturas("archivo_relativo debe ser una ruta relativa POSIX sin traversal")
            ruta = entrada / relativo
            if ruta.is_symlink() or not ruta.is_file():
                raise ErrorCapturas(f"archivo ausente o enlace simbólico: {relativo}")
            ruta_real = ruta.resolve(strict=True)
            if not _en_directorio(ruta_real, entrada):
                raise ErrorCapturas(f"archivo fuera de entrada: {relativo}")
            tam = ruta.stat().st_size
            if tam == 0 or tam > MAX_BYTES:
                raise ErrorCapturas(f"archivo vacío o superior a {MAX_BYTES} bytes")
            sha = _huella_archivo(ruta_real)
            if sha in sha_vistos:
                raise ErrorCapturas(f"mismo archivo SHA-256 que {sha_vistos[sha]} (no es nueva vista)")
            datos_img = _datos_imagen(ruta_real)
            llave_pieza = (datos["producto"], datos["pieza_id"])
            if llave_pieza in pieza_a_lote and pieza_a_lote[llave_pieza] != datos["lote_id"]:
                raise ErrorCapturas("pieza_id reutilizado entre lotes del mismo producto")
            llave_equipo = (datos["dispositivo_id"], datos["operador_id"])
            if datos["sesion_id"] in sesion_a_equipo and sesion_a_equipo[datos["sesion_id"]] != llave_equipo:
                raise ErrorCapturas("sesion_id reutilizado con operador o dispositivo diferente")
            llave_vista = (datos["producto"], datos["pieza_id"], datos["sesion_id"], datos["vista"])
            if llave_vista in vistas_por_pieza:
                raise ErrorCapturas("misma vista repetida para la pieza y sesión; usar otra sesión o revisar")
            datos.update(datos_img)
            datos["sha256"] = sha
            datos["tamano_bytes"] = tam
            datos["archivo_importado"] = f"originales/{sha}{ruta_real.suffix.lower()}"
            datos["confirmacion_visual"] = "pendiente_revision_humana"
            datos["confirmacion_identidad"] = "declarada_no_verificada"
            datos["_origen_path"] = ruta_real  # solo memoria; nunca aparece en exportación
            registros.append(datos)
            ids.add(rid)
            sha_vistos[sha] = rid
            pieza_a_lote[llave_pieza] = datos["lote_id"]
            sesion_a_equipo[datos["sesion_id"]] = llave_equipo
            vistas_por_pieza.add(llave_vista)
        except ErrorCapturas as exc:
            errores.append(f"fila {i}: {exc}")
    return registros, errores


def _escribir_csv(path: Path, campos: tuple[str, ...] | list[str], filas: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=campos, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(filas)


def _fila_revision(reg: dict[str, Any]) -> dict[str, str]:
    """Genera un artefacto compatible con Incremento 05, NUNCA etiquetas."""
    out = {col: "" for col in COLUMNAS_AUDITOR}
    out.update({
        "registro_id": reg["registro_id"], "producto": reg["producto"],
        "sha256": reg["sha256"], "archivo": reg["archivo_importado"],
        "lote_id": reg["lote_id"], "pieza_id": reg["pieza_id"],
        "sesion_id": reg["sesion_id"], "dispositivo_id": reg["dispositivo_id"],
        "estado_revision": "pendiente", "nota_revision": "",
        # Nunca confundir una referencia declarada con una evidencia validada.
        "evidencia_pieza": "", "evidencia_sesion": "",
        "pieza_confirmada": "", "sesion_confirmada": "",
        "calidad_confirmada": "", "cobertura_confirmada": "",
        "etiqueta_visual": "", "rubrica_version": "",
    })
    return out


def ingresar_capturas(csv_path: Path, entrada: Path, salida: Path) -> dict[str, Any]:
    """Ingesta atómica en directorio nuevo; no sobrescribe y no deja lote parcial."""
    # Nunca crear archivos en directorio de entrada de fotografías.
    entrada = entrada.resolve(strict=True)
    salida = salida.resolve(strict=False)
    if _en_directorio(salida, entrada) or salida == entrada:
        raise ErrorCapturas("--salida debe estar fuera del directorio de capturas originales")
    if salida.exists():
        raise ErrorCapturas("la carpeta de salida ya existe; no se sobrescribe una ingesta")
    registros, errores = validar_capturas(csv_path, entrada)
    if errores:
        raise ErrorCapturas("Errores de prevalidación:\n- " + "\n- ".join(errores))
    if not registros:
        raise ErrorCapturas("no hay capturas válidas")
    salida.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".agrop42_06_", dir=salida.parent) as tmp:
        tmp_dir = Path(tmp)
        carpeta_fotos = tmp_dir / "originales"
        carpeta_fotos.mkdir()
        for fila in registros:
            destino = tmp_dir / fila["archivo_importado"]
            shutil.copyfile(fila["_origen_path"], destino)
            if _huella_archivo(destino) != fila["sha256"]:
                raise ErrorCapturas("la copia no coincide con SHA-256 original")
        inventario = tmp_dir / "inventario_capturas.csv"
        revision = tmp_dir / "revisiones_pendientes.csv"
        _escribir_csv(inventario, COLUMNAS_SALIDA, registros)
        _escribir_csv(revision, sorted(COLUMNAS_AUDITOR), [_fila_revision(r) for r in registros])
        audit = auditar_csv(revision)
        # Mantener el control del Incremento 05: la revisión debe permanecer bloqueada.
        if audit["estado_global"] != "bloqueado_por_datos_insuficientes" or audit["errores_integridad"]:
            raise ErrorCapturas("puerta de auditoría incumplida en la plantilla de revisión")
        resumen = {
            "version": VERSION,
            "alcance": "capturas_propias_declaradas_no_validadas_por_revisor",
            "cantidad_fotografias": len(registros),
            "productos": dict(sorted(Counter(r["producto"] for r in registros).items())),
            "piezas_declaradas": len({(r["producto"], r["lote_id"], r["pieza_id"]) for r in registros}),
            "sesiones_declaradas": len({r["sesion_id"] for r in registros}),
            "estado_revision": "pendiente",
            "clases_etiquetadas": 0,
            "entrenamiento_autorizado": False,
            "integridad_copias": "SHA256_verificado",
            "inventario_sha256": _huella_archivo(inventario),
            "archivos": [
                {"registro_id": r["registro_id"], "archivo": r["archivo_importado"], "sha256": r["sha256"]}
                for r in registros
            ],
            "resultado_auditor_incremento05": audit["estado_global"],
            "alertas_resolucion": [r["registro_id"] for r in registros if r["alerta_resolucion"]],
            "aviso": "Identidad, derechos, calidad, cobertura, variedad y etiquetas requieren revisión humana verificable. No subir originales ni EXIF a Git.",
        }
        (tmp_dir / "control_ingesta.json").write_text(
            json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        # Cambio único de directorio: el resultado se vuelve visible al terminar.
        os.replace(tmp_dir, salida)
    return resumen


def verificar_ingesta(salida: Path) -> dict[str, Any]:
    """Verifica bytes de fotos e inventario; revisiones humanas pueden editarse aparte."""
    salida = salida.resolve(strict=True)
    resumen = json.loads((salida / "control_ingesta.json").read_text(encoding="utf-8"))
    if resumen.get("version") != VERSION:
        raise ErrorCapturas("versión de control de ingesta desconocida")
    inventario = salida / "inventario_capturas.csv"
    if not inventario.is_file() or _huella_archivo(inventario) != resumen.get("inventario_sha256"):
        raise ErrorCapturas("inventario_capturas.csv fue alterado o no existe")
    lista = resumen.get("archivos")
    if not isinstance(lista, list) or len(lista) != resumen.get("cantidad_fotografias"):
        raise ErrorCapturas("cantidad de archivos inconsistente")
    with inventario.open("r", newline="", encoding="utf-8") as f:
        inventario_rows = list(csv.DictReader(f))
    if len(inventario_rows) != len(lista):
        raise ErrorCapturas("cantidad del inventario inconsistente")
    for fila, item in zip(inventario_rows, lista):
        ruta_texto = str(item.get("archivo") or "")
        sha = str(item.get("sha256") or "")
        if not _ruta_relativa_segura(ruta_texto) or not ruta_texto.startswith("originales/"):
            raise ErrorCapturas("ruta de original inválida en control")
        imagen = salida / ruta_texto
        if imagen.is_symlink() or not imagen.is_file() or not _en_directorio(imagen.resolve(), salida):
            raise ErrorCapturas("imagen ausente o con enlace no permitido")
        if fila["registro_id"] != item.get("registro_id") or fila["archivo_importado"] != ruta_texto or fila["sha256"] != sha:
            raise ErrorCapturas("registro del inventario no coincide con control")
        if _huella_archivo(imagen) != sha:
            raise ErrorCapturas(f"fotografía alterada: {ruta_texto}")
    return {
        "estado": "integridad_bytes_verificada",
        "fotografias": len(lista),
        "revision_humana": "no_acreditada_por_este_comando",
        "entrenamiento_autorizado": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="accion", required=True)
    plantilla = sub.add_parser("plantilla", help="genera CSV vacío para capturas propias")
    plantilla.add_argument("--csv", type=Path, required=True)
    for nombre in ("prevalidar", "importar"):
        p = sub.add_parser(nombre)
        p.add_argument("--csv", type=Path, required=True)
        p.add_argument("--entrada", type=Path, required=True)
        if nombre == "importar":
            p.add_argument("--salida", type=Path, required=True)
    verify = sub.add_parser("verificar", help="revalida copias contra SHA-256")
    verify.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.accion == "plantilla":
            if args.csv.exists():
                raise ErrorCapturas("el archivo CSV ya existe; no sobrescribir")
            args.csv.parent.mkdir(parents=True, exist_ok=True)
            _escribir_csv(args.csv, COLUMNAS_ENTRADA, [])
            resultado = {"estado": "plantilla_creada", "csv": str(args.csv)}
        elif args.accion == "prevalidar":
            registros, errores = validar_capturas(args.csv, args.entrada)
            resultado = {"estado": "validacion_correcta" if not errores else "errores_de_captura",
                         "fotografias_validas": len(registros), "errores": errores,
                         "revision_humana": "pendiente", "entrenamiento_autorizado": False}
        elif args.accion == "importar":
            resultado = ingresar_capturas(args.csv, args.entrada, args.salida)
        else:
            resultado = verificar_ingesta(args.salida)
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
        return 2 if resultado.get("errores") else 0
    except (ErrorCapturas, FileNotFoundError, NotADirectoryError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"estado": "error", "detalle": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
