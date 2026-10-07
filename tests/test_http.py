import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from app.engine import Company
from app.server import make_handler


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.company = Company(Path(self.temp.name) / 'test.sqlite3')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.company))
        self.worker = threading.Thread(target=self.server.serve_forever)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.worker.join()
        self.server.server_close()
        self.company.close()
        self.temp.cleanup()

    def request(self, method, path, data=None, origin=None):
        conn = HTTPConnection('127.0.0.1', self.server.server_port)
        headers = {'Content-Type': 'application/json'}
        if origin: headers['Origin'] = origin
        conn.request(method, path, json.dumps(data) if data is not None else None, headers)
        response = conn.getresponse()
        result = response.status, response.read()
        conn.close()
        return result

    def test_http_workflow_and_report(self):
        status, body = self.request('POST', '/api/create', {'objective': 'Test üçün araşdırma hesabatı', 'budget': 20})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['status'], 'running')
        for _ in range(30): self.company.tick()
        status, body = self.request('GET', '/api/report')
        self.assertEqual(status, 200)
        self.assertIn('simulyasiya hesabatı', body.decode())

    def test_foreign_origin_rejected(self):
        status, _ = self.request('POST', '/api/create', {'objective': 'Test məqsədi uzun', 'budget': 20}, 'https://example.com')
        self.assertEqual(status, 403)
        self.assertIsNone(self.company.snapshot()['id'])

    def test_invalid_json_shape_and_missing_report(self):
        self.assertEqual(self.request('POST', '/api/create', [1, 2])[0], 400)
        self.assertEqual(self.request('GET', '/api/report')[0], 404)
        self.assertEqual(self.request('GET', '/../../main.py')[0], 404)

    def test_assets(self):
        for path in ['/', '/style.css', '/app.js']:
            self.assertEqual(self.request('GET', path)[0], 200)

if __name__ == '__main__':
    unittest.main()
