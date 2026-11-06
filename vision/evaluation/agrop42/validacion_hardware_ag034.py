"""AG-034 / Incremento 13: preparación y auditoría de evidencia del hardware objetivo.

NO realiza ni certifica pruebas físicas. El hardware de visión es PC + FastAPI;
la balanza ESP32 es una integración distinta. No genera etiquetas E0/E1/E2.
Funciona con biblioteca estándar de Python (sin cámara ni puerto serial).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import ctypes
import hashlib
import json
import math
import os
import platform
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

VERSION = "ag034-validacion-hardware-v1"
FIELDS = (
    "prueba_id", "alcance", "estado", "equipo_id", "responsable",
    "fecha_iso", "evidencia_relativa", "criterio_predefinido",
    "limite_ms", "resultado_ms", "limite_mib", "resultado_mib", "observaciones",
)
# En AG-034 se evalúa el hardware que EJECUTA la visión, no el ESP32.
TESTS = (
    ("VIS-01", "obligatoria", "Ficha e identificación de la PC objetivo y sus recursos"),
    ("VIS-02", "obligatoria", "Benchmark de ambos métodos ejecutado en esa PC"),
    ("VIS-03", "obligatoria", "P95 de latencia y memoria RSS medidos frente a límites predefinidos"),
    ("VIS-04", "obligatoria", "Prueba real de cámara, asociación de captura y procesamiento"),
    ("IOT-01", "complementaria", "ESP32 real conectado y telemetría serial no simulada"),
    ("IOT-02", "complementaria", "Tara y calibración con referencia física documentada"),
    ("INT-01", "complementaria", "Recepción real por FastAPI con ACK y trazabilidad"),
)
_ALLOWED = {"pendiente", "aprobada", "fallida", "bloqueada", "no_aplica"}
_SHA = re.compile(r"[0-9a-f]{64}")


def _json_bytes(obj: object) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_new(path: Path, payload: bytes) -> None:
    with path.open("xb") as f:
        f.write(payload)


def _csv_bytes(rows: list[dict]) -> bytes:
    import io
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")


def plantilla(salida: Path) -> dict:
    salida = Path(salida).resolve()
    if salida.exists():
        raise FileExistsError(f"No se sobrescribe una carpeta existente: {salida}")
    salida.mkdir(parents=True, exist_ok=False)
    rows = []
    for test_id, scope, purpose in TESTS:
        rec = dict.fromkeys(FIELDS, "")
        rec.update(prueba_id=test_id, alcance=scope, estado="pendiente",
                   criterio_predefinido="", observaciones=purpose)
        rows.append(rec)
    _write_new(salida / "AG034_registro_pruebas.csv", _csv_bytes(rows))
    (salida / "evidencias").mkdir()
    _write_new(salida / "AG034_INSTRUCCIONES.txt", (
        "Paquete AG-034 para pruebas físicas. No confundir simulación con hardware.\n"
        "Rellenar AG034_registro_pruebas.csv: estado, equipo, responsable, fecha ISO\n"
        "con zona horaria, evidencia_relativa (p.ej. evidencias/pc01.txt),\n"
        "criterio_predefinido y observaciones. El criterio debe acordarse ANTES\n"
        "de medir. Para VIS-03: limite_ms, resultado_ms (P95, ms),\n"
        "limite_mib, resultado_mib (RSS máximo, MiB).\n"
        "Los controles IOT son complementarios a AG-034; no sustituyen E0/E1/E2.\n"
        "No cambiar prueba_id ni alcance. No inventar resultados.\n"
    ).encode("utf-8"))
    return {"estado": "plantilla_preparada_sin_pruebas_fisicas", "pruebas": len(rows), "salida": str(salida)}


def _iso_valid(value: str) -> bool:
    try:
        parsed = dt.datetime.fromisoformat(value.strip())
        return parsed.tzinfo is not None and parsed.utcoffset() is not None
    except (ValueError, TypeError, OverflowError):
        return False


def _evidence_file(folder: Path, raw: str) -> Path:
    if not raw or "\\" in raw or "\x00" in raw or ":" in raw or raw.startswith("/"):
        raise ValueError("Ruta de evidencia inválida; usar relativa POSIX")
    parts = raw.split("/")
    if len(parts) < 2 or parts[0] != "evidencias" or any(x in {"", ".", ".."} for x in parts):
        raise ValueError("La evidencia debe residir bajo evidencias/ sin traversal")
    path = (folder / raw).resolve()
    if not path.is_relative_to((folder / "evidencias").resolve()):
        raise ValueError("Ruta de evidencia fuera del directorio autorizado")
    if not path.is_file() or path.stat().st_size < 1 or path.stat().st_size > 25 * 1024 * 1024:
        raise ValueError("Archivo de evidencia inexistente, vacío o excesivo")
    return path


def _positive_float(value: str, label: str) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} debe ser un número positivo finito") from None
    if not math.isfinite(n) or n <= 0:
        raise ValueError(f"{label} debe ser un número positivo finito")
    return n


def _read_rows(folder: Path) -> list[dict]:
    path = folder / "AG034_registro_pruebas.csv"
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("CSV excede el tamaño admitido")
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("Columnas CSV faltantes, sobrantes o fuera de orden")
        rows = list(reader)
    if len(rows) != len(TESTS):
        raise ValueError("Cantidad de pruebas incorrecta")
    expected = [(x[0], x[1]) for x in TESTS]
    if [(x["prueba_id"], x["alcance"]) for x in rows] != expected:
        raise ValueError("IDs, alcances u orden de pruebas alterados")
    return rows


def auditar_registros(carpeta: Path) -> dict:
    carpeta = Path(carpeta).resolve()
    records = _read_rows(carpeta)
    errores = []
    evidence = {}
    states = {}
    for rec in records:
        test_id = rec["prueba_id"]
        state = rec["estado"].strip()
        states[test_id] = state
        if state not in _ALLOWED:
            errores.append(f"{test_id}: estado inválido")
            continue
        if state == "no_aplica" and rec["alcance"] == "obligatoria":
            errores.append(f"{test_id}: prueba obligatoria no puede ser 'no_aplica'")
        if state in {"aprobada", "fallida", "bloqueada", "no_aplica"}:
            for name in ("equipo_id", "responsable", "fecha_iso", "observaciones"):
                if not rec[name].strip():
                    errores.append(f"{test_id}: falta {name}")
            if rec["fecha_iso"] and not _iso_valid(rec["fecha_iso"]):
                errores.append(f"{test_id}: fecha sin zona horaria")
        if state in {"aprobada", "fallida"}:
            if not rec["criterio_predefinido"].strip():
                errores.append(f"{test_id}: falta criterio de aceptación acordado previamente")
            try:
                path = _evidence_file(carpeta, rec["evidencia_relativa"].strip())
                evidence[test_id] = {
                    "ruta": rec["evidencia_relativa"].strip(), "sha256": _hash(path),
                    "bytes": path.stat().st_size,
                }
            except (ValueError, OSError) as exc:
                errores.append(f"{test_id}: {exc}")
            if test_id == "VIS-03":
                try:
                    ms_lim = _positive_float(rec["limite_ms"], "limite_ms")
                    ms_obs = _positive_float(rec["resultado_ms"], "resultado_ms")
                    ram_lim = _positive_float(rec["limite_mib"], "limite_mib")
                    ram_obs = _positive_float(rec["resultado_mib"], "resultado_mib")
                    if state == "aprobada" and (ms_obs > ms_lim or ram_obs > ram_lim):
                        errores.append("VIS-03: resultado excede límite, no puede marcarse aprobada")
                    if state == "fallida" and ms_obs <= ms_lim and ram_obs <= ram_lim:
                        errores.append("VIS-03: las mediciones cumplen ambos límites, revisar estado fallida")
                except ValueError as exc:
                    errores.append(f"VIS-03: {exc}")
        else:
            if rec["resultado_ms"].strip() or rec["resultado_mib"].strip():
                errores.append(f"{test_id}: no adjuntar resultados medidos a estado {state}")
        if state == "pendiente" and (rec["evidencia_relativa"].strip() or rec["responsable"].strip()):
            errores.append(f"{test_id}: pendiente no acredita revisión ni evidencia")
    required = {x[0] for x in TESTS if x[1] == "obligatoria"}
    presented = (not errores and all(states.get(key) == "aprobada" for key in required))
    return {
        "version": VERSION, "actividad": "AG-034", "estado": (
            "registros_con_errores" if errores else
            "documentacion_fisica_presentada_sujeta_a_revision" if presented else
            "pruebas_fisicas_pendientes_o_no_conformes"
        ),
        "pruebas": states, "archivos_evidencia": evidence, "errores": errores,
        "hardware_pc_validado_independientemente": False,
        "pruebas_fisicas_declaradas_completas": presented,
        "etiquetas_e0_e1_e2_acreditadas": False,
        "cierre_total_AG034_acreditado": False,
        "advertencia": (
            "La declaración y hashes no autentican el origen físico de la evidencia. "
            "Se requiere revisión independiente; AG-034 no está cerrado por este informe."
        ),
    }


def auditar(carpeta: Path, salida: Path) -> dict:
    carpeta, salida = Path(carpeta).resolve(), Path(salida).resolve()
    if salida.exists() or salida == carpeta or salida.is_relative_to(carpeta):
        raise ValueError("La carpeta de salida debe ser nueva y estar fuera del directorio editable")
    result = auditar_registros(carpeta)
    if result["errores"]:
        raise ValueError("; ".join(result["errores"]))
    salida.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(carpeta / "AG034_registro_pruebas.csv", salida / "AG034_registro_pruebas_snapshot.csv")
    _write_new(salida / "AG034_auditoria_hardware.json", _json_bytes(result))
    lines = [
        "# AG-034 — Informe de validación de hardware (Incremento 13)", "",
        "**Estado:** " + result["estado"], "",
        "El hardware de visión es la PC local con FastAPI; ESP32 adquiere peso.",
        "La comparación disponible solo identifica mango/tomate, no valida defectos E0/E1/E2.", "",
        "| Caso | Alcance | Estado declarado | Evidencia SHA-256 |",
        "|---|---|---|---|",
    ]
    for test_id, scope, _ in TESTS:
        sha = result["archivos_evidencia"].get(test_id, {}).get("sha256", "—")
        lines.append(f"| {test_id} | {scope} | {result['pruebas'][test_id]} | {sha} |")
    lines.extend(["", "**Cierre total AG-034:** NO ACREDITADO.",
                  "La declaración no sustituye revisión independiente, etiquetas E0/E1/E2 ni aprobación docente.", ""])
    _write_new(salida / "AG034_informe_hardware.md", ("\n".join(lines)).encode("utf-8"))
    hashes = {name: _hash(salida / name) for name in (
        "AG034_registro_pruebas_snapshot.csv", "AG034_auditoria_hardware.json", "AG034_informe_hardware.md"
    )}
    _write_new(salida / "AG034_manifest_sha256.json", _json_bytes({"version": VERSION, "archivos": hashes}))
    return {"estado": result["estado"], "archivos": 4, "errores": 0,
            "cierre_total_AG034_acreditado": False, "salida": str(salida)}


def verificar(salida: Path, carpeta: Path | None = None) -> dict:
    salida = Path(salida).resolve()
    manifest = json.loads((salida / "AG034_manifest_sha256.json").read_text("utf-8"))
    names = {"AG034_registro_pruebas_snapshot.csv", "AG034_auditoria_hardware.json", "AG034_informe_hardware.md"}
    if manifest.get("version") != VERSION or set(manifest.get("archivos", {})) != names:
        raise ValueError("Manifiesto de integridad no corresponde a AG-034 Incremento 13")
    for name in names:
        declared = manifest["archivos"][name]
        if not isinstance(declared, str) or not _SHA.fullmatch(declared) or _hash(salida / name) != declared:
            raise ValueError("Integridad alterada: " + name)
    audit = json.loads((salida / "AG034_auditoria_hardware.json").read_text("utf-8"))
    if audit.get("cierre_total_AG034_acreditado") is not False:
        raise ValueError("Informe no puede acreditar cierre total")
    if carpeta is not None:
        carpeta = Path(carpeta).resolve()
        if _hash(carpeta / "AG034_registro_pruebas.csv") != _hash(salida / "AG034_registro_pruebas_snapshot.csv"):
            raise ValueError("El CSV editable cambió desde la auditoría")
        for record in audit.get("archivos_evidencia", {}).values():
            path = _evidence_file(carpeta, record["ruta"])
            if _hash(path) != record["sha256"]:
                raise ValueError("Archivo de evidencia alterado: " + record["ruta"])
    return {"estado": "integridad_documental_verificada", "archivos": 4,
            "evidencias_verificadas": len(audit.get("archivos_evidencia", {})) if carpeta else None,
            "hardware_pc_validado_independientemente": False,
            "cierre_total_AG034_acreditado": False}


def _ram_total_mib() -> int | None:
    """Memoria física declarada por el sistema, no consumo del pipeline."""
    if os.name == "nt":
        class MemStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        mem = MemStatus()
        mem.dwLength = ctypes.sizeof(MemStatus)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
                return round(mem.ullTotalPhys / (1024 ** 2))
        except (AttributeError, OSError):
            return None
    if hasattr(os, "sysconf"):
        try:
            return round(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / (1024 ** 2))
        except (OSError, ValueError, KeyError):
            pass
    return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def diagnosticar(api_url: str, salida: Path, perfil: Path | None = None) -> dict:
    """Consulta solo localhost; los resultados son de diagnóstico, NO prueba física."""
    parsed = urlsplit(api_url)
    if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.fragment or parsed.query
            or parsed.path != "/api/health"):
        raise ValueError("Solo se admite http://localhost:PUERTO/api/health")
    salida = Path(salida).resolve()
    if salida.exists():
        raise FileExistsError("No se sobrescribe diagnóstico existente")
    backend = {"consultado": True, "responde_ok": False}
    try:
        req = urllib.request.Request(api_url, method="GET")
        with urllib.request.build_opener(_NoRedirect()).open(req, timeout=2) as resp:
            body = resp.read(4096)
            backend["status_http"] = resp.status
            payload = json.loads(body)
            backend["responde_ok"] = (resp.status == 200 and isinstance(payload, dict)
                                      and payload.get("status") == "ok")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        backend["error_tipo"] = type(exc).__name__
    profile = None
    if perfil is not None:
        p = Path(perfil)
        if p.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Perfil de recursos demasiado grande")
        source = json.loads(p.read_text("utf-8"))
        if (source.get("tipo") != "benchmark_auxiliar_identificacion_mango_tomate_no_defectos"
                or source.get("decision", {}).get("cierre_total_AG034_acreditado") is not False):
            raise ValueError("Perfil experimental ajeno a AG-034")
        profile = {"sha256": _hash(p), "vistas": source.get("dataset", {}).get("vistas"),
                   "equipo_declarado": source.get("entorno", {}),
                   "tipo": source.get("tipo"), "es_medicion_de_defectos": False}
    result = {"version": VERSION, "estado": "diagnostico_software_no_validacion_fisica",
              "maquina_ejecutora": {
                  "sistema": platform.system(), "version": platform.release(),
                  "arquitectura": platform.machine(), "cpu_logicas": os.cpu_count(),
                  "procesador": platform.processor(), "python": platform.python_version(),
                  "ram_total_mib": _ram_total_mib(),
              }, "backend": backend, "perfil_auxiliar_existente": profile,
              "esp32_fisico_verificado": False, "camara_fisica_verificada": False,
              "hardware_pc_validado_independientemente": False,
              "cierre_total_AG034_acreditado": False}
    _write_new(salida, _json_bytes(result))
    return {"estado": result["estado"], "api_ok": backend["responde_ok"],
            "salida": str(salida), "cierre_total_AG034_acreditado": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AG-034: preparar pruebas físicas y consolidar evidencias")
    subs = parser.add_subparsers(dest="comando", required=True)
    p = subs.add_parser("plantilla"); p.add_argument("--salida", type=Path, required=True)
    p = subs.add_parser("diagnosticar")
    p.add_argument("--api-url", default="http://127.0.0.1:8000/api/health")
    p.add_argument("--perfil", type=Path); p.add_argument("--salida", type=Path, required=True)
    p = subs.add_parser("auditar"); p.add_argument("--carpeta", type=Path, required=True)
    p.add_argument("--salida", type=Path, required=True)
    p = subs.add_parser("verificar"); p.add_argument("--salida", type=Path, required=True)
    p.add_argument("--carpeta", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.comando == "plantilla":
            r = plantilla(args.salida)
        elif args.comando == "diagnosticar":
            r = diagnosticar(args.api_url, args.salida, args.perfil)
        elif args.comando == "auditar":
            r = auditar(args.carpeta, args.salida)
        else:
            r = verificar(args.salida, args.carpeta)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"estado": "error", "detalle": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
