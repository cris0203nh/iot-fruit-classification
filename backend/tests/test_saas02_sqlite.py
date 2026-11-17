"""Regresiones SQLite con archivos sintéticos y conexiones independientes."""
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.organization_models import Organization
from app.database import Base, enable_sqlite_foreign_keys
from app.iot_schemas import MeasurementCreate
from app.models import Measurement
from app.routers.iot import receive_measurement
from app.iot_models import IotDevice, IotStation
from app.services.device_auth import authenticated_device, credential_hash


class SQLiteConcurrencyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='saas02-sqlite-')
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'instance.db'
        self.engine = create_engine(
            f'sqlite:///{self.path.as_posix()}',
            connect_args={'check_same_thread': False, 'timeout': 5},
        )
        self.addCleanup(self.engine.dispose)
        event.listen(self.engine, 'connect', enable_sqlite_foreign_keys)
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as db:
            db.execute(Organization.__table__.insert().values(id=1, name="AgroScan Inicial", is_active=True))
        self.credential = 'agd_' + 'S'*43
        with Session(self.engine, info={'organization_id': 1}) as db:
            db.add(IotStation(id=1, code='test', name='Test'))
            db.flush()
            db.add(IotDevice(station_id=1, device_id='saas02-station',
                             credential_hash=credential_hash(self.credential)))
            db.commit()

    def test_wal_lectura_estable_y_escritura_atomica_con_rollback(self):
        with closing(sqlite3.connect(self.path)) as writer, \
                closing(sqlite3.connect(self.path, timeout=0.02)) as other:
            self.assertEqual(writer.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
            writer.execute('CREATE TABLE counter (value INTEGER NOT NULL)')
            writer.execute('INSERT INTO counter VALUES (0)')
            writer.commit()
            other.execute('BEGIN')
            self.assertEqual(other.execute('SELECT value FROM counter').fetchone()[0], 0)
            writer.execute('BEGIN IMMEDIATE')
            writer.execute('UPDATE counter SET value=1')
            writer.commit()  # Un lector activo no bloquea el commit WAL.
            self.assertEqual(other.execute('SELECT value FROM counter').fetchone()[0], 0)
            other.rollback()
            self.assertEqual(other.execute('SELECT value FROM counter').fetchone()[0], 1)

            writer.execute('BEGIN IMMEDIATE')
            writer.execute('UPDATE counter SET value=2')
            with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                other.execute('BEGIN IMMEDIATE')
            writer.rollback()
            other.execute('BEGIN IMMEDIATE')
            other.execute('UPDATE counter SET value=value+10')
            other.commit()
            self.assertEqual(writer.execute('SELECT value FROM counter').fetchone()[0], 11)

    def test_reenvios_iot_simultaneos_son_idempotentes_en_delete_y_wal(self):
        for sequence, mode in enumerate(('delete', 'wal'), start=1):
            with self.subTest(mode=mode):
                self.engine.dispose()
                with self.engine.connect() as db:
                    self.assertEqual(db.exec_driver_sql(f'PRAGMA journal_mode={mode}').scalar(), mode)
                barrier = Barrier(2)

                payload = MeasurementCreate(
                    device_id='saas02-station', boot_id='synthetic-boot', seq=sequence,
                    weight_g=250, stable=True, calibration_version='synthetic',
                    observed_at=datetime.now(timezone.utc),
                )

                def ingest(_):
                    with Session(self.engine, info={'organization_required': True}) as db:
                        barrier.wait(timeout=5)
                        device = authenticated_device('Bearer '+self.credential, None, db)
                        return receive_measurement(payload, db, device)

                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(ingest, range(2)))
                self.assertEqual(sorted(item['duplicate'] for item in results), [False, True])
                self.assertEqual(results[0]['receivedAt'], results[1]['receivedAt'])
                with Session(self.engine, info={"organization_id": 1}) as db:
                    rows = db.scalars(select(Measurement).where(Measurement.seq == sequence)).all()
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0].weight_g, 250)


if __name__ == '__main__':
    unittest.main()
