"""SMTP siempre simulado, SQLite temporal; sin correo ni credenciales operativas."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
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

import test_com02_applications as fixtures
from app.application_models import CommercialApplication, CommercialApplicationNotification
from app.services import application_notification as notice

ENV={'AGROSCAN_SMTP_ENABLED':'true','AGROSCAN_SMTP_HOST':'smtp.example.test','AGROSCAN_SMTP_PORT':'587',
     'AGROSCAN_SMTP_SECURITY':'starttls','AGROSCAN_SMTP_FROM':'sender@example.test',
     'AGROSCAN_COMMERCIAL_OWNER_EMAIL':'owner@example.test','AGROSCAN_SMTP_USERNAME':'synthetic-user',
     'AGROSCAN_SMTP_PASSWORD':'SYNTHETIC-PRIVATE-PASSWORD'}


class NotificationTests(unittest.TestCase):
    setUpClass = fixtures.ApplicationTests.__dict__['setUpClass']
    setUp = fixtures.ApplicationTests.setUp
    auth = fixtures.ApplicationTests.auth
    restore_override = fixtures.ApplicationTests.restore_override
    protected = fixtures.ApplicationTests.protected
    submit = fixtures.ApplicationTests.submit

    def transport(self, ssl=False):
        mocked=patch.object(notice.smtplib,'SMTP_SSL' if ssl else 'SMTP')
        factory=mocked.start();self.addCleanup(mocked.stop)
        factory.return_value.__enter__.return_value.send_message.return_value={}
        return factory,factory.return_value.__enter__.return_value

    def test_disabled_preserves_request_and_never_connects_even_with_host(self):
        factory,_=self.transport()
        with patch.dict(os.environ,{**ENV,'AGROSCAN_SMTP_ENABLED':'false'}): result=self.submit()
        self.assertEqual(result.status_code,201,result.text)
        self.assertEqual(result.json()['ownerNotification'],'disabled');factory.assert_not_called()
        self.assertEqual(self.protected(),self.before)
        with self.Session() as db:
            self.assertEqual(db.get(CommercialApplicationNotification,result.json()['id']).status,'disabled')

    def test_confirmed_transport_contains_only_authorized_owner_message_and_snapshot(self):
        factory,smtp=self.transport()
        with patch.dict(os.environ,ENV): result=self.submit()
        self.assertEqual(result.status_code,201,result.text);self.assertEqual(result.json()['ownerNotification'],'sent')
        message=smtp.send_message.call_args.args[0]
        self.assertEqual(str(message['To']),ENV['AGROSCAN_COMMERCIAL_OWNER_EMAIL'])
        self.assertEqual(str(message['From']),ENV['AGROSCAN_SMTP_FROM'])
        for expected in (self.body['companyName'],self.body['contactName'],self.body['contactEmail'],self.plan['name'],result.json()['id'],'99.00 PEN'):
            self.assertIn(expected,message.get_content())
        smtp.starttls.assert_called_once();smtp.login.assert_called_once_with(ENV['AGROSCAN_SMTP_USERNAME'],ENV['AGROSCAN_SMTP_PASSWORD'])
        self.assertEqual(factory.call_args.kwargs['timeout'],5)
        self.assertNotIn(self.body['contactEmail'],result.text)
        self.assertEqual(self.protected(),self.before)

    def test_delivery_failure_is_logged_without_private_values_and_never_retried(self):
        _,smtp=self.transport();smtp.send_message.side_effect=smtplib.SMTPException('PRIVATE '+self.body['contactEmail'])
        with patch.dict(os.environ,ENV),patch.object(notice.logger,'warning') as log:
            first=self.submit();repeat=self.submit()
        self.assertEqual(first.status_code,201);self.assertEqual(first.json()['ownerNotification'],'failed')
        self.assertEqual(first.json(),repeat.json());self.assertEqual(smtp.send_message.call_count,1)
        self.assertNotIn('PRIVATE',repr(log.call_args_list));self.assertNotIn(self.body['contactEmail'],repr(log.call_args_list))
        self.assertEqual(self.protected(),self.before)

    def test_missing_or_unsafe_configuration_fails_without_network_and_keeps_request(self):
        factory,_=self.transport()
        with patch.dict(os.environ,{**ENV,'AGROSCAN_SMTP_HOST':''}): result=self.submit()
        self.assertEqual(result.status_code,201,result.text);self.assertEqual(result.json()['ownerNotification'],'failed')
        factory.assert_not_called()
        with patch.dict(os.environ,{**ENV,'AGROSCAN_SMTP_SECURITY':'plain'}),self.assertRaises(ValueError): notice.configuration()

    def test_rejected_recipient_is_not_reported_sent(self):
        _,smtp=self.transport();smtp.send_message.return_value={'owner@example.test':(550,b'PRIVATE')}
        with patch.dict(os.environ,ENV): result=self.submit()
        self.assertEqual(result.json()['ownerNotification'],'failed')
        self.assertNotIn('PRIVATE',result.text)

    def test_concurrent_idempotent_posts_send_only_one_message(self):
        _,smtp=self.transport()
        with patch.dict(os.environ,ENV),ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.submit(),range(4)))
        self.assertEqual(sorted(r.status_code for r in results),[200,200,200,201])
        self.assertEqual(len({r.json()['id'] for r in results}),1)
        self.assertEqual(smtp.send_message.call_count,1)
        self.assertEqual(self.submit(idempotencyKey=str(uuid.uuid4())).status_code,409)
        self.assertEqual(smtp.send_message.call_count,1)

    def test_sending_state_after_interruption_is_not_sent_again(self):
        first=self.submit()
        with self.Session() as db:
            db.get(CommercialApplicationNotification,first.json()['id']).status='sending';db.commit()
        factory,_=self.transport()
        with patch.dict(os.environ,ENV): repeat=self.submit()
        self.assertEqual(repeat.json()['ownerNotification'],'sending');factory.assert_not_called()

    def test_result_write_failure_keeps_claim_and_prevents_duplicate_after_smtp_acceptance(self):
        _,smtp=self.transport();original=Session.commit;calls=0
        def commit(db):
            nonlocal calls
            calls+=1
            if calls==4: raise OperationalError('SQL',{},Exception('PRIVATE'))
            return original(db)
        with patch.dict(os.environ,ENV),patch.object(Session,'commit',new=commit): result=self.submit()
        self.assertEqual(result.status_code,201,result.text);self.assertEqual(result.json()['ownerNotification'],'sending')
        with patch.dict(os.environ,ENV): repeat=self.submit()
        self.assertEqual(repeat.json()['ownerNotification'],'sending');self.assertEqual(smtp.send_message.call_count,1)

    def test_ssl_uses_verified_tls_and_no_starttls_downgrade(self):
        factory,smtp=self.transport(ssl=True)
        with patch.dict(os.environ,{**ENV,'AGROSCAN_SMTP_SECURITY':'ssl','AGROSCAN_SMTP_PORT':'465'}): result=self.submit()
        self.assertEqual(result.json()['ownerNotification'],'sent');smtp.starttls.assert_not_called()
        self.assertTrue(factory.call_args.kwargs['context'].check_hostname)

    def test_legacy_records_are_not_retroactively_emailed(self):
        first=self.submit()
        with self.Session() as db:
            db.delete(db.get(CommercialApplicationNotification,first.json()['id']));db.commit()
        factory,_=self.transport()
        with patch.dict(os.environ,ENV): repeat=self.submit()
        self.assertEqual(repeat.json()['ownerNotification'],'not_requested');factory.assert_not_called()

    def test_migration_copy_preserves_legacy_rows_without_backfill(self):
        self.submit();target=self.root/'migration.db'
        with closing(sqlite3.connect(self.root/'test.db')) as src,closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            before=dst.execute('SELECT * FROM commercial_applications').fetchall()
            dst.execute('DROP TABLE commercial_onboarding_orders')
            dst.execute('DROP INDEX uq_initial_invitation_trace')
            dst.execute('DROP TABLE commercial_application_notifications');dst.commit() # Copia sintética c012.
        env={**os.environ,'AGROSCAN_DATABASE_URL':'sqlite:///'+target.as_posix()};backend=Path(__file__).resolve().parents[1]
        for args in (('stamp','c012initialadmin'),('upgrade','c013ownernotice'),('downgrade','c012initialadmin'),('upgrade','c013ownernotice')):
            result=subprocess.run([sys.executable,'-m','alembic',*args],cwd=backend,env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute('SELECT * FROM commercial_applications').fetchall(),before)
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_application_notifications').fetchone()[0],0)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(),[('ok',)])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
