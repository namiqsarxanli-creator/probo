import json
import unittest
from pathlib import Path

from agency import documents, guard


POLICY = (Path(__file__).resolve().parent.parent / 'agency' / 'samples' / 'bazarim_qaydalar.md').read_text(encoding='utf-8')
TENDER = ('Təkliflər 28.10.2026 saat 17:00-dək qəbul edilir.\n'
          'Təklif təminatı təklif qiymətinin 2%-i məbləğində bank zəmanəti şəklində təqdim edilir.\n'
          'Gecikməyə görə hər gün üçün müqavilə qiymətinin 0,1%-i həcmində cərimə tətbiq edilir.\n')
RETURN = 'Məhsul alındığı gündən etibarən 14 gün ərzində qaytarıla bilər'


class DocumentTest(unittest.TestCase):
    def test_headings_become_categories_and_lines_become_clauses(self):
        clauses = documents.split(POLICY)
        self.assertEqual(clauses[0]['category'], 'Qaytarma')
        self.assertEqual(clauses[0]['id'], 'B1')
        self.assertIn('Çatdırılma', documents.categories(clauses))
        for clause in clauses:
            self.assertEqual(POLICY[clause['start']:clause['end']], clause['text'])

    def test_version_changes_with_wording(self):
        self.assertNotEqual(documents.version_of(POLICY), documents.version_of(POLICY.replace('14', '15')))

    def test_empty_document_is_refused(self):
        with self.assertRaises(ValueError):
            documents.split('   \n# Başlıq\n')


class CheckTest(unittest.TestCase):
    def test_supported_statement_passes(self):
        verdict = guard.check('Məhsulu alındığı gündən 14 gün ərzində qaytara bilərsiniz.', RETURN, POLICY)
        self.assertTrue(verdict['ok'], verdict['problems'])
        self.assertEqual(POLICY[verdict['span'][0]:verdict['span'][1]], RETURN)

    def test_false_promise_with_a_real_quote_is_blocked(self):
        verdict = guard.check('Məhsulu 30 gün ərzində qaytara bilərsiniz.', RETURN, POLICY)
        self.assertFalse(verdict['ok'])
        self.assertIn('«30» sitatda yoxdur', verdict['problems'][0])
        self.assertIn('14', verdict['problems'][0])

    def test_invented_quote_is_blocked(self):
        verdict = guard.check('30 gün ərzində qaytara bilərsiniz.',
                              'Məhsul alındığı gündən etibarən 30 gün ərzində qaytarıla bilər', POLICY)
        self.assertFalse(verdict['ok'])
        self.assertIn('tapılmadı', verdict['problems'][0])

    def test_short_quote_is_not_evidence(self):
        verdict = guard.check('14 gün.', '14 gün', POLICY)
        self.assertFalse(verdict['ok'])
        self.assertIn('qısadır', verdict['problems'][0])

    def test_prohibition_cannot_become_permission(self):
        quote = 'Endirimli məhsullar qaytarılmır'
        blocked = guard.check('Endirimli məhsulları qaytara bilərsiniz.', quote, POLICY)
        self.assertFalse(blocked['ok'])
        self.assertIn('qadağa', blocked['problems'][0])
        self.assertTrue(guard.check('Endirimli məhsullar qaytarılmır.', quote, POLICY)['ok'])

    def test_attributive_negation_is_not_a_prohibition(self):
        quote = 'Ölçüsü uyğun gəlməyən geyim 14 gün ərzində eyni modelin başqa ölçüsü ilə pulsuz dəyişdirilə bilər'
        verdict = guard.check('Geyimi 14 gün ərzində başqa ölçü ilə pulsuz dəyişə bilərsiniz.', quote, POLICY)
        self.assertTrue(verdict['ok'], verdict['problems'])

    def test_predicate_negation_is_a_prohibition(self):
        quote = 'Alt paltarı, kosmetika və gigiyena məhsulları qaytarılmayan məhsullardır'
        self.assertFalse(guard.check('Kosmetikanı qaytara bilərsiniz.', quote, POLICY)['ok'])

    def test_short_verb_roots_still_carry_negation(self):
        quote = 'Zəmanət mexaniki zədələnmə və maye təsiri hallarını əhatə etmir'
        self.assertFalse(guard.check('Zəmanət maye təsirini əhatə edir.', quote, POLICY)['ok'])

    def test_inferred_negative_is_allowed_but_noted(self):
        verdict = guard.check('15-ci gün qaytarma mümkün deyil.', RETURN, POLICY)
        self.assertFalse(verdict['ok'])  # 15 is not in the quote: still conservative
        verdict = guard.check('Bu müddətdən sonra məhsul qaytarılmır.', RETURN, POLICY)
        self.assertTrue(verdict['ok'])
        self.assertTrue(verdict['notes'])

    def test_typography_and_case_are_tolerated(self):
        for quote in ('«XARİCƏ çatdırılma» həyata keçirilmir', 'XARİCƏ ÇATDIRILMA HƏYATA KEÇİRİLMİR'):
            verdict = guard.check('Xaricə çatdırılma yoxdur.', quote, POLICY)
            self.assertTrue(verdict['ok'], verdict['problems'])
        reworded = guard.check('Xaricə çatdırılma yoxdur.', 'Xaricə göndəriş həyata keçirilmir', POLICY)
        self.assertFalse(reworded['ok'])

    def test_ranges_and_times(self):
        quote = 'Müştəri xidməti həftə içi saat 09:00-dan 18:00-dək işləyir'
        self.assertTrue(guard.check('Biz həftə içi 09:00-dan 18:00-dək işləyirik.', quote, POLICY)['ok'])
        verdict = guard.check('Biz həftə içi 09:00-dan 20:00-dək işləyirik.', quote, POLICY)
        self.assertFalse(verdict['ok'])
        self.assertIn('20:00', ' '.join(verdict['problems']))


class TenderFieldTest(unittest.TestCase):
    def test_deadline_must_match_the_document(self):
        quote = 'Təkliflər 28.10.2026 saat 17:00-dək qəbul edilir'
        self.assertTrue(guard.check('28.10.2026, saat 17:00', quote, TENDER)['ok'])
        self.assertTrue(guard.check('28 oktyabr 2026, 17:00', quote, TENDER)['ok'])
        wrong_day = guard.check('29.10.2026, saat 17:00', quote, TENDER)
        self.assertFalse(wrong_day['ok'])
        self.assertIn('2026-10-29', wrong_day['problems'][0])
        self.assertFalse(guard.check('28.10.2026, saat 18:00', quote, TENDER)['ok'])

    def test_percent_written_either_way(self):
        quote = 'Təklif təminatı təklif qiymətinin 2%-i məbləğində bank zəmanəti şəklində təqdim edilir'
        self.assertTrue(guard.check('Təminat: 2 faiz bank zəmanəti', quote, TENDER)['ok'])
        self.assertFalse(guard.check('Təminat: 5% bank zəmanəti', quote, TENDER)['ok'])

    def test_decimal_comma(self):
        quote = 'Gecikməyə görə hər gün üçün müqavilə qiymətinin 0,1%-i həcmində cərimə tətbiq edilir'
        self.assertTrue(guard.check('Gündəlik cərimə 0.1%', quote, TENDER)['ok'])
        self.assertFalse(guard.check('Gündəlik cərimə 1%', quote, TENDER)['ok'])


class FreeTextTest(unittest.TestCase):
    def test_human_false_promise_is_caught_without_a_citation(self):
        result = guard.check_free_text('Salam! Məhsulu 30 gün ərzində qaytara bilərsiniz. Təşəkkür edirik.', POLICY)
        self.assertFalse(result['ok'])
        verdicts = result['sentences']
        self.assertTrue(verdicts[0]['courtesy'])
        self.assertFalse(verdicts[1]['ok'])
        self.assertIn('«30»', verdicts[1]['problems'][0])
        self.assertIn('14 gün', POLICY[verdicts[1]['span'][0]:verdict_end(verdicts[1])])
        self.assertTrue(verdicts[2]['courtesy'])

    def test_honest_reply_passes(self):
        result = guard.check_free_text('Salam! Məhsulu 14 gün ərzində qaytara bilərsiniz.', POLICY)
        self.assertTrue(result['ok'], result)

    def test_sentence_with_no_matching_rule_is_blocked(self):
        result = guard.check_free_text('Bizdə iPhone 15 satışdadır.', POLICY)
        self.assertFalse(result['ok'])
        self.assertIn('uyğun bənd tapılmadı', result['sentences'][0]['problems'][0])


def verdict_end(verdict):
    return verdict['span'][1]


if __name__ == '__main__':
    unittest.main()


class LiveRunRegressionTest(unittest.TestCase):
    """Cases taken from the first live run against Groq on 2026-10-06."""

    def test_front_vowel_negation_is_recognised(self):
        # "bilməz" was missed: the pattern had e where Azerbaijani writes ə.
        verdict = guard.check('Endirimli məhsul olduğu üçün qaytarıla bilməz.', 'Endirimli məhsullar qaytarılmır', POLICY)
        self.assertTrue(verdict['ok'], verdict['problems'])
        for text in ('qaytarıla bilməz', 'edilməməlidir', 'verilməz'):
            self.assertTrue(guard.is_negative(text), text)

    def test_echoed_customer_figure_is_told_apart_from_an_invented_one(self):
        from agency import support
        reply = json.dumps({'situation': '', 'decision': 'answer', 'escalation_reason': '', 'sentences': [
            {'text': '20 gün sonra qaytarmaq mümkün deyil.', 'quote': RETURN}]}, ensure_ascii=False)
        echoed = support.evaluate(reply, POLICY, 'Paltarı 20 gün əvvəl almışam, qaytara bilərəm?')
        self.assertEqual(echoed['outcome'], 'blocked')
        self.assertEqual(echoed['categories'], ['echo'])
        invented = support.evaluate(reply.replace('20 gün', '30 gün'), POLICY, 'Paltarı 20 gün əvvəl almışam')
        self.assertEqual(invented['categories'], ['invented'])

    def test_reply_that_allows_and_forbids_the_same_thing_is_stopped(self):
        from agency import support
        reply = json.dumps({'situation': '', 'decision': 'answer', 'escalation_reason': '', 'sentences': [
            {'text': 'Şalvar 14 gün ərzində qaytarıla bilər.', 'quote': RETURN},
            {'text': 'Endirimli məhsul olduğu üçün qaytarıla bilməz.', 'quote': 'Endirimli məhsullar qaytarılmır'}]},
            ensure_ascii=False)
        result = support.evaluate(reply, POLICY, 'Endirimdən aldığım şalvarı qaytara bilərəm?')
        self.assertEqual(result['outcome'], 'blocked')
        self.assertIn('contradiction', result['categories'])
        self.assertIn('ziddir', result['problems'][0])

    def test_a_rule_and_its_conditional_edge_are_not_a_contradiction(self):
        from agency import support
        reply = json.dumps({'situation': 'Müştəri 20 gün sonra qaytarmaq istəyir', 'decision': 'answer',
                            'escalation_reason': '', 'sentences': [
            {'text': 'Qaydaya görə məhsul alındığı gündən etibarən 14 gün ərzində qaytarıla bilər.', 'quote': RETURN},
            {'text': 'Bu müddət keçibsə, qaytarma mümkün deyil.', 'quote': RETURN}]}, ensure_ascii=False)
        result = support.evaluate(reply, POLICY, 'Paltarı 20 gün əvvəl almışam, qaytara bilərəm?')
        self.assertEqual(result['outcome'], 'passed', result['problems'])
        self.assertNotIn('20', result['message'])  # the customer's figure stays in the internal note


class SecondLiveRunTest(unittest.TestCase):
    """Correct answers the guard wrongly blocked in the 40-ticket live stress test."""

    def test_different_predicates_are_not_a_contradiction(self):
        self.assertEqual(guard.contradictions([
            'Müştəri xidməti həftə içi saat 09:00-dan 18:00-dək işləyir.',
            'Şənbə günü bu saatlarda xidmət mövcud deyil.']), [])

    def test_same_predicate_with_opposite_polarity_still_is(self):
        self.assertTrue(guard.contradictions([
            'Şalvar 14 gün ərzində qaytarıla bilər.', 'Endirimli məhsul olduğu üçün qaytarıla bilməz.']))

    def test_future_negative_is_negative(self):
        verdict = guard.check('Bu səbəbdən şalvarı geri qaytara bilməyəcəksiniz.', 'Endirimli məhsullar qaytarılmır', POLICY)
        self.assertTrue(verdict['ok'], verdict['problems'])

    def test_prohibiting_participle_with_a_distant_copula(self):
        quote = 'Alt paltarı, kosmetika və gigiyena məhsulları qaytarılmayan məhsullardır'
        verdict = guard.check('Kosmetika məhsulları qaytarılmayan məhsullar siyahısına daxildir.', quote, POLICY)
        self.assertTrue(verdict['ok'], verdict['problems'])
        # ...while the attributive use stays positive.
        self.assertFalse(guard.is_negative('Ölçüsü uyğun gəlməyən geyim 14 gün ərzində dəyişdirilə bilər'))
