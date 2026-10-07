import io
import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from app.studio import Studio, check_output
from app.sources import public_url, fetch_text
from app.provider import Provider, RateLimitError


class FakeProvider:
    def __init__(self, bad=False):
        self.bad = bad
        self.started = threading.Event()
        self.release = None

    def status(self):
        return dict(ready=True, model='test', missing=[], key_present=True, endpoint='https://example.test', problem='')

    def prepare(self, messages):
        return dict(reserve=10000, messages=messages)

    def execute(self, call):
        self.started.set()
        if self.release:
            self.release.wait(5)
        context = json.loads(call['messages'][1]['content'])
        source = context['sources'][0]
        return dict(content=json.dumps(dict(findings=[dict(claim='Mənbədə göstərilən məhsul imkanları', source_id=source['id'],
                 quote='Bu sitat mənbədə mövcud deyil' if self.bad else source['body'][:70])],
                 recommendations=['Mənbədəki imkanları ehtiyaclara uyğun qiymətləndirin.'], limitations='Yalnız verilən mənbələr istifadə edilib.')),
                 cost=5000, usage={'prompt_tokens': 20, 'completion_tokens': 30}, estimated=False)


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'studio.sqlite3'
        self.provider = FakeProvider()
        self.s = Studio(self.path, self.provider)

    def tearDown(self):
        self.s.close()
        self.temp.cleanup()

    def project(self, mode='demo', budget=5):
        result = self.s.action('create', dict(title='Məhsulların müqayisəsi', client='Test şirkəti',
                               objective='Komanda üçün məhsul imkanlarını müqayisə et', mode=mode, budget=budget))
        pid = result['project_id']
        if mode == 'live':
            for i in range(2):
                self.s.action('source', dict(project_id=pid, title=f'Məhsul sənədi {i}', url=f'https://example.com/{i}',
                   body=f'Məhsul {i} üçün komanda planında üç istifadəçi yeri və məlumatların CSV formatında ixrac edilməsi mövcuddur.'))
                source_id = self.s.get(pid)['sources'][-1]['id']
                self.s.action('review-source', dict(project_id=pid, source_id=source_id,
                                                    status='approved', relevance=5, note='Sınaq mənbəsi'))
        return pid

    def start(self, pid):
        self.s.action('start', {'project_id': pid})

    def finish(self, steps=40):
        for _ in range(steps):
            self.s.tick()

    def test_demo_complete_approve_memory(self):
        pid = self.project()
        self.start(pid)
        self.finish()
        p = self.s.get(pid)
        self.assertEqual(p['status'], 'awaiting_approval')
        self.assertEqual(len(p['candidates']), 6)
        self.assertEqual(len(p['calls']), 9)
        self.assertEqual(p['spent'], 135000)
        self.assertTrue(all({'evidence', 'completeness', 'economy', 'speed'} <= set(c['metrics']) for c in p['candidates']))
        self.assertIn('NÜMAYİŞ', p['report'])
        self.s.action('approve', {'project_id': pid})
        self.assertEqual(len(self.s.snapshot()['memory']), 1)
        self.assertIn('Sahib tərəfindən təsdiqləndi', self.s.report(pid))

    def test_live_provider_path_no_fake_fallback(self):
        pid = self.project('live')
        self.start(pid)
        self.finish()
        self.assertEqual(self.s.get(pid)['status'], 'awaiting_approval')
        self.assertEqual(self.s.get(pid)['spent'], 45000)
        self.assertNotIn('NÜMAYİŞ', self.s.report(pid))

    def test_live_report_requires_fact_review_and_excludes_rejected(self):
        pid = self.project('live')
        self.start(pid)
        self.finish()
        p = self.s.get(pid)
        self.assertEqual(p['status'], 'awaiting_approval')
        with self.assertRaisesRegex(ValueError, 'bütün faktları'):
            self.s.action('approve', {'project_id': pid})
        first = p['tasks'][0]['output']['findings'][0]
        before = p['report'].count('Mənbədə göstərilən məhsul imkanları')
        self.s.action('review-finding', dict(project_id=pid, finding_id=first['id'], status='rejected', note='İddia zəifdir'))
        self.assertEqual(self.s.get(pid)['report'].count('Mənbədə göstərilən məhsul imkanları'), before - 1)
        for task in self.s.get(pid)['tasks']:
            for finding in task['output']['findings']:
                if finding['id'] != first['id']:
                    self.s.action('review-finding', dict(project_id=pid, finding_id=finding['id'], status='accepted'))
        with self.assertRaisesRegex(ValueError, 'ən azı bir qəbul edilmiş'):
            self.s.action('approve', {'project_id': pid})
        self.s.action('review-finding', dict(project_id=pid, finding_id=first['id'], status='accepted'))
        self.s.action('approve', {'project_id': pid})
        self.assertEqual(self.s.get(pid)['status'], 'completed')

    def test_live_source_must_be_approved_before_start(self):
        pid = self.project('live')
        p = self.s.get(pid)
        first = p['sources'][0]
        self.s.action('review-source', dict(project_id=pid, source_id=first['id'], status='rejected', relevance=1))
        with self.assertRaisesRegex(ValueError, 'iki mənbəni təsdiqləyin'):
            self.s.action('start', {'project_id': pid})
        self.assertEqual(self.s.get(pid)['status'], 'draft')

    @patch('app.studio.search_sources')
    def test_live_discovery_requires_source_review_before_start(self, discover):
        discover.return_value = [
            dict(title='Açıq mənbə A', url='https://example.com/a', body='Birinci açıq mənbədə araşdırma üçün kifayət qədər yoxlanılan məlumat mövcuddur.'),
            dict(title='Açıq mənbə B', url='https://example.org/b', body='İkinci açıq mənbədə müqayisə üçün kifayət qədər yoxlanılan məlumat mövcuddur.')]
        result = self.s.action('create', dict(title='AI təhsil bazarı', client='Test şirkəti',
                               objective='Azərbaycan üçün AI təhsil məhsulunun bazar imkanlarını araşdır',
                               mode='live', budget=5))
        pid = result['project_id']
        with self.assertRaises(ValueError):
            self.s.action('start', {'project_id': pid})
        self.assertEqual(self.s.get(pid)['calls'], [])
        self.assertEqual(self.s.get(pid)['source_discovery']['status'], 'queued')
        self.s.discover_pending()
        project = self.s.get(pid)
        self.assertEqual(project['status'], 'draft')
        self.assertEqual(len(project['sources']), 2)
        self.assertTrue(all(source['origin'] == 'web' for source in project['sources']))
        discover.assert_called_once()
        self.assertEqual(project['source_discovery']['status'], 'done')
        rejected = project['sources'][0]['id']
        self.s.action('remove-source', {'project_id': pid, 'source_id': rejected})
        self.assertEqual(len(project['sources']), 1)
        with self.assertRaises(ValueError):
            self.s.action('start', {'project_id': pid})
        self.s.action('source', dict(project_id=pid, title='Əvəz mənbə', url='https://example.net/third',
                                     body='Bu mənbədə araşdırma üçün kifayət qədər yoxlanılan məlumat mövcuddur.'))
        for source in self.s.get(pid)['sources']:
            self.s.action('review-source', dict(project_id=pid, source_id=source['id'],
                                                status='approved', relevance=4))
        self.s.action('start', {'project_id': pid})
        self.assertEqual(self.s.get(pid)['status'], 'running')

    @patch('app.studio.search_sources')
    def test_discovery_failure_can_retry_and_preserves_manual_sources(self, search):
        pid = self.project('live')
        before = len(self.s.get(pid)['sources'])
        search.side_effect = OSError('Search unavailable')
        self.s.discover_pending()
        self.assertEqual(self.s.get(pid)['source_discovery']['status'], 'error')
        self.assertEqual(len(self.s.get(pid)['sources']), before)
        search.side_effect = None
        search.return_value = []
        self.s.action('discover-sources', {'project_id': pid})
        self.s.discover_pending()
        self.assertEqual(self.s.get(pid)['source_discovery']['status'], 'done')
        self.assertEqual(self.s.get(pid)['source_discovery']['found'], 0)
        self.assertEqual(self.s.get(pid)['calls'], [])

    def test_unconfigured_live_stays_draft(self):
        pid = self.project('live')
        self.s.provider = Provider(Path(self.temp.name))
        with self.assertRaises(ValueError): self.start(pid)
        self.assertEqual(self.s.get(pid)['status'], 'draft')

    def test_low_budget_stops_before_call(self):
        pid = self.project(budget=.01)
        self.start(pid)
        self.s.tick()
        self.assertEqual(self.s.get(pid)['status'], 'budget_blocked')
        self.assertEqual(self.s.get(pid)['spent'], 0)
        self.s.action('budget', dict(project_id=pid, budget=1))
        self.s.action('resume', dict(project_id=pid))
        self.finish()
        self.assertEqual(self.s.get(pid)['status'], 'awaiting_approval')

    def test_fake_citation_blocks_quality(self):
        self.provider.bad = True
        pid = self.project('live')
        self.start(pid)
        self.finish()
        p = self.s.get(pid)
        self.assertEqual(p['status'], 'quality_blocked')
        self.assertIsNone(p['report'])
        self.assertEqual(len(p['calls']), 2)

    def test_fire_handoff_keeps_prior_outputs(self):
        pid = self.project()
        self.start(pid)
        for _ in range(7): self.s.tick()
        p = self.s.get(pid)
        self.assertEqual(p['tasks'][0]['status'], 'done')
        self.s.action('crisis', dict(project_id=pid, kind='worker'))
        self.assertEqual(len(p['handoffs'][0]['previous_outputs']), 1)
        self.finish()
        self.assertEqual(p['status'], 'awaiting_approval')
        self.assertEqual(p['handoffs'][0]['status'], 'verified')
        crisis = p['presentation']['crises'][0]
        self.assertTrue(crisis['resolved'])
        self.assertIsInstance(crisis['recovery_seconds'], int)

    def test_budget_crisis_is_recorded_for_presentation(self):
        pid = self.project()
        self.start(pid)
        p = self.s.get(pid)
        before = p['budget'] - p['spent']
        self.s.action('crisis', dict(project_id=pid, kind='budget'))
        crisis = p['presentation']['crises'][0]
        self.assertEqual(crisis['kind'], 'budget')
        self.assertTrue(crisis['resolved'])
        self.assertEqual(p['budget'] - p['spent'], before // 2)

    def test_inflight_fired_worker_cannot_commit(self):
        pid = self.project('live')
        self.start(pid)
        for _ in range(3): self.s.tick()
        self.provider.started.clear()
        self.provider.release = threading.Event()
        worker = threading.Thread(target=self.s.tick)
        worker.start()
        self.assertTrue(self.provider.started.wait(2))
        self.s.action('crisis', dict(project_id=pid, kind='worker'))
        self.provider.release.set()
        worker.join(3)
        self.assertFalse(worker.is_alive())
        p = self.s.get(pid)
        self.assertEqual(p['calls'][-1]['status'], 'discarded')
        self.assertIsNone(p['tasks'][0]['output'])
        self.assertEqual(p['spent'], 15000)

    def test_pausing_during_call_commits_without_starting_next(self):
        pid = self.project('live')
        self.start(pid)
        self.provider.release = threading.Event()
        worker = threading.Thread(target=self.s.tick)
        worker.start()
        self.assertTrue(self.provider.started.wait(2))
        self.s.action('pause', dict(project_id=pid))
        self.provider.release.set()
        worker.join(3)
        self.finish()
        self.assertEqual(self.s.get(pid)['status'], 'paused')
        self.assertEqual(len(self.s.get(pid)['calls']), 1)

    def test_crash_recovery_reservation_retained(self):
        pid = self.project()
        p = self.s.get(pid)
        p.update(lease='uncertain-call', spent=15000, status='running')
        self.s.save(p)
        self.s.close()
        self.s = Studio(self.path, self.provider)
        self.assertEqual(self.s.get(pid)['status'], 'interrupted')
        self.assertEqual(self.s.get(pid)['spent'], 15000)

    def test_two_projects_are_isolated(self):
        one, two = self.project(), self.project()
        self.start(one)
        self.finish()
        self.assertEqual(self.s.get(two)['status'], 'draft')
        self.assertEqual(self.s.get(two)['calls'], [])
        self.assertNotEqual(self.s.get(one)['sources'][0]['id'], self.s.get(two)['sources'][0]['id'])

    def test_revision_reuses_research(self):
        pid = self.project()
        self.start(pid)
        self.finish()
        p = self.s.get(pid)
        before = p['tasks'][0]['output']
        self.s.action('revise', dict(project_id=pid, note='İxrac imkanlarını daha aydın müqayisə et.'))
        self.finish()
        self.assertEqual(p['tasks'][0]['output'], before)
        self.assertEqual(len(p['calls']), 10)
        self.assertEqual(p['status'], 'awaiting_approval')

    def test_source_snapshot_cannot_change_after_start(self):
        pid = self.project()
        self.start(pid)
        with self.assertRaises(ValueError):
            self.s.action('source',dict(project_id=pid, title='new',body='x'*50))
        self.assertEqual(len(self.s.get(pid)['sources']), 3)

    def test_unknown_source_rejected(self):
        with self.assertRaises(ValueError):
            check_output(json.dumps({'findings':[{'claim':'A valid sounding claim', 'quote':'A valid sounding quote', 'source_id':'fake'}]}), [])

    def test_invalid_quote_is_removed_when_other_evidence_is_valid(self):
        source = dict(id='s1', body='Məhsul on istifadəçi üçün CSV ixracını dəstəkləyir.')
        raw = json.dumps(dict(findings=[
            dict(claim='CSV ixracı mövcuddur', source_id='s1', quote=source['body']),
            dict(claim='PDF ixracı mövcuddur', source_id='s1', quote='Mənbədə olmayan PDF ixracı')],
            recommendations=[], limitations='İnsan yoxlaması lazımdır.'))
        output = check_output(raw, [source])
        self.assertEqual(len(output['findings']), 1)
        self.assertEqual(output['rejected_findings'], 1)
        self.assertEqual(output['findings'][0]['claim'], 'CSV ixracı mövcuddur')

    def test_accepted_quote_uses_source_original_text(self):
        source = dict(id='s1', body='Məhsul  CSV ixracını Dəstəkləyir.')
        raw = json.dumps(dict(findings=[dict(claim='CSV ixracı dəstəklənir', source_id='s1',
                                             quote='məhsul csv ixracını dəstəkləyir.')],
                              recommendations=[], limitations='İnsan yoxlaması lazımdır.'))
        output = check_output(raw, [source])
        self.assertEqual(output['findings'][0]['quote'], source['body'])

    def test_rate_limit_waits_refunds_and_resumes(self):
        pid = self.project('live')
        self.start(pid)
        original = self.provider.execute
        with patch.object(self.provider, 'execute', side_effect=RateLimitError(2)):
            self.s.tick()
        p = self.s.get(pid)
        self.assertEqual(p['status'], 'rate_limited')
        self.assertEqual(p['spent'], 0)
        self.assertEqual(p['calls'][-1]['status'], 'rate_limited')
        self.assertEqual(p['calls'][-1]['cost'], 0)
        self.assertEqual(len(p['tasks'][0]['trials']), 0)
        self.s.tick()
        self.assertEqual(len(p['calls']), 1)
        p['retry_at'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        self.s.save(p)
        with patch.object(self.provider, 'execute', side_effect=original):
            self.s.tick()
        self.assertEqual(p['status'], 'running')
        self.assertEqual(p['calls'][-1]['status'], 'done')
        self.assertIsNone(p['retry_at'])

    def test_rate_limit_can_be_paused_without_auto_resume(self):
        pid = self.project('live')
        self.start(pid)
        with patch.object(self.provider, 'execute', side_effect=RateLimitError(1)):
            self.s.tick()
        p = self.s.get(pid)
        self.s.action('pause', {'project_id': pid})
        p['retry_at'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        self.s.save(p)
        self.s.tick()
        self.assertEqual(p['status'], 'paused')
        self.assertEqual(len(p['calls']), 1)

    def test_provider_reads_retry_after_without_exposing_response(self):
        provider = Provider(Path(self.temp.name))
        headers = Message()
        headers['retry-after'] = '7'
        error = HTTPError('https://api.example.test/chat/completions', 429, 'limited', headers, io.BytesIO())
        self.addCleanup(error.close)
        with patch('app.provider.build_opener') as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(RateLimitError) as caught:
                provider.send(dict(endpoint='https://api.example.test/chat/completions', key='secret'),
                              dict(response_format={'type': 'json_object'}))
        self.assertEqual(caught.exception.retry_after, 7)

    def test_source_url_guards(self):
        for url in ['http://example.com', 'https://user:pass@example.com', 'https://example.com:444']:
            with self.assertRaises(ValueError): public_url(url)
        with patch('app.sources.socket.getaddrinfo', return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError): fetch_text('https://example.com')

    def test_provider_secret_not_in_status(self):
        root = Path(self.temp.name)
        (root/'.env').write_text('AI_API_KEY=do-not-expose\nAI_BASE_URL=https://example.com/v1\nAI_MODEL=test\nAI_INPUT_USD_PER_MILLION=1\nAI_OUTPUT_USD_PER_MILLION=2')
        provider = Provider(root)
        self.assertTrue(provider.status()['ready'])
        self.assertNotIn('do-not-expose', json.dumps(provider.status()))
        prepared = provider.prepare([{'role':'user','content':'test'}])
        self.assertGreater(prepared['reserve'], 0)

    def test_groq_conventional_key_and_defaults(self):
        root = Path(self.temp.name)
        (root/'.env').write_text('AI_BASE_URL=https://api.groq.com/openai/v1\nGROQ_API_KEY=do-not-expose')
        provider = Provider(root)
        status = provider.status()
        self.assertTrue(status['ready'])
        self.assertEqual(status['model'], 'openai/gpt-oss-120b')
        self.assertNotIn('do-not-expose', json.dumps(status))
        call = provider.prepare([{'role':'user','content':'test'}])
        self.assertEqual(call['input_rate'], .15)
        self.assertEqual(call['output_rate'], .60)

    def test_timeout_reserve_retained_without_auto_retry(self):
        pid = self.project('live')
        self.start(pid)
        with patch.object(self.provider, 'execute', side_effect=RuntimeError('Timeout')):
            self.finish()
        self.assertEqual(self.s.get(pid)['status'], 'error')
        self.assertEqual(self.s.get(pid)['spent'], 10000)
        self.assertEqual(len(self.s.get(pid)['calls']), 1)


if __name__ == '__main__':
    unittest.main()
