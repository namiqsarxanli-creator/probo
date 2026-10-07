import tempfile
import unittest
from pathlib import Path

from app.evaluation import score_trial
from app.studio import Studio


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'studio.sqlite3'
        self.studio = Studio(self.path)
        self.pid = self.studio.action('create', dict(title='Keyfiyyət sınağı', client='Test',
            objective='Saxlanmış profillərin sitat keyfiyyətini müqayisə et', mode='demo', budget=1))['project_id']
        self.p = self.studio.get(self.pid)
        self.source = self.p['sources'][0]
        self.task = self.p['tasks'][0]
        self.quote = self.source['body'][:55]
        alternate = self.source['body'][56:116]
        self.task['trials'] = [
            dict(name='Iris', output=dict(findings=[dict(claim='Sübut A', source_id=self.source['id'], quote=self.quote)]),
                 metrics=dict(cost=1500, duration_ms=100), error=None),
            dict(name='Orion', output=dict(findings=[dict(claim='Sübut B', source_id=self.source['id'], quote=alternate)]),
                 metrics=dict(cost=1800, duration_ms=200), error=None)]
        self.studio.save(self.p)

    def tearDown(self):
        self.studio.close()
        self.temp.cleanup()

    def test_versioned_gold_and_profile_comparison(self):
        self.studio.action('eval-add', dict(project_id=self.pid, task_id=self.task['id'],
            source_id=self.source['id'], quote=self.quote, note='Qiymət faktı'))
        self.assertEqual(self.p['eval_version'], 2)
        with self.assertRaises(ValueError):
            self.studio.action('eval-add', dict(project_id=self.pid, task_id=self.task['id'],
                source_id=self.source['id'], quote='Mənbədə olmayan dəlil', note='Yanlış'))
        self.p = self.studio.get(self.pid)
        self.studio.action('eval-run', dict(project_id=self.pid))
        run = self.p['eval_runs'][0]
        self.assertEqual([v['f1'] for v in run['variants']], [1.0, 0.0])
        self.assertEqual(run['comparison'][0]['difference'], -1.0)
        self.assertEqual(run['dataset_version'], 2)
        case_id = self.p['eval_cases'][0]['id']
        self.studio.action('eval-remove', dict(project_id=self.pid, case_id=case_id))
        self.assertEqual(self.p['eval_version'], 3)
        self.assertEqual(len(run['cases']), 1)
        self.studio.close()
        self.studio = Studio(self.path)
        self.assertEqual(self.studio.get(self.pid)['eval_runs'][0]['dataset_version'], 2)

    def test_empty_predictions_zero_and_no_division_error(self):
        case = dict(id='gold', source_id=self.source['id'], quote=self.quote)
        scored = score_trial([case], dict(output=dict(findings=[]), metrics={}))
        self.assertEqual(scored['precision'], 0)
        self.assertEqual(scored['recall'], 0)
        self.assertEqual(scored['f1'], 0)


if __name__ == '__main__':
    unittest.main()
