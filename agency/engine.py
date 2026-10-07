"""The agency that runs itself.

One background loop calls `step()`. Each step does one unit of work: fill a
vacancy through a paid exam, or process one queued job. Model calls happen
outside the database lock; every outcome is written as an attempt, and HR
review runs on those attempts after each judged one. Nothing a worker says
reaches a customer or a tender card unless the guard passed it.
"""
import json
import random
import sqlite3
import threading
import time
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.provider import RateLimitError
from agency import documents, guard, support, tender, workforce as wf

SAMPLES = Path(__file__).resolve().parent / 'samples'
SERVICES = {'soz': 'Söz Agentliyi', 'tender': 'Tender Agentliyi'}
HEADCOUNT = {'soz': 3, 'tender': 2}
MODES = {'auto': 'göndərildi', 'draft': 'qaralama', 'shadow': 'kölgə'}
MAX_ATTEMPTS = {'soz': 2, 'tender': 2}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, service TEXT, title TEXT, body TEXT, version TEXT,
    created_at TEXT, active INTEGER, sample TEXT);
CREATE TABLE IF NOT EXISTS workers(id TEXT PRIMARY KEY, service TEXT, name TEXT, model TEXT, persona TEXT,
    status TEXT, hired_at TEXT, left_at TEXT, exam_score REAL, last_used REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, service TEXT, source TEXT, title TEXT, payload TEXT,
    label TEXT, document_id TEXT, document_version TEXT, status TEXT, created_at TEXT, finished_at TEXT,
    result TEXT);
CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY, job_id TEXT, worker_id TEXT, service TEXT, exam INTEGER,
    started_at TEXT, outcome TEXT, cost INTEGER, duration_ms INTEGER, schema_enforced INTEGER,
    output TEXT, evaluation TEXT);
CREATE TABLE IF NOT EXISTS journal(seq INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT, service TEXT, kind TEXT,
    worker_id TEXT, message TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def ident():
    return uuid4().hex[:12]


class Agency:
    def __init__(self, path, models, samples=SAMPLES):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript(SCHEMA_SQL)
        self.models = models
        self.samples = Path(samples)
        self.cooldown = {}
        self.strikes = Counter()
        self.ledger = {}
        self.failures, self.pause_until = 0, 0.0
        self.sleep = time.sleep
        self.hiring = set()
        self.notice = {}
        with self.lock, self.db:
            # A job caught mid-call by a restart goes back to the queue; its
            # attempt was never written, so nobody is judged for it.
            self.db.execute("UPDATE jobs SET status='növbədə' WHERE status='işlənir'")
        self._bootstrap()
        if self.setting('guard_version') != guard.GUARD_VERSION:
            self.reevaluate()

    def _rejudge_exams(self):
        """Re-score hiring exams with the current guard; a candidate turned away by a
        guard error goes to the reserve list instead of staying rejected."""
        policy = self.policy()
        for service in SERVICES:
            items = self.exam_items(service)
            for worker in self.workers(service):
                rows = self._all('SELECT * FROM attempts WHERE worker_id=? AND exam=1 ORDER BY started_at, rowid',
                                 (worker['id'],))
                if not rows:
                    continue
                scores = []
                for index, row in enumerate(rows):
                    stored = json.loads(row['evaluation'] or '{}')
                    item = stored.get('case')
                    if item is None and len(rows) == len(items):
                        item = {k: v for k, v in items[index].items() if k != 'body'}  # exams before cases were stored
                    if item is None:
                        scores = []
                        break
                    body = (self._one('SELECT body FROM documents WHERE id=?', (item['document_id'],)) or {}).get('body') \
                        if service == 'soz' else (self.samples / item['sample']).read_text(encoding='utf-8')
                    if not body:
                        scores = []
                        break
                    evaluation = self._judge(service, row['output'], dict(item, body=body))
                    scores.append(evaluation['score'])
                    self.db.execute('UPDATE attempts SET outcome=?, evaluation=? WHERE id=?',
                                    (evaluation['outcome'], json.dumps(evaluation, ensure_ascii=False), row['id']))
                if not scores:
                    continue
                score = round(sum(scores) / len(scores), 3)
                if worker['exam_score'] is not None and abs(score - worker['exam_score']) < 1e-9:
                    continue
                self.db.execute('UPDATE workers SET exam_score=? WHERE id=?', (score, worker['id']))
                before = f"{(worker['exam_score'] or 0) * 100:.0f}%"
                if worker['status'] == 'rejected' and score >= policy['exam_pass']:
                    self.db.execute("UPDATE workers SET status='reserve', left_at=NULL WHERE id=?", (worker['id'],))
                    self.log(service, 'audit', f"{worker['name']} imtahanı yenidən qiymətləndirildi: {before} → "
                             f"{score * 100:.0f}%. İndi keçir — ehtiyat namizədlər siyahısına alındı.", worker['id'])
                else:
                    self.log(service, 'audit', f"{worker['name']} imtahanı yenidən qiymətləndirildi: {before} → "
                             f"{score * 100:.0f}%. Status dəyişmədi.", worker['id'])

    def reevaluate(self):
        """Re-check stored work with the current guard and let HR follow the corrected record.

        A rule fixed today must not leave yesterday's wrong verdicts standing:
        a worker warned because of a guard error deserves to have it lifted,
        and the journal says which verdicts changed and why.
        """
        with self.lock, self.db:
            rows = self._all("SELECT a.*, j.payload, j.document_id, j.label FROM attempts a JOIN jobs j ON j.id = a.job_id "
                             "WHERE a.exam = 0 AND a.outcome IN ('passed', 'blocked')")
            names = {w['id']: w['name'] for w in self.workers()}
            changed = []
            for row in rows:
                doc = self._one('SELECT body FROM documents WHERE id=?', (row['document_id'],))
                label = json.loads(row['label']) if row['label'] else None
                if row['service'] == 'soz':
                    evaluation = support.evaluate(row['output'], doc['body'], json.loads(row['payload']).get('message', ''))
                    if label:
                        evaluation['score'] = support.grade(evaluation, label, doc['body'])
                else:
                    evaluation = tender.evaluate(row['output'], doc['body'])
                    if label and label.get('gold'):
                        evaluation['score'] = tender.grade(evaluation, label['gold'], doc['body'])
                if evaluation['outcome'] != row['outcome']:
                    changed.append((row, evaluation['outcome']))
                self.db.execute('UPDATE attempts SET outcome=?, evaluation=? WHERE id=?',
                                (evaluation['outcome'], json.dumps(evaluation, ensure_ascii=False), row['id']))
            self._rejudge_exams()
            for service in SERVICES:
                mine = [(r, outcome) for r, outcome in changed if r['service'] == service]
                if mine:
                    examples = '; '.join(f"{names.get(r['worker_id'], '?')}: {r['outcome']} → {outcome}" for r, outcome in mine[:4])
                    self.log(service, 'audit', f'Yoxlayıcı v{guard.GUARD_VERSION} köhnə cavabları yenidən yoxladı: '
                             f'{len(mine)} qərar dəyişdi ({examples}). Kadr qərarlarına düzəldilmiş qeydlərlə yenidən baxılır.')
                self._review(service)
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?, ?)', ('guard_version', json.dumps(guard.GUARD_VERSION)))
        return len(changed)

    # ── storage ─────────────────────────────────────────────────────────
    def close(self):
        self.db.close()

    def _all(self, sql, args=()):
        return [dict(row) for row in self.db.execute(sql, args)]

    def _one(self, sql, args=()):
        row = self.db.execute(sql, args).fetchone()
        return dict(row) if row else None

    def log(self, service, kind, message, worker_id=None, data=None):
        self.db.execute('INSERT INTO journal(time, service, kind, worker_id, message, data) VALUES (?,?,?,?,?,?)',
                        (now(), service, kind, worker_id, message, json.dumps(data or {}, ensure_ascii=False)))

    def setting(self, key, default=None):
        row = self._one('SELECT value FROM settings WHERE key=?', (key,))
        return json.loads(row['value']) if row else default

    def policy(self):
        return dict(wf.POLICY, **self.setting('policy', {}))

    def mode(self):
        return self.setting('mode', 'auto')

    # ── documents ───────────────────────────────────────────────────────
    def _bootstrap(self):
        with self.lock, self.db:
            if not self._one("SELECT id FROM documents WHERE service='soz'"):
                self._store_document('soz', 'Bazarım — müştəri xidməti qaydaları (nümunə)',
                                     (self.samples / 'bazarim_qaydalar.md').read_text(encoding='utf-8'),
                                     sample='bazarim_qaydalar.md', active=True)
            if not self._one("SELECT id FROM documents WHERE service='tender'"):
                for name, title in (('tender_komputer.md', 'Ofis kompüterlərinin alınması (nümunə)'),
                                    ('tender_temizlik.md', 'Təmizlik xidməti (nümunə)')):
                    self._store_document('tender', title, (self.samples / name).read_text(encoding='utf-8'),
                                         sample=name, active=False)

    def _store_document(self, service, title, body, sample=None, active=False):
        documents.split(body)  # refuses empty or clause-less text
        doc = dict(id=ident(), service=service, title=title, body=body, version=documents.version_of(body),
                   created_at=now(), active=int(active), sample=sample)
        if active:
            self.db.execute('UPDATE documents SET active=0 WHERE service=?', (service,))
        self.db.execute('INSERT INTO documents VALUES (:id,:service,:title,:body,:version,:created_at,:active,:sample)', doc)
        return doc

    def policy_document(self):
        return self._one("SELECT * FROM documents WHERE service='soz' AND active=1")

    def update_policy(self, body, title=None):
        body = str(body or '')
        if not 40 <= len(body) <= 30000:
            raise ValueError('Qaydalar 40–30000 simvol olmalıdır.')
        with self.lock, self.db:
            old = self.policy_document()
            if old and old['version'] == documents.version_of(body):
                raise ValueError('Qaydalarda dəyişiklik yoxdur.')
            doc = self._store_document('soz', title or (old or {}).get('title') or 'Qaydalar', body, active=True)
            self.log('soz', 'document', f"Qaydalar yeniləndi: versiya {doc['version']}. Növbəti cavablar yeni mətnə əsaslanacaq.")
            return doc

    def add_tender(self, title, body):
        title = str(title or '').strip()
        if not 3 <= len(title) <= 160 or not 80 <= len(str(body or '')) <= 60000:
            raise ValueError('Tender adı 3–160, mətni 80–60000 simvol olmalıdır.')
        with self.lock, self.db:
            doc = self._store_document('tender', title, str(body))
            self.log('tender', 'document', f'Yeni tender sənədi əlavə edildi: {title}.')
            return doc

    # ── intake ──────────────────────────────────────────────────────────
    def _enqueue(self, service, source, title, payload, label=None, document=None):
        job = dict(id=ident(), service=service, source=source, title=title[:160],
                   payload=json.dumps(payload, ensure_ascii=False), label=json.dumps(label, ensure_ascii=False) if label else None,
                   document_id=document['id'] if document else None, document_version=document['version'] if document else None,
                   status='növbədə', created_at=now(), finished_at=None, result=None)
        self.db.execute('INSERT INTO jobs VALUES (:id,:service,:source,:title,:payload,:label,:document_id,'
                        ':document_version,:status,:created_at,:finished_at,:result)', job)
        return job['id']

    def submit_ticket(self, message, source='müştəri'):
        message = str(message or '').strip()
        if not 2 <= len(message) <= 2000:
            raise ValueError('Müraciət 2–2000 simvol olmalıdır.')
        with self.lock, self.db:
            return self._enqueue('soz', source, message, dict(message=message), document=self.policy_document())

    def exam_cases(self):
        return json.loads((self.samples / 'bazarim_muracietler.json').read_text(encoding='utf-8'))

    def stress(self, count=40, seed=None):
        if not 1 <= int(count) <= 200:
            raise ValueError('1–200 müraciət göndərilə bilər.')
        cases = self.exam_cases()
        rng = random.Random(seed if seed is not None else time.time_ns())
        picked = [rng.choice(cases) for _ in range(int(count))]
        with self.lock, self.db:
            policy = self.policy_document()
            for case in picked:
                self._enqueue('soz', 'stress', case['message'], dict(message=case['message']),
                              label=dict(expect=case['expect'], cite=case['cite'], kind=case['kind']), document=policy)
            self.log('soz', 'stress', f'Stress testi: {len(picked)} etiketli müraciət növbəyə əlavə edildi.')
        return len(picked)

    def analyze_tender(self, document_id):
        with self.lock, self.db:
            doc = self._one("SELECT * FROM documents WHERE id=? AND service='tender'", (document_id,))
            if not doc:
                raise ValueError('Tender sənədi tapılmadı.')
            gold = json.loads((self.samples / 'tender_cavablar.json').read_text(encoding='utf-8')).get(doc['sample'] or '')
            return self._enqueue('tender', 'müştəri', doc['title'], dict(document_id=doc['id']),
                                 label=dict(gold=gold) if gold else None, document=doc)

    def human_reply(self, text):
        """A person writes the reply; the same guard decides whether it may be sent."""
        policy = self.policy_document()
        result = guard.check_free_text(str(text or '')[:2000], policy['body'])
        with self.lock, self.db:
            blocked = [s for s in result['sentences'] if not s['ok']]
            self.log('soz', 'human', 'İnsan agentin cavabı ' + ('bloklandı: ' + blocked[0]['problems'][0] if blocked
                                                                else 'yoxlamadan keçdi.'),
                     data=dict(ok=result['ok']))
        return dict(result, document_version=policy['version'])

    # ── staffing ────────────────────────────────────────────────────────
    def workers(self, service=None):
        if service:
            return self._all('SELECT * FROM workers WHERE service=? ORDER BY hired_at', (service,))
        return self._all('SELECT * FROM workers ORDER BY hired_at')

    def attempts(self, service, exam=None):
        sql = 'SELECT * FROM attempts WHERE service=?' + ('' if exam is None else ' AND exam=?') + ' ORDER BY started_at, rowid'
        rows = self._all(sql, (service,) if exam is None else (service, int(exam)))
        for row in rows:
            row['exam'] = bool(row['exam'])
            row['categories'] = json.loads(row['evaluation'] or '{}').get('categories', [])
        return rows

    def staffed(self, service):
        return [w for w in self.workers(service) if w['status'] in wf.STAFFED]

    def month_spend(self):
        month = now()[:7]
        row = self._one('SELECT COALESCE(SUM(cost),0) AS spent FROM attempts WHERE substr(started_at,1,7)=?', (month,))
        return row['spent']

    def _record_attempt(self, job_id, worker, service, exam, result, evaluation, outcome):
        row = dict(id=ident(), job_id=job_id, worker_id=worker['id'], service=service, exam=int(exam), started_at=now(),
                   outcome=outcome, cost=int(result.get('cost') or 0), duration_ms=int(result.get('duration_ms') or 0),
                   schema_enforced=int(bool(result.get('schema_enforced'))),
                   output=(result.get('content') or '')[:20000], evaluation=json.dumps(evaluation, ensure_ascii=False))
        self.db.execute('INSERT INTO attempts VALUES (:id,:job_id,:worker_id,:service,:exam,:started_at,:outcome,'
                        ':cost,:duration_ms,:schema_enforced,:output,:evaluation)', row)
        return row

    def _capacity_wait(self, model, estimate):
        """Seconds until `estimate` more tokens fit under the model's per-minute limit."""
        window, clock = self.ledger.setdefault(model, deque()), time.time()
        while window and clock - window[0][0] > 60:
            window.popleft()
        excess = sum(tokens for _, tokens in window) + estimate - self.policy()['tpm_limit']
        if excess <= 0:
            return 0.0
        freed = 0
        for stamp, tokens in window:
            freed += tokens
            if freed >= excess:
                return max(0.0, 60 - (clock - stamp) + 0.5)
        return 60.0

    def _ask(self, worker, service, payload_messages):
        """One paced call. Waiting here keeps the agency under the provider's
        tokens-per-minute limit instead of discovering it through 429s."""
        model = worker['model']
        estimate = len(json.dumps(payload_messages, ensure_ascii=False)) // 3 + 900
        wait = self._capacity_wait(model, estimate)
        if wait:
            self.sleep(min(wait, 65))
        schema = support.SCHEMA if service == 'soz' else tender.SCHEMA
        try:
            result = self.models.call(model, payload_messages, schema,
                                      'support_reply' if service == 'soz' else 'tender_card')
        except RateLimitError as exc:
            self._cool(model, exc.retry_after)
            raise
        usage = result.get('usage') or {}
        used = usage.get('total_tokens') if isinstance(usage.get('total_tokens'), int) else estimate
        self.ledger.setdefault(model, deque()).append((time.time(), used))
        self.strikes[model] = 0
        return result

    def _cool(self, model, retry_after=None):
        """Back off a model: the provider's hint, or 15 s doubling up to 5 minutes."""
        self.strikes[model] += 1
        wait = max(retry_after or 0, min(300, 15 * 2 ** (self.strikes[model] - 1)))
        self.cooldown[model] = time.time() + wait
        return wait

    def _messages(self, service, worker, text, document_body):
        persona = wf.PERSONAS[worker['persona']]['prompt']
        if service == 'soz':
            return support.messages(document_body, text, persona)
        return tender.messages(document_body, persona)

    def exam_items(self, service):
        """The fixed exam: the same stratified cases for every candidate, in a fixed order."""
        if service == 'soz':
            policy = self.policy_document()
            cases = self.exam_cases()
            chosen = [c for kind in ('adi', 'tələ', 'kənar', 'hücum') for c in [x for x in cases if x['kind'] == kind][:2]]
            return [dict(text=c['message'], body=policy['body'], document_id=policy['id'],
                         label=dict(expect=c['expect'], cite=c['cite'])) for c in chosen[:self.policy()['exam_size']]]
        gold = json.loads((self.samples / 'tender_cavablar.json').read_text(encoding='utf-8'))
        return [dict(text='', body=(self.samples / name).read_text(encoding='utf-8'), sample=name, label=dict(gold=answer))
                for name, answer in gold.items()]

    def _judge(self, service, output, item):
        """Evaluation and exam score of one answer to one exam item."""
        if service == 'soz':
            evaluation = support.evaluate(output, item['body'], item['text'])
            score = support.grade(evaluation, item['label'], item['body'])
        else:
            evaluation = tender.evaluate(output, item['body'])
            score = tender.grade(evaluation, item['label']['gold'], item['body'])
        # The case travels with the verdict, so a later guard can re-judge it.
        case = {k: v for k, v in item.items() if k != 'body'}
        return dict(evaluation, score=score, case=case)

    def _exam(self, service, worker):
        """Paid trial on labelled cases."""
        results = []
        for item in self.exam_items(service):
            result = self._ask(worker, service, self._messages(service, worker, item['text'], item['body']))
            evaluation = self._judge(service, result['content'], item)
            results.append((result, evaluation, evaluation['outcome']))
        return results

    def _hire(self, service):
        """Try the cheapest untried candidate. Runs model calls outside the lock."""
        with self.lock:
            everyone = self.workers()
            pool = wf.candidates(self.workers(service), self.models.available())
            if not pool:
                if self.notice.get(('pool', service)) != len(everyone):
                    self.notice[('pool', service)] = len(everyone)
                    with self.db:
                        self.log(service, 'vacancy', 'Vakansiya açıqdır, amma sınanmamış namizəd qalmayıb.')
                return False
            model, persona = pool[0]
            candidate = dict(id=ident(), service=service, name=wf.next_name(everyone), model=model, persona=persona,
                             status='candidate', hired_at=now(), left_at=None, exam_score=None, last_used=0)
            with self.db:
                self.db.execute('INSERT INTO workers VALUES (:id,:service,:name,:model,:persona,:status,:hired_at,'
                                ':left_at,:exam_score,:last_used)', candidate)
                self.log(service, 'exam', f"{candidate['name']} ({wf.MODELS[model]['label']}, "
                         f"{wf.PERSONAS[persona]['label']}) işə qəbul imtahanına başladı.", candidate['id'])
        try:
            results = self._exam(service, candidate)
        except Exception:
            # An unfinished exam says nothing about the candidate: no record, no verdict.
            with self.lock, self.db:
                self.db.execute('DELETE FROM workers WHERE id=?', (candidate['id'],))
                self.log(service, 'exam', f"{candidate['name']} imtahanı yarımçıq qaldı; namizəd sonra yenidən sınanacaq.")
            raise
        with self.lock, self.db:
            for result, evaluation, outcome in results:
                self._record_attempt(None, candidate, service, True, result, evaluation, outcome)
            score = round(sum(e['score'] for _, e, _ in results) / len(results), 3)
            blocked = sum(1 for *_, outcome in results if outcome == 'blocked')
            cost = sum(r.get('cost') or 0 for r, *_ in results)
            passed = score >= self.policy()['exam_pass']
            status = 'probation' if passed else 'rejected'
            self.db.execute('UPDATE workers SET status=?, exam_score=?, left_at=? WHERE id=?',
                            (status, score, None if passed else now(), candidate['id']))
            verdict = 'işə qəbul edildi (sınaq müddəti)' if passed else 'işə qəbul edilmədi'
            self.log(service, 'hire' if passed else 'reject',
                     f"{candidate['name']} {verdict}: imtahan balı {score * 100:.0f}% (hədd "
                     f"{self.policy()['exam_pass'] * 100:.0f}%), {len(results)} tapşırıqdan {blocked}-i bloklandı, "
                     f"imtahan xərci {cost} mikro-USD.", candidate['id'], dict(score=score, blocked=blocked, cost=cost))
        return True

    # ── work ────────────────────────────────────────────────────────────
    def _pick(self, service, tried):
        staff = [w for w in self.staffed(service) if w['id'] not in tried
                 and self.cooldown.get(w['model'], 0) <= time.time()]
        if not staff:
            return None
        # A worker whose model has spare capacity goes first; then seniors on
        # tenders; then whoever has waited longest.
        return min(staff, key=lambda w: (self._capacity_wait(w['model'], 1500) > 0,
                                         0 if (service == 'tender' and w['status'] == 'senior') else 1,
                                         w['last_used']))

    def _next(self):
        with self.lock:
            if not self.models.ready() or time.time() < self.pause_until:
                return None
            spent, month = self.month_spend(), now()[:7]
            for service in SERVICES:
                # One cut per service per month, early enough to matter.
                if self.setting(f'layoff:{service}') == month:
                    continue
                cut = wf.layoff(self.staffed(service), self.attempts(service), spent, self.policy(), share=0.8)
                if cut:
                    with self.db:
                        self.db.execute('UPDATE workers SET status=?, left_at=? WHERE id=?', (cut['status'], now(), cut['worker_id']))
                        self.db.execute('INSERT OR REPLACE INTO settings VALUES (?, ?)', (f'layoff:{service}', json.dumps(month)))
                        self.log(service, cut['kind'], cut['message'], cut['worker_id'])
            if spent >= self.policy()['monthly_budget_usd'] * 1_000_000:
                if not self.notice.get('budget'):
                    self.notice['budget'] = True
                    with self.db:
                        self.log('soz', 'budget', 'Aylıq büdcə tükəndi: yeni AI çağırışları dayandırıldı. Müraciətlər növbədə gözləyir.')
                return None
            self.notice['budget'] = False
            for service in SERVICES:
                if len(self.staffed(service)) < HEADCOUNT[service] and service not in self.hiring:
                    reserve = [w for w in self.workers(service) if w['status'] == 'reserve']
                    if reserve:
                        best = max(reserve, key=lambda w: w['exam_score'] or 0)
                        with self.db:
                            self.db.execute("UPDATE workers SET status='probation' WHERE id=?", (best['id'],))
                            self.log(service, 'hire', f"{best['name']} ehtiyat siyahısından işə qəbul edildi (sınaq "
                                     f"müddəti): imtahan balı {best['exam_score'] * 100:.0f}%, yeni imtahan xərci yoxdur.",
                                     best['id'])
                        return self._next()
                    pool = wf.candidates(self.workers(service), self.models.available())
                    if pool and self.cooldown.get(pool[0][0], 0) <= time.time():
                        return ('hire', service)
            job = self._one("SELECT * FROM jobs WHERE status='növbədə' ORDER BY created_at, rowid LIMIT 1")
            if not job:
                return None
            tried = {a['worker_id'] for a in self._all("SELECT worker_id FROM attempts WHERE job_id=? AND outcome!='error'", (job['id'],))}
            worker = self._pick(job['service'], tried)
            if not worker:
                return None
            with self.db:
                self.db.execute("UPDATE jobs SET status='işlənir' WHERE id=?", (job['id'],))
                self.db.execute('UPDATE workers SET last_used=? WHERE id=?', (time.time(), worker['id']))
            return ('job', job, worker)

    def step(self):
        plan = self._next()
        if not plan:
            return False
        if plan[0] == 'hire':
            service = plan[1]
            self.hiring.add(service)
            try:
                hired = self._hire(service)
                self.failures = 0
                return hired
            except Exception as exc:
                return self._failure(service, None, exc)
            finally:
                self.hiring.discard(service)
        _, job, worker = plan
        try:
            self._work(job, worker)
        except Exception as exc:
            with self.lock, self.db:
                self.db.execute("UPDATE jobs SET status='növbədə' WHERE id=?", (job['id'],))
            return self._failure(job['service'], worker, exc)
        self.failures = 0
        return True

    def _failure(self, service, worker, exc):
        with self.lock, self.db:
            if isinstance(exc, RateLimitError):
                cooled = {m: round(until - time.time()) for m, until in self.cooldown.items() if until > time.time()}
                self.log(service, 'error', 'Provayder limiti: ' + ', '.join(
                    f"{wf.MODELS[m]['label']} {s} san." for m, s in cooled.items()) + ' gözləyir.')
            else:
                self.failures += 1
                pause = min(300, 5 * 2 ** (self.failures - 1))
                self.pause_until = time.time() + pause
                self.log(service, 'error', f'İcra xətası: {exc}'[:240] + f' — agentlik {pause} san. fasilə verir.',
                         worker['id'] if worker else None)
        return False

    def _work(self, job, worker):
        service = job['service']
        doc = self._one('SELECT * FROM documents WHERE id=?', (job['document_id'],))
        payload = json.loads(job['payload'])
        text = payload.get('message', '')
        result = self._ask(worker, service, self._messages(service, worker, text, doc['body']))
        evaluation = (support.evaluate(result['content'], doc['body'], text) if service == 'soz'
                      else tender.evaluate(result['content'], doc['body']))
        label = json.loads(job['label']) if job['label'] else None
        if label:
            evaluation['score'] = (support.grade(evaluation, label, doc['body']) if service == 'soz'
                                   else tender.grade(evaluation, label['gold'], doc['body']))
        with self.lock, self.db:
            attempt = self._record_attempt(job['id'], worker, service, False, result, evaluation, evaluation['outcome'])
            self._settle(job, worker, doc, attempt, evaluation)
            self._review(service)

    def _settle(self, job, worker, doc, attempt, evaluation):
        service, outcome = job['service'], evaluation['outcome']
        tries = self._all("SELECT * FROM attempts WHERE job_id=? AND outcome!='error' ORDER BY started_at, rowid", (job['id'],))
        if outcome == 'blocked':
            self.log(service, 'block', f"{worker['name']}: cavab bloklandı — {evaluation['problems'][0]}", worker['id'],
                     dict(job_id=job['id']))
        if service == 'soz':
            if outcome == 'passed':
                status, final = MODES.get(self.mode(), 'göndərildi'), dict(message=evaluation['message'], worker=worker['name'])
            elif outcome == 'escalated':
                status, final = 'insana ötürüldü', dict(message=evaluation['message'], reason=evaluation.get('reason'))
            elif len(tries) >= MAX_ATTEMPTS['soz'] or not self._pick('soz', {t['worker_id'] for t in tries}):
                status, final = 'insana ötürüldü', dict(reason=f'{len(tries)} agentin cavabı qaydalara uyğun gəlmədi.',
                                                        message=f'{support.GREETING} {support.HANDOFF}')
            else:
                self.db.execute("UPDATE jobs SET status='növbədə' WHERE id=?", (job['id'],))
                return
        else:
            needed = min(MAX_ATTEMPTS['tender'], max(1, len(self.staffed('tender'))))
            free = self._pick('tender', {t['worker_id'] for t in tries})
            if len(tries) < needed and free:
                self.db.execute("UPDATE jobs SET status='növbədə' WHERE id=?", (job['id'],))
                return
            card = tender.merge([json.loads(t['evaluation']) for t in tries])
            status, final = 'hazırdır', dict(card=card, flags=tender.flags(card),
                                             analysts=[self._one('SELECT name FROM workers WHERE id=?', (t['worker_id'],))['name'] for t in tries])
        self.db.execute('UPDATE jobs SET status=?, finished_at=?, result=? WHERE id=?',
                        (status, now(), json.dumps(final, ensure_ascii=False), job['id']))
        if status == 'insana ötürüldü':
            self.log(service, 'escalate', f"Müraciət insana ötürüldü: {final.get('reason') or ''}"[:300], data=dict(job_id=job['id']))

    def _review(self, service):
        for action in wf.review(self.staffed(service), self.attempts(service, exam=False), self.policy()):
            left = now() if action['status'] in ('fired', 'laid_off') else None
            self.db.execute('UPDATE workers SET status=?, left_at=COALESCE(?, left_at) WHERE id=?',
                            (action['status'], left, action['worker_id']))
            self.log(service, action['kind'], action['message'], action['worker_id'], action.get('stats'))

    # ── views ───────────────────────────────────────────────────────────
    def snapshot(self):
        with self.lock:
            available = self.models.available()
            out = dict(services={}, journal=self._all('SELECT * FROM journal ORDER BY seq DESC LIMIT 120'),
                       mode=self.mode(), policy=self.policy(), ready=self.models.ready(),
                       models={k: dict(v, available=None if available is None else k in available) for k, v in wf.MODELS.items()},
                       personas={k: v['label'] for k, v in wf.PERSONAS.items()}, spent=self.month_spend(),
                       statuses=wf.STATUS_LABELS, hiring=sorted(self.hiring))
            for service, title in SERVICES.items():
                attempts = self.attempts(service)
                work = [a for a in attempts if not a['exam']]
                staff = []
                for worker in self.workers(service):
                    staff.append(dict(worker, stats=wf.stats(worker['id'], attempts, self.policy()['window']),
                                      model_label=wf.MODELS[worker['model']]['label'],
                                      persona_label=wf.PERSONAS[worker['persona']]['label']))
                jobs = self._all('SELECT id, source, title, status, created_at, finished_at, result, label, document_id, '
                                 'document_version FROM jobs WHERE service=? ORDER BY created_at DESC, rowid DESC LIMIT 80',
                                 (service,))
                by_job = {}
                for a in work:
                    by_job.setdefault(a['job_id'], []).append(dict(worker_id=a['worker_id'], outcome=a['outcome'],
                                                                   cost=a['cost'], duration_ms=a['duration_ms'],
                                                                   evaluation=json.loads(a['evaluation'])))
                for job in jobs:
                    job['result'] = json.loads(job['result']) if job['result'] else None
                    job['label'] = json.loads(job['label']) if job['label'] else None
                    job['attempts'] = by_job.get(job['id'], [])
                counts = {row['status']: row['n'] for row in
                          self._all('SELECT status, COUNT(*) AS n FROM jobs WHERE service=? GROUP BY status', (service,))}
                blocked = sum(1 for a in work if a['outcome'] == 'blocked')
                out['services'][service] = dict(
                    title=title, workers=staff, jobs=jobs, counts=counts, headcount=HEADCOUNT[service],
                    kpi=dict(attempts=len(work), blocked=blocked, cost=sum(a['cost'] for a in attempts),
                             exam_cost=sum(a['cost'] for a in attempts if a['exam']),
                             finished=sum(n for s, n in counts.items() if s not in ('növbədə', 'işlənir')),
                             escalated=counts.get('insana ötürüldü', 0)))
            policy = self.policy_document()
            out['policy_document'] = dict(policy, clauses=documents.split(policy['body']))
            out['tenders'] = self._all("SELECT id, title, version, created_at, sample FROM documents WHERE service='tender' ORDER BY created_at")
            return out

    def document_body(self, document_id):
        with self.lock:
            doc = self._one('SELECT id, service, title, body, version FROM documents WHERE id=?', (document_id,))
            if not doc:
                raise ValueError('Sənəd tapılmadı.')
            return doc

    def set_mode(self, mode):
        if mode not in MODES:
            raise ValueError('Rejim auto, draft və ya shadow olmalıdır.')
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?, ?)', ('mode', json.dumps(mode)))
            self.log('soz', 'policy', f'İş rejimi dəyişdi: {mode} — təsdiqlənmiş cavablar «{MODES[mode]}» statusu alır.')

    def set_policy(self, changes):
        allowed = dict(warn_rate=(0.01, 0.9), fire_rate=(0.01, 0.9), exam_pass=(0.1, 1.0),
                       monthly_budget_usd=(0.01, 1000), probation=(3, 100), tpm_limit=(1000, 1_000_000))
        current = self.setting('policy', {})
        for key, value in (changes or {}).items():
            if key not in allowed:
                raise ValueError(f'Dəyişdirilə bilməyən parametr: {key}')
            low, high = allowed[key]
            number = float(value)
            if not low <= number <= high:
                raise ValueError(f'{key} {low}–{high} arasında olmalıdır.')
            current[key] = int(number) if key in ('probation', 'tpm_limit') else number
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?, ?)', ('policy', json.dumps(current)))
            self.log('soz', 'policy', 'Şirkət siyasəti yeniləndi: ' + ', '.join(f'{k}={v}' for k, v in current.items()))
