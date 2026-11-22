"""Alta comercial ligada a invitación, con SQLite/identidades únicamente sintéticas."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
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
from sqlalchemy.exc import IntegrityError

import test_com04_initial_admin as fixtures
from app.commercial_models import CommercialOnboardingOrder, CommercialSubscription, CommercialOrder
from app.routers.commercial import now


class OnboardingCommerceTests(unittest.TestCase):
    setUpClass=fixtures.InitialAdminTests.__dict__['setUpClass']
    auth=fixtures.InitialAdminTests.auth
    restore_override=fixtures.InitialAdminTests.restore_override
    protected=fixtures.InitialAdminTests.protected
    submit=fixtures.InitialAdminTests.submit
    decide=fixtures.InitialAdminTests.decide
    emit=fixtures.InitialAdminTests.emit
    register=fixtures.InitialAdminTests.register

    def setUp(self):
        fixtures.InitialAdminTests.setUp(self)
        environment=patch.dict(os.environ,{'AGROSCAN_ENVIRONMENT':'demo','AGROSCAN_SUBSCRIPTION_SIMULATOR':'true'})
        environment.start();self.addCleanup(environment.stop)
        token=self.emit().json()['token']
        result=self.register(token);self.assertEqual(result.status_code,201,result.text)
        self.customer={'Authorization':'Bearer '+result.json()['access_token']}
        self.baseline=self.protected()

    def prepare(self, **extra):
        return self.client.post('/api/commercial/orders',headers=self.customer,json={
            'planId':self.plan['id'],'action':'subscribe','idempotencyKey':str(uuid.uuid4()),**extra})

    def confirm_order(self, order, scenario='approve', headers=None):
        return self.client.post(f'/api/commercial/orders/{order["id"]}/confirm',headers=headers or self.customer,json={'scenario':scenario})

    def company_view(self):
        return self.client.get('/api/commercial/subscription',headers=self.customer).json()

    def new_plan(self):
        result=self.client.post('/api/platform/commercial/plans',headers=self.owner,json={
            'code':'new-plan','name':'Nuevo plan DEMO','description':'Condiciones vigentes','amountCents':15000,'period':'annual','benefits':['Trazabilidad']})
        self.assertEqual(result.status_code,201,result.text)
        return result.json()

    def test_first_approval_completes_with_explicit_references_and_persistence(self):
        self.assertEqual(self.company_view()['onboarding']['stage'],'awaiting_demo_order')
        order=self.prepare().json();result=self.confirm_order(order)
        self.assertEqual(result.status_code,200,result.text)
        data=self.company_view();sub=data['subscription'];trace=data['onboarding']
        self.assertEqual(trace['stage'],'completed');self.assertEqual(trace['orderId'],order['id'])
        self.assertEqual(trace['subscriptionId'],sub['id']);self.assertEqual(trace['applicationId'],self.application_id)
        self.assertEqual(sub['status'],'active');self.assertEqual(sub['plan'],self.plan)
        owner=self.client.get('/api/platform/commercial/overview',headers=self.owner).json()
        self.assertIn(trace,owner['onboardings'])
        applications=self.client.get('/api/platform/commercial/applications',headers=self.owner).json()['items']
        self.assertEqual(applications[0]['provisioningState'],'completed')
        self.assertEqual(applications[0]['commercialOrderId'],order['id'])
        with closing(sqlite3.connect(self.root/'test.db')) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(db.execute('SELECT order_id,subscription_id FROM commercial_onboarding_orders').fetchall(),[(order['id'],sub['id'])])
        after=self.protected()
        for table,rows in self.baseline.items():
            if table not in ('commercial_orders','commercial_transactions','commercial_subscriptions','commercial_onboarding_orders'):
                self.assertEqual(after[table],rows,table)

    def test_rejected_and_cancelled_attempts_do_not_activate_or_complete(self):
        for scenario in ('reject','cancel'):
            order=self.prepare().json();result=self.confirm_order(order,scenario)
            self.assertEqual(result.status_code,200,result.text)
            self.assertIsNone(self.company_view()['subscription'])
            self.assertEqual(self.company_view()['onboarding']['stage'],'awaiting_demo_order')
        self.assertEqual(self.confirm_order(self.prepare().json()).status_code,200)

    def test_first_plan_and_action_cannot_be_bypassed(self):
        other=self.new_plan()
        self.assertEqual(self.prepare(planId=other['id']).status_code,409)
        self.assertEqual(self.prepare(action='change').status_code,409)
        self.assertEqual(self.prepare(amountCents=1).status_code,422)
        self.assertEqual(self.prepare(organizationId=1).status_code,422)
        self.assertIsNone(self.company_view()['subscription'])

    def test_inactive_proposal_requires_explicit_new_selection_without_changing_original(self):
        other=self.new_plan()
        self.client.patch(f'/api/platform/commercial/plans/{self.plan["id"]}/status',headers=self.owner,json={'isActive':False})
        self.assertFalse(self.company_view()['onboarding']['approvedPlanAvailable'])
        self.assertEqual(self.prepare(planId=other['id']).status_code,409)
        order=self.prepare(planId=other['id'],acceptUpdatedPlan=True).json()
        self.assertEqual(self.confirm_order(order).status_code,200)
        data=self.company_view()
        self.assertEqual(data['subscription']['plan']['id'],other['id'])
        self.assertEqual(data['onboarding']['approvedPlan'],self.plan)

    def test_parallel_confirmation_and_retry_do_not_duplicate_periods_or_events(self):
        order=self.prepare().json()
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:self.confirm_order(order),range(4)))
        self.assertEqual([r.status_code for r in results],[200]*4)
        first=self.company_view()['subscription']['endsAt']
        self.assertEqual(len(self.company_view()['transactions']),1)
        self.assertEqual(self.confirm_order(order).status_code,200)
        self.assertEqual(self.company_view()['subscription']['endsAt'],first)

    def test_parallel_distinct_first_orders_complete_once(self):
        orders=[self.prepare().json(),self.prepare().json()]
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(self.confirm_order,orders))
        self.assertEqual(sorted(r.status_code for r in results),[200,409])
        self.assertEqual(len(self.company_view()['transactions']),1)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(CommercialOnboardingOrder).where(CommercialOnboardingOrder.subscription_id.is_not(None))).all()),1)

    def test_renewal_calendar_idempotency_and_change_apply_only_on_approved_result(self):
        clock=datetime(2027,1,31,12)
        with patch('app.routers.commercial.now',return_value=clock):
            first=self.prepare().json();self.confirm_order(first)
            self.assertEqual(self.company_view()['subscription']['endsAt'],'2027-02-28T12:00:00Z')
            renewal=self.prepare(action='renew').json()
            self.assertEqual(self.confirm_order(renewal).status_code,200)
            self.assertEqual(self.confirm_order(renewal).status_code,200)
            self.assertEqual(self.company_view()['subscription']['endsAt'],'2027-03-28T12:00:00Z')
            other=self.new_plan();change=self.prepare(action='change',planId=other['id']).json()
            self.assertEqual(self.company_view()['subscription']['plan']['id'],self.plan['id'])
            self.assertEqual(self.confirm_order(change,'reject').status_code,200)
            self.assertEqual(self.company_view()['subscription']['plan']['id'],self.plan['id'])
            approved=self.prepare(action='change',planId=other['id']).json();self.confirm_order(approved)
            self.assertEqual(self.company_view()['subscription']['endsAt'],'2028-01-31T12:00:00Z')
            self.assertEqual(self.company_view()['onboarding']['orderId'],first['id'])

    def test_expiry_grace_and_immediate_cancellation_do_not_block_operations(self):
        self.confirm_order(self.prepare().json())
        with self.Session() as db:
            sub=db.scalar(select(CommercialSubscription));sub.starts_at=now()-timedelta(days=60);sub.ends_at=now()-timedelta(days=1);db.commit()
        sub=self.company_view()['subscription'];self.assertEqual(sub['status'],'expired');self.assertTrue(sub['inGracePeriod'])
        with self.Session() as db:
            db.scalar(select(CommercialSubscription)).ends_at=now()-timedelta(days=8);db.commit()
        self.assertFalse(self.company_view()['subscription']['inGracePeriod'])
        result=self.client.post('/api/commercial/subscription/cancel',headers=self.customer)
        self.assertEqual(result.json()['status'],'cancelled');self.assertFalse(result.json()['inGracePeriod'])
        self.assertIsNone(result.json()['graceEndsAt']);self.assertEqual(result.json()['cancellationEffect'],'immediate')
        self.assertEqual(self.client.get('/api/lots',headers=self.customer).status_code,200)
        self.assertEqual(self.company_view()['onboarding']['stage'],'completed')

    def test_expired_order_is_visible_but_cannot_activate(self):
        order=self.prepare().json()
        with self.Session() as db:
            db.get(CommercialOrder,order['id']).created_at=now()-timedelta(hours=25);db.commit()
        self.assertTrue(self.company_view()['orders'][0]['isExpired'])
        self.assertEqual(self.confirm_order(order).status_code,409)
        self.assertIsNone(self.company_view()['subscription'])

    def test_role_revocation_and_cross_company_known_ids(self):
        order=self.prepare().json()
        self.assertEqual(self.confirm_order(order,headers=self.auth('adminA',1)).status_code,404)
        for who,org in (('operatorA',1),('shared',2)):
            headers=self.auth(who,org)
            self.assertEqual(self.confirm_order(order,headers=headers).status_code,403)
            self.assertEqual(self.client.post('/api/commercial/subscription/cancel',headers=headers).status_code,403)
        self.assertEqual(self.client.get('/api/commercial/subscription',headers={**self.customer,'X-Organization-ID':'1'}).status_code,403)
        with self.Session() as db:
            from app.organization_models import OrganizationMembership
            member=db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id==self.company));member.is_active=False;db.commit()
        self.assertEqual(self.confirm_order(order).status_code,403)

    def test_failure_rolls_back_subscription_completion_and_transaction(self):
        order=self.prepare().json()
        with patch('app.routers.commercial.CommercialTransaction',side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):self.confirm_order(order)
        self.assertIsNone(self.company_view()['subscription'])
        self.assertEqual(self.company_view()['onboarding']['stage'],'awaiting_demo_order')
        self.assertEqual(self.company_view()['orders'][0]['status'],'pending')

    def test_foreign_key_rejects_cross_company_onboarding(self):
        order=self.prepare().json()
        with self.Session() as db:
            row=db.get(CommercialOnboardingOrder,order['id']);row.organization_id=1
            with self.assertRaises(IntegrityError):db.commit()

    def test_simulator_disabled_prevents_activation(self):
        with patch.dict(os.environ,{'AGROSCAN_SUBSCRIPTION_SIMULATOR':'false'}):
            self.assertEqual(self.prepare().status_code,503)
        self.assertIsNone(self.company_view()['subscription'])

    def test_legacy_company_keeps_renewing_without_fabricating_onboarding_completion(self):
        application=self.submit(companyName='Empresa A',idempotencyKey=str(uuid.uuid4())).json()['id']
        decision=self.client.post(f'/api/platform/commercial/applications/{application}/decision',headers=self.owner,json={
            'action':'approve','reason':'Vinculación legacy verificada en fixture','identityConfirmed':True,
            'existingOrganizationId':1,'idempotencyKey':str(uuid.uuid4())})
        self.assertEqual(decision.status_code,200,decision.text)
        with self.Session() as db:
            db.add(CommercialSubscription(organization_id=1,plan_id=self.plan['id'],snapshot_json=json.dumps(self.plan),
                status='active',starts_at=now(),ends_at=now()+timedelta(days=20)));db.commit()
        headers=self.auth('adminA',1)
        result=self.client.post('/api/commercial/orders',headers=headers,json={
            'planId':self.plan['id'],'action':'renew','idempotencyKey':str(uuid.uuid4())})
        self.assertEqual(result.status_code,201,result.text)
        self.assertEqual(self.confirm_order(result.json(),headers=headers).status_code,200)
        state=self.client.get('/api/commercial/subscription',headers=headers).json()
        self.assertEqual(state['subscription']['status'],'active')
        self.assertEqual(state['onboarding']['stage'],'awaiting_admin')
        self.assertIsNone(state['onboarding']['orderId'])
        self.assertEqual(self.company_view()['onboarding']['stage'],'awaiting_demo_order')

    def test_migration_roundtrip_copy_keeps_application_invitation_and_commerce(self):
        target=self.root/'migration.db'
        with closing(sqlite3.connect(self.root/'test.db')) as src,closing(sqlite3.connect(target)) as dst:src.backup(dst)
        env={**os.environ,'AGROSCAN_DATABASE_URL':'sqlite:///'+target.as_posix()};backend=Path(__file__).resolve().parents[1]
        for args in (('stamp','c014onboarding'),('downgrade','c013ownernotice'),('upgrade','c014onboarding'),('upgrade','c014onboarding')):
            result=subprocess.run([sys.executable,'-m','alembic',*args],cwd=backend,env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(),[('ok',)])
            self.assertEqual(db.execute('SELECT status FROM commercial_applications').fetchall(),[('approved',)])
            self.assertEqual(db.execute('SELECT count(*) FROM commercial_onboarding_orders').fetchone()[0],0)
