#!/usr/bin/env python3
"""Deterministic, conservative path selection for AgroScan CI.

No network calls, no repository modifications, no access to production data.
A missing/unsafe diff base never makes tests appear optional.
"""
from __future__ import annotations

import argparse
import os
from pathlib import PurePosixPath
import re
import subprocess
from typing import Iterable

MODULES = ("backend", "frontend", "iot", "vision", "integracion", "dast")
_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")


def full_selection() -> dict[str, bool]:
    return {name: True for name in MODULES}


def classify(paths: Iterable[str], *, force_full: bool = False) -> dict[str, bool]:
    if force_full:
        return full_selection()
    selected = {name: False for name in MODULES}
    listed = tuple(paths)
    if not listed:
        return full_selection()  # No diff != documentary-only diff.

    for raw in listed:
        path = raw.replace('\\', '/')
        if not path or path.startswith('/') or '..' in PurePosixPath(path).parts:
            return full_selection()
        if (path.startswith('.github/') or path.startswith('scripts/ci/')
                or path.startswith('scripts/devsecops/')):
            return full_selection()
        if path.startswith('backend/'):
            selected['backend'] = True
            selected['integracion'] = True
            selected['dast'] = True
            if (path.startswith('backend/app/') or path == 'backend/requirements.txt'
                    or path.startswith('backend/alembic/')):
                # API, models and shared auth are used by IoT/vision too.
                selected['iot'] = True
                selected['vision'] = True
            if any(k in path.lower() for k in ('iot', 'measurement', 'scale', 'weight')):
                selected['iot'] = True
            if any(k in path.lower() for k in ('vision', 'image', 'geometry', 'quality', 'calibration')):
                selected['vision'] = True
            continue
        if path.startswith('frontend/'):
            selected['frontend'] = True
            if (path.startswith('frontend/tests/') or
                    (path.startswith('frontend/src/') and not
                     path.endswith(('.css', '.scss', '.svg', '.png', '.jpg', '.jpeg', '.webp')))):
                selected['integracion'] = True
            continue
        if path.startswith('firmware/') or path.startswith('hardware/'):
            selected['iot'] = True
            selected['integracion'] = True
            continue
        if path.startswith('vision/'):
            selected['vision'] = True
            selected['backend'] = True
            selected['integracion'] = True
            selected['dast'] = True
            continue
        if path.startswith('tests/'):
            name = PurePosixPath(path).name
            if name.startswith('test_agroscan_i03_'):
                selected['vision'] = True
            elif name.startswith(('test_iot_', 'test_serial_bridge', 'test_weight_simulator', 'test_scale_core')):
                selected['iot'] = True
            elif name.startswith('test_agroscan_demo_deploy'):
                selected['backend'] = True
                selected['dast'] = True
            else:
                return full_selection()  # Unknown integration/e2e surface.
            selected['integracion'] = True
            continue
        if (path.startswith('docs/') or path in ('README.md', 'ATRIBUCIONES.md', 'INFORME.md')
                or (not '/' in path and path.lower().endswith('.md'))):
            continue
        # Unknown code, config, data or root-level file: evaluate everything.
        return full_selection()
    return selected


def git_changes(base: str, head: str = 'HEAD') -> list[str] | None:
    """Return None for invalid/unavailable/non-ancestor bases => run every module."""
    if not _SHA.fullmatch(base or ''):
        return None
    valid = subprocess.run(['git', 'cat-file', '-e', base + '^{commit}'], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if valid.returncode:
        return None
    ancestor = subprocess.run(['git', 'merge-base', '--is-ancestor', base, head], check=False,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if ancestor.returncode == 1:
        return None  # Rewrites/force-push => complete run.
    if ancestor.returncode != 0:
        raise RuntimeError('Git no pudo verificar la ascendencia del commit base')
    changed = subprocess.run(['git', 'diff', '--name-only', '-z', base, head], check=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return [p.decode('utf-8', errors='surrogateescape')
            for p in changed.stdout.split(b'\0') if p]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event', required=True)
    parser.add_argument('--base', default='')
    parser.add_argument('--head', default='HEAD')
    parser.add_argument('--output', required=True)
    parser.add_argument('--summary', required=True)
    args = parser.parse_args()

    manual = args.event == 'workflow_dispatch'
    paths = None if manual else git_changes(args.base, args.head)
    fallback = paths is None
    selection = classify([] if fallback else paths, force_full=manual or fallback)
    mode = 'COMPLETA (manual/base no fiable)' if manual or fallback else 'SELECTIVA'
    with open(args.output, 'a', encoding='utf-8') as output:
        for module, enabled in selection.items():
            output.write(f'{module}={str(enabled).lower()}\n')
    with open(args.summary, 'a', encoding='utf-8') as summary:
        summary.write('## AgroScan CI — selección de módulos\n')
        summary.write(f'**Modo:** {mode}. **Archivos cambiados:** {len(paths) if paths is not None else "no determinado"}.\n\n')
        summary.write('| Componente | Ejecutar |\n|---|---|\n')
        for module, enabled in selection.items():
            summary.write(f'| {module} | {"sí" if enabled else "no (omisión prevista)"} |\n')
        summary.write('\nSeguridad SAST/SCA/Gitleaks siempre es obligatoria.\n')
    print(f'Selección CI ({mode}): ' + ', '.join(f'{k}={v}' for k,v in selection.items()))


if __name__ == '__main__':
    main()
