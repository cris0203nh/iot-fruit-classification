"""Regresión de deriva Alembic/ORM; SQLite y fotografías exclusivamente sintéticas."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class ImageMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='com07-migration-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'agroscan.db'
        self.env = {**os.environ, 'AGROSCAN_DATABASE_URL': 'sqlite:///' + self.path.as_posix(),
                    'AGROSCAN_DATA_DIR': str(self.root), 'AGROSCAN_SMTP_ENABLED': 'false'}
        self.backend = Path(__file__).resolve().parents[1]
        self.run_migration('upgrade', 'c014onboarding')
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute("INSERT INTO lots(id,code,product,status,responsible,created_at,organization_id) VALUES(1,'KEEP','mango','open','Synthetic','2026-11-20',1)")
            db.execute("INSERT INTO evaluations(id,lot_id,piece_id,product,status,image_count,created_at,organization_id) VALUES(1,1,'KEEP','mango','pending_review',1,'2026-11-20',1)")
            db.execute("INSERT INTO images(id,evaluation_id,view,relative_path,content_type,size_bytes,created_at,organization_id) VALUES(1,1,'front','images/keep.jpg','image/jpeg',9,'2026-11-20',1)")
            db.commit()
            self.before = db.execute('SELECT * FROM images').fetchall()
        self.photo = self.root / 'images/keep.jpg'
        self.photo.parent.mkdir()
        self.photo.write_bytes(b'SYNTHETIC')
        self.photo_hash = hashlib.sha256(self.photo.read_bytes()).hexdigest()

    def run_migration(self, *args, succeeds=True):
        result = subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=self.backend, env=self.env,
                                capture_output=True, text=True)
        if succeeds:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def test_upgrade_preserves_ids_metadata_photo_and_enforces_idempotency(self):
        with closing(sqlite3.connect(self.path)) as db:
            self.assertNotIn('idempotency_key', [c[1] for c in db.execute('PRAGMA table_info(images)')])
        self.run_migration('upgrade', 'head')
        self.run_migration('upgrade', 'head')
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            row = db.execute('SELECT * FROM images WHERE id=1').fetchone()
            self.assertEqual(row[:-1], self.before[0])
            self.assertIsNone(row[-1])
            db.execute('UPDATE images SET idempotency_key=? WHERE id=1', ('a'*64,))
            db.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO images(evaluation_id,view,relative_path,content_type,size_bytes,created_at,organization_id,idempotency_key) VALUES(1,'front','other.jpg','image/jpeg',1,'2026-11-20',1,?)", ('a'*64,))
            db.rollback()
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.run_migration('downgrade', 'c014onboarding', succeeds=False)
        self.assertEqual(hashlib.sha256(self.photo.read_bytes()).hexdigest(), self.photo_hash)

    def test_downgrade_without_registered_keys_preserves_legacy_rows(self):
        self.run_migration('upgrade', 'head')
        self.run_migration('downgrade', 'c014onboarding')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT * FROM images').fetchall(), self.before)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(hashlib.sha256(self.photo.read_bytes()).hexdigest(), self.photo_hash)

    def test_duplicate_existing_keys_block_migration_without_deleting_data(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('ALTER TABLE images ADD COLUMN idempotency_key VARCHAR(64)')
            db.execute('UPDATE images SET idempotency_key=?', ('b'*64,))
            db.execute("INSERT INTO images(evaluation_id,view,relative_path,content_type,size_bytes,created_at,organization_id,idempotency_key) VALUES(1,'front','duplicate.jpg','image/jpeg',1,'2026-11-20',1,?)", ('b'*64,))
            db.commit()
        self.run_migration('upgrade', 'head', succeeds=False)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM images').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0], 'c014onboarding')
