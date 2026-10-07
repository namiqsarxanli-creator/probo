import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.studio import Studio
from test_studio import FakeProvider


class MarketResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'studio.sqlite3'
        self.s = Studio(self.path, FakeProvider())
        self.pid = self.s.action('create', dict(title='Bakı kurs bazarı', objective='Kursun qiymətini və ilk müştərisini seçmək',
            mode='live', budget=1, research_type='market', product='English course', region='Baku Azerbaijan',
            audience='18–30 yaşlı işləyənlər', decision='Qiyməti seçmək'))['project_id']

    def tearDown(self):
        self.s.close()
        self.temp.cleanup()

    @patch('app.studio.search_sources')
    def test_question_search_preserves_plan_and_deduplicates(self, search):
        search.return_value = [dict(title='Kurs qiymətləri', url='https://example.org/pricing',
            body='Aylıq kurs qiyməti 100 manatdır. Paketə həftədə iki canlı dərs daxildir.', origin='web')]
        for _ in range(5):
            self.s.discover_pending()
        p = self.s.get(self.pid)
        self.assertEqual(search.call_count, 5)
        self.assertEqual(len(p['sources']), 1)
        self.assertTrue(all(q['status'] == 'done' and len(q['source_ids']) == 1 for q in p['research_plan']))
        self.assertIn('Baku Azerbaijan', search.call_args_list[0].args[0])
        self.assertEqual(p['source_discovery']['status'], 'done')
        self.assertEqual(p['calls'], [])

    def test_evidence_requires_approved_source_exact_quote_and_valid_date(self):
        self.s.action('source', dict(project_id=self.pid, title='Kurs qiymətləri', url='https://example.org/pricing',
            body='Aylıq kurs qiyməti 100 manatdır. Paketə həftədə iki canlı dərs daxildir.'))
        sid = self.s.get(self.pid)['sources'][0]['id']
        data = dict(project_id=self.pid, source_id=sid, question_id='pricing', claim='Aylıq qiymət 100 manatdır.',
                    quote='Aylıq kurs qiyməti 100 manatdır.', published_date='2020-01-01', region='Bakı', entity='Kurs A')
        with self.assertRaises(ValueError):
            self.s.action('market-evidence-add', data)
        self.s.action('review-source', dict(project_id=self.pid, source_id=sid, status='approved', relevance=5))
        with self.assertRaises(ValueError):
            self.s.action('market-evidence-add', dict(data, quote='Bu sözlər orijinal mənbədə yoxdur.'))
        with self.assertRaises(ValueError):
            self.s.action('market-evidence-add', dict(data, published_date='2099-01-01'))
        self.s.action('market-evidence-add', data)
        p = self.s.get(self.pid)
        entry = p['market_evidence'][0]
        self.assertTrue(entry['stale'])
        with self.assertRaises(ValueError):
            self.s.action('remove-source', dict(project_id=self.pid, source_id=sid))
        self.s.action('market-evidence-conflict', dict(project_id=self.pid, evidence_id=entry['id'], note='Digər səhifədə qiymət fərqlidir.'))
        self.assertEqual(self.s.snapshot()['projects'][0]['market_coverage'][3]['count'], 1)
        self.s.action('review-source', dict(project_id=self.pid, source_id=sid, status='rejected', relevance=1))
        self.assertEqual(self.s.snapshot()['projects'][0]['market_coverage'][3]['count'], 0)

    def test_restart_recovers_question_search(self):
        p = self.s.get(self.pid)
        p['source_discovery']['status'] = 'searching'
        p['research_plan'][0]['status'] = 'searching'
        self.s.save(p)
        self.s.close()
        self.s = Studio(self.path, FakeProvider())
        self.assertEqual(self.s.get(self.pid)['research_plan'][0]['status'], 'queued')
