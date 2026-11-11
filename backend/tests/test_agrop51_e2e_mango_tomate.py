"""AG-043/AGROP-51: E2E HTTP controlado; NO prueba de cámara/ESP32 físicos.
No usa backend/data/agroscan.db ni los archivos de imagen de producción.
"""
import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Evaluation, Measurement, Role, User
from app.routers import evaluations, images, uncertainty
from app.security import create_access_token, hash_password
from app.uncertainty import classify_detection


class AG043E2ETests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ag043-e2e-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.storage = self.root / 'evidencia'
        (self.storage / 'images').mkdir(parents=True)
        self.engine = create_engine(
            f"sqlite:///{(self.root / 'aislada.sqlite').as_posix()}",
            connect_args={'check_same_thread': False},
        )
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.sequence = 0
        with self.Session() as db:
            self.users = {}
            for role in ('operador', 'revisor'):
                user = User(username='ag043_'+role, full_name='AG043 '+role,
                            password_hash=hash_password('PasswordTest123!'),
                            is_active=True, roles=[Role(name=role)])
                db.add(user)
                db.flush()
                self.users[role] = user.id
            db.commit()

        def isolated_db():
            with self.Session() as session:
                yield session

        app.dependency_overrides[get_db] = isolated_db
        self.addCleanup(lambda: app.dependency_overrides.pop(get_db, None))
        for module, attribute, value in (
            (images, 'DATA_DIR', self.storage),
            (images, 'IMAGES_DIR', self.storage / 'images'),
            (evaluations, 'DATA_DIR', self.storage),
            (uncertainty, 'DATA_DIR', self.storage),
        ):
            mocked = patch.object(module, attribute, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def auth(self, role='operador'):
        return {'Authorization': 'Bearer '+create_access_token(self.users[role])}

    def post_ok(self, url, data, expected=201):
        res = self.client.post(url, json=data, headers=self.auth())
        self.assertEqual(res.status_code, expected, res.text)
        return res.json()

    def create(self, product, lot, piece):
        self.post_ok('/api/lots', {'code': lot, 'product': product, 'responsible': 'E2E'})
        return self.attempt(lot, piece)

    def attempt(self, lot, piece):
        return self.post_ok('/api/evaluations', {'lotId': lot, 'pieceId': piece})['id']

    def weight(self, eid, stage, grams):
        self.sequence += 1
        now = datetime.now(timezone.utc)
        with self.Session() as db:
            db.add(Measurement(device_id='sensor-SIMULADO', boot_id='boot-SIMULADO',
                seq=self.sequence, weight_g=grams, stable=True, zero_confirmed=True,
                calibration_version='cal-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-1',
                received_at=now, observed_at=now))
            db.commit()
        res = self.client.post(f'/api/evaluations/{eid}/weight/{stage}',
                               headers=self.auth())
        self.assertEqual(res.status_code, 200, res.text)

    def upload(self, eid, product, number):
        canvas = np.full((96,96,3), (20+number*8, 125, 210)
                         if product=='mango' else (22+number*8, 55, 185),
                         dtype=np.uint8)
        ok, encoded = cv2.imencode('.jpg', canvas)
        self.assertTrue(ok)
        raw = encoded.tobytes()
        key = hashlib.sha256(f'{eid}-{number}'.encode()).hexdigest()
        res = self.client.post(f'/api/evaluations/{eid}/images',
            headers={**self.auth(), 'Idempotency-Key': key},
            data={'view': f'vista-{number}'},
            files={'file': ('captura_controlada.jpg', raw, 'image/jpeg')})
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()['id'], raw, key

    def confirm(self, eid):
        return self.client.post(f'/api/evaluations/{eid}/acquisition/confirm',
                                headers=self.auth())

    def test_mango_y_tomate_cadena_completa_y_reporte(self):
        for product, mass in (('mango', 250.0), ('tomate', 120.0)):
            with self.subTest(product=product):
                lot = 'AG043-'+product.upper()
                piece = 'PIEZA-01'
                eid = self.create(product, lot, piece)
                self.weight(eid, 'pre', mass)
                first, raw, idem = self.upload(eid, product, 1)
                self.weight(eid, 'post', mass+1)
                self.assertEqual(self.confirm(eid).status_code, 409)
                repeat = self.client.post(f'/api/evaluations/{eid}/images',
                    headers={**self.auth(), 'Idempotency-Key': idem},
                    data={'view':'vista-1'},
                    files={'file':('repeat.jpg',raw,'image/jpeg')})
                self.assertEqual(repeat.status_code, 201, repeat.text)
                self.assertEqual(repeat.json()['id'], first)
                self.assertEqual(self.confirm(eid).status_code, 409)
                second, raw2, _ = self.upload(eid, product, 2)
                self.assertNotEqual(first, second)
                confirmed = self.confirm(eid)
                self.assertEqual(confirmed.status_code, 200, confirmed.text)
                self.assertEqual(confirmed.json()['imageCount'], 2)
                self.assertEqual(confirmed.json()['evaluationId'], eid)
                self.assertEqual(confirmed.json()['product'], product)
                self.assertEqual(confirmed.json()['pieceId'], piece)
                self.assertEqual(confirmed.json()['status'], 'pending_review')
                self.assertEqual(self.confirm(eid).status_code, 409)
                detail = self.client.get('/api/evaluations/'+eid,
                    headers=self.auth('revisor'))
                self.assertEqual(detail.status_code, 200, detail.text)
                data = detail.json()
                self.assertEqual((data['lotId'], data['pieceId'], data['product']),
                                 (lot, piece, product))
                self.assertEqual({i['id'] for i in data['evidence']},{first,second})
                self.assertIsNone(data['visualCategory'])
                for iid, content in ((first,raw),(second,raw2)):
                    downloaded = self.client.get('/api/images/'+iid,
                        headers=self.auth('revisor'))
                    self.assertEqual(downloaded.status_code, 200, downloaded.text)
                    self.assertEqual(downloaded.content, content)
                summary = self.client.get('/api/piece-history',
                    params={'lot':lot}, headers=self.auth('revisor'))
                self.assertEqual(summary.status_code, 200, summary.text)
                self.assertEqual((summary.json()['pieceCount'],
                                  summary.json()['attemptCount'],
                                  summary.json()['captureCount']), (1,1,2))
                report = self.client.get('/api/piece-history/report',
                    params={'lot':lot}, headers=self.auth('revisor'))
                self.assertEqual(report.status_code, 200, report.text)
                report = report.json()
                self.assertEqual(report['counts']['pieceCount'], 1)
                self.assertEqual(report['counts']['captureCount'], 2)
                self.assertNotEqual(report['integrity']['status'], 'inconsistent')
                self.assertEqual(report['rows'][0]['captureIds'], [first,second])
                with self.Session() as db:
                    record=db.get(Evaluation,int(eid[2:]))
                    self.assertIsNotNone(record.piece_ref_id)
                    self.assertIsNotNone(record.weight_pre_measurement_id)
                    self.assertIsNotNone(record.weight_post_measurement_id)

    def test_misma_pieza_dos_intentos_se_cuenta_una_vez(self):
        eid1 = self.create('tomate','AG043-REINTENTOS','P-01')
        eid2 = self.attempt('AG043-REINTENTOS','P-01')
        report = self.client.get('/api/piece-history/report',
            params={'lot':'AG043-REINTENTOS'},headers=self.auth('revisor'))
        self.assertEqual(report.status_code,200,report.text)
        self.assertEqual(report.json()['counts']['pieceCount'],1)
        self.assertEqual(report.json()['counts']['attemptCount'],2)
        self.assertEqual(report.json()['rows'][0]['attemptIds'],[eid1,eid2])

    def test_fuera_de_alcance_producto_y_fotografia_ajena(self):
        unsupported = self.client.post('/api/lots',
            json={'code':'AG043-BANANA','product':'platano','responsible':'E2E'},
            headers=self.auth())
        self.assertEqual(unsupported.status_code,422)
        mango=self.create('mango','AG043-M-AJENA','PM')
        tomato=self.create('tomate','AG043-T-AJENA','PT')
        iid,_,_=self.upload(mango,'mango',1)
        wrong=self.client.post(f'/api/evaluations/{tomato}/vision/review-gate',
            json={'imageId':iid},headers=self.auth())
        self.assertEqual(wrong.status_code,404,wrong.text)
        self.weight(mango,'pre',250.0)
        self.upload(mango,'mango',2)
        self.weight(mango,'post',251.0)
        self.assertEqual(self.confirm(mango).status_code,200)
        detection=[{'label':'tomato fruit','confidence':0.98,'mask':True,
                    'box':[1,1,90,90]}]
        with patch.object(uncertainty,'_infer',return_value=(
            classify_detection('mango',detection),detection)):
            result=self.client.post(f'/api/evaluations/{mango}/vision/review-gate',
                json={'imageId':iid},headers=self.auth())
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['reason'],'clase_no_esperada')
        self.assertFalse(result.json()['classificationE0E1E2Produced'])
        self.assertTrue(result.json()['originalPreserved'])


if __name__=='__main__':
    unittest.main()
