"""Inicialización/servidor QA local. Nunca usa una base por defecto."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
QA_ROOT = ROOT / '.agroscan-qa'
HEAD = 'c018notifications'
OPERATIONAL = ('lots', 'pieces', 'evaluations', 'images', 'measurements', 'reviews',
               'vision_assessments', 'vision_prechecks', 'fruit_geometries',
               'ag054_board_calibrations', 'ag054_planar_calibrations',
               'ag054_dimensional_comparisons', 'ag055_quality_predictions', 'review_decision_evidence')


def configuration():
    root = Path(os.environ.get('AGROSCAN_QA_ROOT', '')).resolve()
    if root != QA_ROOT.resolve() or root.is_symlink() or getattr(root, 'is_junction', lambda: False)():
        raise ValueError('Se requiere la carpeta QA local explícita, sin enlaces.')
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8-sig'))
    data = root / 'data'
    database = data / 'agroscan.db'
    if (manifest['instance'] != os.environ.get('AGROSCAN_QA_INSTANCE')
            or Path(os.environ.get('AGROSCAN_DATA_DIR', '')).resolve() != data.resolve()
            or os.environ.get('AGROSCAN_DATABASE_URL') != 'sqlite:///' + database.as_posix()
            or data.resolve() != (QA_ROOT / 'data').absolute()
            or database.is_symlink() or getattr(data, 'is_junction', lambda: False)()
            or data.is_symlink()
            or os.environ.get('AGROSCAN_ENVIRONMENT') != 'demo'
            or os.environ.get('AGROSCAN_SUBSCRIPTION_SIMULATOR') != 'true'
            or len(os.environ.get('AGROSCAN_JWT_SECRET', '')) < 32):
        raise ValueError('Configuración QA incoherente: se cancela sin conexión alternativa.')
    # La clave vacía existe en os.environ: dotenv no puede heredar el cliente
    # OAuth/orígenes del backend operativo. QA usa login tradicional propio.
    os.environ['AGROSCAN_GOOGLE_CLIENT_ID'] = ''
    os.environ['AGROSCAN_DEMO_ORIGINS'] = ''
    os.environ['AGROSCAN_SESSION_ALLOW_LOOPBACK_HTTP'] = 'true'
    return manifest, database


def check_database(database, empty=False, allow_previous=False):
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Integridad QA incorrecta.')
        version = db.execute('SELECT version_num FROM alembic_version').fetchall()
        if version != [(HEAD,)] and not (allow_previous and version in ([('c014onboarding',)], [('c015imagekey',)])):
            raise ValueError('Migración QA pendiente; el arranque no migra automáticamente.')
        counts = {table: db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] for table in OPERATIONAL}
        if empty and any(counts.values()):
            raise ValueError('La base QA contiene operaciones anteriores.')
        return counts


def initialize():
    manifest, database = configuration()
    if database.exists():
        raise ValueError('La base QA ya existe. No se sobrescribe ni reinicia.')
    accounts = json.load(sys.stdin)
    if set(accounts) != {'propietario', 'administrador', 'operador', 'revisor'}:
        raise ValueError('Se requieren cuatro cuentas independientes.')
    if len({a['password'] for a in accounts.values()}) != 4 or any(len(a['password']) < 24 for a in accounts.values()):
        raise ValueError('Contraseñas de QA deben ser fuertes y diferentes.')
    database.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', HEAD], cwd=ROOT / 'backend', check=True)
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.database import SessionLocal
    from app import models, commercial_models  # noqa: F401
    from app.models import User, Role
    from app.organization_models import Organization, OrganizationMembership
    from app.bootstrap_owner import assign_first_owner
    from app.security import hash_password
    from app.commercial_models import CommercialPlan
    from sqlalchemy import select
    with SessionLocal() as db:
        if db.scalar(select(User.id)) is not None:
            raise ValueError('No se inicializan cuentas sobre una base con usuarios.')
        roles = {}
        for name in ('administrador', 'operador', 'revisor'):
            role = db.scalar(select(Role).where(Role.name == name))
            if role is None:
                role = Role(name=name)
                db.add(role)
            roles[name] = role
        organization = db.get(Organization, 1)
        organization.name = 'AgroScan QA — DEMO A'
        db.add(Organization(name='AgroScan QA — Aislamiento B', is_active=True))
        db.flush()
        identities = {}
        for role, account in accounts.items():
            user = User(username=account['username'], full_name='QA ' + role,
                        password_hash=hash_password(account['password']), is_active=True,
                        roles=[] if role == 'propietario' else [roles[role]])
            db.add(user)
            db.flush()
            identities[role] = {'id': user.id, 'username': user.username}
            if role != 'propietario':
                db.add(OrganizationMembership(organization_id=1, user_id=user.id, role_id=roles[role].id))
        for code, name, price, period in (
                ('qa-esencial', 'Esencial DEMO', 9900, 'monthly'),
                ('qa-cosecha', 'Cosecha DEMO', 19900, 'monthly'),
                ('qa-anual', 'Anual DEMO', 199000, 'annual')):
            db.add(CommercialPlan(code=code, version=1, name=name, description='Condiciones ilustrativas exclusivas de QA. Sin cobros reales.',
                amount_cents=price, currency='PEN', period=period,
                benefits_json=json.dumps(['Trazabilidad', 'Revisión humana', 'Captura de evaluaciones']),
                limits_json='{}', is_active=True, recommended=code == 'qa-cosecha'))
        db.commit()
        assign_first_owner(db, identities['propietario']['id'])
    counts = check_database(database, empty=True)
    manifest.update(ready=True, schema=HEAD, accounts=identities, operational_counts=counts)
    (QA_ROOT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print('QA inicializado: cuatro cuentas, dos empresas, tres planes DEMO; operaciones vacías.')


def serve():
    manifest, database = configuration()
    if not manifest.get('ready'):
        raise ValueError('Inicialización QA incompleta.')
    check_database(database)
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.main import app
    from fastapi.responses import JSONResponse
    import uvicorn

    @app.middleware('http')
    async def qa_identity(request, call_next):
        if request.headers.get('X-AgroScan-QA') != manifest['instance']:
            return JSONResponse(status_code=503, content={'detail': 'Este servidor requiere el frontend QA autorizado.'})
        response = await call_next(request)
        response.headers['X-AgroScan-QA-ID'] = manifest['instance']
        return response

    uvicorn.run(app, host='127.0.0.1', port=8778, log_level='warning')


if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) == 2 else ''
    if action == 'init':
        initialize()
    elif action == 'serve':
        serve()
    elif action == 'check':
        manifest, database = configuration()
        print(json.dumps({'schema': manifest.get('schema'), 'ready': manifest.get('ready'),
                          'operational_counts': check_database(database)}, indent=2))
    else:
        raise SystemExit('Usar init, serve o check mediante agroscan_qa.ps1')
