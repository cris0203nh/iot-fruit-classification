"""Migracion reversible en SQLite temporal; conserva todas las filas existentes."""
from contextlib import closing
import sqlite3
import unittest
import test_com07_image_migration as migration_fixture


class SessionMigrationTests(unittest.TestCase):
    setUp = migration_fixture.ImageMigrationTests.setUp
    run_migration = migration_fixture.ImageMigrationTests.run_migration

    def test_upgrade_and_downgrade_preserve_every_existing_table(self):
        self.run_migration('upgrade', 'c015imagekey')
        with closing(sqlite3.connect(self.path)) as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                      if row[0] != 'alembic_version']
            before = {table: db.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall() for table in tables}
        self.run_migration('upgrade', 'a016sessions')
        self.run_migration('upgrade', 'a016sessions')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM browser_sessions').fetchone(), (0,))
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            for table, rows in before.items():
                self.assertEqual(db.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall(), rows)
        self.run_migration('downgrade', 'c015imagekey')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE name='browser_sessions'").fetchone(), (0,))
            for table, rows in before.items():
                self.assertEqual(db.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall(), rows)
