"""Outbox/SMTP aislados: nunca entrega correo real ni abre bases operativas."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
import json
import os
from pathlib import Path
import smtplib
import sqlite3
import subprocess
import sys
import unittest
import uuid
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
import test_commercial_demo as commerce
import test_com04_initial_admin as onboarding
from test_com05r1_notifications import ENV
from app.notification_models import CommercialNotification as Notice
from app.identity_models import GoogleIdentity
from app.organization_models import OrganizationMembership
from app.commercial_models import CommercialSubscription
from app.services import application_notification as transport, commercial_notifications as queue


class OutboxTests(unittest.TestCase):
    setUpClass = commerce.CommercialDemoTests.__dict__['setUpClass']
    auth = commerce.CommercialDemoTests.auth
    restore_override = commerce.CommercialDemoTests.restore_override
    order = commerce.CommercialDemoTests.order
    confirm = commerce.CommercialDemoTests.confirm
    overview = commerce.CommercialDemoTests.overview

    def setUp(self):
        commerce.CommercialDemoTests.setUp(self)
        with self.Session() as db:
            for who in ('adminA', 'adminB'):
                db.add(GoogleIdentity(subject='synthetic-' + who, user_id=self.users[who], email=who.lower() + '@example.test'))
            db.commit()

    def notices(self, event=None):
        with self.Session() as db:
            statement = select(Notice).order_by(Notice.created_at)
            return db.scalars(statement.where(Notice.event == event) if event else statement).all()

    def pending(self):
        with self.Session() as db:
            queue.enqueue(db, 'application_approved', 'synthetic-reference', 'authorized@example.test', plan=self.plan)
            db.commit()
        return self.notices()[0].id

    def process(self, notice_id):
        with self.Session() as db:
            return queue.process_one(db, notice_id)

    def due(self, notice_id):
        with self.Session() as db:
            db.get(Notice, notice_id).next_attempt_at = queue.now() - timedelta(seconds=1)
            db.commit()

    def test_confirmed_events_idempotency_and_persisted_snapshots(self):
        for scenario in ('reject', 'cancel'):
            self.confirm(self.order(key='synthetic-' + scenario), scenario)
        self.assertEqual(self.notices(), [])
        approved = self.order(key='synthetic-approved')
        for _ in range(2):
            self.assertEqual(self.confirm(approved).status_code, 200)
        renewed = self.order(key='synthetic-renewal', action='renew')
        for _ in range(2):
            self.assertEqual(self.confirm(renewed).status_code, 200)
        for _ in range(2):
            self.assertEqual(self.client.post('/api/commercial/subscription/cancel', headers=self.auth(), json={}).status_code, 200)
        self.assertEqual([r.event for r in self.notices()], ['subscription_activated', 'subscription_renewed', 'subscription_cancelled'])
        for row in self.notices():
            self.assertEqual(row.organization_id, 1)
            self.assertEqual(row.recipient, 'admina@example.test')
            self.assertEqual(json.loads(row.payload_json)['plan']['amountCents'], self.plan['amountCents'])
        # Publicar otro precio no reescribe el snapshot ni emite cambios contractuales.
        result = self.client.post('/api/platform/commercial/plans', headers=self.owner,
                                 json={**self.plan_body, 'amountCents': 99900})
        self.assertIn(result.status_code, (201, 409))
        self.assertEqual(len(self.notices()), 3)

    def test_authorization_filters_and_no_arbitrary_destination(self):
        for who in ('adminA', 'adminB'):
            self.confirm(self.order(key='synthetic-' + who, who=who), who=who)
        for who, org in (('adminA', 1), ('adminB', 2), ('operatorA', 1), ('shared', 2)):
            headers = self.auth(who, org)
            self.assertEqual(self.client.get('/api/platform/notifications', headers=headers).status_code, 403)
            self.assertEqual(self.client.post('/api/platform/notifications/' + self.notices()[0].id + '/retry', headers=headers, json={}).status_code, 403)
        self.assertEqual(self.client.get('/api/platform/notifications').status_code, 401)
        response = self.client.get('/api/platform/notifications?organization_id=1&event=subscription_activated', headers=self.owner)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.json()['total'], 1)
        self.assertNotIn('adminb@example.test', response.text)
        self.assertNotIn('payload_json', response.text)
        self.assertTrue(response.json()['items'][0]['createdAt'].endswith('Z'))
        self.assertEqual(self.client.post('/api/platform/notifications/' + self.notices()[0].id + '/retry', headers=self.owner,
                         json={'recipient':'attacker@example.test'}).status_code, 422)
        for query in ('event=unknown', 'status=unknown', 'since=2027-01-01&until=2026-01-01'):
            self.assertEqual(self.client.get('/api/platform/notifications?' + query, headers=self.owner).status_code, 422)

    def test_queue_is_atomic_with_business_rollback(self):
        order = self.order()
        with patch.object(queue, 'organization_event', side_effect=RuntimeError('synthetic rollback')):
            with self.assertRaises(RuntimeError):
                self.confirm(order)
        self.assertIsNone(self.overview()['subscription'])
        self.assertEqual(self.notices(), [])
        self.assertEqual(self.confirm(order).status_code, 200)

    def test_configured_smtp_acceptance_is_not_inbox_delivery(self):
        notice_id = self.pending()
        with patch.dict(os.environ, ENV), patch.object(transport, 'send') as send:
            self.assertTrue(self.process(notice_id))
            self.assertFalse(self.process(notice_id))
        send.assert_called_once()
        row = self.notices()[0]
        self.assertEqual((row.status, row.attempts), ('smtp_accepted', 1))
        self.assertIsNotNone(row.smtp_accepted_at)
        message = send.call_args.args[1]
        self.assertIn('No se realiz', message.get_body(preferencelist=('plain',)).get_content())
        self.assertEqual(message.get_content_type(), 'multipart/alternative')
        self.assertEqual(self.client.post('/api/platform/notifications/' + notice_id + '/retry', headers=self.owner, json={}).status_code, 409)

    def test_disabled_and_missing_configuration_preserve_pending(self):
        notice_id = self.pending()
        with patch.object(transport, 'send') as send:
            self.assertFalse(self.process(notice_id))
            self.assertEqual(self.notices()[0].error_code, 'smtp_disabled')
            self.due(notice_id)
            with patch.dict(os.environ, {**ENV, 'AGROSCAN_SMTP_HOST':''}):
                self.assertFalse(self.process(notice_id))
            self.assertEqual(self.notices()[0].error_code, 'configuration_error')
            send.assert_not_called()
        self.assertEqual(self.notices()[0].attempts, 0)

    def test_backoff_authentication_connection_and_maximum(self):
        notice_id = self.pending()
        with patch.dict(os.environ, {**ENV, 'AGROSCAN_NOTIFICATION_MAX_ATTEMPTS':'2'}):
            for error in (smtplib.SMTPAuthenticationError(535, b'PRIVATE'), ConnectionRefusedError('PRIVATE')):
                with patch.object(transport, 'send', side_effect=error):
                    self.assertTrue(self.process(notice_id))
                row = self.notices()[0]
                self.assertNotIn('PRIVATE', row.error_code)
                if row.attempts == 1:
                    self.assertEqual(row.status, 'retry_pending')
                    self.assertGreater(row.next_attempt_at, row.last_attempt_at)
                    self.assertEqual(self.client.post('/api/platform/notifications/' + notice_id + '/retry', headers=self.owner, json={}).status_code, 429)
                    self.due(notice_id)
            self.assertEqual(self.notices()[0].status, 'failed')
            self.assertFalse(self.process(notice_id))

    def test_timeout_is_uncertain_never_automatically_retried(self):
        notice_id = self.pending()
        with patch.dict(os.environ, ENV), patch.object(transport, 'send', side_effect=TimeoutError('PRIVATE')) as send:
            self.process(notice_id)
            self.assertFalse(self.process(notice_id))
            send.assert_called_once()
        row = self.notices()[0]
        self.assertEqual((row.status, row.error_code), ('failed', 'delivery_uncertain'))
        self.assertIsNone(row.smtp_accepted_at)

    def test_concurrent_workers_claim_exactly_one_attempt(self):
        notice_id = self.pending()
        with patch.dict(os.environ, ENV), patch.object(transport, 'send') as send, ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.process(notice_id), range(4)))
        self.assertEqual(sum(results), 1)
        send.assert_called_once()
        self.assertEqual(self.notices()[0].attempts, 1)

    def test_accepted_smtp_then_database_failure_keeps_uncertain_claim(self):
        notice_id = self.pending()
        original = Session.commit
        calls = 0
        def fail_result(db):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OperationalError('synthetic write failure', {}, None)
            return original(db)
        with patch.dict(os.environ, ENV), patch.object(transport, 'send') as send, patch.object(Session, 'commit', fail_result):
            self.process(notice_id)
        send.assert_called_once()
        self.assertEqual(self.notices()[0].status, 'processing')
        with self.Session() as db:
            db.get(Notice, notice_id).last_attempt_at = queue.now() - timedelta(minutes=11)
            db.commit()
            with patch.object(transport, 'send') as retry:
                queue.process_pending(db)
                retry.assert_not_called()
        self.assertEqual(self.notices()[0].error_code, 'delivery_uncertain')

    def test_revoked_administrator_is_not_contacted(self):
        self.confirm(self.order())
        with self.Session() as db:
            db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == self.users['adminA'])).is_active = False
            db.commit()
        with patch.dict(os.environ, ENV), patch.object(transport, 'send') as send:
            self.process(self.notices()[0].id)
            send.assert_not_called()
        self.assertEqual(self.notices()[0].status, 'omitted')

    def test_recipient_validation_and_escaped_html_no_token_payload(self):
        for address in ('a@example.test\r\nBcc: b@example.test', 'a@example.test,b@example.test', '', 'invalid'):
            self.assertIsNone(queue.valid_email(address))
        with self.Session() as db:
            queue.enqueue(db, 'administrator_invited', 'safe-reference', 'test@example.test', name='<script>unsafe</script>', plan={**self.plan, 'token':'PRIVATE-TOKEN'})
            db.commit()
        row = self.notices()[0]
        self.assertNotIn('PRIVATE-TOKEN', row.payload_json)
        with patch.dict(os.environ, ENV):
            message = queue.message_for(row, transport.configuration(row.recipient))
        html = message.get_body(preferencelist=('html',)).get_content()
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_reminders_deduplicate_and_do_not_mutate_contracts(self):
        for who in ('adminA', 'adminB'):
            self.confirm(self.order(key='synthetic-' + who, who=who), who=who)
        with self.Session() as db:
            rows = db.scalars(select(CommercialSubscription).order_by(CommercialSubscription.id)).all()
            rows[0].ends_at = queue.now() + timedelta(days=2)
            rows[1].starts_at = queue.now() - timedelta(days=31)
            rows[1].ends_at = queue.now() - timedelta(days=1)
            db.commit()
            before = [(r.id, r.status, r.snapshot_json, r.ends_at) for r in rows]
        for _ in range(3):
            with self.Session() as db:
                queue.enqueue_expirations(db, limit=1)
        self.assertEqual(len(self.notices('subscription_expiring')), 1)
        self.assertEqual(len(self.notices('subscription_expired')), 1)
        with self.Session() as db:
            self.assertEqual([(r.id, r.status, r.snapshot_json, r.ends_at) for r in db.scalars(select(CommercialSubscription).order_by(CommercialSubscription.id))], before)
        self.client.post('/api/commercial/subscription/cancel', headers=self.auth(), json={})
        with self.Session() as db:
            queue.enqueue_expirations(db)
        self.assertEqual(len(self.notices('subscription_expiring')), 1)

    def test_plan_change_notice_only_after_approval_uses_confirmed_version(self):
        self.confirm(self.order())
        other = self.client.post('/api/platform/commercial/plans', headers=self.owner,
            json={**self.plan_body, 'code':'second-demo', 'name':'Second DEMO', 'amountCents':29900}).json()
        rejected = self.order(key='synthetic-change-reject', action='change', plan=other['id'])
        self.confirm(rejected, 'reject')
        self.assertEqual(self.notices('subscription_changed'), [])
        approved = self.order(key='synthetic-change-approved', action='change', plan=other['id'])
        self.confirm(approved)
        self.confirm(approved)
        rows = self.notices('subscription_changed')
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0].payload_json)['plan']['amountCents'], 29900)

    def test_additive_migration_preserves_all_prior_rows_and_no_backfill(self):
        target = self.root / 'notification-migration.db'
        env = {**os.environ, 'AGROSCAN_DATABASE_URL': 'sqlite:///' + target.as_posix()}
        def alembic(*args):
            result = subprocess.run([sys.executable, '-B', '-m', 'alembic', *args], env=env, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        def snapshot():
            with closing(sqlite3.connect(target)) as db:
                return {t: db.execute(f'SELECT * FROM "{t}" ORDER BY rowid').fetchall() for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'") if t not in ('alembic_version', 'commercial_notification_outbox')}
        alembic('upgrade', 'c017catalog')
        self.confirm(self.order())
        with closing(sqlite3.connect(self.root / 'test.db')) as source, closing(sqlite3.connect(target)) as destination:
            # Condiciones históricas reales del fixture, no una base vacía.
            for table in ('users', 'commercial_plans', 'commercial_subscriptions'):
                rows = source.execute(f'SELECT * FROM "{table}"').fetchall()
                placeholders = ','.join('?' for _ in rows[0])
                destination.executemany(f'INSERT INTO "{table}" VALUES ({placeholders})', rows)
            destination.commit()
        before = snapshot()
        alembic('upgrade', 'c018notifications')
        alembic('upgrade', 'c018notifications')
        self.assertEqual(snapshot(), before)
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM commercial_notification_outbox').fetchone(), (0,))
        alembic('downgrade', 'c017catalog')
        self.assertEqual(snapshot(), before)


class OnboardingNoticeTests(unittest.TestCase):
    setUpClass = onboarding.InitialAdminTests.__dict__['setUpClass']
    setUp = onboarding.InitialAdminTests.setUp
    auth = onboarding.InitialAdminTests.auth
    restore_override = onboarding.InitialAdminTests.restore_override
    protected = onboarding.InitialAdminTests.protected
    submit = onboarding.InitialAdminTests.submit
    decide = onboarding.InitialAdminTests.decide
    emit = onboarding.InitialAdminTests.emit
    register = onboarding.InitialAdminTests.register

    def test_initial_invitation_and_acceptance_notices_without_secret_links(self):
        first = self.emit().json()
        self.assertEqual(self.emit().status_code, 200)
        token = first['token']
        self.assertEqual(self.register(token).status_code, 201)
        self.assertNotEqual(self.register(token).status_code, 201)
        with self.Session() as db:
            rows = db.scalars(select(Notice)).all()
            self.assertEqual(sorted(r.event for r in rows), sorted(['application_received', 'application_approved', 'administrator_invited', 'administrator_activated']))
            for row in rows:
                self.assertNotIn(token, row.payload_json)
            self.assertEqual(db.scalar(select(Notice).where(Notice.event == 'administrator_activated')).recipient, self.body['contactEmail'])
        self.assertEqual(self.client.get('/api/platform/notifications', headers=self.owner).status_code, 200)

    def test_rejection_notifies_persisted_contact_once_without_provisioning(self):
        application = self.submit(companyName='Second synthetic company', contactEmail='second@example.test',
                                  idempotencyKey=str(uuid.uuid4())).json()
        path = '/api/platform/commercial/applications/' + application['id'] + '/decision'
        body = {**self.decision, 'action':'reject', 'identityConfirmed':False, 'approvedPlanId':None,
                'idempotencyKey':str(uuid.uuid4())}
        for _ in range(2):
            result = self.client.post(path, headers=self.owner, json=body)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertIsNone(result.json()['organizationId'])
        with self.Session() as db:
            rows = db.scalars(select(Notice).where(Notice.event == 'application_rejected')).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].recipient, 'second@example.test')
