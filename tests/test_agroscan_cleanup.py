"""Mantenimiento exclusivamente sobre bases y fotografías sintéticas desechables."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import agroscan_cleanup as cleanup


class CleanupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='cleanup-synthetic-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.data = self.root / 'repo' / 'data'
        self.data.mkdir(parents=True)
        (self.data / 'images').mkdir()
        (self.data / 'images/test.jpg').write_bytes(b'synthetic-image-only')
        self.path = self.data / 'agroscan.db'
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript('''
                PRAGMA foreign_keys=ON;
                CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,password_hash TEXT);
                CREATE TABLE roles(id INTEGER PRIMARY KEY,name TEXT);
                CREATE TABLE user_roles(user_id INTEGER REFERENCES users,role_id INTEGER REFERENCES roles,PRIMARY KEY(user_id,role_id));
                CREATE TABLE organizations(id INTEGER PRIMARY KEY,name TEXT);
                CREATE TABLE organization_memberships(organization_id INTEGER REFERENCES organizations,user_id INTEGER REFERENCES users,PRIMARY KEY(organization_id,user_id));
                CREATE TABLE platform_owner(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users);
                CREATE TABLE google_identities(subject TEXT PRIMARY KEY,user_id INTEGER REFERENCES users);
                CREATE TABLE lots(id INTEGER PRIMARY KEY,code TEXT,organization_id INTEGER REFERENCES organizations);
                CREATE TABLE pieces(id INTEGER PRIMARY KEY,lot_id INTEGER REFERENCES lots ON DELETE CASCADE);
                CREATE TABLE evaluations(id INTEGER PRIMARY KEY,lot_id INTEGER REFERENCES lots,piece_ref_id INTEGER REFERENCES pieces);
                CREATE TABLE images(id INTEGER PRIMARY KEY,evaluation_id INTEGER REFERENCES evaluations,relative_path TEXT);
                CREATE TABLE reviews(id INTEGER PRIMARY KEY,evaluation_id INTEGER REFERENCES evaluations,actor_id INTEGER REFERENCES users);
                CREATE TABLE measurements(id INTEGER PRIMARY KEY,device_id TEXT,calibration_version TEXT);
                INSERT INTO users VALUES(1,'linked-operator','SYNTHETIC-HASH'),(2,'admin','SYNTHETIC-HASH'),(3,'owner','SYNTHETIC-HASH'),(4,'orphan','SYNTHETIC-HASH');
                INSERT INTO roles VALUES(1,'operador'),(2,'administrador');
                INSERT INTO user_roles VALUES(1,1),(2,2),(4,1);
                INSERT INTO organizations VALUES(1,'A'),(2,'B');
                INSERT INTO organization_memberships VALUES(1,1),(1,2);
                INSERT INTO platform_owner VALUES(1,3);
                INSERT INTO google_identities VALUES('synthetic-subject',4);
                INSERT INTO lots VALUES(1,'TEST-name-is-not-proof',1),(2,'historical',2),(3,'cascade',1);
                INSERT INTO pieces VALUES(1,1),(2,2),(3,3);
                INSERT INTO evaluations VALUES(1,1,1),(2,2,2);
                INSERT INTO images VALUES(1,1,'images/test.jpg');
                INSERT INTO reviews VALUES(1,1,1);
                INSERT INTO measurements VALUES(1,'demo-marker','demo-marker');
            ''')
        env = patch.dict(os.environ, {'AGROSCAN_DATA_DIR': str(self.data)})
        env.start()
        self.addCleanup(env.stop)
        root = patch.object(cleanup, 'ROOT', self.root / 'repo')
        root.start()
        self.addCleanup(root.stop)
        self.before = self.state()

    def state(self):
        with closing(cleanup.connect(self.path)) as db:
            return cleanup.snapshot(db)

    def plan(self, selections):
        state = self.state()
        entries = []
        for table, pk in selections:
            info = state['tables'][table]
            row = next(r for r in info['rows'] if tuple(r[k] for k in info['pk']) == tuple(pk))
            entries.append({'table': table, 'row_sha256': cleanup.digest(row),
                            'evidence': {'kind': 'user_confirmed', 'detail': 'Synthetic fixture explicitly disposable'}})
        path = self.root / 'plan.json'
        path.write_text(json.dumps({'database': str(self.path.resolve()),
                        'database_digest': state['database_digest'], 'selections': entries}), encoding='utf-8')
        return path

    def execute(self, plan):
        return cleanup.main(['--out', str(self.root / 'execution'), '--plan', str(plan),
                             '--execute', '--maintenance-confirmed', '--confirm-plan-sha256', cleanup.file_hash(plan)])

    def test_inventory_dry_run_does_not_classify_by_name_or_modify_database(self):
        self.assertEqual(cleanup.main(['--out', str(self.root / 'inventory')]), 0)
        self.assertEqual(self.state()['database_digest'], self.before['database_digest'])
        report = json.loads((self.root / 'inventory/inventory.json').read_text(encoding='utf-8'))
        self.assertEqual(report['tables']['lots']['records'][0]['classification'], 'pending_origin_confirmation')
        self.assertEqual(report['orphan_operators'], [{'id': 4, 'username': 'orphan'}])
        self.assertNotIn('SYNTHETIC-HASH', json.dumps(report))
        with closing(cleanup.connect(self.root / 'inventory/agroscan-before.sqlite')) as db:
            self.assertEqual(cleanup.snapshot(db)['database_digest'], self.before['database_digest'])

    def test_exact_filtered_cleanup_preserves_b_and_physical_images(self):
        plan = self.plan([('lots', (1,)), ('pieces', (1,)), ('evaluations', (1,)), ('images', (1,)), ('reviews', (1,))])
        cleanup.main(['--out', str(self.root / 'dry'), '--plan', str(plan)])
        self.assertEqual(self.state()['database_digest'], self.before['database_digest'])
        self.assertEqual(self.execute(plan), 0)
        state = self.state()
        self.assertEqual([r['id'] for r in state['tables']['lots']['rows']], [2, 3])
        self.assertEqual(state['tables']['users'], self.before['tables']['users'])
        self.assertEqual((self.data / 'images/test.jpg').read_bytes(), b'synthetic-image-only')
        result = json.loads((self.root / 'execution/execution.json').read_text())
        self.assertEqual(result['deleted_by_table'], {'lots': 1, 'pieces': 1, 'evaluations': 1, 'images': 1, 'reviews': 1})
        self.assertEqual(result['physical_files_deleted'], 0)

    def test_missing_dependents_rolls_back(self):
        plan = self.plan([('evaluations', (1,))])
        with self.assertRaises(ValueError):
            self.execute(plan)
        self.assertEqual(self.state()['database_digest'], self.before['database_digest'])

    def test_implicit_cascade_cannot_remove_unapproved_rows(self):
        plan = self.plan([('lots', (3,))])
        with self.assertRaisesRegex(ValueError, 'no autorizadas'):
            self.execute(plan)
        self.assertEqual(self.state()['database_digest'], self.before['database_digest'])

    def test_trigger_cannot_modify_protected_company(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("CREATE TRIGGER mutate_company AFTER DELETE ON measurements BEGIN UPDATE organizations SET name='changed'; END")
        before = self.state()['database_digest']
        with self.assertRaisesRegex(ValueError, 'no autorizadas'):
            self.execute(self.plan([('measurements', (1,))]))
        self.assertEqual(self.state()['database_digest'], before)

    def test_only_orphan_operator_and_its_authentication_links_can_be_deleted(self):
        self.assertEqual(self.execute(self.plan([('users', (4,)), ('user_roles', (4, 1)),
                                               ('google_identities', ('synthetic-subject',))])), 0)
        self.assertEqual([r['id'] for r in self.state()['tables']['users']['rows']], [1, 2, 3])

    def test_owner_admin_and_linked_operator_are_protected(self):
        for uid in (1, 2, 3):
            with self.subTest(uid=uid), closing(cleanup.connect(self.path)) as db:
                plan = json.loads(self.plan([('users', (uid,))]).read_text())
                chosen = cleanup.selected_rows(self.before, plan, self.path)
                with self.assertRaises(ValueError):
                    cleanup.validate_user(db, chosen)

    def test_historical_reference_blocks_orphan_user_even_when_selected_for_cleanup(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('UPDATE reviews SET actor_id=4 WHERE id=1')
            db.commit()
        with self.assertRaisesRegex(ValueError, 'históricas'):
            self.execute(self.plan([('users', (4,)), ('reviews', (1,))]))

    def test_stale_plan_unconfirmed_origin_and_protected_table_are_rejected(self):
        plan = self.plan([('measurements', (1,))])
        raw = json.loads(plan.read_text())
        with closing(cleanup.connect(self.path)) as db:
            for change in ('stale', 'unconfirmed', 'protected'):
                item = json.loads(json.dumps(raw))
                if change == 'stale': item['database_digest'] = '0' * 64
                elif change == 'unconfirmed': item['selections'][0]['evidence']['kind'] = 'name_only'
                else: item['selections'][0]['table'] = 'organizations'
                with self.subTest(change=change), self.assertRaises(ValueError):
                    cleanup.selected_rows(self.before, item, self.path)
        with self.assertRaises(SystemExit):
            cleanup.main(['--out', str(self.root / 'blocked'), '--plan', str(plan), '--execute'])

    def test_unsafe_image_paths_and_backup_inside_repository_are_rejected(self):
        state = self.state()
        state['tables']['images']['rows'][0]['relative_path'] = '../outside.jpg'
        self.assertEqual(cleanup.image_files(state, self.data)[0]['status'], 'pending')
        with self.assertRaises(ValueError):
            cleanup.private_directory(self.data / 'backup')

    def test_database_change_after_review_requires_new_inventory(self):
        plan = self.plan([('measurements', (1,))])
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE organizations SET name='new valid state' WHERE id=2")
            db.commit()
        changed = self.state()['database_digest']
        with self.assertRaisesRegex(ValueError, 'base cambió'):
            self.execute(plan)
        self.assertEqual(self.state()['database_digest'], changed)

    def test_authentication_links_cannot_be_deleted_without_the_selected_user(self):
        with self.assertRaisesRegex(ValueError, 'relaciones'):
            self.execute(self.plan([('user_roles', (4, 1))]))


if __name__ == '__main__':
    unittest.main()
