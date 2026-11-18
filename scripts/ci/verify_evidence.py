#!/usr/bin/env python3
"""Check integrity and allowed schema of a sanitized AgroScan CI artifact.

This checks report consistency, not the authenticity of a GitHub Actions run.
To establish provenance, cross-check run_id and the original Actions artifact.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from check_gate import MODULES, MANDATORY, build_report, validate

EXPECTED_NAMES = tuple((*MANDATORY, *MODULES))


def verify(report: object) -> bool:
    """Fail-closed: check exact schema, canonical counts, states and decision."""
    if not isinstance(report, dict) or set(report) != {
        'schema_version', 'scope', 'context', 'decision', 'counts', 'checks', 'violations'
    }:
        return False
    rows = report.get('checks')
    context = report.get('context')
    if not isinstance(rows, list) or len(rows) != len(EXPECTED_NAMES):
        return False
    if not isinstance(context, dict) or set(context) != {'run_id', 'sha', 'event'}:
        return False
    if not all(isinstance(context[k], (str, type(None))) for k in context):
        return False
    flags, results = {}, {}
    for name, row in zip(EXPECTED_NAMES, rows):
        if not isinstance(row, dict) or set(row) != {
            'component', 'selection', 'expected', 'result', 'compliant'
        } or row.get('component') != name:
            return False
        # bool is a subclass of int; canonical comparison below checks exact output.
        if name in MODULES:
            selection = row.get('selection')
            flags[name] = {'selected': 'true', 'not-selected': 'false'}.get(selection, '')
        results[name] = row.get('result')
    # reject any non-allowlisted state and never echo the untrusted payload
    if any(not isinstance(state, str) for state in results.values()):
        return False
    if any(not isinstance(value, str) for value in flags.values()):
        return False
    try:
        expected = build_report(flags, results, metadata={key: (value or '') for key, value in context.items()})
    except (TypeError, ValueError, KeyError):
        return False
    if type(report.get('schema_version')) is not int:
        return False
    if type(report.get('counts')) is not dict:
        return False
    if type(report.get('violations')) is not list:
        return False
    if report != expected:
        return False
    return (expected['decision'] == 'rejected') == bool(validate(flags, results))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = json.loads(args.file.read_text(encoding='utf-8'))
        if not verify(report):
            raise ValueError('invalid evidence')
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        print('Evidencia CI rechazada: archivo ausente o contrato inválido.', file=sys.stderr)
        return 1
    print('Evidencia CI válida: contrato, selección, estados y decisión coherentes.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
