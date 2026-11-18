#!/usr/bin/env python3
"""Fail-closed aggregation of required CI jobs and explicitly skipped jobs."""
from __future__ import annotations

import os
import sys
from pathlib import Path

MODULES = ('backend', 'frontend', 'iot', 'vision', 'integracion', 'dast')
MANDATORY = ('preparacion', 'cambios', 'seguridad')


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


def main() -> int:
    flags = {name: os.getenv(f'SELECT_{name.upper()}', '') for name in MODULES}
    results = {name: os.getenv(f'RESULT_{name.upper()}', '') for name in (*MANDATORY, *MODULES)}
    errors = validate(flags, results)
    summary = ['## AgroScan CI — validación global', '',
               '| Apartado | Seleccionado | Resultado |', '|---|---|---|']
    for name in (*MANDATORY, *MODULES):
        summary.append(f'| {name} | {flags.get(name, "obligatorio")} | {results.get(name) or "ausente"} |')
    summary.extend(['', '**Resultado:** ' + ('RECHAZADO' if errors else 'APROBADO')])
    if errors:
        summary.extend(['', 'Controles incumplidos:', *[f'- {msg}' for msg in errors]])
    summary_path = os.getenv('GITHUB_STEP_SUMMARY')
    if summary_path:
        with Path(summary_path).open('a', encoding='utf-8') as file:
            file.write('\n'.join(summary) + '\n')
    for error in errors:
        print('CI bloqueado: ' + error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
