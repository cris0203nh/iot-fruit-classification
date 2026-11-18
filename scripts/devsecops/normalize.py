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
from datetime import date, datetime, timezone
from pathlib import Path

RANK = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "MODERATE": 2, "HIGH": 3, "CRITICAL": 4}
NPM_EXCEPTION = 'GHSA-fc5q-39xc-vjpf'
NPM_EXCEPTION_EXPIRES = date(2026, 12, 1)


def except_npm_dev(report: dict, raw: dict, lock: dict, *, today: date | None = None) -> None:
    """Excepción única: todas las causas deben terminar en picomatch dev 4.0.7.

    Un ciclo, referencia ausente, nodo productivo o advisory diferente conserva
    el bloqueo. No elimina hallazgos ni cambia sus severidades.
    """
    packages = _items(_items(lock, 'lockfile', dict).get('packages'), 'lock packages', dict)
    if lock.get('lockfileVersion') != 3:
        raise ValueError('Excepción npm requiere lockfile v3')
    active = (today or datetime.now(timezone.utc).date()) < NPM_EXCEPTION_EXPIRES
    vulnerabilities = raw['vulnerabilities']

    def eligible(name, visiting):
        if name in visiting or name not in vulnerabilities:
            return False
        item = vulnerabilities[name]
        if item.get('name') != name or item.get('severity') != 'high':
            return False
        nodes = item.get('nodes')
        instances = {path: dep for path, dep in packages.items()
                     if path.endswith('/node_modules/' + name) or path == 'node_modules/' + name}
        for dep in instances.values():
            _items(dep, 'lock package', dict)
        if (not isinstance(nodes, list) or not nodes or not instances
                or any(node not in instances for node in nodes)
                or any(dep.get('dev') is not True for dep in instances.values())):
            return False
        via = item.get('via')
        if not isinstance(via, list) or not via:
            return False
        for cause in via:
            if isinstance(cause, str):
                if not eligible(cause, visiting | {name}):
                    return False
            elif isinstance(cause, dict):
                if (name != 'picomatch' or cause.get('name') != name
                        or cause.get('dependency') != name or cause.get('severity') != 'high'
                        or cause.get('url') != 'https://github.com/advisories/' + NPM_EXCEPTION
                        or any(dep.get('version') != '4.0.7' for dep in instances.values())):
                    return False
            else:
                return False
        return True

    count = 0
    for finding in report['findings']:
        if active and eligible(finding['package'], set()):
            finding['exception'] = NPM_EXCEPTION
            count += 1
    report['exception'] = {'id': NPM_EXCEPTION, 'cve': 'CVE-2026-112366',
                           'expires_utc': NPM_EXCEPTION_EXPIRES.isoformat(),
                           'active': active, 'excepted_count': count}


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
    policy = report.get('exception', {})
    exception_active = (report.get('tool') == 'npm-audit' and policy.get('id') == NPM_EXCEPTION
                        and policy.get('active') is True
                        and policy.get('expires_utc') == NPM_EXCEPTION_EXPIRES.isoformat())
    findings = [f for f in report['findings']
                if not (exception_active and f.get('exception') == NPM_EXCEPTION)]
    if gate == 'ANY':
        return 1 if findings else 0
    return 1 if any(RANK.get(f.get('severity', ''), -1) >= RANK[gate]
                    for f in findings) else 0


def run(*, tool: str, source: Path, output: Path, exit_code: int, gate: str,
        npm_dev_exception_lock: Path | None = None) -> int:
    try:
        if npm_dev_exception_lock is not None and tool != 'npm-audit':
            raise ValueError('Excepción exclusiva de npm')
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
        if npm_dev_exception_lock is not None:
            except_npm_dev(report, raw, json.loads(npm_dev_exception_lock.read_text(encoding='utf-8')))
            print(f"npm audit: {report['exception']['excepted_count']} hallazgos exceptuados "
                  f"por {NPM_EXCEPTION}; vence {NPM_EXCEPTION_EXPIRES} UTC.")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return evaluate(report, gate)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        output.unlink(missing_ok=True)
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
    parser.add_argument('--npm-dev-exception-lock', type=Path,
                        help='Validar excepción temporal picomatch solo en auditoría npm completa')
    a = parser.parse_args()
    code = run(tool=a.tool, source=a.input, output=a.output, exit_code=a.exit_code, gate=a.gate,
               npm_dev_exception_lock=a.npm_dev_exception_lock)
    if code:
        print(f'{a.tool}: control de seguridad no aprobado (código {code}).', file=sys.stderr)
    else:
        print(f'{a.tool}: control de seguridad aprobado.')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
