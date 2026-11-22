"""COM-04 sobre SQLite temporal, RSA real y claves exclusivamente sintéticas."""
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
import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

import test_com03_decisions as fixtures
import test_saas06_identity as identity
from app.application_models import CommercialApplication, CommercialApplicationInvitation
from app.identity_models import OrganizationInvitation, GoogleIdentity
from app.models import Role, User
from app.organization_models import Organization, OrganizationMembership
from app.platform_models import PlatformOwner
from app.services import google_identity
from app.services.invitations import digest, now


class InitialAdminTests(unittest.TestCase):
    setUpClass = identity.IdentityInvitationTests.__dict__['setUpClass']
    auth = fixtures.DecisionTests.auth
    restore_override = fixtures.DecisionTests.restore_override
    protected = fixtures.DecisionTests.protected
    submit = fixtures.DecisionTests.submit
    decide = fixtures.DecisionTests.decide
    challenge = identity.IdentityInvitationTests.challenge
    credential = identity.IdentityInvitationTests.credential

    def setUp(self):
        fixtures.DecisionTests.setUp(self)
        result=self.decide();self.assertEqual(result.status_code,200,result.text)
        self.company=result.json()['organizationId']
        self.before=self.protected()
        self.path=f'/api/platform/commercial/applications/{self.application_id}/administrator-invitation'
        self.command={'action':'issue','idempotencyKey':str(uuid.uuid4())}

    def emit(self, **changes):
        return self.client.post(self.path,headers=self.owner,json={**self.command,**changes})

    def register(self, token, username='initial-admin'):
        return self.client.post('/api/auth/invitations/register',json={'token':token,'username':username,
            'fullName':'Synthetic Admin','password':self.password})

    def overview(self):
        return next(a for a in self.client.get('/api/platform/commercial/applications',headers=self.owner).json()['items'] if a['id']==self.application_id)

    def configure_google(self):
        configured=patch.dict(os.environ,{'AGROSCAN_GOOGLE_CLIENT_ID':identity.CLIENT});configured.start();self.addCleanup(configured.stop)
        jwk={**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.private.public_key())),'kid':'google-test','alg':'RS256','use':'sig'}
        keys=jwt.PyJWKClient('https://www.googleapis.com/oauth2/v3/certs')
        for mocked in (patch.object(keys,'fetch_data',return_value={'keys':[jwk]}),patch.object(google_identity,'google_keys',return_value=keys)):
            mocked.start();self.addCleanup(mocked.stop)

    def test_first_issue_forces_contact_role_company_and_replay_never_returns_token(self):
        first=self.emit();self.assertEqual(first.status_code,201,first.text)
        data=first.json();self.assertEqual(data['invitation']['email'],self.body['contactEmail'])
        self.assertEqual(data['invitation']['role'],'administrador')
        self.assertEqual(len(data['token']),43)
        repeat=self.emit();self.assertEqual(repeat.status_code,200,repeat.text)
        self.assertNotIn('token',repeat.json())
        self.assertEqual(repeat.json()['invitation'],data['invitation'])
        self.assertEqual(first.headers['cache-control'],'no-store')
        with self.Session() as db:
            stored=db.get(OrganizationInvitation,data['invitation']['id'])
            self.assertEqual(stored.organization_id,self.company)
            self.assertEqual(stored.token_hash,digest(data['token']))
            self.assertNotEqual(stored.token_hash,data['token'])
            self.assertIsNone(db.scalar(select(OrganizationMembership.user_id).where(OrganizationMembership.user_id==self.users['without_membership'])))
        output=self.client.get('/api/platform/commercial/applications',headers=self.owner)
        self.assertNotIn(data['token'],output.text);self.assertNotIn('token_hash',output.text)
        self.assertEqual(self.emit(idempotencyKey=str(uuid.uuid4())).status_code,409)

    def test_local_acceptance_sets_membership_login_stage_and_preserves_other_data(self):
        token=self.emit().json()['token']
        self.assertEqual(self.client.post('/api/auth/invitations/preview',json={'token':token}).json()['organizationName'],self.body['companyName'])
        accepted=self.register(token);self.assertEqual(accepted.status_code,201,accepted.text)
        self.assertFalse(accepted.json()['is_superadmin'])
        headers={'Authorization':'Bearer '+accepted.json()['access_token']}
        me=self.client.get('/api/auth/me',headers=headers).json()
        self.assertEqual(me['roles'],['administrador']);self.assertEqual(me['organizationId'],self.company)
        self.assertEqual(self.client.get('/api/lots',headers={**headers,'X-Organization-ID':'1'}).status_code,403)
        self.assertEqual(self.client.get('/api/platform/organizations',headers=headers).status_code,403)
        self.assertEqual(self.client.get('/api/commercial/subscription',headers=headers).json()['subscription'],None)
        self.assertEqual(self.overview()['provisioningState'],'awaiting_demo_order')
        self.assertTrue(self.overview()['administratorActive'])
        self.assertEqual(self.emit(action='reissue',idempotencyKey=str(uuid.uuid4())).status_code,409)
        self.assertEqual(self.register(token,'another-user').status_code,410)
        after=self.protected()
        for table,rows in self.before.items():
            if table not in ('users','organization_memberships','organization_invitations'):
                self.assertEqual(after[table],rows,table)
        self.assertEqual(len(after['users']),len(self.before['users'])+1)
        self.assertEqual(len(after['organization_memberships']),len(self.before['organization_memberships'])+1)

    def test_expiry_revocation_reissue_and_reissue_replay(self):
        first=self.emit().json()
        with self.Session() as db:
            row=db.get(OrganizationInvitation,first['invitation']['id'])
            row.created_at=now()-timedelta(days=3);row.expires_at=now()-timedelta(days=1);db.commit()
        self.assertEqual(self.register(first['token']).status_code,410)
        second=self.emit(action='reissue',idempotencyKey='replacement-synthetic-1').json()
        self.assertNotEqual(second['token'],first['token'])
        self.assertNotIn('token',self.emit(action='reissue',idempotencyKey='replacement-synthetic-1').json())
        self.assertEqual(self.emit(action='revoke',idempotencyKey='revocation-synthetic-1').status_code,200)
        self.assertEqual(self.emit(action='revoke',idempotencyKey='revocation-synthetic-1').json()['invitation']['status'],'revoked')
        self.assertEqual(self.register(second['token']).status_code,410)
        third=self.emit(action='reissue',idempotencyKey='replacement-synthetic-2').json()
        self.assertEqual(self.register(third['token']).status_code,201)

    def test_reissue_invalidates_still_live_link(self):
        first=self.emit().json()['token']
        second=self.emit(action='reissue',idempotencyKey=str(uuid.uuid4())).json()['token']
        self.assertEqual(self.register(first).status_code,410)
        self.assertEqual(self.register(second).status_code,201)

    def test_concurrent_issuance_reveals_only_one_token(self):
        with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(lambda _:self.emit(),range(4)))
        self.assertEqual(sorted(r.status_code for r in results),[200,200,200,201])
        self.assertEqual(sum('token' in r.json() for r in results),1)
        self.assertEqual(len({r.json()['invitation']['id'] for r in results}),1)

    def test_concurrent_acceptance_creates_only_one_admin(self):
        token=self.emit().json()['token']
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda i:self.register(token,f'initial-{i}'),range(2)))
        self.assertEqual(sorted(r.status_code for r in results),[201,410])
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(OrganizationMembership).where(OrganizationMembership.organization_id==self.company)).all()),1)

    def test_concurrent_reissue_has_one_new_token_and_invalidates_old(self):
        old=self.emit().json()['token']
        key=str(uuid.uuid4())
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:self.emit(action='reissue',idempotencyKey=key),range(3)))
        self.assertEqual(sorted(r.status_code for r in results),[200,200,201])
        self.assertEqual(sum('token' in r.json() for r in results),1)
        self.assertEqual(self.register(old).status_code,410)
        token=next(r.json()['token'] for r in results if 'token' in r.json())
        self.assertEqual(self.register(token).status_code,201)

    def test_initial_invitation_requires_approved_request_and_no_company_header_bypass(self):
        second=self.submit(companyName='Pending synthetic company',idempotencyKey=str(uuid.uuid4())).json()['id']
        result=self.client.post(f'/api/platform/commercial/applications/{second}/administrator-invitation',headers=self.owner,json=self.command)
        self.assertEqual(result.status_code,409)
        token=self.emit().json()['token']
        with self.Session() as db:
            db.get(User,self.users['without_membership']).is_active=False;db.commit()
        self.assertEqual(self.register(token).status_code,403)
        self.assertEqual(self.emit(action='reissue',idempotencyKey=str(uuid.uuid4())).status_code,401)

    def test_company_admin_cannot_bypass_owner_lifecycle_via_legacy_revoke(self):
        invitation=self.emit().json()['invitation']
        with self.Session() as db:
            db.add(OrganizationMembership(organization_id=self.company,user_id=self.users['adminA'],role_id=1));db.commit()
        result=self.client.delete(f'/api/invitations/{invitation["id"]}',headers=self.auth('adminA',self.company))
        self.assertEqual(result.status_code,403,result.text)

    def test_existing_account_requires_password_and_preserves_prior_memberships(self):
        token=self.emit().json()['token']
        path='/api/auth/invitations/accept'
        self.assertEqual(self.client.post(path,headers=self.auth('adminA'),json={'token':token,'password':'incorrect'}).status_code,401)
        result=self.client.post(path,headers=self.auth('adminA'),json={'token':token,'password':self.password})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['organization_id'],self.company)
        self.assertEqual(self.client.get('/api/auth/me',headers=self.auth('adminA',1)).json()['roles'],['administrador'])
        self.assertFalse(result.json()['is_superadmin'])

    def test_google_requires_matching_email_and_real_signature_nonce_without_email_merging(self):
        self.configure_google();token=self.emit().json()['token']
        with self.Session() as db:
            db.get(User,self.users['adminB']).username=self.body['contactEmail'];db.commit()
        nonce=self.challenge()
        wrong=self.client.post('/api/auth/google/accept-invitation',json={'token':token,'credential':self.credential(nonce,email='wrong@example.test')})
        self.assertEqual(wrong.status_code,403)
        nonce=self.challenge()
        result=self.client.post('/api/auth/google/accept-invitation',json={'token':token,'credential':self.credential(nonce,email=self.body['contactEmail'])})
        self.assertEqual(result.status_code,200,result.text)
        self.assertFalse(result.json()['is_superadmin'])
        with self.Session() as db:
            self.assertNotEqual(db.get(GoogleIdentity,'subject-a').user_id,self.users['adminB'])
        self.assertEqual(self.overview()['provisioningState'],'awaiting_demo_order')

    def test_owner_authority_company_state_and_recipient_are_revalidated(self):
        invitation=self.emit().json()
        with self.Session() as db:
            db.get(Organization,self.company).is_active=False;db.commit()
        self.assertEqual(self.register(invitation['token']).status_code,403)
        with self.Session() as db:
            db.get(Organization,self.company).is_active=True
            db.get(CommercialApplication,self.application_id).contact_email='changed@example.test';db.commit()
        self.assertEqual(self.register(invitation['token']).status_code,403)
        with self.Session() as db:
            db.get(CommercialApplication,self.application_id).contact_email=self.body['contactEmail']
            db.delete(db.get(PlatformOwner,1));db.commit()
        self.assertEqual(self.register(invitation['token']).status_code,403)

    def test_linked_google_identity_accepts_explicitly_without_creating_another_account(self):
        self.configure_google();token=self.emit().json()['token']
        with self.Session() as db:
            db.add(GoogleIdentity(subject='subject-a',user_id=self.users['adminA'],email=self.body['contactEmail']));db.commit()
        nonce=self.challenge()
        result=self.client.post('/api/auth/google/accept-invitation',json={'token':token,'credential':self.credential(nonce,email=self.body['contactEmail'])})
        self.assertEqual(result.status_code,200,result.text)
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(User)).all()),len(self.before['users']))
            self.assertEqual(db.get(GoogleIdentity,'subject-a').user_id,self.users['adminA'])

    def test_privileges_and_manipulated_company_email_role_are_rejected(self):
        self.assertEqual(self.client.post(self.path,json=self.command).status_code,401)
        for role in ('adminA','adminB','operatorA','shared'):
            self.assertEqual(self.client.post(self.path,headers=self.auth(role,2),json=self.command).status_code,403)
        for extra in ({'email':'other@example.test'},{'role':'superadmin'},{'organizationId':1},{'expiresHours':169}):
            self.assertEqual(self.emit(**extra).status_code,422)
        token=self.emit().json()['token']
        self.assertEqual(self.client.post('/api/auth/invitations/accept',headers=self.owner,json={'token':token,'password':self.password}).status_code,403)
        self.assertEqual(self.client.get('/api/invitations',headers=self.auth('adminA')).json(),[])

    def test_first_admin_path_cannot_restore_existing_or_revoked_memberships(self):
        with self.Session() as db:
            db.add(OrganizationMembership(organization_id=self.company,user_id=self.users['adminA'],role_id=1,is_active=False));db.commit()
        self.assertEqual(self.emit().status_code,409)

    def test_membership_revocation_after_acceptance_is_effective_without_reopening_onboarding(self):
        token=self.emit().json()['token'];result=self.register(token)
        headers={'Authorization':'Bearer '+result.json()['access_token']}
        with self.Session() as db:
            member=db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id==self.company))
            member.is_active=False;db.commit()
        self.assertEqual(self.client.get('/api/lots',headers=headers).status_code,403)
        self.assertFalse(self.overview()['administratorActive'])
        self.assertEqual(self.overview()['provisioningState'],'awaiting_demo_order')
        self.assertEqual(self.emit(action='reissue',idempotencyKey=str(uuid.uuid4())).status_code,409)

    def test_database_rejects_cross_company_binding(self):
        invitation=self.emit().json()['invitation']
        with self.Session() as db:
            binding=db.get(CommercialApplicationInvitation,invitation['id']);binding.organization_id=1
            with self.assertRaises(IntegrityError): db.commit()

    def test_failure_rolls_back_reissue_and_leaves_previous_token_valid(self):
        first=self.emit().json()
        with patch('sqlalchemy.orm.Session.commit',side_effect=OperationalError('SQL',{},Exception('PRIVATE'))):
            result=self.emit(action='reissue',idempotencyKey=str(uuid.uuid4()))
        self.assertEqual(result.status_code,503,result.text);self.assertNotIn('PRIVATE',result.text)
        self.assertEqual(self.register(first['token']).status_code,201)

    def test_migration_roundtrip_keeps_approval_and_legacy_invitation_rows(self):
        target=self.root/'migration.db'
        with closing(sqlite3.connect(self.root/'test.db')) as src,closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            dst.execute('DROP TABLE commercial_onboarding_orders')
            dst.execute('DROP INDEX uq_initial_invitation_trace')
            dst.execute('DROP TABLE commercial_application_notifications');dst.commit()  # Solo fixture anterior a c013.
        env={**os.environ,'AGROSCAN_DATABASE_URL':'sqlite:///'+target.as_posix()};backend=Path(__file__).resolve().parents[1]
        for args in (('stamp','c012initialadmin'),('downgrade','c011decisions'),('upgrade','c012initialadmin'),('upgrade','c012initialadmin')):
            result=subprocess.run([sys.executable,'-m','alembic',*args],cwd=backend,env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(),[('ok',)])
            self.assertEqual(db.execute('SELECT status FROM commercial_applications').fetchall(),[('approved',)])
