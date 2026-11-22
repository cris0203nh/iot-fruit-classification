"""Solicitudes públicas sin aprovisionamiento; datos sintéticos y SQLite temporal."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
import test_saas03_organizations as fixture
from app.application_models import CommercialApplication, CommercialApplicationAttempt
from app.routers.commercial import now
from app.bootstrap_owner import assign_first_owner


class ApplicationTests(unittest.TestCase):
    setUpClass = fixture.OrganizationIsolationTests.__dict__['setUpClass']
    auth = fixture.OrganizationIsolationTests.auth
    restore_override = fixture.OrganizationIsolationTests.restore_override

    def setUp(self):
        fixture.OrganizationIsolationTests.setUp(self)
        with self.Session() as db:
            assign_first_owner(db, self.users['without_membership'])
        self.owner = self.auth('without_membership')
        result = self.client.post('/api/platform/commercial/plans', headers=self.owner, json={
            'code':'com02','name':'Plan de ensayo','description':'Condiciones DEMO', 'amountCents':9900,
            'period':'monthly','benefits':['Trazabilidad']})
        self.assertEqual(result.status_code, 201, result.text)
        self.plan = result.json()
        self.body = {'companyName':'Empresa solicitante sintética','contactName':'Persona de ensayo',
                     'contactEmail':'contact@example.test','requestedPlanId':self.plan['id'],
                     'requestedPeriod':'monthly','idempotencyKey':str(uuid.uuid4())}
        self.before = self.protected()

    def protected(self):
        with closing(sqlite3.connect(self.root/'test.db')) as db:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                      if not r[0].startswith(('commercial_application','sqlite_'))]
            return {t: db.execute(f'SELECT * FROM "{t}" ORDER BY rowid').fetchall() for t in tables}

    def submit(self, **changes):
        return self.client.post('/api/commercial/applications', json={**self.body, **changes})

    def test_valid_public_receipt_and_owner_details_without_provisioning(self):
        result = self.submit()
        self.assertEqual(result.status_code, 201, result.text)
        self.assertEqual(set(result.json()), {'id','status','message','ownerNotification'})
        self.assertEqual(result.json()['ownerNotification'],'disabled')
        self.assertEqual(result.json()['message'], 'Solicitud recibida, pendiente de revisión')
        self.assertNotIn('contact@example.test', result.text)
        self.assertEqual(self.protected(), self.before)
        owner = self.client.get('/api/platform/commercial/applications', headers=self.owner)
        self.assertEqual(owner.status_code, 200, owner.text)
        self.assertEqual(owner.headers['cache-control'], 'no-store')
        item = owner.json()['items'][0]
        self.assertEqual(item['contactEmail'], self.body['contactEmail'])
        self.assertEqual(item['requestedPeriod'], 'monthly')
        self.assertEqual(item['plan']['amountCents'], 9900)
        self.assertNotIn('idempotency_hash', owner.text)

    def test_idempotency_duplicates_and_private_state_not_exposed(self):
        first = self.submit()
        repeat = self.submit()
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(repeat.json(), first.json())
        self.assertEqual(self.submit(companyName='Different company').status_code, 409)
        self.assertEqual(self.submit(idempotencyKey=str(uuid.uuid4())).status_code, 409)
        with self.Session() as db:
            row = db.scalar(select(CommercialApplication))
            self.assertNotEqual(row.idempotency_hash, self.body['idempotencyKey'])
            row.status='approved'  # Solo fixture, simulando una decisión futura.
            db.commit()
        self.assertEqual(self.submit().json()['status'], 'pending')

    def test_invalid_inactive_plan_and_wrong_period(self):
        self.assertEqual(self.submit(requestedPlanId=9999).status_code, 404)
        self.assertEqual(self.submit(requestedPeriod='annual').status_code, 422)
        self.client.patch(f"/api/platform/commercial/plans/{self.plan['id']}/status", headers=self.owner, json={'isActive':False})
        self.assertEqual(self.submit().status_code, 404)

    def test_only_owner_reads_requests_even_with_foreign_organization_header(self):
        self.submit()
        self.assertEqual(self.client.get('/api/platform/commercial/applications').status_code,401)
        for role in ('adminA','adminB','operatorA','shared'):
            for org in (1,2):
                response=self.client.get('/api/platform/commercial/applications', headers=self.auth(role,org))
                self.assertEqual(response.status_code,403,response.text)
                self.assertNotIn(self.body['contactEmail'],response.text)
        self.assertEqual(self.client.get('/api/commercial/applications').status_code,405)
        self.assertEqual(self.client.get('/api/commercial/applications/known-id').status_code,404)

    def test_filters_pagination_persistence_and_snapshot(self):
        self.submit()
        self.submit(companyName='Second synthetic company', idempotencyKey=str(uuid.uuid4()))
        first=self.client.get('/api/platform/commercial/applications?limit=1&offset=0&status=pending',headers=self.owner).json()
        second=self.client.get('/api/platform/commercial/applications?limit=1&offset=1',headers=self.owner).json()
        self.assertEqual(first['total'],2)
        self.assertNotEqual(first['items'][0]['id'],second['items'][0]['id'])
        self.assertEqual(self.client.get('/api/platform/commercial/applications?status=rejected',headers=self.owner).json()['total'],0)
        self.assertEqual(self.client.get('/api/platform/commercial/applications?plan_id=999',headers=self.owner).json()['total'],0)
        with closing(sqlite3.connect(self.root/'test.db')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_applications').fetchone()[0],2)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(self.protected(),self.before)

    def test_rate_limit_is_persistent_and_forwarded_header_does_not_bypass(self):
        for i in range(5):
            self.assertEqual(self.submit(companyName=f'Company {i}',idempotencyKey=str(uuid.uuid4())).status_code,201)
        response=self.client.post('/api/commercial/applications',json=self.body,headers={'X-Forwarded-For':'192.0.2.9'})
        self.assertEqual(response.status_code,429)
        self.assertEqual(response.headers['retry-after'],'600')
        self.assertEqual(self.protected(),self.before)

    def test_size_limit_handles_stream_and_does_not_echo_private_body(self):
        result=self.client.post('/api/commercial/applications',content=b'x'*9000,headers={'Content-Length':'1'})
        self.assertEqual(result.status_code,413)
        self.assertNotIn('xxxxx',result.text)
        with closing(sqlite3.connect(self.root/'test.db')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_application_attempts').fetchone()[0],0)

    def test_global_budget_and_expiration_affect_only_auxiliary_counters(self):
        with self.Session() as db:
            db.add_all(CommercialApplicationAttempt(bucket_hash=f'{i:064x}', created_at=now()) for i in range(60))
            db.commit()
        self.assertEqual(self.submit().status_code,429)
        with self.Session() as db:
            for attempt in db.scalars(select(CommercialApplicationAttempt)):
                attempt.created_at=now()-timedelta(days=2)
            db.commit()
        self.assertEqual(self.submit().status_code,201)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(CommercialApplicationAttempt)).all()),1)
            self.assertEqual(len(db.scalars(select(CommercialApplication)).all()),1)
        self.assertEqual(self.protected(),self.before)

    def test_validation_errors_forbid_manipulation_and_hide_inputs(self):
        for extra in ({'contactEmail':'PRIVATE-INVALID'}, {'organizationId':2}, {'status':'approved'}, {'amountCents':1}):
            result=self.submit(**extra)
            self.assertEqual(result.status_code,422,result.text)
            self.assertNotIn('PRIVATE-INVALID',result.text)
            self.assertNotIn(self.body['contactEmail'],result.text)
        self.assertEqual(self.client.post('/api/commercial/applications',content=b'not JSON').status_code,422)

    def test_concurrent_retries_create_only_one_request(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.submit(),range(4)))
        self.assertEqual(sorted(r.status_code for r in results),[200,200,200,201])
        self.assertEqual(len({r.json()['id'] for r in results}),1)
        self.assertEqual(self.client.get('/api/platform/commercial/applications',headers=self.owner).json()['total'],1)

    def test_commit_failure_rolls_back_without_exposing_parameters(self):
        from sqlalchemy.orm import Session
        original = Session.commit
        calls = 0
        def fail_after_budget(db):
            nonlocal calls
            calls += 1
            if calls == 1:
                return original(db)
            raise OperationalError('private SQL',{},Exception('PRIVATE'))
        with patch('sqlalchemy.orm.Session.commit', new=fail_after_budget):
            result=self.submit()
        self.assertEqual(result.status_code,503,result.text)
        self.assertNotIn('PRIVATE',result.text)
        self.assertEqual(self.protected(),self.before)
        self.assertEqual(self.client.get('/api/platform/commercial/applications',headers=self.owner).json()['total'],0)

    def test_incremental_migration_roundtrip_preserves_c009(self):
        target=self.root/'migration.db'
        with closing(sqlite3.connect(self.root/'test.db')) as source,closing(sqlite3.connect(target)) as copy:
            source.backup(copy)
            # Solo copia sintética: metadata actual incluye tablas ajenas a la frontera c010.
            copy.execute('DROP TABLE commercial_onboarding_orders')
            copy.execute('DROP INDEX uq_initial_invitation_trace')
            copy.execute('DROP TABLE commercial_application_notifications');copy.commit()
        env={**os.environ,'AGROSCAN_DATABASE_URL':'sqlite:///'+target.as_posix()}
        backend=Path(__file__).resolve().parents[1]
        # Reconstruye la frontera c010, retirando primero revisiones posteriores vacías de metadata.
        for args in (('stamp','c012initialadmin'),('downgrade','c010applications'),('downgrade','c009commerce'),('upgrade','c010applications'),('upgrade','c010applications')):
            result=subprocess.run([sys.executable,'-m','alembic',*args],cwd=backend,env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
        with closing(sqlite3.connect(target)) as copy:
            self.assertEqual(copy.execute('PRAGMA integrity_check').fetchall(),[('ok',)])
            self.assertEqual(copy.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(copy.execute('SELECT count(*) FROM commercial_plans').fetchone()[0],1)
            self.assertEqual(copy.execute('SELECT count(*) FROM commercial_orders').fetchone()[0],0)
