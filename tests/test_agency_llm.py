import unittest

from app.provider import InvalidGeneration
from agency import tender
from agency.llm import Models


class WrongShapeProvider:
    """Mimics Groq answering 400 json_validate_failed after generating output."""

    def config(self):
        return dict(AI_BASE_URL='https://api.example.test/v1', AI_API_KEY='k')

    def status(self):
        return dict(ready=True)

    def execute(self, call):
        raise InvalidGeneration('{"fields": {"items": []}}')


class InvalidGenerationTest(unittest.TestCase):
    def test_wrong_shape_is_the_workers_mistake_and_is_charged(self):
        result = Models(WrongShapeProvider()).call('openai/gpt-oss-20b', [{'role': 'user', 'content': 'x'}],
                                                    tender.SCHEMA, 'tender_card')
        self.assertTrue(result['invalid_generation'])
        self.assertTrue(result['estimated'])
        self.assertGreater(result['cost'], 0)
        verdict = tender.evaluate(result['content'], 'Təkliflər 28.10.2026 saat 17:00-dək qəbul edilir.')
        self.assertEqual(verdict['outcome'], 'blocked')
        self.assertIn('format', verdict['problems'][0])


if __name__ == '__main__':
    unittest.main()
