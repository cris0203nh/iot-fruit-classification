"""Migraciones reales Alembic sobre SQLite sintético, nunca la base original."""
import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config


PREVIOUS = 'b055a1b2c3d4'


class OrganizationMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='saas03-migration-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database = self.root / 'migration.db'
        backend = Path(__file__).resolve().parents[1]
        self.config = Config(str(backend / 'alembic.ini'))
        self.config.set_main_option('script_location', str(backend / 'alembic'))
        env = patch.dict('os.environ', {'AGROSCAN_DATABASE_URL': 'sqlite:///' + self.database.as_posix()})
        env.start()
        self.addCleanup(env.stop)
        command.upgrade(self.config, PREVIOUS)
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute("INSERT INTO roles VALUES (10, 'administrador')")
            db.execute("INSERT INTO roles VALUES (11, 'operador')")
            db.execute("INSERT INTO users VALUES (42, 'legacy', 'HASH-SINTETICO', 'Legacy', 1, '2026-01-01')")
            db.executemany('INSERT INTO user_roles VALUES (?,?)', [(42, 10), (42, 11)])
            db.execute("INSERT INTO lots VALUES (101, 'HISTORY', 'mango', 'open', 'Legacy', '2026-01-01')")
            db.execute("INSERT INTO pieces VALUES (202, 101, 'P-OLD', 'registered', '2026-01-01')")
            db.execute("INSERT INTO evaluations(id,lot_id,piece_id,piece_ref_id,product,status,image_count,created_at) VALUES (303,101,'P-OLD',202,'mango','pending_review',1,'2026-01-01')")
            db.execute("INSERT INTO images(id,evaluation_id,view,relative_path,content_type,size_bytes,created_at) VALUES (404,303,'front','images/old.jpg','image/jpeg',9,'2026-01-01')")
            db.execute("INSERT INTO reviews VALUES (505,303,'review','legacy','Evidencia histórica','E0','E1','2026-01-01')")
            db.execute("INSERT INTO review_decision_evidence VALUES (505,303,404,?,'correct','legacy-request',?)", ('a'*64, 'b'*64))
            db.commit()
        self.photo = self.root / 'images/old.jpg'
        self.photo.parent.mkdir()
        self.photo.write_bytes(b'OLD-PHOTO')

    def snapshot(self, columns=None):
        with closing(sqlite3.connect(self.database)) as db:
            if columns is None:
                tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'")]
                columns = {t: [r[1] for r in db.execute(f'PRAGMA table_info("{t}")')] for t in tables}
            rows = {}
            for table, names in columns.items():
                projection = ','.join(f'"{name}"' for name in names)
                rows[table] = db.execute(f'SELECT {projection} FROM "{table}" ORDER BY rowid').fetchall()
            return columns, rows

    def test_upgrade_preserva_ids_hashes_trazabilidad_y_no_duplica_al_repetir(self):
        columns, before = self.snapshot()
        photo_hash = hashlib.sha256(self.photo.read_bytes()).hexdigest()
        command.upgrade(self.config, 'head')
        command.upgrade(self.config, 'head')
        self.assertEqual(self.snapshot(columns)[1], before)
        self.assertEqual(hashlib.sha256(self.photo.read_bytes()).hexdigest(), photo_hash)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT id,name FROM organizations').fetchall(), [(1, 'AgroScan Inicial')])
            self.assertEqual(db.execute('SELECT organization_id,user_id,role_id FROM organization_memberships ORDER BY role_id').fetchall(), [(1,42,10),(1,42,11)])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            for table in ('lots','pieces','evaluations','images','reviews','review_decision_evidence'):
                self.assertEqual(db.execute(f'SELECT DISTINCT organization_id FROM {table}').fetchall(), [(1,)])
        command.downgrade(self.config, PREVIOUS)
        self.assertEqual(self.snapshot()[1], before)
        command.upgrade(self.config, 'head')

    def test_restricciones_migradas_rechazan_cruces_y_permiten_codigos_por_empresa(self):
        command.upgrade(self.config, 'head')
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute("INSERT INTO organizations VALUES (2,'B',1,'2026-01-01')")
            db.execute("INSERT INTO lots VALUES (102,'HISTORY','mango','open','B','2026-01-01',2)")
            db.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO lots VALUES (103,'history','mango','open','A','2026-01-01',1)")
            db.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('UPDATE images SET organization_id=2 WHERE id=404')
            db.rollback()
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        with self.assertRaisesRegex(RuntimeError, 'organizaciones adicionales'):
            command.downgrade(self.config, PREVIOUS)

    def test_preflight_rechaza_relacion_indirecta_invalida_sin_migracion_parcial(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("INSERT INTO lots VALUES (102,'OTHER','mango','open','B','2026-01-01')")
            db.execute('UPDATE pieces SET lot_id=102 WHERE id=202')
            db.commit()
        _, before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, 'indirecta inconsistente'):
            command.upgrade(self.config, 'head')
        self.assertEqual(self.snapshot()[1], before)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0], PREVIOUS)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='organizations'").fetchone())


if __name__ == '__main__':
    unittest.main()
