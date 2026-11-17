import sqlite3
import unittest
from contextlib import closing
from alembic import command
import test_saas03_migration as fixture


class IdentityMigrationTests(unittest.TestCase):
    snapshot=fixture.OrganizationMigrationTests.snapshot
    def setUp(self):
        fixture.OrganizationMigrationTests.setUp(self)
        command.upgrade(self.config,'s004roles')

    def test_solo_agrega_tablas_preservando_usuario_propietario_y_historicos(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("INSERT INTO platform_owner VALUES(1,42,'2026-01-01')"); db.commit()
        columns,before=self.snapshot()
        photo=self.photo.read_bytes()
        command.upgrade(self.config,'head'); command.upgrade(self.config,'head')
        self.assertEqual(self.snapshot(columns)[1],before)
        self.assertEqual(self.photo.read_bytes(),photo)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            for table in ('google_identities','google_challenges','organization_invitations'):
                self.assertEqual(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0],0)
        command.downgrade(self.config,'s004roles')
        self.assertEqual(self.snapshot()[1],before)

    def test_reversion_no_borra_identidades_vinculadas(self):
        command.upgrade(self.config,'head')
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("INSERT INTO google_identities VALUES('google-sub',42,'legacy@example.test','2026-01-01')"); db.commit()
        with self.assertRaisesRegex(RuntimeError,'identidades'):
            command.downgrade(self.config,'s004roles')


if __name__=='__main__': unittest.main()
