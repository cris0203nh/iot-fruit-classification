"""AG-053: contrato HTTP y transacciones reales con SQLite temporal.

Se sustituye ÚNICAMENTE la salida del detector para probar reglas de negocio.
No representa una medición de exactitud real de YOLOE.
"""
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auto_registration_models import VisionPrecheck
from app.database import Base, get_db
from app.main import app
from app.models import Evaluation, Lot, Piece, Role, User
from app.routers import auto_registration
from app.security import create_access_token, hash_password


class AG053AutoRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ag053-')
        self.addCleanup(self.temp.cleanup)
        dbfile = Path(self.temp.name) / 'isolated.db'
        self.engine = create_engine(
            f'sqlite:///{dbfile.as_posix()}',
            connect_args={'check_same_thread': False, 'timeout': 20},
        )
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.Session() as db:
            self.ids = {}
            for role in ('operador', 'revisor', 'administrador'):
                user = User(
                    username=f'ag053_{role}', full_name=f'AG053 {role}',
                    password_hash=hash_password('PasswordTest123!'),
                    is_active=True, roles=[Role(name=role)],
                )
                db.add(user)
                db.flush()
                self.ids[role] = user.id
            db.add_all([
                Lot(code='MANGO-053', product='mango', status='open'),
                Lot(code='TOMATE-053', product='tomate', status='open'),
            ])
            db.commit()
        def isolated_db():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = isolated_db
        self.addCleanup(lambda: app.dependency_overrides.pop(get_db, None))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        canvas = np.full((180, 180, 3), 90, dtype=np.uint8)
        ok, encoded = cv2.imencode('.jpg', canvas)
        self.assertTrue(ok)
        self.jpeg = encoded.tobytes()

    def auth(self, role='operador'):
        return {'Authorization': 'Bearer ' + create_access_token(self.ids[role])}

    def precheck(self, product='mango', confidence=.92, candidates=1, role='operador'):
        predictions = [
            {'product': product, 'confidence': confidence,
             'box': [12, 12, 150, 150], 'polygon': [[12,12],[150,12],[150,150],[12,150]]}
            for _ in range(candidates)
        ]
        with patch.object(auto_registration, '_infer_products', return_value=predictions):
            return self.client.post('/api/vision/precheck', headers=self.auth(role),
                files={'file': ('foto.jpg', self.jpeg, 'image/jpeg')})

    def register(self, token, lot='MANGO-053', role='operador'):
        return self.client.post('/api/evaluations/auto', headers=self.auth(role),
            json={'lotId': lot, 'detectionToken': token})

    def test_mango_y_tomate_numeracion_por_lote_e_idempotencia(self):
        for lot, product in [('MANGO-053', 'mango'), ('TOMATE-053', 'tomate')]:
            first = self.precheck(product).json()
            self.assertTrue(first['readyToRegister'])
            self.assertEqual(first['product'], product)
            self.assertFalse(first['classificationE0E1E2Produced'])
            saved = self.register(first['detectionToken'], lot)
            self.assertEqual(saved.status_code, 201, saved.text)
            self.assertEqual(saved.json()['pieceId'], 'P-000001')
            self.assertEqual(saved.json()['product'], product)
            replay = self.register(first['detectionToken'], lot)
            self.assertEqual(replay.status_code, 201, replay.text)
            self.assertEqual(replay.json()['id'], saved.json()['id'])
            second = self.precheck(product).json()
            again = self.register(second['detectionToken'], lot)
            self.assertEqual(again.status_code, 201, again.text)
            self.assertEqual(again.json()['pieceId'], 'P-000002')
            with self.Session() as db:
                records = db.scalars(select(Piece).join(Lot).where(Lot.code == lot)).all()
                self.assertEqual(len(records), 2)

    def test_lote_incompatible_y_token_de_otro_usuario(self):
        token = self.precheck('mango').json()['detectionToken']
        self.assertEqual(self.register(token, 'TOMATE-053').status_code, 409)
        self.assertEqual(self.register(token, 'MANGO-053', role='administrador').status_code, 403)
        self.assertEqual(self.register(token, 'MANGO-053').status_code, 201)
        self.assertEqual(self.register(token, 'TOMATE-053').status_code, 409)

    def test_incertidumbre_no_crea_token_y_revisor_no_registra(self):
        ambiguous = self.precheck('mango', candidates=2)
        self.assertEqual(ambiguous.status_code, 200)
        self.assertFalse(ambiguous.json()['readyToRegister'])
        self.assertIsNone(ambiguous.json()['detectionToken'])
        low = self.precheck('mango', confidence=.35).json()
        self.assertFalse(low['readyToRegister'])
        self.assertIsNone(low['product'])
        self.assertEqual(self.precheck(role='revisor').status_code, 403)
        no_token = self.client.post('/api/vision/precheck',
            files={'file': ('foto.jpg', self.jpeg, 'image/jpeg')})
        self.assertEqual(no_token.status_code, 401)

    def test_token_expirado_y_registro_manual_compatibles(self):
        token = self.precheck().json()['detectionToken']
        with self.Session() as db:
            detection = db.get(VisionPrecheck, token)
            detection.created_at = datetime.now(timezone.utc) - timedelta(minutes=20)
            db.commit()
        self.assertEqual(self.register(token).status_code, 409)
        manual = self.client.post('/api/evaluations', headers=self.auth(),
            json={'lotId': 'MANGO-053', 'pieceId': 'MANUAL-001'})
        self.assertEqual(manual.status_code, 201, manual.text)

    def test_sin_modelo_real_falla_explicito(self):
        with patch.object(auto_registration, '_infer_products', side_effect=RuntimeError('modelo no disponible')):
            res = self.client.post('/api/vision/precheck', headers=self.auth(),
                files={'file': ('foto.jpg', self.jpeg, 'image/jpeg')})
        self.assertEqual(res.status_code, 503)

    def test_registros_simultaneos_no_duplican_referencia(self):
        tokens = [self.precheck().json()['detectionToken'] for _ in range(4)]
        # El detector está simulado, la base y las transacciones son reales.
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(self.register, tokens))
        for res in results:
            self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(
            {r.json()['pieceId'] for r in results},
            {'P-000001', 'P-000002', 'P-000003', 'P-000004'},
        )
        with self.Session() as db:
            self.assertEqual(len(db.scalars(select(Evaluation)).all()), 4)


if __name__ == '__main__':
    unittest.main()
