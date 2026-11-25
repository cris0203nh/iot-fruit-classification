"""Ejecución explícita: python -m app.notification_worker process|reminders."""
import argparse
import os
from pathlib import Path
import sqlite3
from contextlib import closing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['process', 'reminders'])
    parser.add_argument('--limit', type=int, default=50)
    args = parser.parse_args()
    data = os.getenv('AGROSCAN_DATA_DIR')
    if not data or not (Path(data) / 'agroscan.db').is_file() or not 1 <= args.limit <= 1000:
        parser.error('Indica AGROSCAN_DATA_DIR existente y límite 1–1000; sin base por defecto.')
    expected = 'sqlite:///' + (Path(data).resolve() / 'agroscan.db').as_posix()
    if os.getenv('AGROSCAN_DATABASE_URL') != expected:
        parser.error('AGROSCAN_DATABASE_URL debe coincidir exactamente con el directorio explícito.')
    try:
        with closing(sqlite3.connect((Path(data).resolve() / 'agroscan.db').as_uri() + '?mode=ro', uri=True)) as connection:
            if connection.execute('SELECT version_num FROM alembic_version').fetchall() != [('c018notifications',)]:
                parser.error('Se requiere c018notifications; este comando no migra ni crea bases.')
    except sqlite3.DatabaseError:
        parser.error('No se pudo verificar la revisión SQLite; sin crear, migrar ni enviar.')
    from .database import SessionLocal
    from .main import app  # noqa: F401; registra modelos sin migrar ni iniciar servicios.
    from .services.commercial_notifications import process_pending, enqueue_expirations
    from sqlalchemy.exc import SQLAlchemyError
    try:
        with SessionLocal() as db:
            result = (process_pending if args.action == 'process' else enqueue_expirations)(db, args.limit)
    except (SQLAlchemyError, ValueError):
        parser.exit(1, 'No se pudo completar el lote. Revisa configuración e integridad; sin reenviar resultados inciertos.\n')
    print(f'{args.action}: {result} registros procesados; aceptación SMTP no acredita recepción en buzón.')


if __name__ == '__main__':
    main()
