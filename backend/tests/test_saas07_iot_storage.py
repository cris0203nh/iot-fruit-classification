"""A/B, revocación, concurrencia y archivos exclusivamente sintéticos."""
import hashlib
import io
import json
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError

import test_saas03_organizations as fixture
from app.iot_models import IotDevice, IotStation
from app.models import Evaluation, Image, Measurement
from app.organization_models import Organization
from app.services.device_auth import credential_hash
from app.services.evidence_storage import evidence_path


class IotStorageTests(unittest.TestCase):
    setUpClass = classmethod(fixture.OrganizationIsolationTests.setUpClass.__func__)
    auth = fixture.OrganizationIsolationTests.auth
    restore_override = fixture.OrganizationIsolationTests.restore_override

    def setUp(self):
        fixture.OrganizationIsolationTests.setUp(self)
        self.tokens = {1: 'agd_'+'A'*43, 2: 'agd_'+'B'*43}
        with self.Session() as db:
            for org in (1, 2):
                db.get(IotDevice, org).credential_hash = credential_hash(self.tokens[org])
            db.commit()
        for target in ('app.routers.organization_export.DATA_DIR', 'app.routers.evaluations.DATA_DIR'):
            p = patch(target, self.root); p.start(); self.addCleanup(p.stop)

    def device_auth(self, org=1):
        return {'Authorization': 'Bearer '+self.tokens[org]}

    def measurement(self, seq=2, weight=250):
        return {'schema_version': 1, 'device_id': 'shared-device', 'boot_id': 'live-boot',
                'seq': seq, 'weight_g': weight, 'stable': True, 'zero_confirmed': True,
                'calibration_version': 'cal-'+'a'*32+'-1', 'observed_at': datetime.now(timezone.utc).isoformat()}

    def send(self, org=1, **kwargs):
        return self.client.post('/api/iot/measurements', headers=self.device_auth(org), json=self.measurement(**kwargs))

    def test_ingreso_exige_dispositivo_y_no_acepta_empresa_o_identidad_ajena(self):
        for headers in ({}, self.auth(), {'Authorization': 'Bearer agd_'+'X'*43}):
            self.assertEqual(self.client.post('/api/iot/measurements', headers=headers, json=self.measurement()).status_code,401)
        for changes, expected in (({'device_id': 'foreign-device'},403), ({'organization_id':2},422), ({'weight_g': 'NaN'},422)):
            response=self.client.post('/api/iot/measurements',headers=self.device_auth(),json={**self.measurement(),**changes})
            self.assertEqual(response.status_code,expected,response.text)
        self.assertEqual(self.client.post('/api/iot/measurements',headers={**self.device_auth(),'X-Organization-ID':'2'},json=self.measurement()).status_code,400)
        for url in ('/api/lots','/api/iot/status','/api/iot/devices','/api/organization/export'):
            self.assertEqual(self.client.get(url,headers=self.device_auth()).status_code,401)

    def test_mismo_codigo_y_secuencia_aislados_y_estado_autenticado(self):
        for org in (1,2):
            response=self.send(org,weight=org*100)
            self.assertEqual(response.status_code,200,response.text)
            self.assertFalse(response.json()['duplicate'])
        for name,weight in (('adminA',100),('adminB',200)):
            status=self.client.get('/api/iot/status',headers=self.auth(name))
            self.assertEqual(status.status_code,200,status.text)
            self.assertEqual(status.json()['weightG'],weight)
        self.assertEqual(self.client.get('/api/iot/status').status_code,401)
        with self.Session() as db:
            rows=db.scalars(select(Measurement).where(Measurement.boot_id=='live-boot')).all()
            self.assertEqual({(r.organization_id,r.weight_g) for r in rows},{(1,100),(2,200)})

    def test_reenvios_concurrentes_un_solo_registro_y_fecha_original(self):
        body=self.measurement()
        def send(_):
            return self.client.post('/api/iot/measurements',headers=self.device_auth(),json=body)
        with ThreadPoolExecutor(max_workers=6) as pool:
            replies=list(pool.map(send,range(12)))
        self.assertTrue(all(r.status_code==200 for r in replies),[(r.status_code,r.text) for r in replies])
        self.assertEqual(sum(not r.json()['duplicate'] for r in replies),1)
        self.assertEqual(len({r.json()['receivedAt'] for r in replies}),1)
        with ThreadPoolExecutor(max_workers=6) as pool:
            replies=list(pool.map(lambda n:self.send(seq=n),range(3,15)))
        self.assertTrue(all(r.status_code==200 for r in replies))
        with self.Session() as db:
            rows=db.scalars(select(Measurement).where(Measurement.boot_id=='live-boot')).all()
            self.assertEqual(len(rows),13)

    def test_administracion_solo_empresa_sin_filtrar_secretos(self):
        station=self.client.post('/api/iot/stations',headers=self.auth(),json={'code':'new','name':'Nueva'})
        self.assertEqual(station.status_code,201,station.text)
        device=self.client.post('/api/iot/devices',headers=self.auth(),json={'stationId':station.json()['id'],'deviceId':'new-device'})
        self.assertEqual(device.status_code,201,device.text)
        credential=device.json()['credential']
        self.assertEqual(device.headers['cache-control'],'no-store')
        with self.Session() as db:
            self.assertEqual(db.get(IotDevice,device.json()['id']).credential_hash,credential_hash(credential))
        listing=self.client.get('/api/iot/devices',headers=self.auth())
        self.assertNotIn(credential,listing.text)
        self.assertNotIn('credential_hash',listing.text)
        self.assertEqual([r['id'] for r in self.client.get('/api/iot/devices',headers=self.auth('adminB')).json()],[2])
        for method,url,body in (('POST','/api/iot/devices',{'stationId':2,'deviceId':'stolen'}),
             ('POST','/api/iot/devices/2/credentials',{}),('DELETE','/api/iot/devices/2/credentials',{}),
             ('PATCH','/api/iot/stations/2',{'isActive':False})):
            response=self.client.request(method,url,headers=self.auth(),json=body)
            self.assertEqual(response.status_code,404,response.text)
        self.assertEqual(self.client.get('/api/iot/devices',headers=self.auth('operatorA')).status_code,403)
        self.assertEqual(self.client.post('/api/iot/stations',headers=self.auth(),json={'code':'x','name':'X','organization_id':2}).status_code,422)
        with self.Session() as db:
            db.add(IotDevice(organization_id=1,station_id=2,device_id='cross'))
            with self.assertRaises(IntegrityError): db.commit()

    def test_rotacion_revocacion_y_estacion_no_resucitan_credenciales(self):
        self.assertEqual(self.send().status_code,200)
        rotated=self.client.post('/api/iot/devices/1/credentials',headers=self.auth())
        self.assertEqual(rotated.status_code,200,rotated.text)
        self.assertEqual(self.send(seq=3).status_code,401)
        self.tokens[1]=rotated.json()['credential']
        self.assertEqual(self.send(seq=3).status_code,200)
        self.assertEqual(self.client.delete('/api/iot/devices/1/credentials',headers=self.auth()).status_code,204)
        self.assertEqual(self.send(seq=4).status_code,401)
        self.assertFalse(self.client.get('/api/iot/status',headers=self.auth()).json()['online'])
        self.tokens[1]=self.client.post('/api/iot/devices/1/credentials',headers=self.auth()).json()['credential']
        self.assertEqual(self.client.patch('/api/iot/stations/1',headers=self.auth(),json={'isActive':False}).status_code,200)
        self.assertEqual(self.client.post('/api/iot/devices/1/credentials',headers=self.auth()).status_code,409)
        self.assertEqual(self.client.patch('/api/iot/stations/1',headers=self.auth(),json={'isActive':True}).status_code,200)
        self.assertEqual(self.send(seq=4).status_code,401)


    def test_revocacion_concurrente_se_serializa_con_ingreso_y_bloquea_siguientes(self):
        inserted, release, revoking = Event(), Event(), Event()
        def observe(connection, cursor, statement, parameters, context, many):
            if statement.startswith('INSERT INTO measurements'):
                inserted.set()
                if not release.wait(3): raise AssertionError('Ingreso no liberado')
            elif statement == 'BEGIN IMMEDIATE' and inserted.is_set():
                revoking.set()
        event.listen(self.engine,'before_cursor_execute',observe)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                ingest=pool.submit(self.send)
                try:
                    self.assertTrue(inserted.wait(2))
                    revoked=pool.submit(self.client.delete,'/api/iot/devices/1/credentials',headers=self.auth())
                    self.assertTrue(revoking.wait(2))
                    self.assertFalse(revoked.done())
                finally: release.set()
                self.assertEqual(ingest.result().status_code,200)
                self.assertEqual(revoked.result().status_code,204)
        finally:
            event.remove(self.engine,'before_cursor_execute',observe)
            release.set()
        self.assertEqual(self.send(seq=5).status_code,401)

    def test_derivados_de_revision_separados_incluso_con_hash_identico(self):
        from app.services.evidence_storage import review_folder
        from vision.ag055.review import review_history
        review_root=self.root/'derived'
        (review_root/'reviews').mkdir(parents=True)
        legacy={'id':'legacy', 'imageSha256':'a'*64,'annotationPurpose':'human_label_declaration_import'}
        (review_root/'reviews/old.json').write_text(json.dumps(legacy),encoding='utf-8')
        a=review_folder(review_root,1)
        b=review_folder(review_root,2,create=True)
        self.assertNotEqual(a,b)
        self.assertEqual(review_history(a,'any','a'*64),[legacy])
        self.assertEqual(review_history(b,'any','a'*64),[])

    def test_empresa_suspendida_y_pesaje_solo_lectura_propia(self):
        with self.Session() as db:
            ev=db.get(Evaluation,1); ev.status='processing'; ev.created_at=datetime.now(timezone.utc)-timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.send(1,weight=111).status_code,200)
        self.assertEqual(self.send(2,weight=222).status_code,200)
        result=self.client.post('/api/evaluations/E-000001/weight/pre',headers=self.auth('operatorA'))
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['weightG'],111)
        with self.Session() as db:
            db.get(Organization,1).is_active=False; db.commit()
        self.assertEqual(self.send(seq=4).status_code,401)
        self.assertEqual(self.client.get('/api/iot/status',headers=self.auth()).status_code,403)

    def test_fotos_nuevas_segregadas_idempotencia_y_descarga_ab(self):
        with self.Session() as db:
            for org in (1,2): db.get(Evaluation,org).status='processing'
            db.commit()
        for org,name in ((1,'adminA'),(2,'adminB')):
            url=f'/api/evaluations/E-{org:06d}/images'
            headers={**self.auth(name),'Idempotency-Key':'a'*64}
            first=self.client.post(url,headers=headers,files={'file':('x.jpg',self.photo_bytes[org],'image/jpeg')})
            self.assertEqual(first.status_code,201,first.text)
            second=self.client.post(url,headers=headers,files={'file':('x.jpg',self.photo_bytes[org],'image/jpeg')})
            self.assertEqual(first.json(),second.json())
            image=first.json()['id']
            self.assertEqual(self.client.get('/api/images/'+image,headers=self.auth(name)).content,self.photo_bytes[org])
            self.assertEqual(self.client.get('/api/images/'+image,headers=self.auth('adminB' if org==1 else 'adminA')).status_code,404)
            with self.Session() as db:
                row=db.get(Image,int(image[2:]))
                self.assertTrue(row.relative_path.startswith(f'images/organizations/{org}/E-{org:06d}/'))
        self.assertEqual(self.client.post('/api/evaluations/E-000002/images',headers={**self.auth(),'Idempotency-Key':'b'*64},
                          files={'file':('x.jpg',self.photo_bytes[1],'image/jpeg')}).status_code,404)

    def test_referencias_cruzadas_traversal_y_descargas_directas_denegadas(self):
        with self.Session() as db:
            photo=db.get(Image,1)
            for relative in ('../test.db',str(self.root/'test.db'),'images/E-000002/evidence.jpg',
                             'images/organizations/2/E-000001/x.jpg','images\\E-000001\\x.jpg'):
                photo.relative_path=relative; db.commit()
                response=self.client.get('/api/images/I-000001',headers=self.auth())
                self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(self.client.get('/api/images/I-000002',headers=self.auth()).status_code,404)
        self.assertEqual(self.client.get('/api/images/I-000001').status_code,401)
        self.assertEqual(self.client.get('/images/E-000002/evidence.jpg').status_code,404)

    def test_enlaces_de_archivo_no_se_siguen(self):
        source=self.root/'images/E-000001/evidence.jpg'
        target=self.root/'images/E-000001/link.jpg'
        try: target.symlink_to(source)
        except OSError: self.skipTest('Windows no permite symlinks en este contexto')
        with self.Session() as db:
            photo=db.get(Image,1); photo.relative_path='images/E-000001/link.jpg'; db.commit()
            with self.assertRaises(HTTPException): evidence_path(photo,self.root)

    def test_exportacion_logica_solo_empresa_sin_hashes_de_acceso_y_manifest_verificable(self):
        for org,name in ((1,'adminA'),(2,'adminB')):
            response=self.client.get('/api/organization/export',headers=self.auth(name))
            self.assertEqual(response.status_code,200,response.text if response.status_code!=200 else '')
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                names=archive.namelist()
                self.assertNotIn('database/agroscan.db',names)
                self.assertIn(f'images/E-{org:06d}/evidence.jpg',names)
                self.assertNotIn(f'images/E-{3-org:06d}/evidence.jpg',names)
                data=json.loads(archive.read('data.json'))
                self.assertEqual(data['organizationId'],org)
                self.assertEqual({r['organization_id'] for r in data['tables']['measurements']},{org})
                self.assertTrue(all('token' not in r for r in data['tables']['vision_prechecks']))
                raw=archive.read('data.json').decode()
                for secret in ('password_hash','credential_hash','token_hash',self.tokens[1],self.tokens[2],self.hashed):
                    self.assertNotIn(secret,raw)
                for item in json.loads(archive.read('manifest.json'))['files']:
                    self.assertEqual(hashlib.sha256(archive.read(item['path'])).hexdigest(),item['sha256'])
        self.assertEqual(self.client.get('/api/organization/export',headers=self.auth('operatorA')).status_code,403)
        for url in ('/api/admin/backups','/api/admin/backups/restore'):
            self.assertEqual(self.client.post(url,headers=self.auth()).status_code,503)

    def test_exportacion_no_publica_paquete_parcial_si_falta_evidencia(self):
        (self.root/'images/E-000001/evidence.jpg').unlink()
        response=self.client.get('/api/organization/export',headers=self.auth())
        self.assertEqual(response.status_code,409)
        self.assertNotEqual(response.headers['content-type'],'application/zip')

    def test_exportacion_conserva_snapshot_sin_bloquear_mediciones_al_comprimir(self):
        original=zipfile.ZipFile.writestr
        def write(archive,name,data,*args,**kwargs):
            if name=='data.json':
                reply=self.send(seq=99)
                self.assertEqual(reply.status_code,200,reply.text)
            return original(archive,name,data,*args,**kwargs)
        with patch.object(zipfile.ZipFile,'writestr',write):
            response=self.client.get('/api/organization/export',headers=self.auth())
        self.assertEqual(response.status_code,200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            rows=json.loads(archive.read('data.json'))['tables']['measurements']
            self.assertNotIn(99,[r['seq'] for r in rows])
        with self.Session() as db:
            self.assertIsNotNone(db.scalar(select(Measurement).where(Measurement.seq==99)))


if __name__=='__main__': unittest.main()
