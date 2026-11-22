"""Inventario privado y limpieza por filas aprobadas. Por defecto: solo lectura.

No importa la aplicación, no carga secretos ni migra. Conserva archivos físicos.
La ejecución requiere plan SHA-256 confirmado y mantenimiento explícito.
"""
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = frozenset(('lots', 'pieces', 'evaluations', 'measurements', 'images', 'reviews',
    'review_decision_evidence', 'vision_assessments', 'vision_prechecks', 'fruit_geometries',
    'ag054_board_calibrations', 'ag054_planar_calibrations', 'ag054_dimensional_comparisons',
    'ag055_quality_predictions', 'commercial_orders', 'commercial_transactions',
    'commercial_subscriptions', 'users', 'user_roles', 'google_identities'))
SAFE = frozenset(('id', 'organization_id', 'user_id', 'role_id', 'code', 'name', 'username',
    'is_active', 'lot_id', 'piece_id', 'piece_ref_id', 'evaluation_id', 'image_id', 'review_id',
    'operator_id', 'actor_id', 'created_by', 'status', 'relative_path', 'device_id',
    'calibration_version', 'amount_cents', 'plan_id', 'order_id', 'geometry_id',
    'board_calibration_id', 'registered_lot_id', 'weight_pre_measurement_id', 'weight_post_measurement_id'))


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=repr,
                                     ensure_ascii=True).encode()).hexdigest()


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def connect(path, writable=False):
    db = sqlite3.connect(path.resolve().as_uri() + ('?mode=rw' if writable else '?mode=ro'), uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=5000')
    return db


def integrity(db):
    if [r[0] for r in db.execute('PRAGMA integrity_check')] != ['ok']:
        raise ValueError('integrity_check no aprobado')
    if db.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('foreign_key_check no aprobado')


def snapshot(db):
    schema = [tuple(r) for r in db.execute(
        'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
    tables = {}
    for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        name = row[0]
        rows = [dict(r) for r in db.execute('SELECT * FROM ' + quote(name))]
        info = list(db.execute('PRAGMA table_info(' + quote(name) + ')'))
        tables[name] = {'rows': rows, 'pk': [r['name'] for r in sorted(info, key=lambda r: r['pk']) if r['pk']],
                        'foreign_keys': [dict(r) for r in db.execute('PRAGMA foreign_key_list(' + quote(name) + ')')]}
    hashes = {t: sorted(digest(r) for r in v['rows']) for t, v in tables.items()}
    return {'schema_sha256': digest(schema), 'database_digest': digest([schema, hashes]), 'tables': tables}


def safe_row(row):
    return {key: value for key, value in row.items() if key in SAFE}


def orphan_operators(db):
    return [dict(r) for r in db.execute("""SELECT DISTINCT u.id,u.username FROM users u
        JOIN user_roles ur ON ur.user_id=u.id JOIN roles r ON r.id=ur.role_id
        WHERE r.name='operador' AND NOT EXISTS
        (SELECT 1 FROM organization_memberships m WHERE m.user_id=u.id) ORDER BY u.id""")]


def image_files(state, data_dir):
    result = []
    for row in state['tables'].get('images', {}).get('rows', []):
        relative = row['relative_path'].replace('\\', '/')
        path = data_dir / relative
        entry = {'image_id': row['id'], 'relative_path': relative}
        try:
            if (not relative.startswith('images/') or '..' in Path(relative).parts
                    or ':' in relative or not path.resolve().is_relative_to(data_dir.resolve())):
                raise ValueError('Ruta fuera del almacenamiento permitido')
            for parent in (path, *path.parents):
                if parent == data_dir.parent:
                    break
                if parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)():
                    raise ValueError('Enlace o junction no permitido')
            if not path.is_file():
                raise ValueError('Archivo ausente')
            entry.update(status='ok', sha256=file_hash(path), size=path.stat().st_size)
        except (OSError, ValueError) as exc:
            entry.update(status='pending', reason=str(exc))
        result.append(entry)
    return result


def private_directory(path):
    # Resuelve enlaces antes de comprobar el límite del proyecto.
    path = path.resolve()
    if path.is_relative_to(ROOT):
        raise ValueError('El directorio de respaldo/reporte debe estar fuera del repositorio AgroScan')
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise ValueError('El directorio privado debe estar vacío; no se sobrescriben informes')
    else:
        path.mkdir(parents=True, exist_ok=False)
    return path


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def backup(db, state, data_dir, out):
    target = out / 'agroscan-before.sqlite'
    with closing(sqlite3.connect(target)) as copy:
        db.backup(copy)
    with closing(connect(target)) as copy:
        integrity(copy)
        if snapshot(copy)['database_digest'] != state['database_digest']:
            raise ValueError('El respaldo no coincide con el inventario')
    photos = image_files(state, data_dir)
    for photo in photos:
        if photo['status'] == 'ok':
            destination = out / 'files' / photo['relative_path']
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(data_dir / photo['relative_path'], destination)
            if file_hash(destination) != photo['sha256'] or file_hash(data_dir / photo['relative_path']) != photo['sha256']:
                raise ValueError('Una fotografía cambió durante el respaldo')
    evidence = {'database_sha256': file_hash(target), 'database_digest': state['database_digest'],
                'integrity_check': 'ok', 'foreign_key_check': [], 'images': photos}
    write_json(out / 'backup-verification.json', evidence)
    return evidence


def selected_rows(state, plan, path):
    if (plan.get('database') != str(path.resolve())
            or plan.get('database_digest') != state['database_digest']):
        raise ValueError('La base cambió o el plan corresponde a otra base; repetir inventario y revisión')
    chosen = {}
    for entry in plan['selections']:
        table = entry['table']
        if table not in ALLOWED or not state['tables'][table]['pk']:
            raise ValueError('Tabla protegida o sin clave primaria')
        if entry.get('evidence', {}).get('kind') != 'user_confirmed' or not entry['evidence'].get('detail', '').strip():
            raise ValueError('Falta confirmación de procedencia/alcance por el usuario')
        rows = [r for r in state['tables'][table]['rows'] if digest(r) == entry['row_sha256']]
        key = (table, entry['row_sha256'])
        if len(rows) != 1 or key in chosen:
            raise ValueError('Fila ausente, modificada o repetida')
        chosen[key] = rows[0]
    return chosen


def validate_user(db, chosen):
    users = [r['id'] for (table, _), r in chosen.items() if table == 'users']
    if len(users) > 1:
        raise ValueError('Solo puede retirarse una cuenta de operador')
    for uid in users:
        roles = {r[0] for r in db.execute('SELECT r.name FROM roles r JOIN user_roles ur ON ur.role_id=r.id WHERE ur.user_id=?', (uid,))}
        if (roles != {'operador'} or db.execute('SELECT 1 FROM organization_memberships WHERE user_id=?', (uid,)).fetchone()
                or db.execute('SELECT 1 FROM platform_owner WHERE user_id=?', (uid,)).fetchone()):
            raise ValueError('Cuenta protegida: propietario, otro rol o vinculación empresarial')
        state = snapshot(db)
        for table, info in state['tables'].items():
            for fk in info['foreign_keys']:
                if fk['table'] == 'users' and table not in ('user_roles', 'google_identities'):
                    if db.execute('SELECT 1 FROM ' + quote(table) + ' WHERE ' + quote(fk['from']) + '=?', (uid,)).fetchone():
                        raise ValueError('La cuenta tiene referencias históricas; conservarla')
    for (table, _), row in chosen.items():
        if table in ('user_roles', 'google_identities') and row['user_id'] not in users:
            raise ValueError('Solo pueden retirarse relaciones de la cuenta seleccionada')


def delete_exact(db, state, chosen):
    validate_user(db, chosen)
    db.execute('PRAGMA defer_foreign_keys=ON')
    counts = Counter()
    remaining = {table for table, _ in chosen}
    order = []
    while remaining:
        leaves = sorted(table for table in remaining if not any(
            child != table and fk['table'] == table for child in remaining
            for fk in state['tables'][child]['foreign_keys']))
        # Ciclos: la comprobación diferida y comparación exhaustiva siguen
        # impidiendo referencias rotas o cascadas fuera del alcance aprobado.
        leaves = leaves or sorted(remaining)
        order.extend(leaves)
        remaining.difference_update(leaves)
    for (table, _), row in sorted(chosen.items(), key=lambda item: order.index(item[0][0])):
        pk = state['tables'][table]['pk']
        statement = 'DELETE FROM ' + quote(table) + ' WHERE ' + ' AND '.join(quote(c) + ' IS ?' for c in pk)
        result = db.execute(statement, tuple(row[c] for c in pk))
        if result.rowcount != 1:
            raise ValueError('El filtro no seleccionó exactamente una fila')
        counts[table] += 1
    integrity(db)
    after = snapshot(db)
    if after['schema_sha256'] != state['schema_sha256']:
        raise ValueError('Cambió el esquema; rollback')
    for table, info in state['tables'].items():
        expected = Counter(digest(row) for row in info['rows'])
        for (selected_table, sha), row in chosen.items():
            if selected_table == table:
                expected[sha] -= 1
        if +expected != Counter(digest(row) for row in after['tables'][table]['rows']):
            raise ValueError('Se alteraron filas no autorizadas; rollback')
    return dict(counts)


def inventory(state, db, data_dir):
    return {'database': str((data_dir / 'agroscan.db').resolve()),
            'database_digest': state['database_digest'], 'schema_sha256': state['schema_sha256'],
            'integrity_check': 'ok', 'foreign_key_check': [], 'orphan_operators': orphan_operators(db),
            'tables': {table: {'count': len(info['rows']), 'primary_key': info['pk'],
                              'foreign_keys': info['foreign_keys'],
                              'records': [{'row_sha256': digest(row), 'identifiers': safe_row(row),
                                           'classification': 'protected' if table not in ALLOWED else 'pending_origin_confirmation'}
                                          for row in info['rows']]}
                       for table, info in state['tables'].items()},
            'image_files': image_files(state, data_dir), 'physical_file_deletion': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='Directorio privado NUEVO fuera del repositorio')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--confirm-plan-sha256')
    parser.add_argument('--maintenance-confirmed', action='store_true')
    args = parser.parse_args(argv)
    path = Path(os.environ.get('AGROSCAN_DATA_DIR', ROOT / 'backend/data')).expanduser().resolve() / 'agroscan.db'
    if not path.is_file():
        parser.error('No existe la base configurada; no se creará otra')
    if args.execute and (not args.plan or not args.maintenance_confirmed
                         or file_hash(args.plan) != args.confirm_plan_sha256):
        parser.error('Ejecución requiere plan revisado, SHA-256 exacto y mantenimiento confirmado')
    out = private_directory(args.out)
    plan = json.loads(args.plan.read_text(encoding='utf-8')) if args.plan else None
    with closing(connect(path, writable=args.execute)) as db:
        committed = False
        try:
            db.execute('BEGIN IMMEDIATE' if args.execute else 'BEGIN')
            integrity(db)
            state = snapshot(db)
            write_json(out / 'inventory.json', inventory(state, db, path.parent))
            chosen = selected_rows(state, plan, path) if plan else {}
            print(json.dumps({'mode': 'execute' if args.execute else 'dry-run', 'database': str(path),
                              'selected': [{'table': t, 'identifiers': safe_row(row)} for (t, _), row in chosen.items()]}, ensure_ascii=True))
            if args.execute:
                if not chosen:
                    raise ValueError('Plan vacío: no hay eliminaciones autorizadas')
                validate_user(db, chosen)
                # Con BEGIN IMMEDIATE no hay escrituras concurrentes; respaldo
                # desde otra conexión RO para evitar backup sobre transacción RW.
                with closing(connect(path)) as source:
                    evidence = backup(source, state, path.parent, out)
                if any(p['status'] != 'ok' for p in evidence['images']):
                    raise ValueError('Respaldo físico incompleto; ejecución bloqueada')
                counts = delete_exact(db, state, chosen)
                report = {'deleted_by_table': counts, 'protected_rows_unchanged': True,
                          'integrity_check': 'ok', 'foreign_key_check': [], 'physical_files_deleted': 0}
                # Si no puede guardarse la evidencia, no se confirma la limpieza.
                write_json(out / 'execution-precommit.json', report)
                db.commit()
                committed = True
                report['committed'] = True
                write_json(out / 'execution.json', report)
            else:
                backup(db, state, path.parent, out)
                with closing(sqlite3.connect(':memory:')) as simulation:
                    simulation.row_factory = sqlite3.Row
                    simulation.execute('PRAGMA foreign_keys=ON')
                    db.backup(simulation)
                    simulation.execute('BEGIN')
                    counts = delete_exact(simulation, state, chosen)
                    simulation.rollback()
                write_json(out / 'dry-run.json', {'would_delete_by_table': counts, 'deleted': 0,
                                                  'protected_rows_unchanged': True, 'physical_files_deleted': 0})
                if not plan:
                    write_json(out / 'plan-empty.json', {'database': str(path),
                               'database_digest': state['database_digest'], 'selections': []})
                db.rollback()
            print('Informes privados: ' + str(out))
        except Exception as exc:
            db.rollback()
            try:
                write_json(out / 'failure.json', {'committed': committed, 'error_type': type(exc).__name__,
                                                  'reason': str(exc), 'rolled_back': not committed})
            except OSError:
                # No ocultar el fallo original si el directorio no es escribible.
                pass
            raise
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
