import tempfile
import unittest
from pathlib import Path
from app.engine import Company


class CompanyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'state.sqlite3'
        self.c = Company(self.path)
        self.c.action('create', {'objective': 'Həftəlik məhsul araşdırması hazırla', 'budget': 20})

    def tearDown(self):
        self.c.close()
        self.temp.cleanup()

    def finish(self):
        for _ in range(100):
            self.c.tick()

    def test_complete_and_persist(self):
        self.finish()
        s = self.c.snapshot()
        self.assertEqual(s['status'], 'completed')
        self.assertEqual(s['spent'], 320)
        self.assertEqual(len(s['employees']), 5)
        self.assertTrue(all(t['status'] == 'done' for t in s['tasks']))
        other = Company(self.path)
        self.assertEqual(other.snapshot(), s)
        other.close()

    def test_fire_handoff_resume(self):
        for _ in range(4): self.c.tick()
        before = self.c.snapshot()['tasks'][0]
        self.assertEqual(before['progress'], 2)
        self.c.action('fire', {'id': before['assignee']})
        self.c.tick()
        s = self.c.snapshot()
        self.assertNotEqual(s['tasks'][0]['assignee'], before['assignee'])
        self.assertEqual(s['tasks'][0]['progress'], 2)
        self.assertEqual(s['handoffs'][0]['notes'], before['notes'])
        self.assertEqual(s['handoffs'][0]['status'], 'accepted')
        self.finish()
        self.assertEqual(self.c.snapshot()['handoffs'][0]['status'], 'verified')

    def test_budget_never_overruns(self):
        self.c.action('budget', {'budget': .3})
        self.finish()
        s = self.c.snapshot()
        self.assertEqual(s['status'], 'budget_blocked')
        self.assertLessEqual(s['spent'], s['budget'])
        self.c.action('budget', {'budget': 10})
        self.c.action('resume', {})
        self.finish()
        self.assertEqual(self.c.snapshot()['status'], 'completed')

    def test_pause_is_durable(self):
        self.c.action('pause', {})
        before = self.c.snapshot()
        self.c.tick()
        self.assertEqual(before, self.c.snapshot())
        other = Company(self.path)
        self.assertEqual(other.snapshot()['status'], 'paused')
        other.close()

    def test_invalid_actions_leave_state_unchanged(self):
        before = self.c.snapshot()
        for action, data in [('fire', {'id': before['employees'][0]['id']}),
                             ('budget', {'budget': 'NaN'}), ('create', {'objective': 'again', 'budget': 20})]:
            with self.assertRaises(ValueError): self.c.action(action, data)
            self.assertEqual(before, self.c.snapshot())

    def test_dependencies(self):
        for _ in range(5): self.c.tick()
        tasks = self.c.snapshot()['tasks']
        self.assertNotEqual(tasks[0]['status'], 'done')
        self.assertTrue(all(t['progress'] == 0 and t['assignee'] is None for t in tasks[1:]))

    def test_restart_mid_handoff(self):
        for _ in range(3): self.c.tick()
        self.c.action('fire', {'id': self.c.snapshot()['tasks'][0]['assignee']})
        self.c.close()
        self.c = Company(self.path)
        self.c.tick()
        self.assertEqual(self.c.snapshot()['handoffs'][0]['status'], 'accepted')
        self.assertEqual(self.c.snapshot()['tasks'][0]['progress'], 1)

if __name__ == '__main__':
    unittest.main()
