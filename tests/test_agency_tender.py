import json
import unittest
from pathlib import Path

from agency import tender

DOC = (Path(__file__).resolve().parent.parent / 'agency' / 'samples' / 'tender_komputer.md').read_text(encoding='utf-8')
EXPERIENCE = 'İddiaçı son 3 il ərzində ən azı 2 oxşar müqaviləni uğurla icra etməlidir'
TURNOVER = 'İddiaçının son ilin illik dövriyyəsi 500 000 AZN-dən az olmamalıdır'


def answer(*fields):
    return json.dumps({'fields': [dict(key=k, found=True, value=v, quote=q) for k, v, q in fields]}, ensure_ascii=False)


class MultiFactTest(unittest.TestCase):
    def test_separate_requirements_from_different_sentences_are_all_kept(self):
        result = tender.evaluate(answer(('tecrube', '3 il, 2 müqavilə', EXPERIENCE),
                                        ('tecrube', 'dövriyyə 500 000 AZN', TURNOVER)), DOC)
        self.assertEqual(result['outcome'], 'passed')
        row = next(r for r in tender.merge([result]) if r['key'] == 'tecrube')
        self.assertEqual(row['status'], 'verified')
        self.assertEqual(len(row['values']), 2)

    def test_two_readings_of_the_same_sentence_are_a_conflict(self):
        quote = 'Təkliflər 28.10.2026 saat 17:00-dək elektron satınalma portalı vasitəsilə qəbul edilir'
        first = tender.evaluate(answer(('son_tarix', '28.10.2026 17:00', quote)), DOC)
        second = tender.evaluate(answer(('son_tarix', '28.10.2026', quote)), DOC)
        row = next(r for r in tender.merge([first, second]) if r['key'] == 'son_tarix')
        self.assertEqual(row['status'], 'conflict')
        same = tender.evaluate(answer(('son_tarix', '28 oktyabr 2026, saat 17:00', quote)), DOC)
        row = next(r for r in tender.merge([first, same]) if r['key'] == 'son_tarix')
        self.assertEqual(row['status'], 'verified')  # same facts, different wording
        self.assertEqual(len(row['values']), 1)

    def test_no_more_than_three_entries_per_field(self):
        many = [('tecrube', '3 il', EXPERIENCE)] * 5
        result = tender.evaluate(answer(*many), DOC)
        self.assertEqual(len([f for f in result['fields'] if f['key'] == 'tecrube']), 3)

    def test_grade_gives_partial_credit_for_partial_requirements(self):
        gold = {'tecrube': ['son 3 ildə ən azı 2 oxşar müqavilə', 'illik dövriyyə 500 000 AZN']}
        one = tender.evaluate(answer(('tecrube', 'son 3 ildə 2 oxşar müqavilə', EXPERIENCE)), DOC)
        both = tender.evaluate(answer(('tecrube', 'son 3 ildə 2 oxşar müqavilə', EXPERIENCE),
                                      ('tecrube', 'illik dövriyyə 500 000 AZN', TURNOVER)), DOC)
        per_field = 1 / len(tender.KEYS)
        others = sum(1 for k in tender.KEYS if k != 'tecrube') * per_field  # absent gold keys count as correct-if-empty
        self.assertAlmostEqual(tender.grade(one, gold, DOC), round(others + per_field / 2, 4))
        self.assertAlmostEqual(tender.grade(both, gold, DOC), round(others + per_field, 4))

    def test_an_invented_entry_voids_the_field(self):
        gold = {'tecrube': ['son 3 ildə ən azı 2 oxşar müqavilə']}
        mixed = tender.evaluate(answer(('tecrube', 'son 3 ildə 2 oxşar müqavilə', EXPERIENCE),
                                       ('tecrube', 'dövriyyə 900 000 AZN', TURNOVER)), DOC)
        self.assertEqual(mixed['outcome'], 'blocked')
        others = sum(1 for k in tender.KEYS if k != 'tecrube') / len(tender.KEYS)
        self.assertAlmostEqual(tender.grade(mixed, gold, DOC), round(others, 4))


class DeadlineTest(unittest.TestCase):
    def test_the_nearest_of_several_deadlines_drives_the_flag(self):
        from datetime import date
        card = [dict(key=key, label=label, critical=critical, status='missing', values=[])
                for key, label, critical in tender.FIELDS]
        card[tender.KEYS.index('son_tarix')].update(status='verified', values=[
            dict(value='Tender təklifi: 16.05.2022 18:00'), dict(value='Digər sənədlər: 05.05.2022 15:00')])
        text = tender.flags(card, today=date(2022, 5, 1))[0]['text']
        self.assertIn('2 ayrı son tarix', text)
        self.assertIn('4 gün qalıb', text)
        self.assertIn('Digər sənədlər', text)


if __name__ == '__main__':
    unittest.main()


class MatchTest(unittest.TestCase):
    def test_terse_numeric_reading_counts_and_wrong_figures_do_not(self):
        self.assertTrue(tender._matches('3 il, 2 müqavilə', 'son 3 ildə ən azı 2 oxşar müqavilə'))
        self.assertTrue(tender._matches('500 000 AZN', 'illik dövriyyə 500 000 AZN'))
        self.assertFalse(tender._matches('5 il, 2 müqavilə', 'son 3 ildə ən azı 2 oxşar müqavilə'))
        self.assertFalse(tender._matches('keyfiyyət', 'ən aşağı qiymət'))
