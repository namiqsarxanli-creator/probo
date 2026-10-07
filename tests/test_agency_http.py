import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from agency.engine import Agency
from agency.server import make_handler
from tests.test_agency_engine import FakeModels


class AgencyHttpTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.agency = Agency(Path(self.folder.name) / 'agency.sqlite3', FakeModels())
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.agency))
        self.port = self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.token = self.get('/api/state')['csrf']

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.agency.close()
        self.folder.cleanup()

    def get(self, path):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}{path}', timeout=10) as response:
            return json.loads(response.read())

    def post(self, path, body, token=None, host=None):
        headers = {'Content-Type': 'application/json'}
        if token is not False:
            headers['X-CSRF-Token'] = token or self.token
        if host:
            headers['Host'] = host
        request = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', data=json.dumps(body).encode(),
                                         headers=headers, method='POST')
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())

    def status_of(self, call):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            call()
        with caught.exception as failure:
            return failure.code, json.loads(failure.read())

    def test_state_carries_both_services_and_the_policy(self):
        state = self.get('/api/state')
        self.assertEqual(set(state['services']), {'soz', 'tender'})
        self.assertIn('14 gün', state['policy_document']['body'])
        self.assertEqual(len(state['tenders']), 2)

    def test_ticket_is_queued_and_human_reply_is_checked(self):
        queued = self.post('/api/ticket', {'message': 'Bakı daxilində çatdırılma neçəyədir?'})
        self.assertTrue(queued['job_id'])
        verdict = self.post('/api/human', {'text': 'Məhsulu 30 gün ərzində qaytara bilərsiniz.'})
        self.assertFalse(verdict['ok'])

    def test_writes_need_the_token_and_a_local_host(self):
        code, _ = self.status_of(lambda: self.post('/api/ticket', {'message': 'salam'}, token=False))
        self.assertEqual(code, 403)
        code, _ = self.status_of(lambda: self.post('/api/ticket', {'message': 'salam'}, host='evil.example'))
        self.assertEqual(code, 403)

    def test_bad_input_answers_400(self):
        code, body = self.status_of(lambda: self.post('/api/stress', {'count': 5000}))
        self.assertEqual(code, 400)
        self.assertIn('1–200', body['error'])
        code, _ = self.status_of(lambda: self.post('/api/mode', {'mode': 'chaos'}))
        self.assertEqual(code, 400)

    def test_panel_is_served_with_a_strict_policy(self):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/', timeout=10) as response:
            self.assertIn("style-src 'self'", response.headers['Content-Security-Policy'])
            self.assertIn('Sübut Agentliyi', response.read().decode())


if __name__ == '__main__':
    unittest.main()
