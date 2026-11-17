"""Solo el delta SaaS-04; reutiliza el histórico sintético de SaaS-03."""
import hashlib
import sqlite3
import unittest
from contextlib import closing

from alembic import command
import test_saas03_migration as migration_fixture


class PermissionMigrationTests(unittest.TestCase):
    snapshot = migration_fixture.OrganizationMigrationTests.snapshot

    def setUp(self):
        migration_fixture.OrganizationMigrationTests.setUp(self)
        command.upgrade(self.config, 's003organizations')

    def test_preserva_historicos_accesos_y_no_promueve_administradores(self):
        columns, before = self.snapshot()
        photo = hashlib.sha256(self.photo.read_bytes()).hexdigest()
        command.upgrade(self.config, 'head')
        command.upgrade(self.config, 'head')
        self.assertEqual(self.snapshot(columns)[1], before)
        self.assertEqual(hashlib.sha256(self.photo.read_bytes()).hexdigest(), photo)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT * FROM platform_owner').fetchall(), [])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        command.downgrade(self.config, 's003organizations')
        self.assertEqual(self.snapshot()[1], before)

    def test_reversion_no_pierde_propietario_y_se_permite_solo_sin_asignacion(self):
        command.upgrade(self.config, 'head')
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("INSERT INTO platform_owner VALUES (1,42,'2026-01-01')")
            db.commit()
        with self.assertRaisesRegex(RuntimeError, 'propietario'):
            command.downgrade(self.config, 's003organizations')
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT user_id FROM platform_owner').fetchone()[0], 42)
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0], 's004roles')
            db.execute('DELETE FROM platform_owner')
            db.commit()
        command.downgrade(self.config, 's003organizations')
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0], 's003organizations')
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='platform_owner'").fetchone())


if __name__ == '__main__':
    unittest.main()
