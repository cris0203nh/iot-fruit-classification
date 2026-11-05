#!/usr/bin/env python3
"""Sanitiza el reporte JSON tradicional de OWASP ZAP, sin publicar URLs ni datos.

El reporte original puede contener rutas, parametros, peticiones y respuestas.
Por eso se elimina incluso si hay errores del escaner o del parser.
"""

import argparse
import json
import re
import sys
from pathlib import Path

RISKS = {0: "INFO", 1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}
RANK = {name: n for n, name in RISKS.items()}


def normalize(report: object) -> dict:
    """Exporta solo identificador de regla, severidad y cantidad agregada."""
    if not isinstance(report, dict) or not isinstance(report.get("site"), list):
        raise ValueError("ZAP: falta site[]")
    if not report["site"]:
        raise ValueError("ZAP: sin sitios analizados")

    aggregate: dict[tuple[str, str], int] = {}
    for site in report["site"]:
        if not isinstance(site, dict) or not isinstance(site.get("alerts"), list):
            raise ValueError("ZAP: sitio sin alerts[]")
        for alert in site["alerts"]:
            if not isinstance(alert, dict):
                raise ValueError("ZAP: alerta inválida")
            rule = str(alert.get("pluginid", ""))
            if not re.fullmatch(r"[0-9]{1,8}", rule):
                raise ValueError("ZAP: identificador de regla inválido")
            try:
                risk = int(alert["riskcode"])
            except (TypeError, ValueError, KeyError) as exc:
                raise ValueError("ZAP: riesgo inválido") from exc
            if risk not in RISKS:
                raise ValueError("ZAP: riesgo desconocido")
            try:
                instances = int(alert.get("count", 1))
            except (TypeError, ValueError) as exc:
                raise ValueError("ZAP: cantidad inválida") from exc
            if instances <= 0:
                raise ValueError("ZAP: cantidad inválida")
            key = (rule, RISKS[risk])
            aggregate[key] = aggregate.get(key, 0) + instances

    findings = [
        {"rule_id": rule, "severity": severity, "occurrences": count}
        for (rule, severity), count in sorted(aggregate.items())
    ]
    by_severity = {severity: sum(x["severity"] == severity for x in findings)
                   for severity in RISKS.values()}
    return {
        "tool": "zap-api-passive",
        "scan_mode": "openapi-safe-no-active-scan",
        "finding_count": len(findings),
        "by_severity": by_severity,
        "findings": findings,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--fail-severity", choices=("MEDIUM", "HIGH", "CRITICAL"), default="HIGH")
    args = parser.parse_args(argv)

    try:
        # ZAP distingue 0 (sin alertas bloqueantes), 1 (FAIL),
        # 2 (WARN) y 3 (error operacional). Cualquier otro código es error.
        if args.exit_code not in (0, 1, 2):
            raise ValueError(f"ZAP: error operativo, salida {args.exit_code}")
        result = normalize(json.loads(args.input.read_text(encoding="utf-8")))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (OSError, TypeError, ValueError) as exc:
        print(f"No se pudo validar el reporte DAST: {exc}", file=sys.stderr)
        return 2
    finally:
        # No subimos informes crudos de ZAP: pueden incluir valores sensibles.
        args.input.unlink(missing_ok=True)

    blocking = [f for f in result["findings"]
                if RANK[f["severity"]] >= RANK[args.fail_severity]]
    print(f"DAST: {result['finding_count']} reglas alertadas; "
          f"{len(blocking)} de severidad {args.fail_severity} o superior.")
    if blocking:
        print("DAST bloqueado por alertas de severidad alta/crítica.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
