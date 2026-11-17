import sqlite3
import unittest
from contextlib import closing

from alembic import command
import test_saas03_migration as fixture
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.services.device_auth import require_iot_schema


class IotMigrationTests(unittest.TestCase):
    snapshot = fixture.OrganizationMigrationTests.snapshot

    def setUp(self):
        fixture.OrganizationMigrationTests.setUp(self)
        command.upgrade(self.config,'s006identity')
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("""INSERT INTO measurements(id,device_id,boot_id,seq,weight_g,stable,calibration_version,
                received_at,zero_confirmed,organization_id)
                VALUES(77,'legacy-scale','boot',1,123,1,'cal-historical','2026-01-01',1,1)""")
            db.execute('UPDATE evaluations SET weight_pre_measurement_id=77 WHERE id=303')
            db.commit()

    def test_migracion_idempotente_preserva_historicos_y_requiere_aprovisionamiento(self):
        columns,before=self.snapshot(); photo=self.photo.read_bytes()
        command.upgrade(self.config,'head'); command.upgrade(self.config,'head')
        self.assertEqual(self.snapshot(columns)[1],before)
        self.assertEqual(self.photo.read_bytes(),photo)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT organization_id,device_id,is_active,credential_hash FROM iot_devices').fetchall(),[(1,'legacy-scale',0,None)])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        command.downgrade(self.config,'s006identity')
        self.assertEqual(self.snapshot()[1],before)

    def test_sin_migracion_iot_permanece_cerrado_con_503(self):
        engine=create_engine('sqlite:///'+str(self.database))
        try:
            with Session(engine) as db:
                with self.assertRaises(HTTPException) as error: require_iot_schema(db)
                self.assertEqual(error.exception.status_code,503)
        finally: engine.dispose()

    def test_fk_migrada_rechaza_medicion_y_estacion_cruzadas_y_reversion_con_secretos(self):
        command.upgrade(self.config,'head')
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute("INSERT INTO organizations VALUES(2,'B',1,'2026-01-01')")
            db.execute("INSERT INTO iot_stations VALUES(2,2,'other','B',1)")
            db.commit()
            for sql in ("UPDATE measurements SET organization_id=2 WHERE id=77",
                        "UPDATE iot_devices SET station_id=2 WHERE device_id='legacy-scale'"):
                with self.assertRaises(sqlite3.IntegrityError): db.execute(sql)
                db.rollback()
            db.execute("UPDATE iot_devices SET credential_hash=?",('a'*64,)); db.commit()
        with self.assertRaisesRegex(RuntimeError,'aprovisionados'):
            command.downgrade(self.config,'s006identity')


if __name__=='__main__': unittest.main()
