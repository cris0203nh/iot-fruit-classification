"""Contratación DEMO: SQLite, JWT y fotos sintéticos; nunca datos operativos."""
import hashlib
import os
import sqlite3
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

import test_saas03_organizations as fixture
from app.bootstrap_owner import assign_first_owner
from app.commercial_models import CommercialOrder, CommercialSubscription, CommercialTransaction
from app.models import User
from app.organization_models import OrganizationMembership
from app.routers.commercial import add_period, NOTICE


class CommercialDemoTests(unittest.TestCase):
    setUpClass = fixture.OrganizationIsolationTests.__dict__['setUpClass']
    auth = fixture.OrganizationIsolationTests.auth
    restore_override = fixture.OrganizationIsolationTests.restore_override

    def setUp(self):
        fixture.OrganizationIsolationTests.setUp(self)
        env = patch.dict(os.environ, {'AGROSCAN_ENVIRONMENT': 'demo', 'AGROSCAN_SUBSCRIPTION_SIMULATOR': 'true'})
        env.start()
        self.addCleanup(env.stop)
        with self.Session() as db:
            assign_first_owner(db, self.users['without_membership'])
        self.owner = self.auth('without_membership')
        self.plan_body = {'code': 'cosecha', 'name': 'Cosecha DEMO', 'description': 'Condiciones de ensayo',
                          'amountCents': 19900, 'currency': 'PEN', 'period': 'monthly',
                          'benefits': ['Trazabilidad', 'Revisión humana'], 'limits': {'evaluaciones': 1000},
                          'recommended': True}
        reply = self.client.post('/api/platform/commercial/plans', headers=self.owner, json=self.plan_body)
        self.assertEqual(reply.status_code, 201, reply.text)
        self.plan = reply.json()

    def order(self, key='synthetic-key-0001', who='adminA', action='subscribe', plan=None):
        reply = self.client.post('/api/commercial/orders', headers=self.auth(who), json={
            'planId': plan or self.plan['id'], 'action': action, 'idempotencyKey': key})
        self.assertEqual(reply.status_code, 201, reply.text)
        return reply.json()

    def confirm(self, order, scenario='approve', who='adminA'):
        return self.client.post('/api/commercial/orders/' + order['id'] + '/confirm',
                                headers=self.auth(who), json={'scenario': scenario})

    def overview(self, who='adminA'):
        reply = self.client.get('/api/commercial/subscription', headers=self.auth(who))
        self.assertEqual(reply.status_code, 200, reply.text)
        return reply.json()

    def test_catalog_public_but_operations_require_company_admin(self):
        catalog = self.client.get('/api/commercial/plans')
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(catalog.json()['plans'][0]['amountCents'], 19900)
        for who, org in [('operatorA', 1), ('shared', 2)]:
            headers = self.auth(who, org)
            for path, method in [('/api/commercial/subscription', 'get'), ('/api/commercial/orders', 'post'),
                                 ('/api/commercial/subscription/cancel', 'post'),
                                 ('/api/platform/commercial/plans', 'post'), ('/api/platform/commercial/overview', 'get')]:
                reply = self.client.request(method, path, headers=headers, **({'json': {}} if method == 'post' else {}))
                self.assertEqual(reply.status_code, 403, (who, path, reply.text))
        self.assertEqual(self.client.get('/api/commercial/subscription', headers=self.owner).status_code, 403)
        self.assertEqual(self.client.get('/api/commercial/subscription').status_code, 401)
        self.assertEqual(self.client.post('/api/platform/commercial/plans', headers=self.auth(), json=self.plan_body).status_code, 403)

    def test_purchase_persists_reload_snapshot_and_real_metrics(self):
        pending = self.order()
        self.assertEqual(pending['status'], 'pending')
        self.assertIsNone(self.overview()['subscription'])
        reply = self.confirm(pending)
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(reply.json()['status'], 'demo_approved')
        data = self.overview()
        self.assertEqual(data['subscription']['status'], 'active')
        self.assertEqual(data['subscription']['plan']['version'], 1)
        self.assertEqual(data['notice'], NOTICE)
        with self.Session() as db:
            self.assertEqual(db.scalar(select(func.count(CommercialTransaction.id))), 1)
        metrics = self.client.get('/api/platform/commercial/overview', headers=self.owner).json()
        self.assertEqual(metrics['activeDemoSubscriptions'], 1)
        self.assertEqual(metrics['simulatedTotalCents'], 19900)
        self.assertEqual(len(metrics['orders']), 1)

    def test_invitation_registration_then_demo_purchase_preserves_business_roles(self):
        invitation = self.client.post('/api/invitations', headers=self.auth(), json={
            'email': 'new-admin@example.test', 'role': 'administrador'})
        self.assertEqual(invitation.status_code, 201, invitation.text)
        registered = self.client.post('/api/auth/invitations/register', json={
            'token': invitation.json()['token'], 'username': 'new-commerce-admin',
            'fullName': 'Administrador de ensayo', 'password': self.password})
        self.assertEqual(registered.status_code, 201, registered.text)
        headers = {'Authorization': 'Bearer ' + registered.json()['access_token']}
        created = self.client.post('/api/commercial/orders', headers=headers, json={
            'planId': self.plan['id'], 'idempotencyKey': 'new-user-purchase-0001'})
        self.assertEqual(created.status_code, 201, created.text)
        confirmed = self.client.post('/api/commercial/orders/' + created.json()['id'] + '/confirm',
                                     headers=headers, json={'scenario': 'approve'})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(self.client.get('/api/auth/me', headers=headers).json()['roles'], ['administrador'])
        self.assertEqual(self.client.get('/api/platform/commercial/overview', headers=headers).status_code, 403)
        self.assertEqual(self.overview('adminB')['orders'], [])

    def test_annual_purchase_and_change_preserve_history_and_expiring_metrics(self):
        annual = self.client.post('/api/platform/commercial/plans', headers=self.owner,
                                 json={**self.plan_body, 'code': 'annual', 'period': 'annual'}).json()
        clock = datetime(2026, 11, 18)
        with patch('app.routers.commercial.now', return_value=clock):
            order = self.order(plan=annual['id'])
            self.assertEqual(self.confirm(order).status_code, 200)
            self.assertEqual(self.overview()['subscription']['endsAt'], '2027-11-18T00:00:00Z')
            change = self.order('change-plan-0001', action='change')
            self.assertEqual(self.confirm(change).status_code, 200)
            self.assertEqual(self.overview()['subscription']['plan']['period'], 'monthly')
            self.assertEqual(len(self.overview()['orders']), 2)
            metrics = self.client.get('/api/platform/commercial/overview', headers=self.owner).json()
            self.assertEqual(metrics['expiringSoon'], 1)

    def test_rejected_and_cancelled_do_not_activate_subscription(self):
        for i, scenario in enumerate(('reject', 'cancel')):
            order = self.order(f'negative-order-{i:04}')
            self.assertEqual(self.confirm(order, scenario).status_code, 200)
        data = self.overview()
        self.assertIsNone(data['subscription'])
        self.assertEqual([o['status'] for o in data['orders']], ['cancelled', 'demo_rejected'])
        self.assertTrue(all(tx['amountCents'] == 0 for tx in data['transactions']))

    def test_duplicate_confirmations_and_creation_are_idempotent_under_concurrency(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            orders = list(pool.map(lambda _: self.order(), range(4)))
        self.assertEqual(len({o['id'] for o in orders}), 1)
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(lambda _: self.confirm(orders[0]), range(4)))
        self.assertEqual([r.status_code for r in replies], [200] * 4)
        data = self.overview()
        self.assertEqual(len(data['orders']), 1)
        self.assertEqual(len(data['transactions']), 1)
        self.assertEqual(self.confirm(orders[0], 'reject').status_code, 409)
        self.assertEqual(self.client.post('/api/commercial/orders', headers=self.auth(), json={
            'planId': self.plan['id'], 'action': 'change', 'idempotencyKey': 'synthetic-key-0001'}).status_code, 409)

    def test_parallel_distinct_subscribe_orders_do_not_double_charge_or_activate(self):
        orders = [self.order(f'parallel-order-{i:04}') for i in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(self.confirm, orders))
        self.assertEqual(sorted(r.status_code for r in replies), [200, 409])
        self.assertEqual(len(self.overview()['transactions']), 1)

    def test_ab_order_subscription_transactions_and_relations_are_isolated(self):
        a, b = self.order(), self.order(who='adminB')
        self.assertEqual(self.confirm(a, who='adminB').status_code, 404)
        self.assertEqual(self.confirm(b).status_code, 404)
        self.assertEqual(self.confirm(a).status_code, 200)
        self.assertEqual(self.overview('adminB')['transactions'], [])
        self.assertIsNone(self.overview('adminB')['subscription'])
        self.assertEqual([o['id'] for o in self.overview('adminB')['orders']], [b['id']])
        self.assertEqual(self.client.get('/api/commercial/subscription', headers=self.auth('adminA', 2)).status_code, 403)
        with self.Session() as db:
            db.add(CommercialTransaction(organization_id=2, order_id=a['id'], actor_id=self.users['adminB'],
                                        outcome='demo_approved', amount_cents=19900, created_at=datetime(2026, 1, 1)))
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_tampered_prices_roles_scope_and_scenarios_are_rejected(self):
        valid = {'planId': self.plan['id'], 'action': 'subscribe', 'idempotencyKey': 'tampered-key-0001'}
        for extra in ({'amountCents': 1}, {'organizationId': 2}, {'currency': 'USD'}, {'role': 'superadmin'}):
            reply = self.client.post('/api/commercial/orders', headers=self.auth(), json={**valid, **extra})
            self.assertEqual(reply.status_code, 422, reply.text)
        order = self.order()
        self.assertEqual(self.client.post('/api/commercial/orders/' + order['id'] + '/confirm',
            headers=self.auth(), json={'scenario': 'approve', 'amountCents': 0}).status_code, 422)
        self.assertEqual(self.confirm(order, 'uncontrolled').status_code, 422)
        for amount in (-1, 1.5, True, 100000001):
            self.assertEqual(self.client.post('/api/platform/commercial/plans', headers=self.owner,
                json={**self.plan_body, 'amountCents': amount}).status_code, 422)

    def test_versioned_conditions_and_inactive_plan(self):
        order = self.order()
        self.assertEqual(self.confirm(order).status_code, 200)
        newer = self.client.post('/api/platform/commercial/plans', headers=self.owner,
                                json={**self.plan_body, 'amountCents': 25000}).json()
        self.assertEqual(newer['version'], 2)
        self.assertEqual(self.overview()['subscription']['plan']['amountCents'], 19900)
        self.assertEqual(self.overview()['orders'][0]['amountCents'], 19900)
        self.assertEqual(len(self.client.get('/api/commercial/plans').json()['plans']), 1)
        self.assertEqual(self.client.patch(f"/api/platform/commercial/plans/{self.plan['id']}/status",
            headers=self.owner, json={'isActive': True}).status_code, 409)
        self.assertEqual(self.client.post('/api/commercial/orders', headers=self.auth(), json={
            'planId': self.plan['id'], 'action': 'renew', 'idempotencyKey': 'inactive-key-0001'}).status_code, 404)

    def test_monthly_annual_renewal_expiry_and_cancellation(self):
        start = datetime(2026, 1, 31)
        self.assertEqual(add_period(start, 'monthly'), datetime(2026, 2, 28))
        self.assertEqual(add_period(datetime(2024, 2, 29), 'annual'), datetime(2025, 2, 28))
        with patch('app.routers.commercial.now', return_value=start):
            order = self.order()
            self.confirm(order)
            renewal = self.order('renewal-key-0001', action='renew')
            self.assertEqual(self.confirm(renewal).status_code, 200)
            data = self.overview()
            self.assertEqual(data['subscription']['endsAt'], '2026-03-28T00:00:00Z')
            metrics = self.client.get('/api/platform/commercial/overview', headers=self.owner).json()
            self.assertEqual(metrics['activeDemoSubscriptions'], 1)
        with patch('app.routers.commercial.now', return_value=start + timedelta(days=90)):
            self.assertEqual(self.overview()['subscription']['status'], 'expired')
        self.assertEqual(self.client.post('/api/commercial/subscription/cancel', headers=self.auth()).status_code, 200)
        self.client.post('/api/commercial/subscription/cancel', headers=self.auth())
        self.assertEqual(self.overview()['subscription']['status'], 'cancelled')
        self.assertEqual(len(self.overview()['transactions']), 3)

    def test_disabled_simulator_blocks_all_mutations_but_preserves_catalog_and_history(self):
        order = self.order()
        for config in ({'AGROSCAN_ENVIRONMENT': 'production'}, {'AGROSCAN_SUBSCRIPTION_SIMULATOR': 'false'}):
            with patch.dict(os.environ, config):
                self.assertFalse(self.client.get('/api/commercial/plans').json()['simulatorEnabled'])
                self.assertEqual(self.confirm(order).status_code, 503)
                self.assertEqual(self.client.post('/api/commercial/orders', headers=self.auth(), json={
                    'planId': self.plan['id'], 'idempotencyKey': 'disabled-key-0001'}).status_code, 503)
                self.assertEqual(self.client.post('/api/commercial/subscription/cancel', headers=self.auth()).status_code, 503)
                self.assertEqual(self.overview()['orders'][0]['status'], 'pending')

    def test_expired_order_and_revoked_membership_cannot_confirm(self):
        order = self.order()
        with patch('app.routers.commercial.now', return_value=datetime.now() + timedelta(days=2)):
            self.assertEqual(self.confirm(order).status_code, 409)
        with self.Session() as db:
            membership = db.get(OrganizationMembership, (1, self.users['adminA'], 1))
            membership.is_active = False
            db.commit()
        self.assertEqual(self.confirm(order).status_code, 403)

    def test_transaction_failure_rolls_back_order_subscription_and_transaction(self):
        order = self.order()
        with patch('app.routers.commercial.CommercialTransaction', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):
                self.confirm(order)
        data = self.overview()
        self.assertEqual(data['orders'][0]['status'], 'pending')
        self.assertIsNone(data['subscription'])
        self.assertEqual(data['transactions'], [])

    def test_migration_copy_roundtrip_preserves_all_operational_rows(self):
        # Únicamente copia de la fixture sintética, nunca la base operativa.
        source = self.root / 'test.db'
        target = self.root / 'migration.db'
        with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
        def fingerprint():
            with closing(sqlite3.connect(target)) as conn:
                names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                         if not row[0].startswith(('commercial_', 'alembic_', 'sqlite_'))]
                return {name: hashlib.sha256(repr(conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()).encode()).hexdigest() for name in names}
        before = fingerprint()
        with closing(sqlite3.connect(target)) as conn:
            # Retira tablas posteriores vacías para reconstruir exclusivamente la revisión c009.
            for table in ('commercial_onboarding_orders', 'commercial_application_notifications', 'commercial_application_invitations', 'commercial_application_decisions',
                          'commercial_application_attempts', 'commercial_applications',
                          'commercial_transactions', 'commercial_orders', 'commercial_subscriptions', 'commercial_plans'):
                conn.execute(f'DROP TABLE {table}')
            conn.commit()
        env = {**os.environ, 'AGROSCAN_DATABASE_URL': f'sqlite:///{target.as_posix()}'}
        backend = Path(__file__).resolve().parents[1]
        # Esta regresión reconstruye solo c009; las revisiones posteriores tienen su propia prueba.
        for args in (('stamp', 's007iot'), ('upgrade', 'c009commerce'), ('upgrade', 'c009commerce'),
                     ('downgrade', 's007iot'), ('upgrade', 'c009commerce')):
            result = subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=backend,
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(fingerprint(), before)
        with closing(sqlite3.connect(target)) as conn:
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(conn.execute('SELECT count(*) FROM commercial_plans').fetchone()[0], 0)
