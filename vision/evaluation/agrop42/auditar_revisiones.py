"""AGROP-42: puerta de entrada documental a una comparación experimental.

No clasifica imágenes ni crea etiquetas. Distingue aprobación de notas de
validación trazable de datos por pieza y sesión.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path, PureWindowsPath, PurePosixPath

FRUTAS = ("mango", "tomate")
ETIQUETAS = {"E0", "E1", "E2"}
ESTADOS = {"pendiente", "revisada", "no_evaluable"}
COLUMNAS = {
    "registro_id", "producto", "sha256", "archivo", "estado_revision",
    "etiqueta_visual", "revisor_id", "revisado_en", "rubrica_version",
    "calidad_confirmada", "cobertura_confirmada", "pieza_confirmada",
    "sesion_confirmada", "lote_id", "pieza_id", "sesion_id",
    "dispositivo_id", "evidencia_pieza", "evidencia_sesion",
    "justificacion_etiqueta", "nota_revision",
}


def _si(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"si", "sí", "true", "1", "yes"}


def _texto(fila: dict, campo: str) -> str:
    return str(fila.get(campo) or "").strip()


def _fecha_valida(value: str) -> bool:
    if not value:
        return False
    try:
        # Acepta ISO 8601 con fecha; no inventa horas de anotación.
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _ruta_segura(value: str) -> bool:
    """Evita rutas absolutas y traversal en Windows y POSIX, en ambos hosts."""
    if not value or "\\" in value or ":" in value:
        # No admitir separadores Windows en manifiestos de rutas POSIX.
        return False
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    return (not posix.is_absolute() and not windows.is_absolute()
            and not windows.drive and ".." not in posix.parts
            and posix.parts and posix.parts[0] not in ("", "."))


def _conflictos_por_pieza(filas: list[dict]) -> list[str]:
    """No adjudicar dos clases de calidad a una pieza sin resolver discrepancia.

    Una sesión puede contener varias piezas y clases; solo se agrupa aquí por
    producto/lote/pieza. Se contabilizan exclusivamente etiquetas acreditables.
    """
    por_pieza: dict[tuple[str, str], set[str]] = defaultdict(set)
    for fila in filas:
        if not _fila_elegible(fila):
            continue
        llave = (_texto(fila, "lote_id"), _texto(fila, "pieza_id"))
        por_pieza[llave].add(_texto(fila, "etiqueta_visual"))
    return [f"etiquetas_contradictorias_pieza: lote={lote!r} pieza={pieza!r}"
            for (lote, pieza), etiquetas in sorted(por_pieza.items())
            if len(etiquetas) > 1]


def _fila_elegible(fila: dict) -> bool:
    """Una descripción revisada NO basta para una etiqueta E0/E1/E2."""
    return (
        _texto(fila, "estado_revision") == "revisada"
        and _texto(fila, "etiqueta_visual") in ETIQUETAS
        and all(_si(fila.get(c)) for c in (
            "calidad_confirmada", "cobertura_confirmada",
            "pieza_confirmada", "sesion_confirmada"))
        and all(_texto(fila, c) for c in (
            "registro_id", "sha256", "revisor_id", "rubrica_version",
            "lote_id", "pieza_id", "sesion_id", "dispositivo_id",
            "evidencia_pieza", "evidencia_sesion", "justificacion_etiqueta"))
        and _fecha_valida(_texto(fila, "revisado_en"))
    )


def asignar_grupos(filas: list[dict]) -> dict[str, str]:
    """Grupo indivisible por pieza o sesión; entrada de un único producto."""
    if not filas:
        return {}
    padres = list(range(len(filas)))

    def find(i: int) -> int:
        while padres[i] != i:
            padres[i] = padres[padres[i]]
            i = padres[i]
        return i

    def union(i: int, j: int) -> None:
        padres[find(i)] = find(j)

    vistos: dict[tuple[str, str], int] = {}
    for i, fila in enumerate(filas):
        for campo in ("pieza_id", "sesion_id"):
            llave = (campo, _texto(fila, campo))
            if llave in vistos:
                union(i, vistos[llave])
            else:
                vistos[llave] = i
    raices = sorted({find(i) for i in range(len(filas))})
    nombres = {raiz: f"grupo_{n:05d}" for n, raiz in enumerate(raices, 1)}
    return {_texto(fila, "registro_id"): nombres[find(i)] for i, fila in enumerate(filas)}


def _grupos_independientes(filas: list[dict]) -> int:
    return len(set(asignar_grupos(filas).values()))


def auditar_csv(ruta: str | Path) -> dict:
    ruta = Path(ruta)
    with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        faltantes = sorted(COLUMNAS - set(lector.fieldnames or []))
        if faltantes:
            raise ValueError("Columnas obligatorias faltantes: " + ", ".join(faltantes))
        filas = list(lector)

    errores = []
    ids: set[str] = set()
    shas: set[str] = set()
    por_producto = defaultdict(list)
    for n, fila in enumerate(filas, 2):
        rid = _texto(fila, "registro_id")
        sha = _texto(fila, "sha256")
        producto = _texto(fila, "producto").lower()
        estado = _texto(fila, "estado_revision")
        etiqueta = _texto(fila, "etiqueta_visual")
        ruta_archivo = _texto(fila, "archivo")
        if not rid or rid in ids:
            errores.append(f"fila {n}: registro_id vacío o repetido")
        ids.add(rid)
        sha_norm = sha.lower()
        if len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha_norm) or sha_norm in shas:
            errores.append(f"fila {n}: SHA256 inválido o repetido")
        shas.add(sha_norm)
        if producto not in FRUTAS:
            errores.append(f"fila {n}: producto no admitido: {producto!r}")
            continue
        if estado not in ESTADOS:
            errores.append(f"fila {n}: estado_revision no admitido: {estado!r}")
        if etiqueta and etiqueta not in ETIQUETAS:
            errores.append(f"fila {n}: etiqueta_visual no admitida: {etiqueta!r}")
        if not _ruta_segura(ruta_archivo):
            errores.append(f"fila {n}: ruta relativa insegura")
        if None in fila:
            errores.append(f"fila {n}: columnas extra respecto al encabezado")
        if estado in ("pendiente", "no_evaluable") and etiqueta:
            errores.append(f"fila {n}: etiqueta no autorizada en estado {estado}")
        por_producto[producto].append(fila)

    for producto in FRUTAS:
        errores.extend(f"{producto}: {conflicto}"
                       for conflicto in _conflictos_por_pieza(por_producto[producto]))

    informe = {"version": "agrop42-gate-v1", "origen_csv": str(ruta),
               "cantidad_registros": len(filas), "errores_integridad": errores, "productos": {}}
    for producto in FRUTAS:
        grupo = por_producto[producto]
        admitidas = [fila for fila in grupo if _fila_elegible(fila)]
        clases = Counter(_texto(fila, "etiqueta_visual") for fila in admitidas)
        n_grupos = _grupos_independientes(admitidas)
        motivos = []
        if not grupo:
            motivos.append("sin_fotografias")
        if n_grupos < 3:
            motivos.append("menos_de_tres_grupos_independientes")
        if len(clases) < 2:
            motivos.append("menos_de_dos_clases_con_etiquetas_revisadas_y_sesion")
        if errores:
            motivos.append("errores_integridad_del_archivo")
        informe["productos"][producto] = {
            "fotografias": len(grupo),
            "notas_revisadas": sum(_texto(f, "estado_revision") == "revisada" for f in grupo),
            "no_evaluables": sum(_texto(f, "estado_revision") == "no_evaluable" for f in grupo),
            "etiquetas_elegibles": len(admitidas),
            "grupos_independientes": n_grupos,
            "clases_elegibles": dict(sorted(clases.items())),
            "estado": "apto_para_diseno_experimental" if not motivos else "bloqueado_por_datos_insuficientes",
            "motivos": motivos,
        }
    informe["estado_global"] = (
        "apto_para_diseno_experimental" if all(
            p["estado"] == "apto_para_diseno_experimental"
            for p in informe["productos"].values()) else "bloqueado_por_datos_insuficientes"
    )
    # Apto para diseño no equivale a métricas válidas o entrenamiento realizado.
    informe["evaluacion_ejecutada"] = False
    informe["metricas_estimadas"] = None
    return informe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path, help="CSV de anotaciones de AGROP-42")
    parser.add_argument("--output", required=True, type=Path, help="Informe JSON de auditoría")
    args = parser.parse_args()
    informe = auditar_csv(args.csv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"estado": informe["estado_global"], "productos": informe["productos"]},
                     ensure_ascii=False, indent=2))
    return 0 if not informe["errores_integridad"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
