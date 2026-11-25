"""Guardas del desarrollo local, siempre con SQLite temporal."""
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
import agroscan_dev as dev


class DevelopmentSmtpLauncherTests(unittest.TestCase):
    def test_launcher_preserves_explicit_smtp_opt_in_and_defaults_disabled(self):
        # Evalúa los bloques originales del lanzador y ejecuta un hijo real.
        # No invoca prepare/serve, no usa secretos reales ni abre SQLite/SMTP.
        script = (dev.ROOT / 'tools/agroscan_dev.ps1').as_posix().replace("'", "''")
        python = sys.executable.replace("'", "''")
        harness = r'''
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile('__SCRIPT__', [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Launcher syntax error' }
$assignment = $ast.Find({param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -eq '$environment'}, $true)
$outer = @($ast.EndBlock.Statements | Where-Object { $_ -is [System.Management.Automation.Language.TryStatementAst] })[0]
function Import-Clixml { ConvertTo-SecureString ('x' * 48) -AsPlainText -Force }
$dev = 'C:\synthetic-dev'; $secret = 'unused-synthetic.clixml'
$before = [Environment]::GetEnvironmentVariable('AGROSCAN_SMTP_ENABLED', 'Process')
$previous = @{}
Invoke-Expression $assignment.Extent.Text
Invoke-Expression $outer.Body.Statements[0].Extent.Text
$probe = 'import os,json;print(json.dumps({"enabled":os.getenv("AGROSCAN_SMTP_ENABLED"),"hostInherited":os.getenv("AGROSCAN_SMTP_HOST")=="smtp.example.test","passwordInherited":os.getenv("AGROSCAN_SMTP_PASSWORD")=="synthetic-only","fromInherited":os.getenv("AGROSCAN_SMTP_FROM")=="sender@example.test","timeoutInherited":os.getenv("AGROSCAN_SMTP_TIMEOUT_SECONDS")=="15"}))'
$probe | & '__PYTHON__' -B -
if ($LASTEXITCODE -ne 0) { throw 'Child probe failed' }
foreach ($statement in $outer.Finally.Statements) { Invoke-Expression $statement.Extent.Text }
if ([Environment]::GetEnvironmentVariable('AGROSCAN_SMTP_ENABLED', 'Process') -cne $before) { throw 'Environment not restored' }
'''.replace('__SCRIPT__', script).replace('__PYTHON__', python)
        for value, expected in ((None, 'false'), ('false', 'false'), ('true', 'true'), ('TRUE', 'false')):
            with self.subTest(enabled=value):
                environment = {**os.environ, 'AGROSCAN_SMTP_HOST':'smtp.example.test',
                    'AGROSCAN_SMTP_FROM':'sender@example.test', 'AGROSCAN_SMTP_PASSWORD':'synthetic-only',
                    'AGROSCAN_SMTP_TIMEOUT_SECONDS':'15'}
                environment.pop('AGROSCAN_SMTP_ENABLED', None)
                if value is not None:
                    environment['AGROSCAN_SMTP_ENABLED'] = value
                result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', harness],
                                        env=environment, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                status = json.loads(result.stdout)
                self.assertEqual(status, {'enabled':expected, 'hostInherited':True,
                                         'passwordInherited':True, 'fromInherited':True, 'timeoutInherited':True})
                self.assertNotIn('synthetic-only', result.stdout)


class DevelopmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='auth01r5-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.private = self.root / 'development'
        self.private.mkdir()
        self.source = self.root / 'source/agroscan.db'
        self.source.parent.mkdir()
        self.database = self.private / 'data/agroscan.db'
        self.environment = {'AGROSCAN_DEV_ROOT':str(self.private), 'AGROSCAN_DATA_DIR':str(self.database.parent),
            'AGROSCAN_DATABASE_URL':'sqlite:///'+self.database.as_posix(), 'AGROSCAN_ENVIRONMENT':'demo',
            'AGROSCAN_SESSION_ALLOW_LOOPBACK_HTTP':'true','AGROSCAN_JWT_SECRET':secrets.token_hex(32)}
        for mock in (patch.object(dev,'DEV_ROOT',self.private),
                     patch.dict(os.environ,self.environment)):
            mock.start(); self.addCleanup(mock.stop)

    def test_wrong_paths_or_missing_opt_in_cannot_create_database(self):
        for name,value in [('AGROSCAN_DEV_ROOT',''),('AGROSCAN_DATA_DIR',str(dev.ROOT/'backend/data')),
                           ('AGROSCAN_DATABASE_URL','sqlite:///backend/data/agroscan.db'),
                           ('AGROSCAN_SESSION_ALLOW_LOOPBACK_HTTP','false'),('AGROSCAN_JWT_SECRET','short')]:
            with self.subTest(name=name),patch.dict(os.environ,{name:value}),self.assertRaises(ValueError):
                dev.prepare()
        self.assertFalse(self.database.exists())

    def test_existing_database_without_marker_is_never_replaced(self):
        self.database.parent.mkdir()
        self.database.write_bytes(b'synthetic-existing-do-not-replace')
        with self.assertRaises(ValueError): dev.prepare()
        self.assertEqual(self.database.read_bytes(),b'synthetic-existing-do-not-replace')

    def test_missing_database_does_not_copy_or_create_data(self):
        with self.assertRaisesRegex(ValueError,'no se copia QA'): dev.prepare()
        self.assertFalse(self.database.exists())

    def test_existing_dev_preserves_accounts_and_is_repeatable(self):
        source_env={**os.environ,'AGROSCAN_DATA_DIR':str(self.source.parent),
                    'AGROSCAN_DATABASE_URL':'sqlite:///'+self.source.as_posix()}
        subprocess.run([sys.executable,'-m','alembic','upgrade',dev.SCHEMA],cwd=dev.ROOT/'backend',env=source_env,
                       check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        with closing(sqlite3.connect(self.source)) as db:
            db.execute("INSERT INTO users(id,username,full_name,password_hash,is_active) VALUES(100,'synthetic','Synthetic','synthetic-hash',1)")
            db.execute("INSERT INTO roles(id,name) VALUES(100,'operador')")
            db.execute('INSERT INTO organization_memberships(user_id,organization_id,role_id,is_active) VALUES(100,1,100,1)')
            db.execute("INSERT INTO browser_sessions(token_hash,user_id,password_fingerprint,created_at,expires_at,absolute_expires_at) VALUES(?,100,?,'2026-01-01','2099-01-01','2099-01-01')",('a'*64,'b'*64))
            db.commit()
            expected=db.execute('SELECT * FROM users').fetchall()
            memberships=db.execute('SELECT * FROM organization_memberships').fetchall()
        self.database.parent.mkdir()
        with closing(sqlite3.connect(self.source)) as source, closing(sqlite3.connect(self.database)) as target:
            source.backup(target)
        (self.private/'manifest.json').write_text('{"ready":true,"instance":"synthetic"}')
        digest=hashlib.sha256(self.source.read_bytes()).hexdigest()
        dev.prepare()
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute('SELECT * FROM users').fetchall(),expected)
            self.assertEqual(db.execute('SELECT * FROM organization_memberships').fetchall(),memberships)
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone(),(dev.SCHEMA,))
            self.assertIsNone(db.execute('SELECT revoked_at FROM browser_sessions').fetchone()[0])
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),digest)
        before=hashlib.sha256(self.database.read_bytes()).hexdigest()
        dev.prepare()
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(),before)
