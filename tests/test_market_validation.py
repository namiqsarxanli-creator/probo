import copy
import json
import tempfile
import unittest
from pathlib import Path
from app.studio import Studio
from app.customer_research import study_input, study_summary
from app.market_sizing import sizing_input, calculate
from test_studio import FakeProvider


def study_data(**updates):
    return dict(kind='survey', method='convenience', sample_size=20, problem_count=10,
                intent_count=8, paid_count=2, observed_date='2026-01-01', sample_code='SURVEY-001',
                region='Azərbaycan, Bakı', segment='İşləyən şəxslər', recruitment='Açıq sosial şəbəkə sorğusu',
                summary='İştirakçılar mövcud kursların vaxtını əlverişsiz hesab edir.', **{}) | updates


def sizing_data():
    values = dict(population=10000, eligible_percent=20, reachable_percent=50, annual_spend=600,
                  capture_low=1, capture_base=5, capture_high=10)
    return dict(currency='AZN', horizon_months=12,
                inputs={key: dict(value=value, basis='assumption', evidence_id='',
                                  note='İlkin pilot üçün yoxlanacaq fərziyyə') for key, value in values.items()})


class MarketValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'studio.sqlite3'
        self.s = Studio(self.path, FakeProvider())
        self.pid = self.s.action('create', dict(title='Kurs bazarı', objective='Qiyməti və müştəri seqmentini seçmək',
            mode='demo', budget=1, research_type='market', product='İngilis dili kursu', region='Azərbaycan, Bakı',
            audience='İşləyən şəxslər', decision='İlk qiyməti seçmək'))['project_id']

    def tearDown(self):
        self.s.close()
        self.temp.cleanup()

    def act(self, action, **data):
        return self.s.action(action, dict(project_id=self.pid, **data))

    def test_sizing_correct_units_subset_order_and_horizon(self):
        self.act('market-sizing-save', **sizing_data())
        result = self.s.snapshot()['projects'][0]['market_size_result']
        self.assertEqual(result['tam_annual'], 6000000)
        self.assertEqual(result['sam_customers'], 1000)
        self.assertEqual(result['sam_annual'], 600000)
        self.assertEqual([x['customers'] for x in result['scenarios']], [10, 50, 100])
        self.assertEqual([x['annual_potential'] for x in result['scenarios']], [6000, 30000, 60000])
        longer = sizing_data() | dict(horizon_months=24)
        self.act('market-sizing-save', **longer)
        self.assertEqual(self.s.snapshot()['projects'][0]['market_size_result']['scenarios'], result['scenarios'])
        self.assertEqual(result['assumption_count'], 7)

    def test_sizing_rejects_nonfinite_bad_bounds_units_and_order(self):
        for field, bad in [('population', float('nan')), ('annual_spend', float('inf')),
                           ('eligible_percent', 101), ('capture_base', -1), ('population', True)]:
            data = sizing_data()
            data['inputs'][field]['value'] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                self.act('market-sizing-save', **data)
        for updates in ({'currency': 'XXX'}, {'horizon_months': 0}, {'horizon_months': 1.5}):
            with self.assertRaises(ValueError):
                self.act('market-sizing-save', **(sizing_data() | updates))
        data = sizing_data()
        data['inputs']['capture_low']['value'] = 30
        with self.assertRaises(ValueError):
            self.act('market-sizing-save', **data)
        data = sizing_data()
        del data['inputs']['annual_spend']
        with self.assertRaises(ValueError):
            self.act('market-sizing-save', **data)
        self.assertIsNone(self.s.get(self.pid)['market_sizing'])

    def add_evidence(self):
        p = self.s.get(self.pid)
        source = p['sources'][0]
        self.act('market-evidence-add', question_id='pricing', source_id=source['id'],
                 claim='Luma planının qiyməti 19 demo vahididir.', quote=source['body'][:70],
                 region='Azərbaycan, Bakı')
        return p['market_evidence'][0]['id'], source['id']

    def test_sizing_provenance_changes_when_linked_evidence_removed(self):
        evidence_id, _ = self.add_evidence()
        data = sizing_data()
        data['inputs']['annual_spend'].update(basis='evidence', evidence_id=evidence_id,
                                               note='Sitatın dövrünü və vahidini insan yoxlamalıdır.')
        self.act('market-sizing-save', **data)
        before = self.s.snapshot()['projects'][0]['market_size_result']
        self.assertEqual(before['assumption_count'], 6)
        self.assertEqual(before['unverified_count'], 0)
        self.assertTrue(before['warnings'])  # No publication date is known.
        self.act('market-evidence-remove', evidence_id=evidence_id)
        after = self.s.snapshot()['projects'][0]['market_size_result']
        self.assertEqual(after['unverified_count'], 1)
        self.assertEqual(after['sam_annual'], before['sam_annual'])
        self.assertTrue(any('çıxarılıb' in warning for warning in after['warnings']))

    def test_sizing_cannot_label_missing_evidence_as_sourced(self):
        data = sizing_data()
        data['inputs']['population'].update(basis='evidence', evidence_id='missing')
        with self.assertRaises(ValueError):
            self.act('market-sizing-save', **data)

    def test_studies_reject_impossible_counts_and_duplicate_codes(self):
        for update in ({'problem_count': 21}, {'sample_size': 0}, {'intent_count': -1},
                       {'paid_count': 1.5}, {'observed_date': '2099-01-01'},
                       {'kind': 'interview', 'sample_size': 20}, {'method': 'made-up'}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.act('customer-study-add', **study_data(**update))
        self.act('customer-study-add', **study_data())
        with self.assertRaises(ValueError):
            self.act('customer-study-add', **study_data(sample_code='survey-001'))
        self.assertEqual(len(self.s.get(self.pid)['customer_studies']), 1)

    def test_summary_weights_counts_and_keeps_pilot_separate(self):
        records = [study_input(study_data()),
                   study_input(study_data(sample_code='SURVEY-002', sample_size=80, problem_count=16)),
                   study_input(study_data(kind='pilot', sample_code='PILOT-001'))]
        result = study_summary(records)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['sample_size'], 100)
        self.assertEqual(result[0]['problem_percent'], 26)
        self.assertEqual(result[1]['sample_size'], 20)

    def test_interview_can_record_payment_without_prior_intent(self):
        self.act('customer-study-add', **study_data(kind='interview', sample_size=1,
                                                  problem_count=1, intent_count=0, paid_count=1))
        self.assertEqual(self.s.snapshot()['projects'][0]['customer_summary'][0]['paid_percent'], 100)

    def test_customer_notes_never_enter_ai_messages(self):
        self.act('customer-study-add', **study_data(summary='PRIVATE-NOTE-ONLY-FOR-LOCAL-REPORT'))
        p = self.s.get(self.pid)
        payload = json.dumps(self.s.messages(p, p['tasks'][0], 'profile'), ensure_ascii=False)
        self.assertNotIn('PRIVATE-NOTE', payload)
        self.assertNotIn('customer_studies', payload)

    def test_roundtrip_persistence_and_legacy_defaults(self):
        self.act('customer-study-add', **study_data())
        self.act('market-sizing-save', **sizing_data())
        self.s.close()
        self.s = Studio(self.path, FakeProvider())
        self.assertEqual(len(self.s.get(self.pid)['customer_studies']), 1)
        self.assertEqual(self.s.get(self.pid)['market_sizing']['currency'], 'AZN')
        p = self.s.get(self.pid)
        del p['customer_studies']
        del p['market_sizing']
        self.s.save(p)
        self.s.close()
        self.s = Studio(self.path, FakeProvider())
        self.assertEqual(self.s.get(self.pid)['customer_studies'], [])
        self.assertIsNone(self.s.get(self.pid)['market_sizing'])

    def test_report_export_includes_local_observations_and_formulas_and_freezes_after_approval(self):
        self.act('customer-study-add', **study_data())
        self.act('market-sizing-save', **sizing_data())
        self.act('start')
        for _ in range(20):
            self.s.tick()
        p = self.s.get(self.pid)
        self.assertEqual(p['status'], 'awaiting_approval')
        report = self.s.report(self.pid)
        self.assertIn('SURVEY-001', report)
        self.assertIn('TAM =', report)
        self.assertIn('statistik etibar intervalı deyil', report)
        self.act('customer-study-add', **study_data(sample_code='SURVEY-002'))
        self.assertIn('SURVEY-002', self.s.report(self.pid))
        self.act('approve')
        with self.assertRaises(ValueError):
            self.act('market-sizing-save', **sizing_data())
        with self.assertRaises(ValueError):
            self.act('customer-study-remove', study_id=p['customer_studies'][0]['id'])

    def test_general_project_rejects_validation_actions(self):
        p = self.s.get(self.pid)
        p['research_brief'] = None
        for action, data in [('customer-study-add', study_data()), ('market-sizing-save', sizing_data())]:
            with self.assertRaises(ValueError):
                self.act(action, **data)
