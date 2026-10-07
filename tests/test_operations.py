import tempfile
import unittest
from pathlib import Path

from app.operations import plan_input, scenario_input, project
from app.studio import Studio


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'studio.sqlite3'
        self.studio = Studio(self.path)
        self.pid = self.studio.action('create', dict(title='Əməliyyat sınağı', client='Test',
            objective='Aylıq maliyyə və tapşırıq axınını yoxla', mode='demo', budget=1))['project_id']

    def tearDown(self):
        self.studio.close()
        self.temp.cleanup()

    def act(self, action, **data):
        return self.studio.action(action, dict(project_id=self.pid, **data))

    def test_finance_and_scenarios_are_deterministic_and_persist(self):
        plan = dict(starting_cash=1000, monthly_customers=10, price=20, variable_cost=5,
                    fixed_cost=100, churn=0, growth=0, months=3)
        self.act('finance-plan', **plan)
        base = self.studio.snapshot()['projects'][0]['finance_projection']
        self.assertEqual(base['ending_cash'], 1600)
        self.assertEqual([r['cash'] for r in base['rows']], [1050, 1250, 1600])
        self.act('scenario-add', name='İki ay gecikmə', sales_multiplier=1,
                 cost_multiplier=1, delay_months=2)
        changed = self.studio.snapshot()['projects'][0]['scenarios'][0]['projection']
        self.assertEqual(changed['ending_cash'], 850)
        self.assertEqual(self.studio.get(self.pid)['finance_plan'], plan_input(plan))
        self.studio.close()
        self.studio = Studio(self.path)
        self.assertEqual(len(self.studio.get(self.pid)['scenarios']), 1)
        self.assertEqual(self.studio.snapshot()['projects'][0]['scenarios'][0]['projection'], changed)

    def test_work_and_portal_feedback_are_isolated(self):
        self.act('work-add', title='Pilot təqdimatı', owner='Aysel', due='2026-10-01')
        item = self.studio.get(self.pid)['work_items'][0]
        self.assertIn(b'DTSTART;VALUE=DATE:20261001', self.studio.calendar(self.pid))
        self.act('work-status', item_id=item['id'], status='done')
        self.act('portal-create')
        token = self.studio.get(self.pid)['portal_token']
        portal = self.studio.portal_project(self.pid, token)
        self.assertEqual(portal['work_items'][0]['status'], 'done')
        self.assertNotIn('sources', portal)
        self.assertNotIn('calls', portal)
        self.studio.portal_feedback(self.pid, token, 'Təqdimat tarixini təsdiqləyirəm.')
        self.assertEqual(len(self.studio.get(self.pid)['client_feedback']), 1)
        self.act('portal-revoke')
        with self.assertRaises(ValueError):
            self.studio.portal_project(self.pid, token)

    def test_validation_does_not_mutate_project(self):
        before = self.studio.get(self.pid).copy()
        for action, data in [('finance-plan', dict(starting_cash=-1)),
                             ('scenario-add', dict(name='x')),
                             ('work-add', dict(title='İş', owner='A', due='2026-99-99'))]:
            with self.assertRaises(ValueError):
                self.act(action, **data)
        self.assertEqual(self.studio.get(self.pid), before)
        with self.assertRaises(ValueError):
            scenario_input(dict(name='Şok', sales_multiplier=float('nan'), cost_multiplier=1, delay_months=0))


if __name__ == '__main__':
    unittest.main()
