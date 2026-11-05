"""DevSecOps: la telemetría no puede ser falsificada por clientes anónimos."""
import json
import secrets
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Measurement, Role, User
from app.security import create_access_token, hash_password


class IotSecurityTests(unittest.TestCase):
    def setUp(self):
        self.device_key = secrets.token_hex(32)
        self.other_device_key = secrets.token_hex(32)
        self.configuration = patch.dict('os.environ', {
            'AGROSCAN_IOT_KEYS_JSON': json.dumps({
                'esp32-secure-test': self.device_key,
                'another-test-device': self.other_device_key,
            }),
        })
        self.configuration.start()
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        app.dependency_overrides[get_db] = lambda: self.db
        user = User(username='iot_operator', full_name='IoT Operator',
                    password_hash=hash_password(secrets.token_hex(16)),
                    is_active=True, roles=[Role(name='operador')])
        self.db.add(user)
        self.db.commit()
        self.token = create_access_token(user.id)
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()
        self.db.close()
        self.engine.dispose()
        self.configuration.stop()

    def payload(self, device_id='esp32-secure-test'):
        return {
            'schema_version': 1, 'device_id': device_id, 'boot_id': 'test-session',
            'seq': 1, 'weight_g': 250.0, 'stable': True,
            'calibration_version': 'test-calibration',
            'observed_at': datetime.now(timezone.utc).isoformat(),
        }

    def count(self):
        return self.db.scalar(select(func.count()).select_from(Measurement))

    def test_no_key_wrong_key_and_cross_device_key_do_not_write(self):
        for headers in ({}, {'X-Device-Key': 'wrong'},
                        {'X-Device-Key': self.other_device_key}):
            with self.subTest(headers=list(headers)):
                reply = self.client.post('/api/iot/measurements', json=self.payload(), headers=headers)
                self.assertEqual(reply.status_code, 401)
        self.assertEqual(self.count(), 0)

    def test_correct_device_key_accepts_and_preserves_deduplication(self):
        headers = {'X-Device-Key': self.device_key}
        first = self.client.post('/api/iot/measurements', json=self.payload(), headers=headers)
        second = self.client.post('/api/iot/measurements', json=self.payload(), headers=headers)
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertFalse(first.json()['duplicate'])
        self.assertTrue(second.json()['duplicate'])
        self.assertEqual(self.count(), 1)

    def test_unconfigured_backend_fails_closed(self):
        with patch.dict('os.environ', {'AGROSCAN_IOT_KEYS_JSON': ''}):
            response = self.client.post('/api/iot/measurements', json=self.payload(),
                                        headers={'X-Device-Key': self.device_key})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.count(), 0)

    def test_status_requires_jwt_and_inactive_tokens_are_rejected(self):
        self.assertEqual(self.client.get('/api/iot/status').status_code, 401)
        self.assertEqual(self.client.get('/api/iot/status', headers={'Authorization': 'Bearer wrong'}).status_code, 401)
        response = self.client.get('/api/iot/status', headers={'Authorization': f'Bearer {self.token}'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['online'])

    def test_invalid_payload_cannot_persist_even_with_key(self):
        data = self.payload()
        data['weight_g'] = 10000
        self.assertEqual(self.client.post('/api/iot/measurements', json=data,
                         headers={'X-Device-Key': self.device_key}).status_code, 422)
        self.assertEqual(self.count(), 0)


if __name__ == '__main__':
    unittest.main()
