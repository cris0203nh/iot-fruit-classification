"""Pruebas HTTP locales: el servidor de prueba no es el backend AgroScan."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import unittest
from firmware.weight_simulator import measurement, send


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.bodies = []
        self.codes = [200]
        self.seen = set()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers['Content-Length']))
                outer.bodies.append(raw)
                payload = json.loads(raw)
                key = (payload['device_id'], payload['boot_id'], payload['seq'])
                duplicate = key in outer.seen
                # Simula persistencia seguida de una respuesta 503.
                outer.seen.add(key)
                code = outer.codes.pop(0) if outer.codes else 200
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(dict(received=True, duplicate=duplicate,
                                                receivedAt='2026-10-22T00:00:00Z')).encode())

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/api/iot/measurements'
        self.payload = measurement(152.8, 1, 'test-boot', True)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_valid_and_duplicate(self):
        self.assertFalse(send(self.url, self.payload)['duplicate'])
        self.assertTrue(send(self.url, self.payload)['duplicate'])
        self.assertEqual(len(self.seen), 1)

    def test_503_retry_preserves_identity_and_body(self):
        self.codes = [503, 200]
        self.assertTrue(send(self.url, self.payload, delay=0)['duplicate'])
        self.assertEqual(self.bodies[0], self.bodies[1])
        self.assertEqual(len(self.seen), 1)

    def test_4xx_is_not_retried(self):
        self.codes = [422]
        with self.assertRaisesRegex(RuntimeError, '422'):
            send(self.url, self.payload, delay=0)
        self.assertEqual(len(self.bodies), 1)

    def test_5xx_stops_after_three_attempts(self):
        self.codes = [503, 503, 503]
        with self.assertRaisesRegex(RuntimeError, '3 intentos'):
            send(self.url, self.payload, delay=0)
        self.assertEqual(len(self.bodies), 3)

    def test_invalid_weights_and_boundaries(self):
        for weight in [-1, 5001, float('nan'), float('inf')]:
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                measurement(weight, 1, 'boot')
        for weight in [0, 5000]:
            self.assertEqual(measurement(weight, 1, 'boot')['weight_g'], weight)


if __name__ == '__main__':
    unittest.main()
