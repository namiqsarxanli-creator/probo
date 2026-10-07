import json
import re
import tempfile
import unittest
from pathlib import Path

from app.provider import RateLimitError
from agency import guard, tender
from agency.engine import Agency, SAMPLES

CASES = json.loads((SAMPLES / 'bazarim_muracietler.json').read_text(encoding='utf-8'))
BY_MESSAGE = {c['message']: c for c in CASES}
EXAM = {c['message'] for kind in ('adi', 'tələ', 'kənar', 'hücum') for c in [x for x in CASES if x['kind'] == kind][:2]}
GOLD = json.loads((SAMPLES / 'tender_cavablar.json').read_text(encoding='utf-8'))


class FakeModels:
    """Deterministic stand-in for the provider. Behaviour per (model, persona)."""

    def __init__(self, behaviour=None, default='honest', tokens=10):
        self.behaviour, self.default, self.calls, self.tokens = behaviour or {}, default, [], tokens
        self.current = None
        self.doubts = set()  # customer messages a colleague will say the cited rule does not fit

    def ready(self):
        return True

    def available(self):
        return {'openai/gpt-oss-20b', 'openai/gpt-oss-120b', 'qwen/qwen3.8-27b'}

    def call(self, model, messages, schema, name, max_tokens=3000):
        persona = 'komekci' if 'köməksevər' in messages[0]['content'] else 'diqqetli'
        style = self.behaviour.get((model, persona), self.default)
        if 'YENİ GÖSTƏRİŞ' in messages[0]['content']:
            style = 'liar'  # instructions rewritten to promise discounts
        self.calls.append((model, persona, name))
        if style == 'error':
            raise RuntimeError('provayder cavab vermədi')
        if style == 'ratelimit':
            raise RateLimitError(7)
        payload = json.loads(messages[1]['content'])
        if name == 'peer_review':
            fits = payload['müştəri_mesajı'] not in self.doubts
            content = dict(applies=fits, reason='' if fits else 'Qayda başqa vəziyyətə aiddir.')
        else:
            content = (self.support(payload, style) if name == 'support_reply' else self.tender(payload, style))
        return dict(content=json.dumps(content, ensure_ascii=False), cost=100, usage=dict(total_tokens=self.tokens),
                    duration_ms=5, schema_enforced=True)

    def support(self, payload, style):
        message = payload['müştəri_mesajı']
        case = BY_MESSAGE.get(message)
        lying = style == 'liar' and message not in EXAM
        if not case or (case['expect'] == 'escalate' and not lying):
            return dict(decision='escalate', sentences=[], escalation_reason='Qaydalarda cavab yoxdur.')
        if lying:
            if case['expect'] == 'escalate':
                return dict(decision='answer', escalation_reason='', sentences=[dict(
                    text='Bu xidmət pulsuzdur.', quote='Bu xidmət hər zaman pulsuz təqdim olunur')])
            text = re.sub(r'\d+', '30', case['cite']) if re.search(r'\d', case['cite']) else 'Bəli, bu mümkündür.'
            return dict(decision='answer', escalation_reason='', sentences=[dict(text=text, quote=case['cite'])])
        return dict(decision='answer', escalation_reason='', sentences=[dict(text=case['cite'] + '.', quote=case['cite'])])

    def tender(self, payload, style):
        document = payload['tender']
        gold = next(g for name, g in GOLD.items() if (SAMPLES / name).read_text(encoding='utf-8') == document)
        lines = [line.strip() for line in document.splitlines() if line.strip() and not line.startswith('#')]
        fields = []
        for key in tender.KEYS:
            expected = gold.get(key)
            if expected is None:
                fields.append(dict(key=key, found=False, value='', quote=''))
                continue
            for item in (expected if isinstance(expected, list) else [expected]):
                value = item.replace('2026', '2027') if style == 'liar' and guard.dates(item) else item
                supported = [l.rstrip('.') for l in lines if guard.check(item, l.rstrip('.'), document)['ok']]
                # The line sharing the most words with the expected value is the one an analyst would quote.
                line = max(supported, key=lambda l: len(guard._stems(l) & guard._stems(item)), default=lines[0])
                fields.append(dict(key=key, found=True, value=value, quote=line))
        return dict(fields=fields)


class EngineCase(unittest.TestCase):
    def build(self, **kwargs):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.models = FakeModels(**kwargs)
        self.agency = Agency(Path(self.folder.name) / 'agency.sqlite3', self.models)
        self.addCleanup(self.agency.close)
        return self.agency

    def run_until_idle(self, limit=400):
        for _ in range(limit):
            if not self.agency.step():
                return
        self.fail('Agentlik dayanmadı')

    def journal(self, kind):
        return [row for row in self.agency.snapshot()['journal'] if row['kind'] == kind]

    def job(self, job_id):
        return next(j for s in self.agency.snapshot()['services'].values() for j in s['jobs'] if j['id'] == job_id)


class StaffingTest(EngineCase):
    def test_starts_with_documents_and_no_staff(self):
        snap = self.build().snapshot()
        self.assertIn('14 gün', snap['policy_document']['body'])
        self.assertEqual(len(snap['tenders']), 2)
        self.assertEqual(snap['services']['soz']['workers'], [])

    def test_company_hires_its_own_staff_through_exams(self):
        self.build()
        self.run_until_idle()
        soz = self.agency.snapshot()['services']['soz']
        self.assertEqual(len([w for w in soz['workers'] if w['status'] == 'probation']), 3)
        first = soz['workers'][0]
        self.assertEqual((first['model'], first['persona']), ('openai/gpt-oss-20b', 'diqqetli'))  # cheapest first
        self.assertEqual(first['exam_score'], 1.0)
        self.assertEqual(len(self.journal('hire')), 5)  # 3 support + 2 tender
        self.assertGreater(soz['kpi']['exam_cost'], 0)

    def test_candidate_who_fails_the_exam_is_not_hired(self):
        self.build(behaviour={('openai/gpt-oss-20b', 'diqqetli'): 'error'})
        self.agency.step()  # exam crashes: candidate removed, no verdict
        self.assertEqual(self.agency.workers('soz'), [])
        self.assertFalse(self.agency.step())  # and the agency pauses instead of retrying at once
        self.assertIn('fasilə', self.journal('error')[0]['message'])
        self.agency.pause_until = 0
        liar_exam = FakeModels(default='honest')
        liar_exam.support = lambda payload, style: dict(decision='answer', escalation_reason='', sentences=[
            dict(text='30 gün.', quote='Məhsul alındığı gündən etibarən 14 gün ərzində qaytarıla bilər')])
        self.agency.models = liar_exam
        self.agency.step()
        rejected = [w for w in self.agency.workers('soz') if w['status'] == 'rejected']
        self.assertEqual(len(rejected), 1)
        self.assertIn('işə qəbul edilmədi', self.journal('reject')[0]['message'])


class SupportFlowTest(EngineCase):
    def setUp(self):
        self.build()
        self.run_until_idle()

    def test_honest_reply_is_assembled_from_verified_sentences(self):
        job = self.agency.submit_ticket('Bakı daxilində çatdırılma neçəyədir?')
        self.run_until_idle()
        done = self.job(job)
        self.assertEqual(done['status'], 'göndərildi')
        self.assertTrue(done['result']['message'].startswith('Salam!'))
        self.assertIn('5 AZN', done['result']['message'])

    def test_question_outside_the_rules_goes_to_a_person(self):
        job = self.agency.submit_ticket('Mağazanız harada yerləşir?')
        self.run_until_idle()
        self.assertEqual(self.job(job)['status'], 'insana ötürüldü')

    def test_draft_mode_holds_replies_for_approval(self):
        self.agency.set_mode('draft')
        job = self.agency.submit_ticket('Bakı daxilində çatdırılma neçəyədir?')
        self.run_until_idle()
        self.assertEqual(self.job(job)['status'], 'qaralama')

    def test_human_false_promise_is_blocked_too(self):
        verdict = self.agency.human_reply('Salam! Məhsulu 30 gün ərzində qaytara bilərsiniz.')
        self.assertFalse(verdict['ok'])
        self.assertIn('bloklandı', self.journal('human')[0]['message'])

    def test_policy_change_creates_a_new_version(self):
        before = self.agency.policy_document()
        after = self.agency.update_policy(before['body'].replace('14 gün ərzində qaytarıla', '21 gün ərzində qaytarıla'))
        self.assertNotEqual(before['version'], after['version'])
        self.assertEqual(self.agency.policy_document()['id'], after['id'])
        with self.assertRaises(ValueError):
            self.agency.update_policy(after['body'])


class FiringTest(EngineCase):
    def test_worker_who_passes_the_exam_but_lies_at_work_is_fired_and_replaced(self):
        self.build(behaviour={('openai/gpt-oss-20b', 'komekci'): 'liar'})
        self.run_until_idle()
        liar = next(w for w in self.agency.workers('soz') if w['persona'] == 'komekci')
        self.assertEqual(liar['status'], 'probation')  # the exam did not catch it
        self.agency.stress(60, seed=3)
        self.run_until_idle(limit=1000)
        liar = next(w for w in self.agency.workers('soz') if w['id'] == liar['id'])
        self.assertEqual(liar['status'], 'fired')
        fired = self.journal('fire')[0]['message']
        self.assertIn(liar['name'], fired)
        self.assertIn('95% interval', fired)
        self.assertEqual(len(self.agency.staffed('soz')), 3)  # the seat was refilled
        blocked = [j for j in self.agency.snapshot()['services']['soz']['jobs']
                   if any(a['outcome'] == 'blocked' for a in j['attempts'])]
        self.assertTrue(blocked)
        # A blocked draft never reached the customer: another worker or a person answered.
        self.assertTrue(all(j['status'] in ('göndərildi', 'insana ötürüldü') for j in blocked))


class TenderFlowTest(EngineCase):
    def test_two_analysts_build_a_verified_card(self):
        self.build()
        self.run_until_idle()
        doc = next(t for t in self.agency.snapshot()['tenders'] if t['sample'] == 'tender_komputer.md')
        job = self.agency.analyze_tender(doc['id'])
        self.run_until_idle()
        done = self.job(job)
        self.assertEqual(done['status'], 'hazırdır')
        self.assertEqual(len(done['result']['analysts']), 2)
        rows = {row['key']: row for row in done['result']['card']}
        self.assertEqual(rows['son_tarix']['status'], 'verified')
        self.assertIn('28.10.2026', rows['son_tarix']['values'][0]['value'])
        self.assertTrue(done['result']['flags'])

    def test_invented_dates_never_reach_the_card(self):
        self.build(default='liar')
        # Liars cannot pass the tender exam, so staff the seats by hand.
        with self.agency.lock, self.agency.db:
            for index, model in enumerate(('openai/gpt-oss-20b', 'openai/gpt-oss-120b')):
                self.agency.db.execute("INSERT INTO workers VALUES (?,?,?,?,?,?,?,?,?,?)",
                                       (f'w{index}', 'tender', f'W{index}', model, 'diqqetli', 'active', '2026', None, 1.0, 0))
                self.agency.db.execute("INSERT INTO workers VALUES (?,?,?,?,?,?,?,?,?,?)",
                                       (f's{index}', 'soz', f'S{index}', model, 'diqqetli', 'active', '2026', None, 1.0, 0))
            self.agency.db.execute("INSERT INTO workers VALUES (?,?,?,?,?,?,?,?,?,?)",
                                   ('s9', 'soz', 'S9', 'qwen/qwen3.8-27b', 'diqqetli', 'active', '2026', None, 1.0, 0))
        doc = self.agency.snapshot()['tenders'][0]
        job = self.agency.analyze_tender(doc['id'])
        self.run_until_idle()
        rows = {row['key']: row for row in self.job(job)['result']['card']}
        self.assertEqual(rows['son_tarix']['status'], 'missing')
        self.assertTrue(any('Son tarix təsdiqlənmədi' in f['text'] for f in self.job(job)['result']['flags']))


class PacingTest(EngineCase):
    def test_agency_waits_instead_of_hitting_the_token_limit(self):
        self.build(tokens=3000)
        waits = []
        self.agency.sleep = waits.append
        self.agency.step()  # one exam: 8 calls of 3,000 tokens against a 7,000 per-minute budget
        self.assertTrue(waits)
        self.assertTrue(all(0 < w <= 65 for w in waits))

    def test_rate_limit_backs_off_harder_each_time(self):
        self.build()
        first = self.agency._cool('openai/gpt-oss-20b')
        second = self.agency._cool('openai/gpt-oss-20b')
        self.assertEqual((first, second), (15, 30))
        self.assertEqual(self.agency._cool('openai/gpt-oss-120b', retry_after=42), 42)


class ResilienceTest(EngineCase):
    def test_rate_limit_cools_the_model_and_keeps_the_job(self):
        self.build()
        self.run_until_idle()
        self.agency.models = FakeModels(default='ratelimit')
        job = self.agency.submit_ticket('Bakı daxilində çatdırılma neçəyədir?')
        self.assertFalse(self.agency.step())
        self.assertEqual(self.job(job)['status'], 'növbədə')
        self.assertTrue(self.agency.cooldown)
        self.assertIn('Provayder limiti', self.journal('error')[0]['message'])
        self.assertFalse(self.agency.step())  # the cooled model is not called again straight away

    def test_budget_cuts_one_seat_early_then_stops_new_calls(self):
        self.build()
        self.agency.set_policy(dict(monthly_budget_usd=0.01))  # 10,000 micro-dollars = 100 fake calls
        self.run_until_idle()
        self.agency.stress(120, seed=1)
        self.run_until_idle(limit=1000)
        cuts = self.journal('layoff')
        self.assertEqual(sorted(c['service'] for c in cuts), ['soz', 'tender'])  # one per service per month
        for cut in cuts:
            share = int(re.search(r'büdcənin (\d+)%', cut['message']).group(1))
            self.assertTrue(80 <= share < 100, cut['message'])
        self.assertTrue(self.journal('budget'))
        waiting = self.agency.snapshot()['services']['soz']['counts'].get('növbədə', 0)
        self.assertGreater(waiting, 0)
        self.assertFalse(self.agency.step())

    def test_restart_returns_interrupted_jobs_to_the_queue(self):
        self.build()
        self.run_until_idle()
        job = self.agency.submit_ticket('Bakı daxilində çatdırılma neçəyədir?')
        with self.agency.lock, self.agency.db:
            self.agency.db.execute("UPDATE jobs SET status='işlənir' WHERE id=?", (job,))
        path = Path(self.folder.name) / 'agency.sqlite3'
        self.agency.close()
        self.agency = Agency(path, self.models)
        self.addCleanup(self.agency.close)
        self.assertEqual(self.job(job)['status'], 'növbədə')

    def test_bad_settings_are_refused(self):
        self.build()
        for bad in (dict(fire_rate=5), dict(unknown=1), dict(monthly_budget_usd=0)):
            with self.assertRaises(ValueError):
                self.agency.set_policy(bad)
        with self.assertRaises(ValueError):
            self.agency.set_mode('chaos')


if __name__ == '__main__':
    unittest.main()


class ReevaluationTest(EngineCase):
    def test_guard_fix_rechecks_old_verdicts_and_lifts_an_unfair_warning(self):
        self.build()
        self.run_until_idle()
        worker = self.agency.staffed('soz')[0]
        policy = self.agency.policy_document()
        quote = 'Endirimli məhsullar qaytarılmır'
        good = json.dumps({'situation': '', 'decision': 'answer', 'escalation_reason': '',
                           'sentences': [{'text': 'Bu səbəbdən qaytara bilməyəcəksiniz.', 'quote': quote}]}, ensure_ascii=False)
        with self.agency.lock, self.agency.db:
            for _ in range(8):
                job = self.agency._enqueue('soz', 'stress', 'Endirimli şalvarı qaytara bilərəm?',
                                           dict(message='Endirimli şalvarı qaytara bilərəm?'), document=policy)
                # Stored as the old, buggy guard judged it.
                self.agency.db.execute(
                    "INSERT INTO attempts VALUES (?,?,?,?,0,?,?,?,?,1,?,?)",
                    (f'a{_}', job, worker['id'], 'soz', '2026-10-06T00:00:00+00:00', 'blocked', 100, 5, good,
                     json.dumps({'outcome': 'blocked', 'categories': ['polarity'], 'problems': ['köhnə qərar']})))
            self.agency.db.execute("UPDATE workers SET status='warned' WHERE id=?", (worker['id'],))
            self.agency.db.execute("DELETE FROM settings WHERE key='guard_version'")
        changed = self.agency.reevaluate()
        self.assertEqual(changed, 8)
        # The warning is lifted; with a clean, cheapest record the worker may also be promoted.
        self.assertIn(self.agency._one('SELECT status FROM workers WHERE id=?', (worker['id'],))['status'], ('active', 'senior'))
        self.assertTrue(any(worker['name'] in row['message'] for row in self.journal('restore')))
        audit = self.journal('audit')[0]['message']
        self.assertIn('8 qərar dəyişdi', audit)
        self.assertIn('blocked → passed', audit)


class ExamRejudgingTest(EngineCase):
    def test_candidate_rejected_by_a_guard_error_moves_to_reserve_and_fills_the_next_vacancy(self):
        self.build()
        self.run_until_idle()
        honest = FakeModels()
        items = self.agency.exam_items('soz')
        with self.agency.lock, self.agency.db:
            self.agency.db.execute("INSERT INTO workers VALUES (?,?,?,?,?,?,?,?,?,?)",
                                   ('old', 'soz', 'Orxan', 'openai/gpt-oss-120b', 'komekci', 'rejected', '2026', '2026', 0.5, 0))
            for index, item in enumerate(items):
                output = json.dumps(dict(honest.support({'müştəri_mesajı': item['text']}, 'honest'), situation=''),
                                    ensure_ascii=False)
                # Stored the way the first exams were: no case attached, judged by the old guard.
                self.agency.db.execute("INSERT INTO attempts VALUES (?,?,?,?,1,?,?,?,?,1,?,?)",
                                       (f'x{index}', None, 'old', 'soz', f'2026-10-06T00:00:{index:02d}+00:00', 'blocked',
                                        100, 5, output, json.dumps({'outcome': 'blocked', 'score': 0})))
            self.agency.db.execute("DELETE FROM settings WHERE key='guard_version'")
        self.agency.reevaluate()
        orxan = self.agency._one("SELECT * FROM workers WHERE id='old'")
        self.assertEqual(orxan['status'], 'reserve')
        self.assertEqual(orxan['exam_score'], 1.0)
        self.assertTrue(any('50% → 100%' in row['message'] for row in self.journal('audit')))
        # A vacancy is now filled from the reserve, without paying for a new exam.
        leaving = self.agency.staffed('soz')[0]
        with self.agency.lock, self.agency.db:
            self.agency.db.execute("UPDATE workers SET status='fired' WHERE id=?", (leaving['id'],))
        calls = len(self.models.calls)
        self.agency.step()
        self.assertEqual(self.agency._one("SELECT status FROM workers WHERE id='old'")['status'], 'probation')
        self.assertEqual(len(self.models.calls), calls)
        self.assertTrue(any('ehtiyat siyahısından' in row['message'] for row in self.journal('hire')))


class ReplayTest(EngineCase):
    def record(self):
        """A live run, then a later firing, saved and reopened as a replay."""
        from datetime import datetime, timedelta
        self.build()
        self.run_until_idle()
        job = self.agency.submit_ticket('Bakı daxilində çatdırılma neçəyədir?')
        self.run_until_idle()
        victim = self.agency.staffed('soz')[0]
        last = datetime.fromisoformat(self.agency._one('SELECT MAX(time) AS t FROM journal')['t'])
        fired_at = (last + timedelta(seconds=100)).isoformat(timespec='seconds')
        with self.agency.lock, self.agency.db:
            self.agency.db.execute("INSERT INTO journal(time, service, kind, worker_id, message, data) VALUES (?,?,?,?,?,?)",
                                   (fired_at, 'soz', 'fire', victim['id'], f"{victim['name']} işdən çıxarıldı.", '{}'))
            self.agency.db.execute("UPDATE workers SET status='fired' WHERE id=?", (victim['id'],))
        path = Path(self.folder.name) / 'agency.sqlite3'
        self.agency.close()
        self.agency = Agency(path, self.models, replay=1)
        self.addCleanup(self.agency.close)
        return job, victim, last

    def seek(self, moment):
        self.agency.replay_seek(moment)

    def test_start_shows_nothing_and_the_end_shows_the_recorded_outcome(self):
        job, victim, _ = self.record()
        self.seek(self.agency.replay['start'])
        early = self.agency.snapshot()
        self.assertEqual(early['journal'], [])
        self.assertEqual(early['services']['soz']['workers'], [])
        self.assertEqual(early['services']['soz']['jobs'], [])
        self.seek(self.agency.replay['end'])
        late = self.agency.snapshot()
        self.assertEqual(late['replay']['progress'], 1.0)
        self.assertEqual(next(j for j in late['services']['soz']['jobs'] if j['id'] == job)['status'], 'göndərildi')
        self.assertEqual(next(w for w in late['services']['soz']['workers'] if w['id'] == victim['id'])['status'], 'fired')

    def test_a_worker_appears_as_they_were_at_that_moment(self):
        from datetime import timedelta
        _, victim, last = self.record()
        self.seek(last + timedelta(seconds=50))  # after hiring, before the recorded firing
        then = self.agency.snapshot()
        status = next(w for w in then['services']['soz']['workers'] if w['id'] == victim['id'])['status']
        self.assertNotEqual(status, 'fired')
        self.assertFalse(any(j['kind'] == 'fire' for j in then['journal']))

    def test_replay_accepts_no_new_work_and_calls_no_model(self):
        self.record()
        calls = len(self.models.calls)
        for action in (lambda: self.agency.submit_ticket('salam'), lambda: self.agency.stress(5),
                       lambda: self.agency.set_mode('draft')):
            with self.assertRaises(ValueError):
                action()
        self.assertFalse(self.agency.step())
        self.assertEqual(len(self.models.calls), calls)
        # The deterministic human-agent check still works, offline.
        self.assertFalse(self.agency.human_reply('Məhsulu 30 gün ərzində qaytara bilərsiniz.')['ok'])

    def test_restart_and_speed_bounds(self):
        self.record()
        self.agency.restart_replay(speed=30)
        self.assertEqual(self.agency.replay['speed'], 30)
        with self.assertRaises(ValueError):
            self.agency.restart_replay(speed=500)


class ReplayGapTest(ReplayTest):
    def test_long_idle_gaps_are_squeezed(self):
        from datetime import timedelta
        self.record()  # contains a 100 s gap before the recorded firing
        r = self.agency.replay
        recorded = (r['end'] - r['start']).total_seconds()
        self.assertLess(r['marks'][-1], recorded)  # the timeline is shorter than the recording
        self.assertGreaterEqual(recorded - r['marks'][-1], 100 - 20 - 1)
