"""Catalogo versionado: exclusivamente SQLite temporal y usuarios sinteticos."""
import json
import sqlite3
import os
import subprocess
import sys
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from contextlib import closing

from sqlalchemy import select
import test_commercial_demo as commerce
from app.commercial_models import CommercialPlan, CommercialSubscription


class CatalogTests(unittest.TestCase):
    setUpClass = commerce.CommercialDemoTests.__dict__['setUpClass']
    setUp = commerce.CommercialDemoTests.setUp
    auth = commerce.CommercialDemoTests.auth
    restore_override = commerce.CommercialDemoTests.restore_override
    order = commerce.CommercialDemoTests.order
    confirm = commerce.CommercialDemoTests.confirm
    overview = commerce.CommercialDemoTests.overview

    def draft(self, **changes):
        body = {**self.plan_body, 'amountCents': 24900, 'publish': False, 'expectedVersion': 1,
                'idempotencyKey': 'catalog-draft-key-00001', 'changeNote': 'Nuevo precio DEMO', **changes}
        return self.client.post('/api/platform/commercial/plans', headers=self.owner, json=body)

    def status(self, plan, active=True, actor=None):
        return self.client.patch(f"/api/platform/commercial/plans/{plan['id']}/status",
                                 headers=actor or self.owner, json={'isActive': active})

    def test_publish_199_to_249_preserves_entire_contract_and_new_application(self):
        self.assertEqual(self.confirm(self.order()).status_code, 200)
        original = self.overview()['subscription']
        result = self.draft(period='monthly', benefits=['Condiciones nuevas'], limits={'vistas': 50})
        self.assertEqual(result.status_code, 201, result.text)
        draft = result.json()
        self.assertEqual(draft['state'], 'draft')
        catalog = lambda: self.client.get('/api/commercial/plans').json()['plans']
        self.assertEqual(catalog()[0]['amountCents'], 19900)
        self.assertEqual(self.overview()['subscription'], original)
        self.assertEqual(self.status(draft).status_code, 200)
        self.assertEqual(catalog()[0]['amountCents'], 24900)
        self.assertEqual(catalog()[0]['id'], draft['id'])
        self.assertEqual(self.overview()['subscription'], original)
        self.assertEqual(original['plan']['period'], 'monthly')
        self.assertEqual(original['plan']['benefits'], self.plan_body['benefits'])
        self.assertEqual(original['plan']['limits'], self.plan_body['limits'])
        received = self.client.post('/api/commercial/applications', json={
            'companyName': 'Catalogo QA Empresa', 'contactName': 'Contacto de ensayo',
            'contactEmail': 'catalog@example.test', 'requestedPlanId': draft['id'],
            'requestedPeriod': 'monthly', 'idempotencyKey': 'catalog-application-0001'})
        self.assertEqual(received.status_code, 201, received.text)
        details = self.client.get('/api/platform/commercial/applications', headers=self.owner).json()
        self.assertEqual(details['items'][0]['plan']['version'], 2)
        self.assertEqual(details['items'][0]['plan']['amountCents'], 24900)
        annual = self.draft(expectedVersion=2, period='annual', idempotencyKey='catalog-annual-key-001').json()
        self.assertEqual(self.status(annual).status_code, 200)
        self.assertEqual(catalog()[0]['period'], 'annual')
        self.assertEqual(self.overview()['subscription'], original)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(CommercialSubscription)).all()), 1)

    def test_history_and_status_idempotence(self):
        draft = self.draft().json()
        for _ in range(2):
            self.assertEqual(self.status(draft).status_code, 200)
        history = self.client.get(f"/api/platform/commercial/plans/{draft['id']}/versions", headers=self.owner).json()
        self.assertEqual([row['version'] for row in history], [2, 1])
        self.assertEqual([row['amountCents'] for row in history], [24900, 19900])
        self.assertIsNotNone(history[0]['createdAt'])
        self.assertIsNotNone(history[0]['publishedAt'])
        self.assertEqual(history[0]['createdBy'], self.users['without_membership'])
        self.assertEqual(self.status(self.plan).status_code, 409)
        self.assertEqual(self.status(draft, False).status_code, 200)
        self.assertEqual(self.client.get('/api/commercial/plans').json()['plans'], [])
        self.assertEqual(self.status(draft).status_code, 200)

    def test_concurrent_retry_and_stale_edit(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(lambda _: self.draft(), range(4)))
        self.assertTrue(all(reply.status_code == 201 for reply in replies), [r.text for r in replies])
        self.assertEqual(len({reply.json()['id'] for reply in replies}), 1)
        self.assertEqual(self.draft(amountCents=30000).status_code, 409)
        self.assertEqual(self.draft(idempotencyKey='another-creation-key-01').status_code, 409)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(CommercialPlan)).all()), 2)

    def test_invalid_payloads_and_unauthorized_roles(self):
        for change in ({'amountCents': -1}, {'period': 'weekly'}, {'currency': 'USD'},
                       {'benefits': [' ']}, {'displayOrder': -1}, {'limits': {'bad': -2}},
                       {'limits': {'bad': True}}, {'isActive': True}):
            self.assertEqual(self.draft(**change).status_code, 422, change)
        for who, org in [('adminA', 1), ('adminB', 2), ('operatorA', 1), ('shared', 2)]:
            headers = self.auth(who, org)
            for method, path, body in [('POST', '/plans', self.plan_body),
                                      ('PATCH', f"/plans/{self.plan['id']}/status", {'isActive': False}),
                                      ('GET', f"/plans/{self.plan['id']}/versions", None)]:
                reply = self.client.request(method, '/api/platform/commercial'+path, headers=headers,
                                            **({'json': body} if body is not None else {}))
                self.assertEqual(reply.status_code, 403)
        self.assertEqual(self.client.get(f"/api/platform/commercial/plans/{self.plan['id']}/versions").status_code, 401)

    def test_display_order_recommended_and_public_information(self):
        second = self.draft(code='early-demo', expectedVersion=0, displayOrder=1, recommended=False, publish=True, idempotencyKey='second-plan-key-00001').json()
        draft = self.draft(expectedVersion=1, displayOrder=20).json()
        self.assertEqual(self.status(draft).status_code, 200)
        plans = self.client.get('/api/commercial/plans').json()['plans']
        self.assertEqual([p['id'] for p in plans], [second['id'], draft['id']])
        self.assertTrue(plans[1]['recommended'])
        self.assertNotIn('createdBy', plans[1])
        self.assertNotIn('changeNote', plans[1])

    def test_failure_rolls_back_versions_and_publication(self):
        with patch.object(CommercialPlan, '__init__', side_effect=RuntimeError('isolated persistence failure')):
            with self.assertRaises(RuntimeError):
                self.draft(publish=True)
        public = self.client.get('/api/commercial/plans').json()['plans']
        self.assertEqual([p['id'] for p in public], [self.plan['id']])

    def test_draft_cannot_be_requested_or_purchased_and_legacy_retries_do_not_duplicate(self):
        for _ in range(2):
            reply = self.client.post('/api/platform/commercial/plans', headers=self.owner, json=self.plan_body)
            self.assertEqual(reply.json()['id'], self.plan['id'])
        draft = self.draft().json()
        reply = self.client.post('/api/commercial/orders', headers=self.auth(), json={
            'planId': draft['id'], 'idempotencyKey': 'draft-cannot-buy-0001'})
        self.assertEqual(reply.status_code, 404)
        reply = self.client.post('/api/commercial/applications', json={
            'companyName': 'Empresa de ensayo', 'contactName': 'Contacto de ensayo',
            'contactEmail': 'private@example.test', 'requestedPlanId': draft['id'],
            'requestedPeriod': 'monthly', 'idempotencyKey': 'draft-cannot-request-01'})
        self.assertEqual(reply.status_code, 404)

    def test_older_draft_cannot_replace_newer_version(self):
        older = self.draft().json()
        newer = self.draft(expectedVersion=2, idempotencyKey='newer-draft-key-00001', amountCents=30000).json()
        self.assertEqual(self.status(older).status_code, 409)
        self.assertEqual(self.status(newer).status_code, 200)
        self.assertEqual(self.status(older).status_code, 409)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(CommercialPlan)).all()), 3)

    def test_migration_roundtrip_on_disposable_sqlite(self):
        target = self.root/'catalog-migration.db'
        env = {**os.environ, 'AGROSCAN_DATABASE_URL': f'sqlite:///{target.as_posix()}'}
        backend = Path(__file__).resolve().parents[1]
        def alembic(*args):
            result = subprocess.run([sys.executable, '-m', 'alembic', *args], env=env, cwd=backend, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        alembic('upgrade', 'a016sessions')
        with closing(sqlite3.connect(target)) as db:
            db.execute("INSERT INTO commercial_plans (code,version,name,description,amount_cents,currency,period,benefits_json,limits_json,is_active,recommended) VALUES ('historical',1,'Historical','Original',19900,'PEN','monthly','[\"Original\"]','{}',1,0)")
            db.execute("INSERT INTO commercial_subscriptions (organization_id,plan_id,snapshot_json,status,starts_at,ends_at) VALUES (1,1,?,'active','2026-01-01','2027-01-01')", (json.dumps({'id': 1, 'version': 1, 'amountCents': 19900, 'period': 'monthly', 'benefits': ['Original']}),))
            before = db.execute('SELECT * FROM commercial_plans').fetchall()
            subscriptions = db.execute('SELECT * FROM commercial_subscriptions').fetchall()
            db.commit()
        alembic('upgrade', 'c017catalog')
        alembic('upgrade', 'c017catalog')
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(db.execute('SELECT id,code,version,name,description,amount_cents,currency,period,benefits_json,limits_json,is_active,recommended FROM commercial_plans').fetchall(), before)
            self.assertEqual(db.execute('SELECT * FROM commercial_subscriptions').fetchall(), subscriptions)
        alembic('downgrade', 'a016sessions')
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute('SELECT * FROM commercial_plans').fetchall(), before)
            self.assertEqual(db.execute('SELECT * FROM commercial_subscriptions').fetchall(), subscriptions)
