"""Human review (audits, shadow comparison), policy regression, word numbers and masking."""
import json
import unittest

from agency import guard, privacy
from tests.test_agency_engine import CASES, EngineCase, FakeModels

ADI = [c for c in CASES if c['kind'] == 'adi']


class WordNumberTest(unittest.TestCase):
    DOC = 'Məhsul 14 gün ərzində qaytarıla bilər. Çatdırılma 2 000 manatdan yuxarı sifarişlərdə pulsuzdur.'

    def test_spelled_out_number_matches_the_digits_in_the_quote(self):
        self.assertTrue(guard.check('Məhsulu on dörd gün ərzində qaytara bilərsiniz.',
                                    'Məhsul 14 gün ərzində qaytarıla bilər', self.DOC)['ok'])
        self.assertTrue(guard.check('İki min manatdan yuxarı sifarişlərdə çatdırılma pulsuzdur.',
                                    'Çatdırılma 2 000 manatdan yuxarı sifarişlərdə pulsuzdur', self.DOC)['ok'])

    def test_spelled_out_wrong_number_is_blocked(self):
        verdict = guard.check('Məhsulu otuz gün ərzində qaytara bilərsiniz.', 'Məhsul 14 gün ərzində qaytarıla bilər', self.DOC)
        self.assertFalse(verdict['ok'])
        self.assertEqual(verdict['unsupported'], ['otuz'])

    def test_article_and_pronoun_are_not_numbers(self):
        self.assertEqual(guard.numbers('Bir məhsulu ondan sonra qaytarmaq olar.'), [])
        self.assertEqual([r for _, r in guard.numbers('iyirmi bir gün, üçüncü dəfə, on faiz')],
                         [{21.0}, {3.0}, {10.0, 0.1}])

    def test_scale_after_digits_is_read_once(self):
        self.assertEqual([t for t, _ in guard.numbers('5 min manat')], ['5'])


class MaskTest(unittest.TestCase):
    def test_personal_data_is_masked_and_policy_figures_are_not(self):
        text, kinds = privacy.mask('Nömrəm 050 123 45 67, kart 4169 7388 1234 5678, ali@mail.az, FİN 5ABC12D. '
                                   '1200 manatlıq paltarı 20 gün əvvəl almışam.')
        for secret in ('050 123', '4169', 'ali@mail.az', '5ABC12D'):
            self.assertNotIn(secret, text)
        self.assertIn('1200 manatlıq paltarı 20 gün', text)
        self.assertEqual(sorted(kinds), ['FİN', 'e-poçt', 'kart', 'telefon'])

    def test_names_and_street_addresses_but_not_cities(self):
        text, kinds = privacy.mask('Adım Leyla Məmmədova. Nizami küçəsi 45, mənzil 12 ünvanına göndərin. Gəncəyə də göndərirsiniz?')
        self.assertNotIn('Leyla', text)
        self.assertNotIn('Nizami', text)
        self.assertIn('Adım [ad]', text)
        self.assertIn('Gəncəyə', text)
        self.assertEqual(sorted(kinds), ['ad', 'ünvan'])
        self.assertEqual(privacy.mask('Ünvanım: Xətai rayonu, Babək prospekti 20')[0], 'Ünvanım: [ünvan]')
        self.assertEqual(privacy.mask('Ünvan dəyişmək olar?'), ('Ünvan dəyişmək olar?', []))

    def test_international_phone_and_iban(self):
        text, kinds = privacy.mask('+994 55 555 55 55, IBAN AZ21NABZ00000000137010001944')
        self.assertEqual(text, '[telefon], IBAN [IBAN]')


class SeeingModels(FakeModels):
    def call(self, model, messages, schema, name, max_tokens=3000):
        self.seen = getattr(self, 'seen', []) + [messages[1]['content']]
        return super().call(model, messages, schema, name, max_tokens)


class MaskingInEngineTest(EngineCase):
    def test_provider_never_sees_the_phone_number(self):
        agency = self.build()
        agency.models = SeeingModels()
        self.run_until_idle()
        job_id = agency.submit_ticket('Salam, 050 123 45 67 nömrəsindən yazıram. Kartım 4169738812345678.')
        self.run_until_idle()
        sent = agency.models.seen[-1]
        self.assertNotIn('123 45 67', sent)
        self.assertNotIn('4169738812345678', sent)
        self.assertIn('[telefon]', sent)
        self.assertEqual(self.job(job_id)['pii'], ['kart', 'telefon'])


class ReviewTest(EngineCase):
    def staffed(self, **kwargs):
        agency = self.build(**kwargs)
        self.run_until_idle()
        return agency

    def test_sampled_replies_go_to_audit_and_a_wrong_one_counts_against_its_author(self):
        agency = self.staffed()
        agency.set_policy({'audit_rate': 1.0})
        jobs = [agency.submit_ticket(case['message']) for case in ADI[:3]]
        self.run_until_idle()
        reviews = agency.snapshot()['reviews']
        self.assertEqual({item['job_id'] for item in reviews['queue']}, set(jobs))
        self.assertEqual(reviews['summary']['audit']['pending'], 3)
        item = reviews['queue'][0]
        self.assertTrue(item['message'] and item['sentences'])
        author = next(w for w in agency.workers('soz') if w['name'] == item['worker'])

        agency.review(item['job_id'], 'wrong', note='Sitat düzgündür, amma bu müştəriyə aid deyil.')
        snap = agency.snapshot()
        stats = next(w for w in snap['services']['soz']['workers'] if w['id'] == author['id'])['stats']
        self.assertEqual(stats['blocked'], 1)
        self.assertEqual(stats['reasons'], {'audit': 1})
        audit = snap['reviews']['summary']['audit']
        self.assertEqual((audit['reviewed'], audit['wrong'], audit['pending']), (1, 1, 2))
        self.assertTrue(any('YANLIŞ' in j['message'] for j in snap['journal'] if j['kind'] == 'review'))
        with self.assertRaises(ValueError):
            agency.review(item['job_id'], 'ok')

    def test_newcomers_are_audited_twice_as_often(self):
        agency = self.staffed()
        agency.set_policy({'audit_rate': 0.3, 'peer_review': 0})

        class Fixed:
            def random(self):
                return 0.45  # above the base rate, below the doubled one
        agency.rng = Fixed()
        job_id = agency.submit_ticket(ADI[0]['message'])
        self.run_until_idle()
        author = next(a['worker_id'] for a in self.job(job_id)['attempts'] if a['outcome'] == 'passed')
        status = next(w['status'] for w in agency.workers('soz') if w['id'] == author)
        audited = bool(agency.snapshot()['reviews']['queue'])
        self.assertEqual(audited, status == 'probation')

    def test_no_audit_when_the_rate_is_zero(self):
        agency = self.staffed()
        agency.set_policy({'audit_rate': 0.0})
        agency.submit_ticket(ADI[0]['message'])
        self.run_until_idle()
        self.assertEqual(agency.snapshot()['reviews']['queue'], [])

    def test_shadow_drafts_are_compared_with_the_human_reply(self):
        agency = self.staffed()
        agency.set_mode('shadow')
        job_id = agency.submit_ticket(ADI[0]['message'])
        self.run_until_idle()
        item = agency.snapshot()['reviews']['queue'][0]
        self.assertEqual((item['job_id'], item['kind']), (job_id, 'shadow'))
        # The person answering the customer promised more than the policy allows.
        agency.review(job_id, 'ok', reply='Salam! Məhsulu 60 gün ərzində qaytara bilərsiniz.')
        shadow = agency.snapshot()['reviews']['summary']['shadow']
        self.assertEqual((shadow['reviewed'], shadow['wrong'], shadow['human_replies'], shadow['human_ok']), (1, 0, 1, 0))


class RegressionTest(EngineCase):
    def test_policy_change_rechecks_sent_replies_and_retests_the_team(self):
        agency = self.build()
        self.run_until_idle()
        agency.set_policy({'audit_rate': 1.0})
        returns = next(c for c in ADI if '14 gün' in c['cite'])
        agency.submit_ticket(returns['message'])
        self.run_until_idle()
        wrong = agency.snapshot()['reviews']['queue'][0]['job_id']
        agency.review(wrong, 'wrong')

        body = agency.policy_document()['body'].replace('14 gün', '10 gün')
        agency.update_policy(body)
        report = agency.snapshot()['regression']
        self.assertEqual(report['checked'], 1)
        self.assertEqual(report['broken'], 1)
        self.assertIn('tapılmadı', report['examples'][0]['problem'])  # the "14 gün" wording is gone
        self.assertEqual((report['queued'], report['audit_cases']), (9, 1))

        self.run_until_idle()
        report = agency.snapshot()['regression']
        self.assertEqual(report['finished'], report['total'])
        self.assertIsNotNone(report['score'])
        statuses = {j['status'] for j in agency.snapshot()['services']['soz']['jobs'] if j['source'] == 'reqressiya'}
        self.assertNotIn('göndərildi', statuses)  # regression answers never count as sent


class PeerReviewTest(EngineCase):
    def staffed(self):
        agency = self.build()
        self.run_until_idle()
        agency.set_policy({'audit_rate': 0.0})
        return agency

    def test_a_doubted_reply_is_held_and_the_author_is_not_blamed_yet(self):
        agency = self.staffed()
        agency.models.doubts.add(ADI[0]['message'])
        job_id = agency.submit_ticket(ADI[0]['message'])
        self.run_until_idle()
        job = self.job(job_id)
        self.assertEqual(job['status'], 'qaralama')
        author, peer = [a for a in job['attempts'] if a['outcome'] == 'passed'][0], \
            [a for a in job['attempts'] if a['outcome'] == 'peer'][0]
        self.assertNotEqual(author['worker_id'], peer['worker_id'])
        models = {w['id']: w['model'] for w in agency.workers('soz')}
        self.assertNotEqual(models[author['worker_id']], models[peer['worker_id']])  # another model, other blind spots
        item = agency.snapshot()['reviews']['queue'][0]
        self.assertEqual((item['kind'], item['peer']['applies']), ('flag', False))
        workers = {w['id']: w for w in agency.snapshot()['services']['soz']['workers']}
        self.assertEqual(workers[author['worker_id']]['stats']['blocked'], 0)
        self.assertEqual(workers[peer['worker_id']]['stats']['peer_reviews'], 1)

        agency.review(job_id, 'wrong')
        self.assertEqual(self.job(job_id)['status'], 'insana ötürüldü')
        workers = {w['id']: w for w in agency.snapshot()['services']['soz']['workers']}
        self.assertEqual(workers[author['worker_id']]['stats']['reasons'], {'audit': 1})
        flag = agency.snapshot()['reviews']['summary']['flag']
        self.assertEqual((flag['reviewed'], flag['wrong']), (1, 1))

    def test_a_wrong_doubt_releases_the_reply(self):
        agency = self.staffed()
        agency.models.doubts.add(ADI[1]['message'])
        job_id = agency.submit_ticket(ADI[1]['message'])
        self.run_until_idle()
        agency.review(job_id, 'ok')
        self.assertEqual(self.job(job_id)['status'], 'göndərildi')

    def test_approving_the_draft_settles_the_doubt(self):
        agency = self.staffed()
        agency.models.doubts.add(ADI[2]['message'])
        job_id = agency.submit_ticket(ADI[2]['message'])
        self.run_until_idle()
        agency.approve_draft(job_id)
        self.assertEqual(agency.snapshot()['reviews']['summary']['flag']['pending'], 0)

    def test_undoubted_reply_goes_out_and_review_cost_stays_out_of_cost_per_answer(self):
        agency = self.staffed()
        job_id = agency.submit_ticket(ADI[0]['message'])
        self.run_until_idle()
        self.assertEqual(self.job(job_id)['status'], 'göndərildi')
        reviewer = next(w for w in agency.snapshot()['services']['soz']['workers'] if w['stats']['peer_reviews'])
        self.assertEqual(reviewer['stats']['tasks'], 0)
        self.assertEqual(reviewer['stats']['peer_cost'], 100)

    def test_no_second_opinion_means_the_reply_is_audited(self):
        agency = self.staffed()
        original = agency.models.call

        def failing(model, messages, schema, name, max_tokens=3000):
            if name == 'peer_review':
                raise RuntimeError('provayder cavab vermədi')
            return original(model, messages, schema, name, max_tokens)
        agency.models.call = failing
        job_id = agency.submit_ticket(ADI[0]['message'])
        self.run_until_idle()
        self.assertEqual(self.job(job_id)['status'], 'göndərildi')
        self.assertEqual(agency.snapshot()['reviews']['queue'][0]['kind'], 'audit')

    def test_it_can_be_switched_off(self):
        agency = self.staffed()
        agency.set_policy({'peer_review': 0})
        agency.models.doubts.add(ADI[0]['message'])
        job_id = agency.submit_ticket(ADI[0]['message'])
        self.run_until_idle()
        self.assertEqual(self.job(job_id)['status'], 'göndərildi')
        self.assertFalse(any(a['outcome'] == 'peer' for a in self.job(job_id)['attempts']))


if __name__ == '__main__':
    unittest.main()
