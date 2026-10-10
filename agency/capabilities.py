"""Inspectable decisions and local, explicitly labelled demonstration operations."""
import json
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from agency import documents, guard


def local_day():
    return datetime.now(timezone(timedelta(hours=4), 'Asia/Baku')).date()


class Capabilities:
    def capability_init(self):
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS demo_orders(id TEXT PRIMARY KEY, data TEXT);
        CREATE TABLE IF NOT EXISTS demo_stock(sku TEXT, size TEXT, quantity INTEGER,
            PRIMARY KEY(sku,size));
        CREATE TABLE IF NOT EXISTS demo_exchanges(id TEXT PRIMARY KEY, order_id TEXT,
            size TEXT, policy_version TEXT, state TEXT, created_at TEXT);
        ''')

    def operation_state(self):
        with self.lock:
            return dict(demo=True, orders=[json.loads(r['data']) for r in self._all('SELECT data FROM demo_orders')],
                        stock=self._all('SELECT * FROM demo_stock ORDER BY sku,size'),
                        exchanges=self._all('SELECT * FROM demo_exchanges ORDER BY created_at DESC'))

    def load_demo_operations(self):
        self._live()
        with self.lock, self.db:
            # Idempotent: clicking again never refills consumed stock.
            for oid, days, size, status in [('48213', 3, 'M', 'Təhvil verilib'),
                                            ('48214', 20, 'S', 'Təhvil verilib')]:
                data = dict(id=oid, sku='SHIRT-01', product='Test köynəyi', size=size, region='Bakı',
                            received_on=(local_day()-timedelta(days=days)).isoformat(),
                            status=status, unused=True, packaged=True, discounted=False, demo=True)
                self.db.execute('INSERT OR IGNORE INTO demo_orders VALUES (?,?)', (oid, json.dumps(data, ensure_ascii=False)))
            for size, quantity in [('S', 2), ('M', 0), ('L', 3)]:
                self.db.execute('INSERT OR IGNORE INTO demo_stock VALUES (?,?,?)', ('SHIRT-01', size, quantity))
        return self.operation_state()

    def tool_reply(self, message):
        """Local read tools; the model never sees private order records."""
        order_ids = re.findall(r'(?<!\d)(48213|48214)(?!\d)', message)
        if len(set(order_ids)) != 1 or not re.search(r'sifariş|sifaris|ölç|olcu|stok|dəyiş|deyis', message, re.I):
            return None
        with self.lock:
            row = self._one('SELECT data FROM demo_orders WHERE id=?', (order_ids[0],))
            if not row:
                return None
            order = json.loads(row['data'])
            stock = self._all('SELECT size,quantity FROM demo_stock WHERE sku=? ORDER BY size', (order['sku'],))
            exchange = None
            reply = f"TEST SİFARİŞİ {order['id']}: {order['status']}. Məhsul: {order['product']}."
            reply += ' Stok: ' + ', '.join(f"{s['size']} — {s['quantity']} ədəd" for s in stock) + '.'
            sizes = re.findall(r'(?<!\w)(S|M|L)(?!\w)', message, re.I)
            if re.search(r'dəyiş|deyis', message, re.I):
                if len(set(s.upper() for s in sizes)) == 1:
                    try:
                        exchange = self.prepare_exchange(order['id'], sizes[0].upper())
                        reply += f" {sizes[0].upper()} ölçüsünə dəyişmə müraciəti hazırlandı. Təsdiq gözləyir; stok dəyişməyib."
                    except ValueError as exc:
                        reply += ' Müraciət yaradılmadı: ' + str(exc)
                else:
                    reply += ' Dəyişmə üçün istədiyiniz bir ölçünü yazın: S, M və ya L.'
            return dict(outcome='passed', decision='answer', sentences=[], message=reply, problems=[],
                        tool=dict(name='Sifariş və stok oxuma', order=order, stock=stock, demo=True, exchange=exchange),
                        categories=[])

    def _exchange_check(self, order_id, size):
        row = self._one('SELECT data FROM demo_orders WHERE id=?', (order_id,))
        if not row:
            raise ValueError('Test sifarişi tapılmadı. Əvvəl test məlumatlarını yükləyin.')
        order = json.loads(row['data'])
        if size == order['size'] or size not in ('S', 'M', 'L'):
            raise ValueError('Fərqli mövcud ölçü seçin.')
        policy = self.policy_document()
        clauses = documents.split(policy['body'])
        rule = next((c for c in clauses if 'eyni modelin başqa ölçüsü' in c['text'] and '14 gün' in c['text']), None)
        stock_rule = next((c for c in clauses if 'anbarda həmin ölçü mövcud' in c['text']), None)
        if not rule or not stock_rule:
            raise ValueError('Dəyişmə qaydası avtomatik yoxlama üçün uyğun deyil; insan baxışı tələb olunur.')
        elapsed = (local_day()-datetime.fromisoformat(order['received_on']).date()).days
        if not 0 <= elapsed <= 14 or not order['unused'] or not order['packaged'] or order['discounted']:
            raise ValueError('Sifariş test dəyişmə şərtlərinə uyğun deyil.')
        stock = self._one('SELECT quantity FROM demo_stock WHERE sku=? AND size=?', (order['sku'], size))
        if not stock or stock['quantity'] < 1:
            raise ValueError('Seçilən ölçü stokda yoxdur.')
        return order, policy, [rule, stock_rule]

    def prepare_exchange(self, order_id, size):
        self._live()
        with self.lock, self.db:
            if self._one("SELECT id FROM demo_exchanges WHERE order_id=? AND state IN ('prepared','confirmed')", (order_id,)):
                raise ValueError('Bu sifariş üçün dəyişmə müraciəti artıq mövcuddur.')
            order, policy, rules = self._exchange_check(order_id, size)
            eid = uuid4().hex[:12]
            self.db.execute('INSERT INTO demo_exchanges VALUES (?,?,?,?,?,?)',
                            (eid, order_id, size, policy['version'], 'prepared', datetime.now().isoformat()))
            return dict(id=eid, order=order, size=size, rules=rules, state='prepared', demo=True)

    def confirm_exchange(self, exchange_id):
        self._live()
        with self.lock, self.db:
            exchange = self._one('SELECT * FROM demo_exchanges WHERE id=?', (exchange_id,))
            if not exchange:
                raise ValueError('Müraciət tapılmadı.')
            if exchange['state'] == 'confirmed':
                return dict(exchange, demo=True)
            order, policy, _ = self._exchange_check(exchange['order_id'], exchange['size'])
            if policy['version'] != exchange['policy_version']:
                raise ValueError('Qaydalar dəyişib; müraciəti insan yoxlamalıdır.')
            self.db.execute('UPDATE demo_stock SET quantity=quantity-1 WHERE sku=? AND size=?',
                            (order['sku'], exchange['size']))
            self.db.execute("UPDATE demo_exchanges SET state='confirmed' WHERE id=?", (exchange_id,))
            # Reserve replacement stock; don't invent a warehouse receipt for the returned item.
            return dict(exchange, state='confirmed', demo=True)

    def save_company(self, data):
        self._live()
        name = str(data.get('name') or '').strip()
        body = str(data.get('body') or '').strip()
        if not 2 <= len(name) <= 160 or not 20 <= len(body) <= 30000:
            raise ValueError('Şirkət adı və 20–30000 simvolluq sübut sənədi tələb olunur.')
        value = dict(name=name, body=body, version=documents.version_of(body),
                     notice='İstifadəçinin daxil etdiyi sənəd; autentikliyi müstəqil təsdiqlənməyib.')
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('company_profile', json.dumps(value, ensure_ascii=False)))
        return value

    def company_fit(self, document_id):
        with self.lock:
            doc = self._one("SELECT * FROM documents WHERE id=? AND service='tender'", (document_id,))
            if not doc:
                raise ValueError('Tender tapılmadı.')
            profile = self.setting('company_profile', {})
            body = profile.get('body', '')
            rows = []
            # Evaluate original clauses, including requirements the AI card may have missed.
            for clause in documents.split(doc['body']):
                text = clause['text']
                if not re.search(r'iddiaçı|təqdim edilməlidir', text, re.I):
                    continue
                status, proof, explanation = 'missing', '', 'Uyğunluğu təsdiqləyən müqayisə edilə bilən sübut yoxdur.'
                threshold = re.search(r'dövriyyə(?:si)?\s+([\d\s]+)\s*AZN', text, re.I)
                contracts = re.search(r'son\s+(\d+)\s+il.*?ən azı\s+(\d+)\s+oxşar müqavilə', text, re.I)
                if threshold:
                    limit = int(re.sub(r'\s', '', threshold[1]))
                    year = local_day().year - 1
                    matches = re.findall(rf'^.*\b{year}\b.*dövriyyə(?:si)?\s*[:—-]?\s*([\d ]+)\s*AZN.*$', body, re.I | re.M)
                    if len(matches) == 1:
                        amount = int(matches[0].replace(' ', ''))
                        proof = next(line for line in body.splitlines() if str(year) in line and matches[0] in line)
                        status = 'matches' if amount >= limit else 'fails'
                        explanation = f'{year} dövriyyəsi {amount:,} AZN; tələb {limit:,} AZN.'.replace(',', ' ')
                elif contracts:
                    years, count = map(int, contracts.groups())
                    try:
                        start = local_day().replace(year=local_day().year-years)
                    except ValueError:
                        start = local_day() - timedelta(days=365*min(years, 100))
                    accepted = []
                    for line in body.splitlines():
                        if 'oxşar müqavilə' not in line.lower() or 'uğurla icra' not in line.lower():
                            continue
                        dates = guard.dates(line)
                        try:
                            if len(dates) == 1 and start <= datetime.fromisoformat(next(iter(dates))).date() <= local_day():
                                accepted.append(line)
                        except ValueError:
                            continue
                    if accepted:
                        proof = '\n'.join(dict.fromkeys(accepted))
                        n = len(set(accepted))
                        # A partial list doesn't prove that other contracts do not exist.
                        status = 'matches' if n >= count else 'missing'
                        explanation = f'Təqdim edilmiş sənəddə müddətə uyğun {n} qeyd var; tələb {count}. Oxşarlığı insan yoxlamalıdır.'
                elif 'Vergi və sosial sığorta borcunun olmaması' in text:
                    match = next((line for line in body.splitlines() if 'Vergi və sosial sığorta borcu yoxdur' in line and str(local_day()) in line), '')
                    if match:
                        status, proof = 'matches', match
                        explanation = 'Bugünkü tarixli bəyanat tapıldı; rəsmi arayışın autentikliyini insan yoxlamalıdır.'
                rows.append(dict(requirement=text, clause=clause['id'], status=status, proof=proof, explanation=explanation))
            outcome = 'fails' if any(r['status']=='fails' for r in rows) else 'incomplete' if not rows or any(r['status']=='missing' for r in rows) else 'document_match'
            return dict(profile=profile.get('name'), profile_version=profile.get('version'), document_version=doc['version'],
                        rows=rows, outcome=outcome, notice='Sənədlər üzrə ilkin müqayisədir. Təminat, tarix, lot və bütün digər şərtlər ayrıca yoxlanmalıdır; iştirak qərarı deyil.')

    def decision_trace(self, job_id):
        with self.lock:
            snap = self.snapshot()
            job = next((j for service in snap['services'].values() for j in service['jobs'] if j['id']==job_id), None)
            if not job:
                raise ValueError('Müraciət görünən qeydlərdə tapılmadı.')
            doc = self._one('SELECT * FROM documents WHERE id=?', (job['document_id'],))
            names = {w['id']: w for service in snap['services'].values() for w in service['workers']}
            steps = [dict(title='Müraciət', detail=job['title'], status='done')]
            for attempt in job['attempts']:
                worker = names.get(attempt['worker_id'], {})
                ev = attempt['evaluation']
                evidence = [dict(text=s.get('text', s.get('value','')), quote=s.get('quote',''), span=s.get('span'),
                                 ok=s.get('ok',False)) for s in ev.get('sentences', ev.get('fields', [])) if s.get('quote')]
                steps.append(dict(title=worker.get('name','Agent')+' · '+worker.get('model_label',''),
                                  status=attempt['outcome'], cost=attempt['cost'], duration_ms=attempt['duration_ms'],
                                  detail='; '.join(ev.get('problems', [])) or ev.get('reason') or 'Saxlanmış yoxlama nəticəsi',
                                  evidence=evidence if attempt['outcome']=='peer' else [], tool=ev.get('tool')))
                if evidence and attempt['outcome']!='peer':
                    steps.append(dict(title='Kodla sübut yoxlaması', status=attempt['outcome'], evidence=evidence,
                                      detail='Sitatın sənəddə olması, rəqəm və tarix uyğunluğu, qadağa və ziddiyyət yoxlaması. '
                                             'Məna doğruluğuna zəmanət deyil.'))
            steps.append(dict(title='Yekun', status=job['status'], detail=(job.get('result') or {}).get('message',job['status'])))
            return dict(job_id=job_id, steps=steps, document=dict(id=doc['id'], version=doc['version'], body=doc['body']),
                        notice='Saxlanmış alət və yoxlama nəticələri; modelin daxili düşüncə mətni deyil.')
