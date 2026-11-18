#!/usr/bin/env python3
"""Fail-closed CI gate with an allowlisted, machine-readable report.

The summary and artifact contain only known job identifiers and safe state enums.
They never include credentials, scanner raw data, PR bodies or user-controlled paths.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

MODULES = ('backend', 'frontend', 'iot', 'vision', 'integracion', 'dast')
MANDATORY = ('preparacion', 'cambios', 'seguridad')
STATES = ('success', 'failure', 'skipped', 'cancelled')


def validate(flags: dict[str, str], results: dict[str, str]) -> list[str]:
    errors = []
    for name in MANDATORY:
        if results.get(name) != 'success':
            errors.append(f'{name}: obligatorio, resultado={results.get(name)!r}')
    for name in MODULES:
        flag = flags.get(name)
        result = results.get(name)
        if flag not in ('true', 'false'):
            errors.append(f'{name}: selección ausente o inválida: {flag!r}')
        elif flag == 'true' and result != 'success':
            errors.append(f'{name}: requerido, resultado={result!r}')
        elif flag == 'false' and result != 'skipped':
            errors.append(f'{name}: omisión prevista, resultado={result!r}')
    return errors


def _safe(value: str | None, options: tuple[str, ...]) -> str:
    """Never emit unchecked environment values into Markdown or artifacts."""
    return value if value in options else 'invalid'


def build_report(flags: dict[str, str], results: dict[str, str],
                 *, metadata: dict[str, str] | None = None) -> dict:
    metadata = metadata or {}
    rows = []
    for name in (*MANDATORY, *MODULES):
        result = _safe(results.get(name), STATES)
        if name in MANDATORY:
            selected = 'mandatory'
            expected = 'success'
        else:
            flag = _safe(flags.get(name), ('true', 'false'))
            selected = {'true': 'selected', 'false': 'not-selected'}.get(flag, 'invalid')
            expected = {'true': 'success', 'false': 'skipped'}.get(flag, 'invalid')
        compliant = expected != 'invalid' and result == expected
        rows.append({'component': name, 'selection': selected,
                     'expected': expected, 'result': result, 'compliant': compliant})

    # Context fields are explicitly constrained; never report an arbitrary env var.
    sha = metadata.get('sha', '')
    run_id = metadata.get('run_id', '')
    event = metadata.get('event', '')
    context = {
        'run_id': run_id if re.fullmatch(r'[0-9]{1,20}', run_id) else None,
        'sha': sha if re.fullmatch(r'[0-9a-fA-F]{40}', sha) else None,
        'event': event if event in ('push', 'pull_request', 'workflow_dispatch') else 'unknown',
    }
    violations = [
        f"{row['component']}: esperado={row['expected']}, observado={row['result']}"
        for row in rows if not row['compliant']
    ]
    return {
        'schema_version': 1,
        'scope': 'CI tests and gates; does not certify hardware, production or model accuracy',
        'context': context,
        'decision': 'rejected' if violations else 'approved',
        'counts': {
            'mandatory': len(MANDATORY),
            'selected_modules': sum(row['selection'] == 'selected' for row in rows),
            'expected_skips': sum(row['selection'] == 'not-selected' for row in rows),
            'noncompliant': len(violations),
        },
        'checks': rows,
        'violations': violations,
    }


def markdown(report: dict) -> str:
    lines = [
        '## AgroScan CI — informe consolidado (Etapa 06)', '',
        '**Decisión:** ' + report['decision'].upper(),
        '**Alcance:** controles automatizados del commit; no acredita hardware físico ni despliegue.', '',
        '| Componente | Selección | Esperado | Observado | Cumple |',
        '|---|---|---|---|---|',
    ]
    for row in report['checks']:
        lines.append(f"| {row['component']} | {row['selection']} | {row['expected']} | "
                     f"{row['result']} | {'sí' if row['compliant'] else 'no'} |")
    count = report['counts']
    lines += ['', f"**Módulos seleccionados:** {count['selected_modules']}. "
              f"**Omisiones justificadas:** {count['expected_skips']}. "
              f"**Incumplimientos:** {count['noncompliant']}."]
    if report['violations']:
        lines += ['', '**Condiciones incumplidas:**', *[f'- {item}' for item in report['violations']]]
    lines += ['', 'Los resultados individuales y reportes sanitizados de seguridad están en '
              'los jobs y artefactos de esta ejecución. Los módulos omitidos no se consideran ejecutados.']
    return '\n'.join(lines) + '\n'


def main() -> int:
    flags = {name: os.getenv(f'SELECT_{name.upper()}', '') for name in MODULES}
    results = {name: os.getenv(f'RESULT_{name.upper()}', '') for name in (*MANDATORY, *MODULES)}
    errors = validate(flags, results)
    report = build_report(flags, results, metadata={
        'run_id': os.getenv('GITHUB_RUN_ID', ''),
        'sha': os.getenv('GITHUB_SHA', ''),
        'event': os.getenv('GITHUB_EVENT_NAME', ''),
    })
    # Validate and report must agree; otherwise fail closed.
    if bool(errors) != (report['decision'] == 'rejected'):
        print('CI bloqueado: inconsistencia interna del validador.', file=sys.stderr)
        return 1
    try:
        artifact_path = os.getenv('CI_REPORT_PATH', '')
        if artifact_path:
            path = Path(artifact_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        summary_path = os.getenv('GITHUB_STEP_SUMMARY', '')
        if summary_path:
            with Path(summary_path).open('a', encoding='utf-8') as file:
                file.write(markdown(report))
    except (OSError, ValueError, TypeError) as exc:
        # A malformed/unwritable report must never leave a green final check.
        print(f'CI bloqueado: error al escribir el informe ({type(exc).__name__}).', file=sys.stderr)
        return 1
    for error in report['violations']:
        print('CI bloqueado: ' + error, file=sys.stderr)
    print('CI global: ' + report['decision'])
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
