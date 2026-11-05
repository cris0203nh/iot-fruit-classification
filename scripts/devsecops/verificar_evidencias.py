#!/usr/bin/env python3
"""Verifica snapshots de escaneos CI sanitizados y reproduce las métricas finales.

No necesita red. No ejecuta ningún escáner y no pretende demostrar el estado de
un despliegue futuro; los snapshots pertenecen a commits y runs explícitos.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "docs" / "devsecops" / "evidencias"
SCANNERS = ("bandit.json", "npm.json", "pip-backend.json", "pip-firmware.json",
            "gitleaks-history.json", "gitleaks-new.json")


def _integer(value):
    if type(value) is not int or value < 0:
        raise ValueError("El conteo debe ser un entero no negativo")
    return value


def load_verified(root: Path):
    """Comprueba integridad SHA-256 de todos los snapshots congelados."""
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), dict):
        raise ValueError("Manifiesto sin contrato de versión válido")
    expected = {
        f"{group}/{f}" for group in ("baseline", "post02", "post04")
        for f in SCANNERS
    } | {"dast03/zap.json", "dast04/zap.json"}
    if set(manifest["files"]) != expected:
        raise ValueError("El manifiesto debe incluir los 20 reportes previstos")
    parsed = {}
    for rel, meta in manifest["files"].items():
        if not isinstance(meta, dict) or not isinstance(meta.get("sha256"), str):
            raise ValueError("Entrada inválida del manifiesto")
        path = root / rel
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != meta["sha256"]:
            raise ValueError(f"Evidencia modificada: {rel}")
        data = json.loads(content)
        if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
            raise ValueError(f"Reporte incompleto: {rel}")
        if _integer(data.get("finding_count")) != len(data["findings"]):
            raise ValueError(f"Conteo inconsistente: {rel}")
        parsed[rel] = data
    return parsed


def _counts(scans, group):
    def n(file):
        return scans[f"{group}/{file}"], scans[f"{group}/{file}"]["finding_count"]
    b, bn = n("bandit.json")
    z, zn = n("npm.json")
    p, pn = n("pip-backend.json")
    f, fn = n("pip-firmware.json")
    h, hn = n("gitleaks-history.json")
    new, nn = n("gitleaks-new.json")
    tools = (b, z, p, f, h, new)
    expected_names = ("bandit", "npm-audit", "pip-audit", "pip-audit", "gitleaks", "gitleaks")
    if tuple(x.get("tool") for x in tools) != expected_names:
        raise ValueError("Herramientas no coinciden con los artefactos")
    return {
        "bandit": bn, "npm": zn, "pip_backend": pn, "pip_firmware": fn,
        "gitleaks_history": hn, "gitleaks_new": nn,
        "total": sum((bn, zn, pn, fn, hn, nn)),
    }


def calculate(root: Path = ROOT):
    reports = load_verified(root)
    before = _counts(reports, "baseline")
    post02 = _counts(reports, "post02")
    post04 = _counts(reports, "post04")
    dast = {}
    for group in ("dast03", "dast04"):
        report = reports[group + "/zap.json"]
        if report.get("tool") != "zap-api-passive":
            raise ValueError("El informe DAST no es un escaneo ZAP pasivo")
        if not isinstance(report.get("by_severity"), dict):
            raise ValueError("ZAP sin desglose de severidad")
        if sum(_integer(v) for v in report["by_severity"].values()) != report["finding_count"]:
            raise ValueError("ZAP: severidades inconsistentes")
        if any(_integer(f.get("occurrences")) < 1 for f in report["findings"]):
            raise ValueError("ZAP: ocurrencias inválidas")
        dast[group] = {
            "rules": report["finding_count"],
            "by_severity": report["by_severity"],
            "occurrences": sum(x["occurrences"] for x in report["findings"]),
            "rule_ids": [x["rule_id"] for x in report["findings"]],
        }
    return {
        "version": 1,
        "scope": "snapshots sanitizados por commit, no pentest de producción",
        "baseline": before,
        "after_increment02": post02,
        "after_increment04": post04,
        "total_records_reduced": before["total"] - post04["total"],
        "reduction_percent": round(100 * (before["total"] - post04["total"]) / before["total"], 1),
        "dast_before_http": dast["dast03"],
        "dast_after_http": dast["dast04"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=None,
                        help="Archivo JSON opcional; no se imprime ningún secreto")
    args = parser.parse_args(argv)
    try:
        summary = calculate(args.evidence_root)
    except (ValueError, OSError, TypeError, json.JSONDecodeError, ZeroDivisionError) as error:
        print(f"Evidencia inválida: {error}", file=sys.stderr)
        return 2
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Evidencias verificadas por SHA-256: 20 snapshots.")
    print(f"SAST/SCA/secretos: {summary['baseline']['total']} -> {summary['after_increment04']['total']} "
          f"({summary['reduction_percent']}% menos registros).")
    print(f"DAST pasivo: {summary['dast_before_http']['rules']} -> {summary['dast_after_http']['rules']} "
          "reglas; los hallazgos requieren revisión contextual.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
