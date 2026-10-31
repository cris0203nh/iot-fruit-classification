"""Real team IoT routes, isolated SQLite; no physical hardware or production data."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.models import Measurement
from app.routers import iot
from firmware.tools.serial_bridge import extract_measurement
from firmware.weight_simulator import measurement

class BackendIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions=sessionmaker(bind=self.engine)
        def isolated_db():
            with self.sessions() as db:
                yield db
        app=FastAPI();app.include_router(iot.router);app.dependency_overrides[get_db]=isolated_db
        self.client=TestClient(app)
        self.addCleanup(self.engine.dispose);self.addCleanup(self.client.close)
    def payload(self):
        env={'type':'telemetry','simulated':False,'status':'stable','measurement':{
            'schema_version':1,
            'device_id':'esp32-test',
            'boot_id':'test-boot',
            'seq':1,
            'weight_g':250.0,
            'stable':True,
            'zero_confirmed':True,
            'calibration_version':'cal-test-1'}}
        return extract_measurement(env)
    def test_firmware_payload_received_and_duplicate_not_refreshed(self):
        first=self.client.post('/api/iot/measurements',json=self.payload())
        self.assertEqual(first.status_code,200);self.assertFalse(first.json()['duplicate'])
        again=self.client.post('/api/iot/measurements',json=self.payload())
        self.assertTrue(again.json()['duplicate']);self.assertEqual(first.json()['receivedAt'],again.json()['receivedAt'])
        with self.sessions() as db:self.assertEqual(db.scalar(select(func.count()).select_from(Measurement)),1)
        status=self.client.get('/api/iot/status').json()
        self.assertTrue(status['online']);self.assertEqual(status['weightG'],250.0)
    def test_simulator_payload_accepted_in_isolated_test(self):
        response=self.client.post('/api/iot/measurements',json=measurement(152.8,1,'sim-test',True))
        self.assertEqual(response.status_code,200);self.assertTrue(response.json()['received'])
    def test_422_for_invalid_weight_schema_and_identifier(self):
        for update in [{'weight_g':-1},{'weight_g':5001},{'schema_version':2},{'device_id':'x'*65}]:
            with self.subTest(update=update):
                p=self.payload();p.update(update)
                self.assertEqual(self.client.post('/api/iot/measurements',json=p).status_code,422)
    def test_expired_weight_is_not_current(self):
        self.client.post('/api/iot/measurements',json=self.payload())
        with self.sessions() as db:
            m=db.scalar(select(Measurement));m.received_at=datetime.now(timezone.utc)-timedelta(seconds=11);db.commit()
        status=self.client.get('/api/iot/status').json()
        self.assertFalse(status['online']);self.assertIsNone(status['weightG']);self.assertIsNone(status['stable'])
    def test_unstable_and_absent_sensor_states(self):
        status=self.client.get('/api/iot/status').json();self.assertFalse(status['online']);self.assertIsNone(status['weightG'])
        p=self.payload();p['stable']=False
        self.assertEqual(self.client.post('/api/iot/measurements',json=p).status_code,200)
        self.assertFalse(self.client.get('/api/iot/status').json()['stable'])

if __name__=='__main__':unittest.main()
