#!/usr/bin/env python3
"""Deterministic local CI gate test matrix; not a GitHub Actions execution."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from check_gate import MANDATORY, MODULES, build_report, validate
from select_jobs import classify
from verify_evidence import verify


CASES = (
    ('complete_ci', ['.github/workflows/ci.yml'], None, None, 'approved'),
    ('docs_only', ['docs/ci/ETAPA07_VALIDACION_FINAL.md'], None, None, 'approved'),
    ('frontend_style', ['frontend/src/App.css'], None, None, 'approved'),
    ('backend_shared', ['backend/app/dependencies.py'], None, None, 'approved'),
    ('unknown_path', ['tools/new_security_hook.py'], None, None, 'approved'),
    ('backend_failure', ['backend/app/dependencies.py'], 'backend', 'failure', 'rejected'),
    ('security_failure', ['docs/ci/ETAPA07_VALIDACION_FINAL.md'], 'seguridad', 'failure', 'rejected'),
    ('mandatory_skipped', ['docs/ci/ETAPA07_VALIDACION_FINAL.md'], 'seguridad', 'skipped', 'rejected'),
    ('unexpected_skip', ['backend/app/dependencies.py'], 'backend', 'skipped', 'rejected'),
    ('cancelled_module', ['frontend/src/App.css'], 'frontend', 'cancelled', 'rejected'),
)


def execute() -> dict:
    rows = []
    for case, paths, change, state, target in CASES:
        selected = classify(paths)
        flags = {name: ('true' if selected[name] else 'false') for name in MODULES}
        results = {name: 'success' for name in MANDATORY}
        results.update({name: ('success' if selected[name] else 'skipped') for name in MODULES})
        if change:
            results[change] = state
        report = build_report(flags, results, metadata={'event': 'workflow_dispatch'})
        actual = report['decision']
        if actual != target or not verify(report) or bool(validate(flags, results)) != (target == 'rejected'):
            raise AssertionError('Fallo de escenario local: ' + case)
        rows.append({'case': case, 'expected': target, 'actual': actual,
                     'selected': [name for name in MODULES if selected[name]],
                     'simulated': True})
    return {'schema_version': 1, 'kind': 'local-contract-simulation',
            'scope': 'Deterministic unit-like scenarios. Not GitHub checks or branch protection.',
            'cases': rows, 'all_match': True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = execute()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"Matriz local: {len(report['cases'])} escenarios verificados; salida={args.output}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
