import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from app.market import plan
from app.studio import Studio
from app.studio_server import make_handler


FACTS = dict(market_size=500_000, arpu=19, cac=40, churn_monthly=0.04, cpm=12.5, sales_cycle_days=90)
TEAMS = [dict(id='a', name='Ucuz', strategy='cheap', cash=600_000),
         dict(id='b', name='Premium', strategy='premium', cash=600_000)]


def request(**overrides):
    base = dict(parameters=dict(FACTS), firms=[dict(f) for f in TEAMS], horizon=24, replications=20,
                sensitivity=['arpu'])
    base.update(overrides)
    return base


class PlanTest(unittest.TestCase):
    def test_returns_race_sensitivity_and_what_was_simulated(self):
        result = plan(request())
        self.assertEqual(result['race']['runs'], 20)
        self.assertEqual(result['seed_range'], [0, 19])
        self.assertEqual(result['parameters'], FACTS)
        self.assertEqual([s['key'] for s in result['sensitivity']], ['arpu'])
        self.assertIn('price_sensitivity', result['assumptions'])

    def test_same_request_gives_the_same_verdict(self):
        self.assertEqual(json.dumps(plan(request())), json.dumps(plan(request())))

    def test_sensitivity_defaults_to_the_documented_sweep(self):
        keys = {s['key'] for s in plan(request(sensitivity=None, replications=20))['sensitivity']}
        self.assertIn('price_sensitivity', keys)
        self.assertIn('cac', keys)

    def test_hostile_input_is_refused(self):
        cases = [
            request(parameters={}),
            request(parameters=dict(FACTS, churn_monthly=5)),
            request(parameters=dict(FACTS, arpu='çox')),
            request(firms=[]),
            request(firms=[dict(id='a', name='A', strategy='uydurma', cash=1000)]),
            request(firms=[dict(id='a', name='A', strategy='cheap', cash=-5)]),
            request(firms=[dict(TEAMS[0]), dict(TEAMS[0])]),
            request(horizon=2),
            request(replications=5000),
            request(crises=[dict(kind='meteor', step=1)]),
            request(crises=[dict(kind='cpm_shock', step=99)]),
            request(sensitivity=['uydurma_acar']),
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    plan(payload)

    def test_crisis_is_echoed_back_with_the_verdict(self):
        result = plan(request(crises=[dict(kind='cpm_shock', step=4, factor=2.0)]))
        self.assertEqual(result['crises'][0]['kind'], 'cpm_shock')
        self.assertEqual(result['crises'][0]['step'], 4)


class ArenaEndpointTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.studio = Studio(Path(self.folder.name) / 'studio.sqlite3')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.studio))
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.token = self.get('/api/studio')['csrf']

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.studio.close()
        self.folder.cleanup()

    def url(self, path):
        return f'http://127.0.0.1:{self.port}{path}'

    def get(self, path):
        with urllib.request.urlopen(self.url(path), timeout=10) as response:
            return json.loads(response.read())

    def post(self, path, payload, token=None):
        headers = {'Content-Type': 'application/json', 'Host': f'127.0.0.1:{self.port}'}
        if token is not False:
            headers['X-CSRF-Token'] = token or self.token
        raw = urllib.request.Request(self.url(path), data=json.dumps(payload).encode(),
                                     headers=headers, method='POST')
        with urllib.request.urlopen(raw, timeout=30) as response:
            return response.status, json.loads(response.read())

    def test_arena_runs_over_http(self):
        status, body = self.post('/api/arena', request())
        self.assertEqual(status, 200)
        self.assertEqual(body['race']['runs'], 20)
        self.assertEqual(set(body['race']['firms']), {'a', 'b'})

    def test_strategies_are_listed_for_the_form(self):
        strategies = self.get('/api/arena/strategies')
        self.assertEqual(set(strategies), {'cheap', 'premium', 'b2b'})
        self.assertEqual(strategies['b2b']['segment'], 'institution')

    def test_bad_request_answers_400_not_500(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post('/api/arena', request(horizon=1))
        self.assertEqual(caught.exception.code, 400)
        with caught.exception as failure:
            self.assertIn('Üfüq', json.loads(failure.read())['error'])

    def test_arena_still_requires_the_csrf_token(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post('/api/arena', request(), token=False)
        with caught.exception as failure:
            self.assertEqual(failure.code, 403)

    def test_arena_does_not_touch_stored_projects(self):
        before = self.get('/api/studio')['projects']
        self.post('/api/arena', request())
        self.assertEqual(self.get('/api/studio')['projects'], before)


if __name__ == '__main__':
    unittest.main()
