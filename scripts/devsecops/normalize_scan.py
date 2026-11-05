#!/usr/bin/env python3
"""Normalize security scanner reports without publishing raw secrets.

Some scanners use exit status 1 for findings rather than operational failure.
The workflow gates findings by severity or count for Bandit, Python SCA,
frontend SCA and new secrets; historical secrets remain observational.
Unexpected scanner exits and malformed reports always fail closed.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _is_object(value: Any) -> bool:
    return isinstance(value, dict)


def normalize(tool: str, report: Any) -> dict[str, Any]:
    """Allowlist report attributes; especially never copy Gitleaks Match/Secret."""
    findings: list[dict[str, Any]] = []
    by_severity: dict[str, int] = {}

    if tool == "bandit":
        if not _is_object(report) or not isinstance(report.get("results"), list):
            raise ValueError("Bandit: falta results[]")
        for item in report["results"]:
            if not _is_object(item):
                raise ValueError("Bandit: resultado inválido")
            severity = str(item.get("issue_severity", "UNKNOWN")).upper()
            findings.append({
                "rule": str(item.get("test_id", "")),
                "file": str(item.get("filename", "")),
                "line": item.get("line_number"),
                "severity": severity,
                "confidence": str(item.get("issue_confidence", "UNKNOWN")).upper(),
            })
            by_severity[severity] = by_severity.get(severity, 0) + 1

    elif tool == "pip-audit":
        if not _is_object(report) or not isinstance(report.get("dependencies"), list):
            raise ValueError("pip-audit: falta dependencies[]")
        for dependency in report["dependencies"]:
            if not _is_object(dependency) or not isinstance(dependency.get("vulns"), list):
                raise ValueError("pip-audit: dependencia inválida")
            for vuln in dependency["vulns"]:
                if not _is_object(vuln):
                    raise ValueError("pip-audit: vulnerabilidad inválida")
                findings.append({
                    "package": str(dependency.get("name", "")),
                    "version": str(dependency.get("version", "")),
                    "id": str(vuln.get("id", "")),
                    "fix_versions": [str(v) for v in vuln.get("fix_versions", [])],
                })
        # pip-audit JSON doesn't include a uniform CVSS severity: don't infer one.

    elif tool == "npm-audit":
        if not _is_object(report) or not isinstance(report.get("vulnerabilities"), dict):
            raise ValueError("npm audit: faltan vulnerabilities{} (posible error de registro)")
        if "error" in report:
            raise ValueError("npm audit: error de registro")
        for package, details in report["vulnerabilities"].items():
            if not _is_object(details):
                raise ValueError("npm audit: detalles inválidos")
            severity = str(details.get("severity", "unknown")).upper()
            ids = []
            for via in details.get("via", []):
                if _is_object(via):
                    ids.append(str(via.get("source", via.get("name", ""))))
            findings.append({
                "package": str(package),
                "severity": severity,
                "direct": bool(details.get("isDirect", False)),
                "advisory_ids": ids,
                "fix_available": bool(details.get("fixAvailable", False)),
            })
            by_severity[severity] = by_severity.get(severity, 0) + 1
        # npm reports package entries, not a unique CVE count.

    elif tool == "gitleaks":
        if not isinstance(report, list):
            raise ValueError("Gitleaks: se esperaba un arreglo JSON")
        for leak in report:
            if not _is_object(leak):
                raise ValueError("Gitleaks: resultado inválido")
            findings.append({
                "rule": str(leak.get("RuleID", "")),
                "file": str(leak.get("File", "")),
                "line": leak.get("StartLine"),
                "commit": str(leak.get("Commit", "")),
                "fingerprint": str(leak.get("Fingerprint", "")),
            })
        # Never include Secret, Match, author email or other raw scanner fields.

    else:
        raise ValueError(f"Herramienta desconocida: {tool}")

    return {"tool": tool, "finding_count": len(findings), "by_severity": by_severity, "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", required=True, choices=("bandit", "pip-audit", "npm-audit", "gitleaks"))
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--fail-findings", action="store_true")
    parser.add_argument("--fail-severity", choices=("MEDIUM", "HIGH", "CRITICAL"))
    args = parser.parse_args()

    if args.exit_code not in (0, 1):
        # A failed tool may leave partial reports behind, which must not be uploaded.
        args.input.unlink(missing_ok=True)
        print(f"Error operativo de {args.tool}: código {args.exit_code}", file=sys.stderr)
        return 2

    try:
        # Gitleaks may not create a report when there are zero findings.
        if args.tool == "gitleaks" and args.exit_code == 0 and not args.input.exists():
            raw = []
        else:
            raw = json.loads(args.input.read_text(encoding="utf-8"))
        if args.tool == "gitleaks" and raw is None and args.exit_code == 0:
            raw = []  # Some releases serialize an empty results list as null.
        result = normalize(args.tool, raw)
        if args.exit_code == 0 and result["finding_count"]:
            raise ValueError("El escáner reportó éxito, pero el JSON contiene hallazgos")
        if args.exit_code == 1 and result["finding_count"] == 0:
            raise ValueError("El escáner falló, pero el JSON no explica los hallazgos")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError) as exc:
        print(f"No fue posible validar/sanitizar el reporte de {args.tool}: {exc}", file=sys.stderr)
        return 2
    finally:
        # Raw reports may contain secrets: never save them as CI artifacts.
        args.input.unlink(missing_ok=True)

    print(f"{args.tool}: {result['finding_count']} hallazgos normalizados; modo={'gate' if (args.fail_findings or args.fail_severity) else 'baseline'}. ")
    if args.fail_findings and result["finding_count"]:
        print(f"Se bloquea por {result['finding_count']} hallazgo(s) de {args.tool}.", file=sys.stderr)
        return 1
    if args.fail_severity:
        rank = {"LOW": 1, "MEDIUM": 2, "MODERATE": 2, "HIGH": 3, "CRITICAL": 4}
        selected = rank[args.fail_severity]
        blocking = [item for item in result["findings"]
                    if rank.get(item.get("severity", ""), 0) >= selected]
        if blocking:
            print(f"Se bloquea por {len(blocking)} hallazgo(s) de severidad {args.fail_severity} o superior.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
