#!/usr/bin/env python3
"""Normalización de reportes de scanners: solo campos permitidos; errores cerrados.

Elimina JSON crudo incluso ante error. Nunca copia valores secretos, cuerpos HTTP,
URLs completas, tokens ni cookies de reportes originales a artefactos de CI.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RANK = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "MODERATE": 2, "HIGH": 3, "CRITICAL": 4}


def _items(value, key, kind):
    if not isinstance(value, kind):
        raise ValueError(f"Informe inválido: {key}")
    return value


def normalize(tool: str, raw: object) -> dict:
    findings: list[dict] = []
    if tool == "bandit":
        for item in _items(_items(raw, 'bandit', dict).get('results'), 'results', list):
            _items(item, 'hallazgo', dict)
            severity = str(item.get('issue_severity', '')).upper()
            if severity not in RANK:
                raise ValueError('Bandit: severidad desconocida')
            findings.append({'severity': severity, 'rule': str(item.get('test_id', '')),
                             'file': str(item.get('filename', '')), 'line': item.get('line_number')})
    elif tool == 'pip-audit':
        for dep in _items(_items(raw, 'pip-audit', dict).get('dependencies'), 'dependencies', list):
            _items(dep, 'dependencia', dict)
            for vuln in _items(dep.get('vulns'), 'vulns', list):
                _items(vuln, 'advisory', dict)
                findings.append({'package': str(dep.get('name', '')),
                                 'version': str(dep.get('version', '')),
                                 'id': str(vuln.get('id', ''))})
    elif tool == 'npm-audit':
        report = _items(raw, 'npm-audit', dict)
        if 'error' in report:
            raise ValueError('npm audit: error operacional del registro')
        for name, item in _items(report.get('vulnerabilities'), 'vulnerabilities', dict).items():
            _items(item, 'paquete', dict)
            severity = str(item.get('severity', '')).upper()
            if severity not in RANK:
                raise ValueError('npm audit: severidad desconocida')
            findings.append({'package': str(name), 'severity': severity,
                             'direct': bool(item.get('isDirect', False))})
    elif tool == 'gitleaks':
        for item in _items(raw, 'gitleaks', list):
            _items(item, 'secreto', dict)
            # Nunca copiar Match/Secret ni correo del autor.
            findings.append({'rule': str(item.get('RuleID', '')),
                             'file': str(item.get('File', '')),
                             'line': item.get('StartLine')})
    elif tool == 'zap':
        report = _items(raw, 'zap', dict)
        sites = _items(report.get('site'), 'site', list)
        if not sites:
            raise ValueError('ZAP no analizó ningún sitio')
        for site in sites:
            _items(site, 'sitio', dict)
            for alert in _items(site.get('alerts'), 'alerts', list):
                _items(alert, 'alerta', dict)
                rule = str(alert.get('pluginid', ''))
                if not re.fullmatch(r'[0-9]{1,8}', rule):
                    raise ValueError('ZAP: regla sin identificador válido')
                try:
                    risk = int(alert['riskcode'])
                    count = int(alert.get('count', 1))
                except (KeyError, ValueError, TypeError) as exc:
                    raise ValueError('ZAP: riesgo/cantidad inválido') from exc
                if risk not in (0, 1, 2, 3, 4) or count <= 0:
                    raise ValueError('ZAP: riesgo/cantidad fuera de rango')
                findings.append({'rule': rule, 'severity': ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')[risk],
                                 'occurrences': count})
    else:
        raise ValueError('Escáner no soportado')
    by_severity: dict[str, int] = {}
    for item in findings:
        severity = item.get('severity', 'UNCLASSIFIED')
        by_severity[severity] = by_severity.get(severity, 0) + 1
    return {'tool': tool, 'finding_count': len(findings),
            'by_severity': by_severity, 'findings': findings}


def evaluate(report: dict, gate: str) -> int:
    if gate == 'ANY':
        return 1 if report['finding_count'] else 0
    return 1 if any(RANK.get(f.get('severity', ''), -1) >= RANK[gate]
                    for f in report['findings']) else 0


def run(*, tool: str, source: Path, output: Path, exit_code: int, gate: str) -> int:
    try:
        allowed = (0, 1, 2) if tool == 'zap' else (0, 1)
        if exit_code not in allowed:
            raise ValueError('Escáner no completó su ejecución')
        if tool == 'gitleaks' and exit_code == 0 and not source.exists():
            raw = []
        else:
            raw = json.loads(source.read_text(encoding='utf-8'))
        if tool == 'gitleaks' and raw is None and exit_code == 0:
            raw = []
        report = normalize(tool, raw)
        if tool != 'zap' and exit_code == 0 and report['finding_count']:
            raise ValueError('Resultado contradictorio: exit 0 con hallazgos')
        if tool != 'zap' and exit_code == 1 and not report['finding_count']:
            raise ValueError('Resultado contradictorio: exit 1 sin hallazgos')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return evaluate(report, gate)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'{tool}: escaneo o informe inválido: {type(exc).__name__}', file=sys.stderr)
        return 2
    finally:
        source.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tool', required=True, choices=('bandit','pip-audit','npm-audit','gitleaks','zap'))
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--exit-code', required=True, type=int)
    parser.add_argument('--gate', required=True, choices=('ANY','MEDIUM','HIGH','CRITICAL'))
    a = parser.parse_args()
    code = run(tool=a.tool, source=a.input, output=a.output, exit_code=a.exit_code, gate=a.gate)
    if code:
        print(f'{a.tool}: control de seguridad no aprobado (código {code}).', file=sys.stderr)
    else:
        print(f'{a.tool}: control de seguridad aprobado.')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
