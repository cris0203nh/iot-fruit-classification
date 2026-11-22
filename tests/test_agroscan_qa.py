"""Guardas y creación de QA, siempre sobre SQLite temporal independiente."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import agroscan_qa as qa


class QaEnvironmentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='qa-fixture-')
        self.addCleanup(temp.cleanup)
        self.qa = Path(temp.name) / 'private-qa'
        self.qa.mkdir()
        self.database = self.qa / 'data/agroscan.db'
        (self.qa / 'manifest.json').write_text(json.dumps({'instance': 'synthetic-instance', 'ready': False}))
        root = patch.object(qa, 'QA_ROOT', self.qa)
        root.start()
        self.addCleanup(root.stop)
        self.environment = {'AGROSCAN_QA_ROOT': str(self.qa), 'AGROSCAN_QA_INSTANCE': 'synthetic-instance',
            'AGROSCAN_DATA_DIR': str(self.database.parent), 'AGROSCAN_DATABASE_URL': 'sqlite:///' + self.database.as_posix(),
            'AGROSCAN_JWT_SECRET': secrets.token_hex(32), 'AGROSCAN_ENVIRONMENT': 'demo',
            'AGROSCAN_SUBSCRIPTION_SIMULATOR': 'true', 'AGROSCAN_SMTP_ENABLED': 'false', 'PYTHONIOENCODING': 'utf-8'}
        env = patch.dict(os.environ, self.environment)
        env.start()
        self.addCleanup(env.stop)

    def test_configuration_requires_explicit_identity_paths_and_demo_flags(self):
        self.assertEqual(qa.configuration()[1], self.database)
        self.assertEqual(os.environ['AGROSCAN_GOOGLE_CLIENT_ID'], '')
        for name, value in (('AGROSCAN_QA_ROOT', ''), ('AGROSCAN_QA_INSTANCE', 'other'),
                            ('AGROSCAN_DATA_DIR', str(qa.ROOT / 'backend/data')),
                            ('AGROSCAN_DATABASE_URL', 'sqlite:///backend/data/agroscan.db'),
                            ('AGROSCAN_ENVIRONMENT', 'production'), ('AGROSCAN_SUBSCRIPTION_SIMULATOR', 'false'),
                            ('AGROSCAN_JWT_SECRET', 'short')):
            with self.subTest(name=name), patch.dict(os.environ, {name: value}), self.assertRaises(ValueError):
                qa.configuration()
        self.assertFalse(self.database.exists())

    def test_pending_initialization_never_starts_or_creates_database(self):
        with self.assertRaisesRegex(ValueError, 'incompleta'):
            qa.serve()
        self.assertFalse(self.database.exists())

    def test_check_does_not_create_missing_database(self):
        self.database.parent.mkdir()
        with self.assertRaises(sqlite3.OperationalError):
            qa.check_database(self.database)
        self.assertFalse(self.database.exists())

    def test_real_migrations_four_roles_empty_operations_and_no_reset(self):
        accounts = {role: {'username': 'test_' + role, 'password': secrets.token_urlsafe(32)}
                    for role in ('propietario', 'administrador', 'operador', 'revisor')}
        code = "import sys,os; from pathlib import Path; sys.path.insert(0,'tools'); import agroscan_qa as q; q.QA_ROOT=Path(os.environ['AGROSCAN_QA_ROOT']); q.initialize()"
        result = subprocess.run([sys.executable, '-c', code], input=json.dumps(accounts),
            cwd=qa.ROOT, env={**os.environ, **self.environment}, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        for account in accounts.values():
            self.assertNotIn(account['password'], result.stdout + result.stderr)
        self.assertTrue(json.loads((self.qa / 'manifest.json').read_text(encoding='utf-8'))['ready'])
        self.assertFalse(any(qa.check_database(self.database, empty=True).values()))
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0], 4)
            self.assertEqual(db.execute('SELECT count(*) FROM organizations').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT count(*) FROM organization_memberships').fetchone()[0], 3)
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_plans').fetchone()[0], 3)
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_orders').fetchone()[0], 0)
            owner = db.execute('SELECT user_id FROM platform_owner').fetchone()[0]
            self.assertEqual(db.execute('SELECT count(*) FROM organization_memberships WHERE user_id=?', (owner,)).fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM user_roles WHERE user_id=?', (owner,)).fetchone()[0], 0)
            for role in ('administrador', 'operador', 'revisor'):
                self.assertEqual(db.execute('''SELECT r.name,m.organization_id FROM organization_memberships m
                    JOIN roles r ON r.id=m.role_id JOIN users u ON u.id=m.user_id WHERE u.username=?''',
                    ('test_' + role,)).fetchall(), [(role, 1)])
            before = db.execute('SELECT id,password_hash FROM users ORDER BY id').fetchall()
        again = subprocess.run([sys.executable, '-c', code], input=json.dumps(accounts), cwd=qa.ROOT,
            env={**os.environ, **self.environment}, capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(again.returncode, 0)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(before, db.execute('SELECT id,password_hash FROM users ORDER BY id').fetchall())

    def test_verifier_preserves_populated_qa_and_runs_on_disposable_copy(self):
        accounts = {role: {'username': 'test_' + role, 'password': secrets.token_urlsafe(32)}
                    for role in ('propietario', 'administrador', 'operador', 'revisor')}
        initialize = "import sys,os; from pathlib import Path; sys.path.insert(0,'tools'); import agroscan_qa as q; q.QA_ROOT=Path(os.environ['AGROSCAN_QA_ROOT']); q.initialize()"
        result = subprocess.run([sys.executable, '-c', initialize], input=json.dumps(accounts), cwd=qa.ROOT,
            env={**os.environ, **self.environment}, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        exercise = '''
import sys,os,json,hashlib
from pathlib import Path
sys.path[:0]=['tools','backend']
import agroscan_qa as q
q.QA_ROOT=Path(os.environ['AGROSCAN_QA_ROOT'])
from app.main import app
from app.database import engine
from app.database import SessionLocal
from app.models import Lot,Piece,Evaluation,Image
from fastapi.testclient import TestClient
accounts=json.load(sys.stdin)
with TestClient(app) as client:
    login=client.post('/api/auth/login',data=accounts['administrador'])
    assert login.status_code==200
    headers={'Authorization':'Bearer '+login.json()['access_token']}
    plan=client.get('/api/commercial/plans').json()['plans'][0]
    order=client.post('/api/commercial/orders',headers=headers,json={'planId':plan['id'],'action':'subscribe','idempotencyKey':'existing-synthetic-history'})
    assert order.status_code==201
    assert client.post('/api/commercial/orders/'+order.json()['id']+'/confirm',headers=headers,json={'scenario':'approve'}).status_code==200
photo=q.QA_ROOT/'data/images/com07-keep/evidence.jpg'
photo.parent.mkdir(parents=True)
content=b'COM07-SYNTHETIC-PHOTO-ONLY'
photo.write_bytes(content)
with SessionLocal() as db:
    lot=Lot(organization_id=1,code='COM07-KEEP',product='mango');db.add(lot);db.flush()
    piece=Piece(organization_id=1,lot_id=lot.id,code='COM07-KEEP');db.add(piece);db.flush()
    evaluation=Evaluation(organization_id=1,lot_id=lot.id,piece_ref_id=piece.id,piece_id=piece.code,product='mango',status='pending_review',image_count=1)
    db.add(evaluation);db.flush()
    db.add(Image(organization_id=1,evaluation_id=evaluation.id,view='front',relative_path='images/com07-keep/evidence.jpg',content_type='image/jpeg',size_bytes=len(content)));db.commit()
engine.dispose()
database=q.QA_ROOT/'data/agroscan.db'
before=hashlib.sha256(database.read_bytes()).hexdigest()
# Verifier imports the engine after selecting the disposable DB; use a fresh process below.
print(before)
'''
        seeded = subprocess.run([sys.executable, '-c', exercise], input=json.dumps(accounts), cwd=qa.ROOT,
            env={**os.environ, **self.environment}, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(seeded.returncode, 0, seeded.stderr)
        verify = "import sys,os; from pathlib import Path; sys.path.insert(0,'tools'); import agroscan_qa as q; q.QA_ROOT=Path(os.environ['AGROSCAN_QA_ROOT']); import agroscan_qa_verify as v; v.QA_ROOT=q.QA_ROOT; v.main()"
        checked = subprocess.run([sys.executable, '-c', verify], input=json.dumps(accounts), cwd=qa.ROOT,
            env={**os.environ, **self.environment}, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(), seeded.stdout.strip())
        report = json.loads((self.qa / 'commerce-verification.json').read_text(encoding='utf-8'))
        self.assertTrue(report['qaDatabaseUnchanged'])
        self.assertEqual(report['ordersAddedOnCopy'], 7)
        self.assertFalse(report['browserExecuted'])
        self.assertEqual(report['qaPhotoFilesVerified'], 1)
        self.assertEqual((self.qa / 'data/images/com07-keep/evidence.jpg').read_bytes(), b'COM07-SYNTHETIC-PHOTO-ONLY')
        for account in accounts.values():
            self.assertNotIn(account['password'], checked.stdout + checked.stderr)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_orders').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0], 4)


if __name__ == '__main__':
    unittest.main()
