import json
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from app.studio import Studio
from app.studio_server import make_handler


class StudioHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.studio = Studio(Path(self.temp.name) / 'studio.sqlite3')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.studio))
        self.worker = threading.Thread(target=self.server.serve_forever)
        self.worker.start()
        self.token = json.loads(self.request('GET', '/api/studio')[1])['csrf']

    def tearDown(self):
        self.server.shutdown()
        self.worker.join()
        self.server.server_close()
        self.studio.close()
        self.temp.cleanup()

    def request(self, method, path, data=None, headers=None):
        conn = HTTPConnection('127.0.0.1', self.server.server_port)
        common = {'Content-Type':'application/json', 'X-CSRF-Token':getattr(self, 'token', '')}
        common.update(headers or {})
        conn.request(method, path, json.dumps(data) if data is not None else None, common)
        response = conn.getresponse()
        result = response.status, response.read()
        conn.close()
        return result

    def test_complete_http_demo_and_export(self):
        status, body = self.request('POST', '/api/studio/create',dict(title='HTTP sınaq sifarişi', client='Test', objective='İki məhsul arasında uyğunluğu araşdır', mode='demo', budget=1))
        self.assertEqual(status, 200)
        pid = json.loads(body)['project_id']
        self.assertEqual(self.request('POST', '/api/studio/start', {'project_id':pid})[0], 200)
        for _ in range(20): self.studio.tick()
        self.assertEqual(self.request('GET', '/api/export?id='+pid)[0], 200)
        status, audit = self.request('GET', '/api/export?id='+pid+'&format=json')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(audit)['status'], 'awaiting_approval')
        self.assertEqual(self.request('POST', '/api/studio/approve', {'project_id':pid})[0], 200)

    def test_csrf_and_origin_and_host(self):
        for headers in [{'X-CSRF-Token':''},{'Origin':'https://hostile.example'}, {'Host':'hostile.example'}]:
            self.assertEqual(self.request('POST','/api/studio/create',{},headers)[0],403)
        self.assertEqual(self.request('GET','/api/studio',headers={'Host':'hostile.example'})[0],403)

    def test_static_assets_and_unknown_routes(self):
        for route in ['/', '/studio.js', '/studio_extra.js', '/studio_modules.js', '/studio_eval.js',
                      '/studio_research.js', '/studio_validation.js', '/studio_validation.css',
                      '/portal', '/portal.js', '/studio.css', '/studio_extra.css', '/studio_modules.css',
                      '/studio_eval.css', '/health']:
            self.assertEqual(self.request('GET',route)[0],200)

    def test_customer_and_market_sizing_http_persistence(self):
        from test_market_validation import study_data, sizing_data
        status, body = self.request('POST', '/api/studio/create', dict(title='HTTP bazar pilotu',
            objective='Bazar həcmini və kurs qiymətini yoxlamaq', mode='demo', budget=1,
            research_type='market', product='Kurs', region='Azərbaycan, Bakı',
            audience='İşləyən şəxslər', decision='İlk qiyməti seçmək'))
        self.assertEqual(status, 200)
        pid = json.loads(body)['project_id']
        status, body = self.request('POST', '/api/studio/customer-study-add', dict(project_id=pid, **study_data()))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['state']['projects'][0]['customer_summary'][0]['sample_size'], 20)
        status, body = self.request('POST', '/api/studio/market-sizing-save', dict(project_id=pid, **sizing_data()))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['state']['projects'][0]['market_size_result']['sam_customers'], 1000)
        _, body = self.request('GET', '/api/export?id=' + pid + '&format=json')
        audit = json.loads(body)
        self.assertEqual(audit['customer_studies'][0]['sample_code'], 'SURVEY-001')
        self.assertEqual(audit['market_sizing']['currency'], 'AZN')
        self.assertEqual(self.request('POST', '/api/studio/customer-study-add',
            dict(project_id=pid, **study_data(problem_count=999)))[0], 400)
        for route in ['/.env','/../main.py','/data/studio.sqlite3']:
            self.assertEqual(self.request('GET',route)[0],404)

    def test_bad_payload(self):
        self.assertEqual(self.request('POST','/api/studio/create',[])[0],400)
        self.assertEqual(self.request('POST','/api/studio/create',{}, {'Content-Type':'text/plain'})[0],415)

    def test_evaluation_export_is_scoped(self):
        self.assertEqual(self.request('GET', '/api/evaluation/export?id=missing')[0], 404)
        _, body = self.request('POST', '/api/studio/create', dict(title='Qiymətləndirmə', client='Test',
            objective='Sınaq nəticələrinin ixracını yoxla', mode='demo', budget=1))
        pid = json.loads(body)['project_id']
        status, payload = self.request('GET', '/api/evaluation/export?id='+pid)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)['project_id'], pid)

    def test_portal_is_scoped_and_revocable_over_http(self):
        _, body = self.request('POST', '/api/studio/create', dict(title='Portal sınağı', client='Test',
            objective='Müştəri baxışının təhlükəsizliyini yoxla', mode='demo', budget=1))
        pid = json.loads(body)['project_id']
        self.assertEqual(self.request('GET', '/api/portal?id='+pid+'&token=wrong')[0], 403)
        self.request('POST', '/api/studio/portal-create', {'project_id':pid})
        portal_token = self.studio.get(pid)['portal_token']
        status, body = self.request('GET', '/api/portal?id='+pid+'&token='+portal_token)
        self.assertEqual(status, 200)
        self.assertNotIn('sources', json.loads(body))
        self.assertEqual(self.request('GET', '/api/calendar?id='+pid)[0], 200)
        status, _ = self.request('POST', '/api/portal/feedback', dict(project_id=pid,
            portal_token=portal_token, message='Bu ay görüş planlayaq.'))
        self.assertEqual(status, 200)
        self.assertEqual(len(self.studio.get(pid)['client_feedback']), 1)
        self.request('POST', '/api/studio/portal-revoke', {'project_id':pid})
        self.assertEqual(self.request('GET', '/api/portal?id='+pid+'&token='+portal_token)[0], 403)

    def test_fact_review_updates_export_over_http(self):
        status, body = self.request('POST', '/api/studio/create', dict(
            title='Fakt baxışı sınağı', client='Test',
            objective='İki nümunə məhsulun imkanlarını araşdır', mode='demo', budget=1))
        self.assertEqual(status, 200)
        pid = json.loads(body)['project_id']
        self.assertEqual(self.request('POST', '/api/studio/start', {'project_id': pid})[0], 200)
        for _ in range(20): self.studio.tick()
        finding = self.studio.get(pid)['tasks'][0]['output']['findings'][0]
        self.assertEqual(self.request('POST', '/api/studio/review-finding',
                                      {'project_id': pid, 'finding_id': finding['id'], 'status': 'rejected'})[0], 200)
        _, audit = self.request('GET', '/api/export?id=' + pid + '&format=json')
        project = json.loads(audit)
        self.assertEqual(project['tasks'][0]['output']['findings'][0]['review']['status'], 'rejected')
        self.assertEqual(self.request('POST', '/api/studio/review-finding',
                                      {'project_id': pid, 'finding_id': finding['id'], 'status': 'accepted'})[0], 200)

    @patch('app.studio.search_sources')
    def test_live_sources_are_reviewed_before_http_start(self, search):
        search.return_value = [
            dict(title='Açıq mənbə A', url='https://example.com/a',
                 body='Birinci mənbədə yerli tətbiq haqqında kifayət qədər yoxlanılan məlumat mövcuddur.', origin='web'),
            dict(title='Açıq mənbə B', url='https://example.com/b',
                 body='İkinci mənbədə yerli tətbiq haqqında kifayət qədər yoxlanılan məlumat mövcuddur.', origin='web')]
        status, body = self.request('POST', '/api/studio/create', dict(
            title='Yerli tətbiq müqayisəsi', client='Test',
            objective='Yerli tətbiqlərin imkanlarını iki mənbə ilə müqayisə et', mode='live', budget=1))
        self.assertEqual(status, 200)
        pid = json.loads(body)['project_id']
        self.assertEqual(self.request('POST', '/api/studio/start', {'project_id': pid})[0], 400)
        self.assertEqual(self.request('POST', '/api/studio/discover-sources', {'project_id': pid})[0], 200)
        self.assertEqual(self.studio.get(pid)['source_discovery']['status'], 'queued')
        self.studio.discover_pending()
        project = self.studio.get(pid)
        self.assertEqual(project['status'], 'draft')
        self.assertEqual(len(project['sources']), 2)
        self.assertEqual(self.request('POST', '/api/studio/remove-source',
                                      {'project_id': pid, 'source_id': project['sources'][0]['id']})[0], 200)
        self.assertEqual(self.request('POST', '/api/studio/start', {'project_id': pid})[0], 400)

if __name__ == '__main__':
    unittest.main()
