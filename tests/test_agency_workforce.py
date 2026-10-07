import unittest

from agency import workforce as wf


def worker(identifier, status='active', model='openai/gpt-oss-20b', persona='diqqetli', name=None):
    return dict(id=identifier, name=name or identifier, status=status, model=model, persona=persona)


def attempts(worker_id, passed, blocked, cost=100, exam=False):
    rows = [dict(worker_id=worker_id, outcome='passed', cost=cost, duration_ms=500, exam=exam) for _ in range(passed)]
    rows += [dict(worker_id=worker_id, outcome='blocked', cost=cost, duration_ms=500, exam=exam) for _ in range(blocked)]
    return rows


class WilsonTest(unittest.TestCase):
    def test_interval_narrows_with_evidence(self):
        small, large = wf.wilson(1, 5), wf.wilson(20, 100)
        self.assertGreater(small[1] - small[0], large[1] - large[0])
        self.assertEqual(wf.wilson(0, 0), (0.0, 1.0))

    def test_salary_uses_list_price(self):
        self.assertEqual(wf.salary('openai/gpt-oss-120b', 1000, 1000), 750)  # 1000*0.15 + 1000*0.60


class ReviewTest(unittest.TestCase):
    def act(self, actions, kind):
        return [a for a in actions if a['kind'] == kind]

    def test_nobody_is_judged_during_probation(self):
        actions = wf.review([worker('a', 'probation')], attempts('a', 1, 4))
        self.assertEqual(actions, [])

    def test_clear_evidence_fires_with_numbers_in_the_reason(self):
        actions = wf.review([worker('a', name='Nur')], attempts('a', 13, 7))
        fired = self.act(actions, 'fire')
        self.assertEqual(len(fired), 1)
        self.assertIn('Nur işdən çıxarıldı', fired[0]['message'])
        self.assertIn('7-i bloklanıb', fired[0]['message'])
        self.assertIn('95% interval', fired[0]['message'])

    def test_borderline_record_warns_instead_of_firing(self):
        actions = wf.review([worker('a')], attempts('a', 7, 2))  # 22%, but lower bound under 10%
        self.assertFalse(self.act(actions, 'fire'))
        self.assertEqual(self.act(actions, 'warn')[0]['status'], 'warned')

    def test_warning_is_lifted_after_recovery(self):
        record = attempts('a', 30, 2)
        actions = wf.review([worker('a', 'warned')], record)
        self.assertEqual(self.act(actions, 'restore')[0]['status'], 'active')

    def test_probation_ends_with_a_clean_record(self):
        actions = wf.review([worker('a', 'probation')], attempts('a', 10, 0))
        self.assertTrue(self.act(actions, 'confirm'))

    def test_exam_attempts_never_count_as_work(self):
        actions = wf.review([worker('a')], attempts('a', 0, 20, exam=True))
        self.assertEqual(actions, [])

    def test_cheapest_reliable_worker_is_promoted_and_old_senior_steps_down(self):
        staff = [worker('a', 'senior', name='Leyla'), worker('b', name='Kamal')]
        record = attempts('a', 20, 0, cost=900) + attempts('b', 20, 0, cost=100)
        actions = wf.review(staff, record)
        self.assertEqual(self.act(actions, 'promote')[0]['worker_id'], 'b')
        self.assertEqual(self.act(actions, 'demote')[0]['worker_id'], 'a')

    def test_fired_worker_cannot_be_promoted(self):
        record = attempts('a', 11, 9, cost=1)
        actions = wf.review([worker('a')], record)
        self.assertFalse(self.act(actions, 'promote'))


class StaffingTest(unittest.TestCase):
    def test_candidates_skip_tried_pairs_and_unavailable_models(self):
        staff = [worker('a', model='openai/gpt-oss-20b', persona='diqqetli')]
        pool = wf.candidates(staff, available={'openai/gpt-oss-20b', 'openai/gpt-oss-120b'})
        self.assertNotIn(('openai/gpt-oss-20b', 'diqqetli'), pool)
        self.assertNotIn('qwen/qwen3.8-27b', {model for model, _ in pool})
        self.assertEqual(pool[0][0], 'openai/gpt-oss-20b')  # cheapest first

    def test_layoff_only_when_budget_is_spent_and_never_the_last_seat(self):
        staff = [worker('a'), worker('b')]
        record = attempts('a', 10, 0, cost=50) + attempts('b', 10, 0, cost=500)
        self.assertIsNone(wf.layoff(staff, record, spent=100))
        cut = wf.layoff(staff, record, spent=6_000_000)
        self.assertEqual(cut['worker_id'], 'b')
        self.assertIsNone(wf.layoff([worker('a')], record, spent=6_000_000))

    def test_names_are_not_reused(self):
        self.assertEqual(wf.next_name([worker('x', name='Nur')]), 'Kamal')


if __name__ == '__main__':
    unittest.main()
