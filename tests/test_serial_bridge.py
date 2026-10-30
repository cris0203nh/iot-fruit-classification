import copy
import importlib.util
import json
from pathlib import Path
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

spec=importlib.util.spec_from_file_location('serial_bridge',Path(__file__).resolve().parents[1]/'firmware/tools/serial_bridge.py')
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)

def envelope(sim=False):
    return {'type':'telemetry','simulated':sim,'uptime_ms':2000,'status':'stable',
            'measurement':{'schema_version':1,'device_id':'simulator-test' if sim else 'esp32-test',
            'boot_id':'boot-test','seq':1,'weight_g':250.0,'stable':True,
            'calibration_version':'simulated-test-1' if sim else 'cal-test-1'}}

class BridgeTests(unittest.TestCase):
    def test_valid_and_events(self):
        self.assertEqual(bridge.extract_measurement(envelope())['weight_g'],250)
        self.assertIsNone(bridge.extract_measurement({'type':'event','status':'sensor_unavailable'}))
        x=envelope();x['measurement']=None;self.assertIsNone(bridge.extract_measurement(x))
    def test_simulation_gate(self):
        with self.assertRaises(ValueError):bridge.extract_measurement(envelope(True))
        self.assertTrue(bridge.extract_measurement(envelope(True),True)['device_id'].startswith('simulator-'))
        x=envelope(True);x['simulated']=False
        with self.assertRaises(ValueError):bridge.extract_measurement(x,True)
    def test_invalid_weights(self):
        for w in [True,-1,5001,float('nan'),float('inf'),'250',None]:
            x=envelope();x['measurement']['weight_g']=w
            with self.subTest(weight=w),self.assertRaises(ValueError):bridge.extract_measurement(x)
    def test_schema_types_and_status(self):
        for key,value in [('schema_version',True),('seq',True),('seq',0),('stable',1),('boot_id',''),('device_id','x'*65)]:
            x=envelope();x['measurement'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):bridge.extract_measurement(x)
        x=envelope();x['measurement']['extra']=1
        with self.assertRaises(ValueError):bridge.extract_measurement(x)
        x=envelope();x['status']='sensor_unavailable'
        with self.assertRaises(ValueError):bridge.extract_measurement(x)
    def test_unstable_forwarded_as_unstable(self):
        x=envelope();x['status']='unstable';x['measurement']['stable']=False
        self.assertFalse(bridge.extract_measurement(x)['stable'])
    def test_url_validation(self):
        for url in ['file:///etc/passwd','http://a:b@localhost/x','http:///x','https://localhost/x#frag']:
            with self.subTest(url=url),self.assertRaises(ValueError):bridge.validate_url(url)
    def request(self, replies):
        bodies=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                bodies.append(self.rfile.read(int(self.headers['Content-Length'])))
                item=replies[min(len(bodies)-1,len(replies)-1)]
                code,ack=item
                if code=='truncated':
                    self.send_response(200);self.send_header('Content-Length','100');self.end_headers()
                    self.wfile.write(b'{');self.wfile.flush();self.close_connection=True;return
                self.send_response(code)
                self.send_header('Content-Type','application/json')
                self.end_headers();self.wfile.write(json.dumps(ack).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(thread.join);self.addCleanup(server.shutdown)
        return f'http://127.0.0.1:{server.server_port}/api/iot/measurements',bodies
    def test_ack(self):
        url,bodies=self.request([(200,{'received':True,'duplicate':False,'receivedAt':'2026-10-30T00:00:00Z'})])
        self.assertTrue(bridge.send(url,envelope()['measurement'],delay=0)['received']);self.assertEqual(len(bodies),1)
    def test_retry_503_identical_payload(self):
        url,bodies=self.request([(503,{}),(200,{'received':True,'duplicate':True,'receivedAt':'test'})])
        self.assertTrue(bridge.send(url,envelope()['measurement'],delay=0)['duplicate'])
        self.assertEqual(len(bodies),2);self.assertEqual(bodies[0],bodies[1])
    def test_truncated_ack_retries_identical_payload(self):
        url,bodies=self.request([('truncated',{}),(200,{'received':True,'duplicate':True,'receivedAt':'test'})])
        self.assertTrue(bridge.send(url,envelope()['measurement'],delay=0)['duplicate'])
        self.assertEqual(len(bodies),2);self.assertEqual(bodies[0],bodies[1])
    def test_4xx_not_retried(self):
        url,bodies=self.request([(422,{})])
        with self.assertRaises(RuntimeError):bridge.send(url,envelope()['measurement'],delay=0)
        self.assertEqual(len(bodies),1)
    def test_retry_limit(self):
        url,bodies=self.request([(503,{})])
        with self.assertRaises(RuntimeError):bridge.send(url,envelope()['measurement'],delay=0)
        self.assertEqual(len(bodies),3)
    def test_invalid_ack_not_retried(self):
        url,bodies=self.request([(200,{'received':True,'duplicate':False})])
        with self.assertRaises(RuntimeError):bridge.send(url,envelope()['measurement'],delay=0)
        self.assertEqual(len(bodies),1)
    def test_bad_options(self):
        for kwargs in [{'attempts':4},{'timeout':0},{'delay':-1}]:
            with self.assertRaises(ValueError):bridge.send('http://127.0.0.1:1',{},**kwargs)

if __name__=='__main__':unittest.main()
