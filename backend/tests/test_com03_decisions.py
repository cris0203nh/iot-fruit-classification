"""COM-03: solo SQLite/JWT/archivos sintéticos; nunca abre la base operativa."""
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
from sqlalchemy.exc import OperationalError, IntegrityError
from app.application_models import CommercialApplication, CommercialApplicationDecision
from app.commercial_models import CommercialPlan, CommercialSubscription
from app.models import User
from app.organization_models import Organization
from app.routers.commercial import now
import test_com02_applications as fixtures


class DecisionTests(unittest.TestCase):
    setUpClass = fixtures.ApplicationTests.__dict__['setUpClass']
    auth = fixtures.ApplicationTests.auth
    restore_override = fixtures.ApplicationTests.restore_override
    protected = fixtures.ApplicationTests.protected
    submit = fixtures.ApplicationTests.submit

    def setUp(self):
        fixtures.ApplicationTests.setUp(self)
        self.application_id = self.submit().json()['id']
        self.decision = {'action':'approve','reason':'Identidad empresarial verificada de forma explícita.',
                         'identityConfirmed':True,'approvedPlanId':self.plan['id'],'idempotencyKey':str(uuid.uuid4())}

    def decide(self, **changes):
        return self.client.post(f'/api/platform/commercial/applications/{self.application_id}/decision',
                                headers=self.owner, json={**self.decision,**changes})

    def assert_no_other_effects(self, allow_company=False):
        after = self.protected()
        for name, rows in self.before.items():
            if allow_company and name == 'organizations':
                self.assertEqual(after[name][:len(rows)],rows)
                self.assertEqual(len(after[name]),len(rows)+1)
            else:
                self.assertEqual(after[name],rows,name)

    def test_approve_persists_original_proposal_company_and_audit_only(self):
        result=self.decide()
        self.assertEqual(result.status_code,200,result.text)
        data=result.json()
        self.assertEqual(data['status'],'approved')
        self.assertEqual(data['provisioningState'],'awaiting_admin')
        self.assertIsInstance(data['organizationId'],int)
        self.assertEqual(data['plan'],self.plan)
        self.assertEqual([d['action'] for d in data['decisions']],['review','approve'])
        self.assertEqual(data['decisions'][-1]['actorUserId'],self.users['without_membership'])
        self.assertEqual(data['decisions'][-1]['reason'],self.decision['reason'])
        self.assertEqual(result.headers['cache-control'],'no-store')
        self.assert_no_other_effects(allow_company=True)
        with closing(sqlite3.connect(self.root/'test.db')) as db:
            self.assertEqual(db.execute('SELECT status FROM commercial_applications').fetchone()[0],'approved')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(),[('ok',)])

    def test_reject_and_retry_are_auditable_without_provisioning(self):
        body={'action':'reject','identityConfirmed':False,'approvedPlanId':None,'reason':'Identidad pendiente de sustento.'}
        first=self.decide(**body)
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json(),self.decide(**body).json())
        self.assertEqual(first.json()['status'],'rejected')
        self.assertIsNone(first.json()['organizationId'])
        self.assertEqual(len(first.json()['decisions']),1)
        self.assert_no_other_effects()

    def test_same_key_is_stable_but_changed_payload_or_terminal_decision_conflicts(self):
        first=self.decide()
        self.assertEqual(first.json(),self.decide().json())
        self.assertEqual(self.decide(reason='Otro motivo administrativo').status_code,409)
        self.assertEqual(self.decide(idempotencyKey=str(uuid.uuid4())).status_code,409)
        self.assertEqual(self.decide(action='reject',identityConfirmed=False,approvedPlanId=None,idempotencyKey=str(uuid.uuid4())).status_code,409)
        self.assert_no_other_effects(allow_company=True)

    def test_explicit_review_then_approve(self):
        review=self.decide(action='review',identityConfirmed=False,approvedPlanId=None)
        self.assertEqual(review.status_code,200,review.text)
        self.assertEqual(review.json()['status'],'under_review')
        self.assertEqual(self.decide(idempotencyKey=str(uuid.uuid4())).status_code,200)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(CommercialApplicationDecision)).all()),2)

    def test_concurrent_retries_and_different_keys_cannot_duplicate_company(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.decide(),range(4)))
        self.assertEqual([r.status_code for r in results],[200]*4)
        self.assertEqual(len({r.json()['organizationId'] for r in results}),1)
        self.assert_no_other_effects(allow_company=True)

    def test_two_applications_same_company_cannot_provision_twice(self):
        other=self.submit(contactName='Otro contacto sintético',idempotencyKey=str(uuid.uuid4())).json()['id']
        def call(appid):
            return self.client.post(f'/api/platform/commercial/applications/{appid}/decision',headers=self.owner,
                                    json={**self.decision,'idempotencyKey':str(uuid.uuid4())})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(call,[self.application_id,other]))
        self.assertEqual(sorted(r.status_code for r in results),[200,409])
        self.assert_no_other_effects(allow_company=True)

    def test_existing_company_requires_explicit_matching_identity_without_modifying_legacy(self):
        with self.Session() as db:
            db.get(CommercialApplication,self.application_id).company_name='Empresa A'
            db.get(Organization,1).is_active=False
            db.info['platform_authorized']=True
            db.info['organization_id']=1
            db.add(CommercialSubscription(organization_id=1,plan_id=self.plan['id'],snapshot_json=json.dumps(self.plan),
                status='active',starts_at=now(),ends_at=now()+timedelta(days=30)))
            db.commit()
        self.before=self.protected()
        self.assertEqual(self.decide().status_code,409)
        self.assertEqual(self.decide(existingOrganizationId=2).status_code,409)
        result=self.decide(existingOrganizationId=1)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['organizationId'],1)
        self.assert_no_other_effects()

    def test_inactive_or_changed_plan_is_not_repriced_or_substituted(self):
        with self.Session() as db:
            db.get(CommercialPlan,self.plan['id']).is_active=False; db.commit()
        self.assertEqual(self.decide().status_code,409)
        with self.Session() as db:
            plan=db.get(CommercialPlan,self.plan['id']);plan.is_active=True;plan.amount_cents+=100;db.commit()
        self.assertEqual(self.decide().status_code,409)
        with self.Session() as db:
            row=db.get(CommercialApplication,self.application_id)
            self.assertEqual(row.status,'pending')
            self.assertEqual(json.loads(row.plan_snapshot_json),self.plan)
            self.assertEqual(db.scalars(select(CommercialApplicationDecision)).all(),[])

    def test_identity_confirmation_and_payload_validation(self):
        for changes in ({'identityConfirmed':False},{'reason':' '},{'amountCents':0},{'role':'superadmin'}):
            self.assertEqual(self.decide(**changes).status_code,422)
        self.assertEqual(self.decide(approvedPlanId=999).status_code,409)
        self.assertEqual(self.decide(existingOrganizationId=999).status_code,404)
        self.assert_no_other_effects()

    def test_authorization_roles_and_cross_company_ids(self):
        path=f'/api/platform/commercial/applications/{self.application_id}/decision'
        self.assertEqual(self.client.post(path,json=self.decision).status_code,401)
        for role in ('adminA','adminB','operatorA','shared'):
            for org in (1,2):
                result=self.client.post(path,headers=self.auth(role,org),json={**self.decision,'existingOrganizationId':org})
                self.assertEqual(result.status_code,403,result.text)
                self.assertNotIn(self.body['contactEmail'],result.text)
        self.assert_no_other_effects()

    def test_deactivated_owner_token_is_not_authorized(self):
        with self.Session() as db:
            db.get(User,self.users['without_membership']).is_active=False;db.commit()
        self.assertEqual(self.decide().status_code,401)

    def test_commit_failure_rolls_back_company_status_and_audit(self):
        with patch('sqlalchemy.orm.Session.commit',side_effect=OperationalError('SQL',{},Exception('PRIVATE'))):
            result=self.decide()
        self.assertEqual(result.status_code,503,result.text)
        self.assertNotIn('PRIVATE',result.text)
        self.assert_no_other_effects()
        with self.Session() as db:
            self.assertEqual(db.get(CommercialApplication,self.application_id).status,'pending')
            self.assertEqual(db.scalars(select(CommercialApplicationDecision)).all(),[])

    def test_database_rejects_second_terminal_decision(self):
        self.decide()
        with self.Session() as db:
            db.add(CommercialApplicationDecision(application_id=self.application_id,action='reject',reason='Otro motivo',
                actor_user_id=self.users['without_membership'],created_at=now(),idempotency_hash='x'*64,payload_hash='x'*64))
            with self.assertRaises(IntegrityError): db.commit()

    def test_migration_copy_roundtrip_and_refusal_to_lose_audit(self):
        target=self.root/'migration.db'
        with closing(sqlite3.connect(self.root/'test.db')) as src,closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            dst.execute('DROP TABLE commercial_onboarding_orders')
            dst.execute('DROP INDEX uq_initial_invitation_trace')
            dst.execute('DROP TABLE commercial_application_notifications');dst.commit()  # Solo fixture anterior a c013.
        env={**os.environ,'AGROSCAN_DATABASE_URL':'sqlite:///'+target.as_posix()}
        backend=Path(__file__).resolve().parents[1]
        def run(*args):
            return subprocess.run([sys.executable,'-m','alembic',*args],cwd=backend,env=env,capture_output=True,text=True)
        for args in (('stamp','c012initialadmin'),('downgrade','c011decisions'),('downgrade','c010applications'),('upgrade','c011decisions'),('upgrade','c011decisions')):
            result=run(*args);self.assertEqual(result.returncode,0,result.stderr)
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute('SELECT status FROM commercial_applications').fetchall(),[('pending',)])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            db.execute('INSERT INTO commercial_application_decisions(application_id,action,reason,actor_user_id,created_at,idempotency_hash,payload_hash) VALUES(?,?,?,?,?,?,?)',
                (self.application_id,'review','Ensayo',self.users['without_membership'],now(),'k'*64,'p'*64));db.commit()
        self.assertNotEqual(run('downgrade','c010applications').returncode,0)
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_application_decisions').fetchone()[0],1)
