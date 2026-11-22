"""Desarrollo local existente; nunca copia QA ni usa SQLite por defecto."""
import json
import os
from pathlib import Path
import sys

from agroscan_qa import HEAD as SCHEMA, check_database

ROOT = Path(__file__).resolve().parents[1]
DEV_ROOT = Path.home() / 'Documents' / 'AgroScan-Dev'


def configuration():
    root = Path(os.environ.get('AGROSCAN_DEV_ROOT', '')).resolve()
    expected = DEV_ROOT.resolve()
    data = root / 'data'
    database = data / 'agroscan.db'
    if (root != expected or root.is_symlink() or getattr(root, 'is_junction', lambda: False)()
            or root.is_relative_to(ROOT) or data.is_symlink() or database.is_symlink()
            or getattr(data, 'is_junction', lambda: False)()
            or Path(os.environ.get('AGROSCAN_DATA_DIR', '')).resolve() != data.resolve()
            or os.environ.get('AGROSCAN_DATABASE_URL') != 'sqlite:///' + database.as_posix()
            or os.environ.get('AGROSCAN_SESSION_ALLOW_LOOPBACK_HTTP') != 'true'
            or os.environ.get('AGROSCAN_ENVIRONMENT') != 'demo'
            or len(os.environ.get('AGROSCAN_JWT_SECRET', '')) < 32):
        raise ValueError('Desarrollo exige rutas privadas explícitas y configuración local coherente.')
    return root, database


def prepare():
    root, database = configuration()
    manifest = root / 'manifest.json'
    if database.exists():
        if not manifest.is_file() or not json.loads(manifest.read_text())['ready']:
            raise ValueError('Desarrollo incompleto; no se sobrescribe la base existente.')
        check_database(database)
        return
    raise ValueError('Falta la SQLite DEV existente; no se copia QA ni se recrean cuentas o datos.')


def serve():
    root, database = configuration()
    check_database(database)
    manifest = json.loads((root / 'manifest.json').read_text())
    if not manifest.get('ready'):
        raise ValueError('Preparar desarrollo antes de iniciar.')
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.main import app
    from fastapi.responses import JSONResponse
    import uvicorn

    @app.middleware('http')
    async def local_identity(request, call_next):
        if request.headers.get('X-AgroScan-Dev') != manifest['instance']:
            return JSONResponse(status_code=503, content={'detail': 'Usa el frontend de desarrollo autorizado.'})
        response = await call_next(request)
        response.headers['X-AgroScan-Dev-ID'] = manifest['instance']
        return response

    uvicorn.run(app, host='127.0.0.1', port=8000, log_level='warning')


if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) == 2 else ''
    if action == 'prepare':
        prepare()
    elif action == 'serve':
        serve()
    elif action == 'check':
        _, database = configuration()
        check_database(database)
        print(f'Desarrollo SQLite {SCHEMA}: integridad y claves foráneas correctas.')
    else:
        raise SystemExit('Usar tools/agroscan_dev.ps1 -Action backend|frontend')
