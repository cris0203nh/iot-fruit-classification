"""Cierre integral A/B y bridge HTTP real; imágenes/inferencia de ensayo, sin hardware."""
import hashlib
import socket
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

import cv2
import numpy as np
import uvicorn

import test_saas07_iot_storage as previous
from app.main import app
from app.models import Role, User
from app.organization_models import OrganizationMembership
from firmware.tools.serial_bridge import send


class PilotValidationTests(unittest.TestCase):
    setUpClass = previous.IotStorageTests.__dict__['setUpClass']
    auth = previous.IotStorageTests.auth
    restore_override = previous.IotStorageTests.restore_override
    device_auth = previous.IotStorageTests.device_auth
    measurement = previous.IotStorageTests.measurement
    send = previous.IotStorageTests.send

    def setUp(self):
        previous.IotStorageTests.setUp(self)
        with self.Session() as db:
            for name, org, role in (('reviewerA', 1, 3), ('operatorB', 2, 2), ('reviewerB', 2, 3)):
                user = User(username=name, full_name=name, password_hash=self.hashed,
                            is_active=True, roles=[db.get(Role, role)])
                db.add(user); db.flush()
                db.add(OrganizationMembership(organization_id=org, user_id=user.id, role_id=role))
                self.users[name] = user.id
            db.commit()

    def test_dos_empresas_tres_roles_cadena_captura_revision_reporte_y_revocacion(self):
        headers = {}
        for name, org, role in (('adminA',1,'administrador'),('operatorA',1,'operador'),('reviewerA',1,'revisor'),
                                ('adminB',2,'administrador'),('operatorB',2,'operador'),('reviewerB',2,'revisor')):
            login = self.client.post('/api/auth/login', data={'username':name,'password':self.password})
            self.assertEqual(login.status_code,200,login.text)
            headers[name] = {'Authorization':'Bearer '+login.json()['access_token']}
            profile = self.client.get('/api/auth/me',headers=headers[name])
            self.assertEqual(profile.json()['organizationId'],org)
            self.assertEqual(profile.json()['roles'],[role])
        valid, encoded = cv2.imencode('.jpg',np.full((160,160,3),(30,100,180),dtype=np.uint8))
        self.assertTrue(valid); photo = encoded.tobytes(); digest = hashlib.sha256(photo).hexdigest()
        resources = {}
        for org, operator, reviewer, foreign in ((1,'operatorA','reviewerA','reviewerB'),(2,'operatorB','reviewerB','reviewerA')):
            with self.subTest(organization=org):
                # Sustitución explícita de detección, sin simular métricas de exactitud.
                detection = [{'product':'mango','confidence':.95,'box':[20,20,140,140],
                              'polygon':[[20,20],[140,20],[140,140],[20,140]]}]
                with patch('app.routers.auto_registration._infer_products',return_value=detection):
                    proof = self.client.post('/api/vision/precheck',headers=headers[operator],
                                             files={'file':('fixture.jpg',photo,'image/jpeg')})
                self.assertEqual(proof.status_code,200,proof.text)
                body = {'lotId':'SHARED','detectionToken':proof.json()['detectionToken']}
                created = self.client.post('/api/evaluations/auto',headers=headers[operator],json=body)
                self.assertEqual(created.status_code,201,created.text)
                eid = created.json()['id']
                self.assertEqual(self.client.post('/api/evaluations/auto',headers=headers[operator],json=body).json()['id'],eid)
                self.assertEqual(self.send(org,seq=100,weight=100*org).status_code,200)
                pre = self.client.post(f'/api/evaluations/{eid}/weight/pre',headers=headers[operator])
                self.assertEqual(pre.status_code,200,pre.text)
                photos = []
                for view in (1,2):
                    upload = self.client.post(f'/api/evaluations/{eid}/images',
                        headers={**headers[operator],'Idempotency-Key':hashlib.sha256(f'{org}-{view}'.encode()).hexdigest()},
                        data={'view':f'vista-{view}'},files={'file':('fixture.jpg',photo,'image/jpeg')})
                    self.assertEqual(upload.status_code,201,upload.text)
                    photos.append(upload.json()['id'])
                self.assertEqual(self.send(org,seq=101,weight=100*org+1).status_code,200)
                post = self.client.post(f'/api/evaluations/{eid}/weight/post',headers=headers[operator])
                self.assertEqual(post.status_code,200,post.text)
                confirm = self.client.post(f'/api/evaluations/{eid}/acquisition/confirm',headers=headers[operator])
                self.assertEqual(confirm.status_code,200,confirm.text)
                revision = None
                for index, iid in enumerate(photos):
                    decision = {'action':'initial_label' if index==0 else 'confirm','imageId':iid,'newValue':'E1',
                        'expectedReviewId':revision,'requestId':str(uuid4()),
                        'reason':'Etiqueta sintética de prueba de software, sin diagnóstico agronómico.'}
                    url = f'/api/evaluations/{eid}/review-decisions'
                    self.assertEqual(self.client.post(url,headers=headers[operator],json=decision).status_code,403)
                    self.assertEqual(self.client.post(url,headers=headers[foreign],json=decision).status_code,404)
                    accepted = self.client.post(url,headers=headers[reviewer],json=decision)
                    self.assertEqual(accepted.status_code,201,accepted.text)
                    self.assertEqual(accepted.json()['imageSha256'],digest)
                    revision = accepted.json()['id']
                    self.assertEqual(self.client.get('/api/images/'+iid,headers=headers[reviewer]).content,photo)
                    self.assertEqual(self.client.get('/api/images/'+iid,headers=headers[foreign]).status_code,404)
                detail = self.client.get('/api/evaluations/'+eid,headers=headers[reviewer])
                self.assertEqual(detail.json()['status'],'completed',detail.text)
                log = self.client.get(f'/api/evaluations/{eid}/review-decisions',headers=headers[reviewer]).json()
                self.assertEqual(len(log['decisions']),2)
                self.assertEqual(log['currentValue'],'E1')
                self.assertEqual(self.client.get('/api/evaluations/'+eid,headers=headers[foreign]).status_code,404)
                resources[org] = (eid,photos)
        for org, reviewer in ((1,'reviewerA'),(2,'reviewerB')):
            report = self.client.get('/api/piece-history/report?lot=SHARED',headers=headers[reviewer])
            self.assertEqual(report.status_code,200,report.text)
            self.assertIn(resources[org][0],report.text)
            self.assertNotIn(resources[3-org][0],report.text)
            self.assertEqual(hashlib.sha256(report.json()['csv'].encode()).hexdigest(),report.json()['csvSha256'])
        changed = self.client.patch(f'/api/users/{self.users["operatorB"]}/role',headers=headers['adminB'],json={'role':'revisor'})
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertEqual(self.client.post('/api/vision/precheck',headers=headers['operatorB'],
                         files={'file':('fixture.jpg',photo,'image/jpeg')}).status_code,403)
        self.assertEqual(self.client.delete(f'/api/users/{self.users["operatorB"]}/membership',headers=headers['adminB']).status_code,204)
        self.assertEqual(self.client.get('/api/lots',headers=headers['operatorB']).status_code,403)
        self.assertEqual(self.client.get('/api/lots',headers=headers['operatorA']).status_code,200)

    def test_bridge_http_real_identidad_empresa_reenvio_rotacion_y_revocacion(self):
        sock = socket.socket()
        sock.bind(('127.0.0.1',0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False,lifespan='off',ws='none'))
        thread = threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True)
        def stop():
            server.should_exit = True
            thread.join(5)
            sock.close()
            self.assertFalse(thread.is_alive(),'El servidor aislado no se detuvo')
        self.addCleanup(stop)
        thread.start()
        deadline = time.monotonic()+5
        while not server.started and thread.is_alive() and time.monotonic()<deadline:
            threading.Event().wait(.01)
        self.assertTrue(server.started,'Servidor aislado no disponible')
        url = f'http://127.0.0.1:{port}/api/iot/measurements'
        payload = self.measurement()
        with patch.dict('os.environ',{'AGROSCAN_DEVICE_TOKEN':self.tokens[1]}):
            self.assertFalse(send(url,payload,delay=0)['duplicate'])
            self.assertTrue(send(url,payload,delay=0)['duplicate'])
        with patch.dict('os.environ',{'AGROSCAN_DEVICE_TOKEN':self.tokens[2]}):
            self.assertFalse(send(url,payload,delay=0)['duplicate'])
        rotated = self.client.post('/api/iot/devices/1/credentials',headers=self.auth())
        self.assertEqual(rotated.status_code,200,rotated.text)
        with patch.dict('os.environ',{'AGROSCAN_DEVICE_TOKEN':self.tokens[1]}):
            with self.assertRaisesRegex(RuntimeError,'HTTP 401'): send(url,payload,delay=0)
        with patch.dict('os.environ',{'AGROSCAN_DEVICE_TOKEN':rotated.json()['credential']}):
            self.assertTrue(send(url,payload,delay=0)['duplicate'])
            self.assertEqual(self.client.delete('/api/iot/devices/1/credentials',headers=self.auth()).status_code,204)
            with self.assertRaisesRegex(RuntimeError,'HTTP 401'): send(url,payload,delay=0)


if __name__=='__main__': unittest.main()
