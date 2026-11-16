"""AG-046/I04: FastAPI real en proceso secundario, con SQLite temporal obligatorio.

NO se importa desde app.main ni se instala como endpoint del backend productivo.
Solo se ejecuta mediante ag046_i04_run.py, que crea un sandbox verificable.
"""
from __future__ import annotations

import os
import secrets
import struct
import sys
import zlib
from pathlib import Path

from fastapi import Request

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def _sandbox() -> Path:
    # El padre envía la ruta real del sandbox y un comprobante por ejecución.
    # No depender de tempfile.gettempdir() en el hijo: Windows puede resolver
    # TEMP/TMP de forma diferente entre procesos o entornos virtuales.
    raw_data = os.environ.get('AG046_I04_DATA_DIR')
    raw_root = os.environ.get('AG046_I04_SANDBOX_ROOT')
    token = os.environ.get('AG046_I04_SANDBOX_TOKEN', '')
    if not raw_data or not raw_root or len(token) != 64 or any(
            char not in '0123456789abcdef' for char in token):
        raise RuntimeError('AG046 I04: faltan parametros verificables de sandbox')

    candidate_data, candidate_root = Path(raw_data), Path(raw_root)
    if (candidate_data.is_symlink() or candidate_root.is_symlink()
            or (hasattr(candidate_data, 'is_junction') and candidate_data.is_junction())
            or (hasattr(candidate_root, 'is_junction') and candidate_root.is_junction())):
        raise RuntimeError('AG046 I04: enlaces o junctions no permitidos')

    data = candidate_data.resolve(strict=True)
    root = candidate_root.resolve(strict=True)
    production_data = (BACKEND / 'data').resolve()
    marker = root / '.ag046-i04-sandbox'
    allowed = (
        root.is_dir() and data.is_dir()
        and root.name.startswith('ag046-i04-')
        and data == root / 'data'
        and data != production_data
        and production_data not in data.parents
        and data not in production_data.parents
        and marker.is_file() and not marker.is_symlink()
        and not (hasattr(marker, 'is_junction') and marker.is_junction())
    )
    if not allowed:
        raise RuntimeError('AG046 I04: directorio no es un sandbox temporal autorizado')
    try:
        verified = marker.stat().st_size == 64 and secrets.compare_digest(
            marker.read_text(encoding='ascii'), token)
    except (OSError, UnicodeError):
        verified = False
    if not verified:
        raise RuntimeError('AG046 I04: marcador de sandbox no corresponde a esta ejecucion')
    return data


def _png(rgb: tuple[int, int, int]) -> bytes:
    """PNG de 4x4 píxeles, original sintético, construido con biblioteca estándar."""
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return struct.pack('>I', len(payload)) + tag + payload + struct.pack(
            '>I', zlib.crc32(tag + payload) & 0xffffffff)

    ihdr = struct.pack('>2I5B', 4, 4, 8, 2, 0, 0, 0)
    raw = b''.join(b'\x00' + bytes(rgb) * 4 for _ in range(4))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def main() -> None:
    data = _sandbox()
    port = int(os.environ['AG046_I04_PORT'])
    nonce = os.environ['AG046_I04_NONCE']
    passwd = os.environ['AG046_I04_PASSWORD']
    if not nonce or not passwd or not 1024 <= port <= 65535:
        raise RuntimeError('AG046 I04: parametros de sandbox invalidos')

    # Redirigir toda importación de DATA_DIR ANTES de importar routers/servicios.
    import app.database as database
    from sqlalchemy import create_engine, event, select
    from sqlalchemy.orm import sessionmaker

    database.DATA_DIR = data
    database.DATABASE_URL = f'sqlite:///{(data / "agroscan.db").as_posix()}'
    database.engine = create_engine(database.DATABASE_URL,
        connect_args={'check_same_thread': False, 'timeout': 5})

    @event.listens_for(database.engine, 'connect')
    def _enable_fk(connection, _record):
        connection.execute('PRAGMA foreign_keys=ON')

    database.SessionLocal = sessionmaker(bind=database.engine, autoflush=False,
                                         autocommit=False)

    from app.main import app
    from app.models import Evaluation, Image, Lot, Piece, Role, User
    from app.security import hash_password
    from fastapi import HTTPException
    import uvicorn

    database.Base.metadata.create_all(database.engine)
    with database.SessionLocal() as db:
        existing = db.scalar(select(Lot).where(Lot.code == 'AG046-I04-SEED'))
        if existing is None:
            operator = Role(name='operador')
            reviewer = Role(name='revisor')
            db.add_all([
                User(username='ag046_i04_operador', full_name='Operador de laboratorio I04',
                     password_hash=hash_password(passwd), roles=[operator], is_active=True),
                User(username='ag046_i04_revisor', full_name='Revisor de laboratorio I04',
                     password_hash=hash_password(passwd), roles=[reviewer], is_active=True),
            ])
            lot = Lot(code='AG046-I04-SEED', product='tomate', status='open',
                      responsible='Prueba aislada I04')
            db.add(lot)
            db.flush()
            piece = Piece(lot_id=lot.id, code='FRUTA-I04-01', status='registered')
            db.add(piece)
            db.flush()
            ev = Evaluation(lot_id=lot.id, piece_ref_id=piece.id,
                piece_id=piece.code, product='tomate', status='pending_review',
                image_count=2, weight_pre_g=180.0)
            db.add(ev)
            db.flush()
            folder = data / 'images' / f'E-{ev.id:06d}'
            folder.mkdir(parents=True, exist_ok=True)
            for i, rgb in enumerate(((245, 70, 60), (235, 95, 82)), start=1):
                name = f'vista-{i}.png'
                original = _png(rgb)
                (folder / name).write_bytes(original)
                db.add(Image(evaluation_id=ev.id, view=f'vista-{i}',
                    relative_path=f'images/E-{ev.id:06d}/{name}',
                    content_type='image/png', size_bytes=len(original),
                    idempotency_key=('%064x' % i)))
            db.commit()

    config = uvicorn.Config(app, host='127.0.0.1', port=port,
                            log_level='warning', access_log=False, workers=1)
    server = uvicorn.Server(config)

    @app.post('/__ag046_i04__/shutdown', include_in_schema=False)
    def _shutdown(request: Request):
        from secrets import compare_digest
        received = request.headers.get('X-AG046-I04-Nonce', '')
        if not compare_digest(received, nonce):
            raise HTTPException(status_code=403, detail='Solicitud de auditoria no autorizada')
        server.should_exit = True
        return {'shutdown': 'requested'}

    server.run()
    database.engine.dispose()


if __name__ == '__main__':
    main()
