"""Regresión HTTP IoT SaaS-07 usando SQLite y credenciales exclusivamente sintéticas.

Comprueba la integración entre telemetría ESP32/puente y la API real de IoT,
no la exactitud de la báscula ni la conectividad del dispositivo físico.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from app.database import Base, enable_sqlite_foreign_keys, get_db
from app.iot_models import IotDevice, IotStation
from app.models import Measurement, Role, User
from app.organization_models import Organization, OrganizationMembership
from app.routers import iot
from app.security import create_access_token
from app.services.device_auth import credential_hash
from firmware.tools.serial_bridge import extract_measurement
from firmware.weight_simulator import measurement


class BackendIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='agroscan-iot-ci-')
        self.addCleanup(temporary.cleanup)
        database = Path(temporary.name) / 'integration.sqlite'
        self.engine = create_engine(
            f'sqlite:///{database.as_posix()}',
            connect_args={'check_same_thread': False},
        )
        self.addCleanup(self.engine.dispose)
        event.listen(self.engine, 'connect', enable_sqlite_foreign_keys)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

        # La empresa, el usuario y los dispositivos solo existen en esta copia.
        self.tokens = {
            'esp32-test': 'agd_' + 'A' * 43,
            'simulator-fernando-001': 'agd_' + 'B' * 43,
        }
        with self.sessions() as db:
            db.add(Organization(id=1, name='Empresa CI'))
            db.add(Role(id=1, name='administrador'))
            db.add(User(id=1, username='iot-ci', full_name='Operador CI',
                        password_hash='solo-fixture-sintetica', is_active=True))
            db.flush()
            db.add(OrganizationMembership(organization_id=1, user_id=1, role_id=1))
            db.add(IotStation(id=1, organization_id=1, code='test', name='Pruebas'))
            db.flush()
            for index, (device_id, token) in enumerate(self.tokens.items(), start=1):
                db.add(IotDevice(id=index, organization_id=1, station_id=1,
                                 device_id=device_id, credential_hash=credential_hash(token)))
            db.commit()

        def isolated_db():
            with self.sessions(info={'organization_required': True}) as db:
                yield db

        app = FastAPI()
        app.include_router(iot.router)
        app.dependency_overrides[get_db] = isolated_db
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def device_auth(self, name='esp32-test'):
        return {'Authorization': 'Bearer ' + self.tokens[name]}

    def user_auth(self):
        return {'Authorization': 'Bearer ' + create_access_token(1)}

    def payload(self):
        envelope = {'type': 'telemetry', 'simulated': False, 'status': 'stable',
                    'measurement': {
                        'schema_version': 1,
                        'device_id': 'esp32-test',
                        'boot_id': 'test-boot',
                        'seq': 1,
                        'weight_g': 250.0,
                        'stable': True,
                        'zero_confirmed': True,
                        'calibration_version': 'cal-test-1',
                    }}
        return extract_measurement(
            envelope, observed_at=datetime.now(timezone.utc).isoformat())

    def send(self, payload, name='esp32-test', headers=None):
        return self.client.post('/api/iot/measurements', json=payload,
                                headers=headers if headers is not None else self.device_auth(name))

    def status(self):
        return self.client.get('/api/iot/status', headers=self.user_auth())

    def test_firmware_payload_received_and_duplicate_not_refreshed(self):
        first = self.send(self.payload())
        self.assertEqual(first.status_code, 200, first.text)
        self.assertFalse(first.json()['duplicate'])
        again = self.send(self.payload())
        self.assertEqual(again.status_code, 200, again.text)
        self.assertTrue(again.json()['duplicate'])
        self.assertEqual(first.json()['receivedAt'], again.json()['receivedAt'])
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Measurement)), 1)
        status = self.status()
        self.assertEqual(status.status_code, 200, status.text)
        self.assertTrue(status.json()['online'])
        self.assertEqual(status.json()['weightG'], 250.0)

    def test_simulator_payload_accepted_only_with_own_device_credential(self):
        sim_payload = measurement(152.8, 1, 'sim-test', True)
        sim_payload['observed_at'] = datetime.now(timezone.utc).isoformat()
        self.assertEqual(self.send(sim_payload).status_code, 403)
        response = self.send(sim_payload, name='simulator-fernando-001')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['received'])

    def test_rejects_missing_or_wrong_device_credential(self):
        self.assertEqual(self.send(self.payload(), headers={}).status_code, 401)
        self.assertEqual(self.send(self.payload(), headers=self.user_auth()).status_code, 401)
        self.assertEqual(self.send(self.payload(), headers={'Authorization': 'Bearer agd_' + 'X' * 43}).status_code, 401)
        self.assertEqual(self.send(self.payload(), name='simulator-fernando-001').status_code, 403)
        self.assertEqual(self.send(self.payload(), headers={**self.device_auth(), 'X-Organization-ID': '1'}).status_code, 400)
        self.assertEqual(self.client.get('/api/iot/status').status_code, 401)
        self.assertEqual(self.client.get('/api/iot/status', headers=self.device_auth()).status_code, 401)

    def test_422_for_invalid_weight_schema_and_identifier(self):
        for update in ({'weight_g': -1}, {'weight_g': 5001},
                       {'schema_version': 2}, {'device_id': 'x' * 65}):
            with self.subTest(update=update):
                payload = self.payload()
                payload.update(update)
                response = self.send(payload)
                self.assertEqual(response.status_code, 422, response.text)

    def test_expired_weight_is_not_current(self):
        first = self.send(self.payload())
        self.assertEqual(first.status_code, 200, first.text)
        with self.sessions() as db:
            current = db.scalar(select(Measurement))
            current.received_at = datetime.now(timezone.utc) - timedelta(seconds=11)
            db.commit()
        status = self.status()
        self.assertEqual(status.status_code, 200, status.text)
        self.assertFalse(status.json()['online'])
        self.assertIsNone(status.json()['weightG'])
        self.assertIsNone(status.json()['stable'])

    def test_unstable_and_absent_sensor_states(self):
        empty = self.status()
        self.assertEqual(empty.status_code, 200, empty.text)
        self.assertFalse(empty.json()['online'])
        self.assertIsNone(empty.json()['weightG'])
        payload = self.payload()
        payload['stable'] = False
        response = self.send(payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(self.status().json()['stable'])


if __name__ == '__main__':
    unittest.main()
