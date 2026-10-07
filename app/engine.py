"""Persistent, transactional company simulation. No external AI/API calls."""
import copy
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def uid():
    return uuid4().hex[:12]


class Company:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
        row = self.db.execute('SELECT body FROM state WHERE id=1').fetchone()
        self.s = json.loads(row[0]) if row else self.empty()

    @staticmethod
    def empty():
        return dict(id=None, name='Autonomous Inc.', objective='', status='idle', mode='simulation',
                    budget=0, spent=0, tick=0, employees=[], tasks=[], events=[], handoffs=[], candidates=[], report=None)

    def close(self):
        self.db.close()

    def save(self):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO state VALUES (1, ?)', (json.dumps(self.s, ensure_ascii=False),))

    def event(self, kind, message):
        self.s['events'].append(dict(id=uid(), kind=kind, message=message,
                                    time=datetime.now(timezone.utc).isoformat()))

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.s)

    def action(self, action, data):
        with self.lock:
            previous = copy.deepcopy(self.s)
            try:
                if action == 'create':
                    self.create(data)
                elif action == 'pause':
                    if self.s['status'] != 'running':
                        raise ValueError('Yalnız işləyən şirkət dayandırıla bilər.')
                    self.s['status'] = 'paused'
                    self.event('owner', 'Şirkətin işi sahibi tərəfindən dayandırıldı.')
                elif action == 'resume':
                    if self.s['status'] not in ('paused', 'budget_blocked'):
                        raise ValueError('Şirkət davam etməyə hazır deyil.')
                    self.s['status'] = 'running'
                    self.event('owner', 'Şirkətin işi davam etdirildi.')
                elif action == 'fire':
                    self.fire(data.get('id'))
                elif action == 'budget':
                    budget = self.valid_budget(data.get('budget'))
                    if budget < self.s['spent']:
                        raise ValueError('Büdcə artıq sərf edilmiş məbləğdən aşağı ola bilməz.')
                    self.s['budget'] = budget
                    self.event('budget', f'Büdcə {budget / 100:.2f} kreditə dəyişdirildi.')
                else:
                    raise ValueError('Naməlum əməliyyat.')
                self.save()
            except Exception:
                self.s = previous
                raise
            return copy.deepcopy(self.s)

    @staticmethod
    def valid_budget(value):
        try:
            amount = float(value)
            if not 0.1 <= amount <= 10000:
                raise ValueError()
            return round(amount * 100)
        except (TypeError, ValueError, OverflowError):
            raise ValueError('Büdcə 0.10–10000 kredit arasında olmalıdır.')

    def create(self, data):
        if self.s['id']:
            raise ValueError('Bu versiya bir şirkət saxlayır; mövcud tarixçə silinmir.')
        objective = str(data.get('objective', '')).strip()
        if not 10 <= len(objective) <= 2000:
            raise ValueError('Məqsəd 10–2000 simvol olmalıdır.')
        budget = self.valid_budget(data.get('budget', 20))
        self.s.update(id=uid(), objective=objective, budget=budget, status='running')
        self.s['employees'].append(dict(id=uid(), name='Ada', role='director', status='active', completed=0, score=100))
        self.event('owner', 'Şirkət yaradıldı. Simulyasiya rejimi: real pul və API sərf edilmir.')

    def charge(self, amount):
        if self.s['spent'] + amount > self.s['budget']:
            self.s['status'] = 'budget_blocked'
            self.event('budget', 'Növbəti əməliyyat büdcəni aşır. İş saxlanıldı; büdcəni artırıb davam edin.')
            return False
        self.s['spent'] += amount
        return True

    def hire(self, role):
        if sum(e['status'] == 'active' for e in self.s['employees']) >= 5:
            return None
        if not self.charge(20):
            return None
        # Deterministic fixture scores make simulation repeatable; not model benchmarks.
        trials = [dict(name=n, role=role, quality=q, speed=v, economy=c,
                       score=round(q * .6 + v * .2 + c * .2))
                  for n, q, v, c in [('Nova', 91, 76, 80), ('Atlas', 78, 92, 85), ('Lumen', 84, 81, 95)]]
        winner = max(trials, key=lambda x: x['score'])
        self.s['candidates'].append(dict(id=uid(), role=role, trials=trials, selected=winner['name']))
        employee = dict(id=uid(), name=f"{winner['name']} {len(self.s['employees'])}", role=role,
                        status='active', completed=0, score=winner['score'])
        self.s['employees'].append(employee)
        self.event('hire', f"{employee['name']} işə qəbul edildi: {role}. Üç simulyasiya namizədi müqayisə edildi.")
        return employee

    def fire(self, employee_id):
        if self.s['status'] not in ('running', 'paused', 'budget_blocked'):
            raise ValueError('Hazırda işçi çıxarmaq mümkün deyil.')
        employee = next((e for e in self.s['employees'] if e['id'] == employee_id), None)
        if not employee or employee['status'] != 'active' or employee['role'] == 'director':
            raise ValueError('Aktiv mütəxəssis seçin. Rəhbər bu versiyada dəyişdirilmir.')
        employee['status'] = 'dismissed'
        for task in self.s['tasks']:
            if task['assignee'] == employee_id and task['status'] != 'done':
                package = dict(id=uid(), task_id=task['id'], from_id=employee_id, to_id=None,
                               progress=task['progress'], notes=list(task['notes']),
                               next_step=f"{task['progress'] + 1}/4 mərhələsindən davam et",
                               status='pending')
                self.s['handoffs'].append(package)
                task.update(assignee=None, status='queued')
        self.event('handoff', f"{employee['name']} çıxarıldı. Yarımçıq işlər və qeydlər təhvil üçün saxlanıldı.")

    def tick(self):
        with self.lock:
            if self.s['status'] != 'running':
                return
            previous = copy.deepcopy(self.s)
            try:
                self._tick()
                self.save()
            except Exception:
                self.s = previous
                raise

    def _tick(self):
        self.s['tick'] += 1
        if not self.s['tasks']:
            roles = [('researcher', 'Araşdırma planı'), ('analyst', 'Müqayisə çərçivəsi'),
                     ('editor', 'Hesabat layihəsi'), ('reviewer', 'Tamlıq yoxlaması')]
            for index, (role, title) in enumerate(roles):
                self.s['tasks'].append(dict(id=uid(), title=title, role=role, status='queued',
                                           assignee=None, progress=0, notes=[], depends=index - 1))
            self.event('plan', 'Rəhbər məqsəd üçün dörd mərhələli iş planı yaratdı.')
            return
        for index, task in enumerate(self.s['tasks']):
            if task['status'] == 'done':
                continue
            if task['depends'] >= 0 and self.s['tasks'][task['depends']]['status'] != 'done':
                continue
            if not task['assignee']:
                employee = next((e for e in self.s['employees'] if e['role'] == task['role'] and e['status'] == 'active'), None)
                employee = employee or self.hire(task['role'])
                if not employee:
                    return
                task.update(assignee=employee['id'], status='working')
                for package in self.s['handoffs']:
                    if package['task_id'] == task['id'] and package['status'] == 'pending':
                        if package['progress'] != task['progress'] or package['notes'] != task['notes']:
                            raise ValueError('Təhvil məlumatı tapşırıqla uyğun deyil.')
                        package.update(to_id=employee['id'], status='accepted')
                        self.event('handoff', f"{employee['name']} təhvil paketini qəbul etdi; iş {task['progress']}/4 mərhələsindən davam edir.")
                self.event('assign', f"{task['title']} → {employee['name']}")
                return
            if not self.charge(15):
                return
            task['progress'] += 1
            task['notes'].append(f"Mərhələ {task['progress']}: {task['title']} üçün simulyasiya qeydi saxlanıldı.")
            if task['progress'] == 4:
                task['status'] = 'done'
                employee = next(e for e in self.s['employees'] if e['id'] == task['assignee'])
                employee['completed'] += 1
                for package in self.s['handoffs']:
                    if package['task_id'] == task['id'] and package['to_id'] == employee['id'] and package['status'] == 'accepted':
                        package['status'] = 'verified'
                self.event('done', f"{task['title']} tamamlandı; nəticə növbəti mərhələyə ötürüldü.")
            return
        self.s['status'] = 'completed'
        self.s['report'] = '\n'.join([
            '# Autonomous Inc. — simulyasiya hesabatı', '', '## Məqsəd', self.s['objective'], '',
            'Bu sənəd iş axınının nümayişidir. İnternet araşdırması və LLM çağırışı aparılmayıb.',
            'Mənbə, fakt və bazar nəticəsi yaradılmayıb.', '', '## Tamamlanan iş axını',
            *[f"- {t['title']}: 4/4 mərhələ" for t in self.s['tasks']], '',
            f"Simulyasiya xərci: {self.s['spent'] / 100:.2f} kredit", '',
            '## Real hesabat üçün növbəti addımlar',
            '- Araşdırma suallarını və qəbul meyarlarını müəyyənləşdirmək.',
            '- Etibarlı mənbələri toplamaq və iddiaları yoxlamaq.',
            '- Analiz nəticələrini mənbələrlə əlaqələndirmək.',
            '- İnsan tərəfindən yekun baxış keçirmək.'
        ])
        self.event('done', 'İş axını tamamlandı. Simulyasiya hesabatı hazırdır.')
