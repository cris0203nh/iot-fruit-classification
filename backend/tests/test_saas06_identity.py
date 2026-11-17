"""RSA real y SQLite aislado; sin Google real, correo ni credenciales originales."""
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import func, select

import test_saas03_organizations as fixture
from app.identity_models import GoogleChallenge, GoogleIdentity, OrganizationInvitation
from app.models import User
from app.organization_models import Organization, OrganizationMembership
from app.platform_models import PlatformOwner
from app.services import google_identity
from app.services.invitations import digest
from app.routers.auth_identity import COOKIE

CLIENT = 'synthetic-client.apps.googleusercontent.com'


class IdentityInvitationTests(unittest.TestCase):
    setUp = fixture.OrganizationIsolationTests.setUp
    restore_override = fixture.OrganizationIsolationTests.restore_override
    auth = fixture.OrganizationIsolationTests.auth

    @classmethod
    def setUpClass(cls):
        fixture.OrganizationIsolationTests.setUpClass.__func__(cls)
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        fixture.OrganizationIsolationTests.setUp(self)
        configured = patch.dict(os.environ, {'AGROSCAN_GOOGLE_CLIENT_ID': CLIENT})
        configured.start(); self.addCleanup(configured.stop)
        jwk = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.private.public_key())), 'kid':'google-test', 'alg':'RS256', 'use':'sig'}
        keys = jwt.PyJWKClient('https://www.googleapis.com/oauth2/v3/certs')
        fetch = patch.object(keys,'fetch_data',return_value={'keys':[jwk]})
        fetch.start(); self.addCleanup(fetch.stop)
        resolver = patch.object(google_identity,'google_keys',return_value=keys)
        resolver.start(); self.addCleanup(resolver.stop)

    def challenge(self):
        result = self.client.post('/api/auth/google/challenge', headers={'X-AgroScan-Intent':'google'})
        self.assertEqual(result.status_code,200,result.text)
        self.assertIn('HttpOnly',result.headers['set-cookie'])
        self.assertIn('SameSite=strict',result.headers['set-cookie'])
        return result.json()['nonce']

    def credential(self, nonce_value, **changes):
        now = int(datetime.now(timezone.utc).timestamp())
        claims = {'iss':'https://accounts.google.com','aud':CLIENT,'sub':'subject-a','iat':now,'exp':now+300,
                  'nonce':nonce_value,'email':'recipient@example.test','email_verified':True,'name':'Recipient'}
        claims.update(changes)
        for key in list(claims):
            if claims[key] is None: del claims[key]
        return jwt.encode(claims,self.private,algorithm='RS256',headers={'kid':'google-test'})

    def invitation(self, company='adminA', **changes):
        body = {'email':'recipient@example.test','role':'operador',**changes}
        result = self.client.post('/api/invitations', headers=self.auth(company), json=body)
        self.assertEqual(result.status_code,201,result.text)
        return result.json()

    def test_firma_claims_y_nonce_invalidos_no_autentican(self):
        nonce = self.challenge()
        for changes in ({'iss':'https://evil.example'},{'aud':'other-client'},{'sub':None},{'sub':''},
                        {'exp':1},{'iat':9999999999},{'email_verified':False},{'nonce':'Z'*43},
                        {'azp':'other-client'},{'exp':None}):
            with self.subTest(changes=changes):
                result = self.client.post('/api/auth/google/login',json={'credential':self.credential(nonce,**changes)})
                self.assertEqual(result.status_code,401,result.text)
        valid = self.credential(nonce)
        tampered = valid[:-8] + 'AAAAAAAA'
        for token in (tampered, jwt.encode({'sub':'subject-a'},'synthetic-hmac-secret-000000000000000000',algorithm='HS256'),
                      jwt.encode({'sub':'subject-a'},self.private,algorithm='RS256',headers={'kid':'unknown'})):
            self.assertEqual(self.client.post('/api/auth/google/login',json={'credential':token}).status_code,401)
        self.client.cookies.clear()
        self.assertEqual(self.client.post('/api/auth/google/login',json={'credential':valid}).status_code,401)

    def test_no_hay_enlace_por_correo_y_vinculacion_exige_cuenta_y_contrasena(self):
        with self.Session() as db:
            db.get(User,self.users['adminB']).username='recipient@example.test'
            db.add(PlatformOwner(id=1,user_id=self.users['adminB'])); db.commit()
        nonce = self.challenge()
        token = self.credential(nonce)
        self.assertEqual(self.client.post('/api/auth/google/login',json={'credential':token}).status_code,403)
        self.assertEqual(self.client.post('/api/auth/google/link',json={'credential':token,'password':self.password}).status_code,401)
        wrong = self.client.post('/api/auth/google/link',headers=self.auth(),json={'credential':token,'password':'incorrect'})
        self.assertEqual(wrong.status_code,401)
        linked = self.client.post('/api/auth/google/link',headers=self.auth(),json={'credential':token,'password':self.password})
        self.assertEqual(linked.status_code,200,linked.text)
        with self.Session() as db:
            self.assertEqual(db.get(GoogleIdentity,'subject-a').user_id,self.users['adminA'])
            self.assertEqual(db.scalar(select(func.count(User.id))),5)
        nonce = self.challenge()
        signed_in = self.client.post('/api/auth/google/login',json={'credential':self.credential(nonce)})
        self.assertEqual(signed_in.status_code,200)
        self.assertFalse(signed_in.json()['is_superadmin'])
        nonce = self.challenge()
        result = self.client.post('/api/auth/google/link',headers=self.auth('adminB'),json={'credential':self.credential(nonce),'password':self.password})
        self.assertEqual(result.status_code,409)

    def test_login_google_usa_jwt_local_y_desafio_de_un_solo_uso(self):
        with self.Session() as db:
            db.add(GoogleIdentity(subject='subject-a',user_id=self.users['operatorA'],email='recipient@example.test')); db.commit()
        nonce = self.challenge(); cookie = self.client.cookies.get(COOKIE)
        token = self.credential(nonce)
        self.assertEqual(self.client.get('/api/auth/me',headers={'Authorization':'Bearer '+token}).status_code,401)
        result = self.client.post('/api/auth/google/login',json={'credential':token})
        self.assertEqual(result.status_code,200,result.text)
        self.assertFalse(result.json()['is_superadmin'])
        me = self.client.get('/api/auth/me',headers={'Authorization':'Bearer '+result.json()['access_token']})
        self.assertEqual(me.json()['roles'],['operador'])
        replay = self.client.post('/api/auth/google/login',headers={'Cookie':f'{COOKIE}={cookie}'},json={'credential':token})
        self.assertEqual(replay.status_code,401)
        with self.Session() as db:
            db.get(OrganizationMembership,(1,self.users['operatorA'],2)).is_active=False; db.commit()
        nonce=self.challenge()
        again=self.client.post('/api/auth/google/login',json={'credential':self.credential(nonce)})
        self.assertEqual(again.status_code,200)
        self.assertEqual(self.client.get('/api/lots',headers={'Authorization':'Bearer '+again.json()['access_token']}).status_code,403)
        with self.Session() as db:
            db.get(User,self.users['operatorA']).is_active=False; db.commit()
        nonce=self.challenge()
        self.assertEqual(self.client.post('/api/auth/google/login',json={'credential':self.credential(nonce)}).status_code,401)

    def test_invitaciones_solo_admin_de_su_empresa_sin_tokens_en_listados(self):
        invitation=self.invitation(email='RECIPIENT@EXAMPLE.TEST')
        self.assertEqual(invitation['email'],'recipient@example.test')
        with self.Session() as db:
            stored=db.get(OrganizationInvitation,invitation['id'])
            self.assertEqual(stored.token_hash,digest(invitation['token']))
            self.assertNotEqual(stored.token_hash,invitation['token'])
        own=self.client.get('/api/invitations',headers=self.auth())
        self.assertEqual(own.status_code,200)
        self.assertNotIn(invitation['token'],own.text)
        self.assertNotIn('token_hash',own.text)
        self.assertEqual(self.client.get('/api/invitations',headers=self.auth('adminB')).json(),[])
        self.assertEqual(self.client.delete(f'/api/invitations/{invitation["id"]}',headers=self.auth('adminB')).status_code,404)
        for headers,status in (({},401),(self.auth('operatorA'),403),(self.auth('shared',2),403)):
            self.assertEqual(self.client.post('/api/invitations',headers=headers,json={'email':'x@example.test','role':'operador'}).status_code,status)
        for extra in ({'role':'superadmin'},{'organization_id':2},{'expiresHours':169},{'email':'bad'}):
            body={'email':'x@example.test','role':'operador',**extra}
            self.assertEqual(self.client.post('/api/invitations',headers=self.auth(),json=body).status_code,422)

    def test_aceptacion_concurrente_crea_una_sola_cuenta_y_membresia(self):
        invitation=self.invitation(role='revisor')
        def register(number):
            return self.client.post('/api/auth/invitations/register',json={'token':invitation['token'],
                'username':f'new-user-{number}','fullName':'New User','password':self.password})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(register,(1,2)))
        self.assertEqual(sorted(r.status_code for r in results),[201,410])
        result=next(r for r in results if r.status_code==201)
        headers={'Authorization':'Bearer '+result.json()['access_token']}
        self.assertEqual(self.client.get('/api/auth/me',headers=headers).json()['roles'],['revisor'])
        self.assertEqual(self.client.get('/api/evaluations/E-000002',headers=headers).status_code,404)
        with self.Session() as db:
            self.assertEqual(db.scalar(select(func.count(User.id))),6)
            self.assertIsNotNone(db.get(OrganizationInvitation,invitation['id']).accepted_at)

    def test_aceptacion_explicita_cuenta_existente_no_sobrescribe_roles_ni_reactiva(self):
        invitation=self.invitation(company='adminB',role='revisor')
        accepted=self.client.post('/api/auth/invitations/accept',headers=self.auth(),
            json={'token':invitation['token'],'password':self.password})
        self.assertEqual(accepted.status_code,200,accepted.text)
        self.assertEqual(accepted.json()['organization_id'],2)
        self.assertEqual(self.client.get('/api/auth/me',headers=self.auth('adminA',1)).json()['roles'],['administrador'])
        self.assertEqual(self.client.get('/api/auth/me',headers=self.auth('adminA',2)).json()['roles'],['revisor'])
        another=self.invitation(company='adminB',role='administrador')
        self.assertEqual(self.client.post('/api/auth/invitations/accept',headers=self.auth(),
            json={'token':another['token'],'password':self.password}).status_code,409)
        with self.Session() as db:
            db.get(OrganizationMembership,(2,self.users['adminA'],3)).is_active=False; db.commit()
        self.assertEqual(self.client.post('/api/auth/invitations/accept',headers=self.auth(),
            json={'token':another['token'],'password':self.password}).status_code,409)

    def test_vencimiento_revocacion_empresa_e_invitador_inactivos_impiden_aceptar(self):
        expired=self.invitation()
        with self.Session() as db:
            row=db.get(OrganizationInvitation,expired['id'])
            row.created_at=datetime.now(timezone.utc)-timedelta(days=3)
            row.expires_at=datetime.now(timezone.utc)-timedelta(days=1)
            db.commit()
        self.assertEqual(self.client.post('/api/auth/invitations/preview',json={'token':expired['token']}).status_code,410)
        revoked=self.invitation()
        self.assertEqual(self.client.delete(f'/api/invitations/{revoked["id"]}',headers=self.auth()).status_code,204)
        self.assertEqual(self.client.post('/api/auth/invitations/preview',json={'token':revoked['token']}).status_code,410)
        active=self.invitation()
        with self.Session() as db:
            db.get(Organization,1).is_active=False; db.commit()
        self.assertEqual(self.client.post('/api/auth/invitations/preview',json={'token':active['token']}).status_code,403)
        with self.Session() as db:
            db.get(Organization,1).is_active=True
            db.get(OrganizationMembership,(1,self.users['adminA'],1)).is_active=False; db.commit()
        self.assertEqual(self.client.post('/api/auth/invitations/preview',json={'token':active['token']}).status_code,403)

    def test_google_invitado_exige_correo_verificado_y_no_fusiona_cuentas(self):
        invitation=self.invitation()
        nonce=self.challenge()
        wrong=self.client.post('/api/auth/google/accept-invitation',json={'token':invitation['token'],
            'credential':self.credential(nonce,email='other@example.test')})
        self.assertEqual(wrong.status_code,403)
        accepted=self.client.post('/api/auth/google/accept-invitation',json={'token':invitation['token'],
            'credential':self.credential(nonce)})
        self.assertEqual(accepted.status_code,200,accepted.text)
        with self.Session() as db:
            identity=db.get(GoogleIdentity,'subject-a')
            self.assertNotIn(identity.user_id,self.users.values())
            self.assertIsNone(db.get(PlatformOwner,1))
        self.assertFalse(accepted.json()['is_superadmin'])

    def test_sin_cliente_oauth_cerrado_y_errores_no_exponen_secretos(self):
        with patch.dict(os.environ,{'AGROSCAN_GOOGLE_CLIENT_ID':''}):
            self.assertEqual(self.client.get('/api/auth/google/config').json(),{'enabled':False,'clientId':None})
            self.assertEqual(self.client.post('/api/auth/google/challenge',headers={'X-AgroScan-Intent':'google'}).status_code,503)
        secret='SENSITIVE-ID-TOKEN-ONLY'
        error=self.client.post('/api/auth/google/link',headers=self.auth(),json={'credential':secret})
        self.assertEqual(error.status_code,422)
        self.assertNotIn(secret,error.text)
        self.assertEqual(self.client.post('/api/auth/google/challenge').status_code,403)

    def test_desafio_vencido_e_invitacion_inexistente_no_procesan_credenciales(self):
        nonce=self.challenge()
        cookie=self.client.cookies.get(COOKIE)
        with self.Session() as db:
            db.get(GoogleChallenge,digest(cookie)).expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
            db.commit()
        with patch.object(google_identity,'google_keys') as keys:
            result=self.client.post('/api/auth/google/login',json={'credential':self.credential(nonce)})
            self.assertEqual(result.status_code,401)
            keys.assert_not_called()
        with patch('app.routers.auth_identity.hash_password') as hashing:
            result=self.client.post('/api/auth/invitations/register',json={'token':'X'*43,
                'username':'new-user','fullName':'New User','password':self.password})
            self.assertEqual(result.status_code,404)
            hashing.assert_not_called()


if __name__=='__main__':
    unittest.main()
