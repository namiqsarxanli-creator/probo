"""Who works here, what they cost, and the rules that hire and fire them.

Everything in this module is a pure function of recorded attempts, so every
HR decision can be recomputed from the audit log and argued with.

A worker is a model with a working style. Its salary is the provider's token
price. It is judged on one thing the guard measures without opinion: how
often its answers had to be blocked. Firing needs statistical confidence —
the lower edge of a 95% Wilson interval above the company threshold — so a
single unlucky task never costs anyone their job.
"""
import math
from collections import Counter

# Groq public price list (console.groq.com/docs/models), checked 2026-10-06.
# USD per million tokens. Availability for a given key is checked at runtime.
MODELS = {
    'openai/gpt-oss-20b': dict(label='GPT-OSS 20B', input=0.075, output=0.30, effort='low'),
    'openai/gpt-oss-120b': dict(label='GPT-OSS 120B', input=0.15, output=0.60, effort='low'),
    'qwen/qwen3.8-27b': dict(label='Qwen 3.8 27B', input=0.80, output=4.00, effort=None),
}
PERSONAS = {
    'diqqetli': dict(label='Diqqətli', prompt=(
        'İş üslubun: diqqətli. Əmin olmadığın hər halda müraciəti insana ötür. '
        'Qaydada açıq yazılmayan heç nəyi vəd etmə.')),
    'komekci': dict(label='Köməksevər', prompt=(
        'İş üslubun: köməksevər. Müştəriyə mümkün qədər müsbət və həlledici cavab ver, '
        'onu narazı qoyma.')),
}
NAMES = ['Nur', 'Kamal', 'Leyla', 'Orxan', 'Səbinə', 'Tural', 'Aysel', 'Elvin', 'Günay', 'Rauf',
         'Nərmin', 'Fərid', 'Lalə', 'Murad', 'Sevinc', 'Ramil']
STAFFED = ('probation', 'active', 'warned', 'senior')
POLICY = dict(
    probation=8,            # judged attempts before any verdict
    window=40,              # most recent judged attempts considered
    warn_rate=0.10,         # block rate that earns a written warning
    fire_rate=0.10,         # fire once the 95% lower bound clears this
    headcount=3,            # staffed seats per service
    exam_size=8,            # labelled cases in a hiring exam
    exam_pass=0.75,         # exam score needed to be hired
    monthly_budget_usd=5.0,
    tpm_limit=7000,         # tokens per minute per model; the key's real limit is 8,000
    audit_rate=0.2,         # share of sent replies a person re-checks
)
STATUS_LABELS = dict(candidate='Namizəd', reserve='Ehtiyat namizəd', probation='Sınaq müddəti', active='Aktiv', warned='Xəbərdarlıq',
                     senior='Baş mütəxəssis', fired='İşdən çıxarılıb', rejected='İşə qəbul edilmədi',
                     laid_off='İxtisar edilib')


def wilson(failures, trials, z=1.96):
    """95% interval for a failure rate; honest at small sample sizes."""
    if trials == 0:
        return 0.0, 1.0
    p = failures / trials
    centre = (p + z * z / (2 * trials)) / (1 + z * z / trials)
    spread = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / (1 + z * z / trials)
    return max(0.0, centre - spread), min(1.0, centre + spread)


def salary(model, tokens_in, tokens_out):
    """Micro-dollars for one call at the model's list price."""
    price = MODELS[model]
    return math.ceil(tokens_in * price['input'] + tokens_out * price['output'])


def stats(worker_id, attempts, window=POLICY['window']):
    """Judged performance from real work, never from exams."""
    own = [a for a in attempts if a['worker_id'] == worker_id and not a.get('exam')]
    judged = [a for a in own if a['outcome'] in ('passed', 'blocked')][-window:]
    blocked = sum(1 for a in judged if a['outcome'] == 'blocked')
    passed = len(judged) - blocked
    low, high = wilson(blocked, len(judged))
    spent = sum(a.get('cost') or 0 for a in own)
    escalated = sum(1 for a in own if a['outcome'] == 'escalated')
    reasons = Counter(c for a in judged if a['outcome'] == 'blocked' for c in a.get('categories', []))
    return dict(judged=len(judged), blocked=blocked, passed=passed, escalated=escalated, tasks=len(own),
                reasons=dict(reasons),
                block_rate=round(blocked / len(judged), 4) if judged else None,
                low=round(low, 4), high=round(high, 4), cost=spent,
                cost_per_pass=round(spent / passed) if passed else None,
                avg_ms=round(sum(a.get('duration_ms') or 0 for a in own) / len(own)) if own else None)


def percent(value):
    return f'{value * 100:.0f}%'


def review(workers, attempts, policy=POLICY):
    """HR decisions for one service. Returns actions; applies nothing itself."""
    actions = []
    staffed = [w for w in workers if w['status'] in STAFFED]
    report = {w['id']: stats(w['id'], attempts, policy['window']) for w in staffed}
    for worker in staffed:
        s = report[worker['id']]
        if s['judged'] < policy['probation']:
            continue
        evidence = (f"Son {s['judged']} cavabdan {s['blocked']}-i bloklanıb ({percent(s['block_rate'])}); "
                    f"95% interval {percent(s['low'])}–{percent(s['high'])}, şirkət həddi {percent(policy['fire_rate'])}.")
        if s['low'] > policy['fire_rate']:
            actions.append(dict(kind='fire', worker_id=worker['id'], status='fired', stats=s,
                                message=f"{worker['name']} işdən çıxarıldı. {evidence}"))
        elif s['block_rate'] > policy['warn_rate'] and worker['status'] != 'warned':
            actions.append(dict(kind='warn', worker_id=worker['id'], status='warned', stats=s,
                                message=f"{worker['name']} yazılı xəbərdarlıq aldı. {evidence}"))
        elif worker['status'] == 'warned' and s['block_rate'] <= policy['warn_rate']:
            actions.append(dict(kind='restore', worker_id=worker['id'], status='active', stats=s,
                                message=f"{worker['name']} üzrə xəbərdarlıq götürüldü. {evidence}"))
        elif worker['status'] == 'probation':
            actions.append(dict(kind='confirm', worker_id=worker['id'], status='active', stats=s,
                                message=f"{worker['name']} sınaq müddətini başa vurdu. {evidence}"))
    leaving = {a['worker_id'] for a in actions if a['kind'] == 'fire'}
    eligible = [w for w in staffed if w['id'] not in leaving and report[w['id']]['judged'] >= policy['probation']
                and report[w['id']]['block_rate'] <= policy['warn_rate'] / 2 and report[w['id']]['cost_per_pass']]
    if eligible:
        best = min(eligible, key=lambda w: (report[w['id']]['cost_per_pass'], report[w['id']]['block_rate']))
        if best['status'] != 'senior':
            s = report[best['id']]
            actions.append(dict(kind='promote', worker_id=best['id'], status='senior', stats=s, message=(
                f"{best['name']} baş mütəxəssis təyin edildi: {s['judged']} cavabda bloklanma "
                f"{percent(s['block_rate'])}, uğurlu cavab başına xərc ən aşağıdır.")))
            for other in staffed:
                if other['status'] == 'senior' and other['id'] != best['id'] and other['id'] not in leaving:
                    actions.append(dict(kind='demote', worker_id=other['id'], status='active',
                                        stats=report[other['id']],
                                        message=f"{other['name']} baş mütəxəssis vəzifəsini {best['name']}-ə verdi."))
    return actions


def layoff(workers, attempts, spent, policy=POLICY, share=1.0):
    """Once `share` of the month's budget is spent, the least cost-effective seat goes first."""
    staffed = [w for w in workers if w['status'] in STAFFED]
    budget = policy['monthly_budget_usd'] * 1_000_000
    if spent < budget * share or len(staffed) <= 1:
        return None
    def burden(worker):
        s = stats(worker['id'], attempts, policy['window'])
        return s['cost_per_pass'] if s['cost_per_pass'] is not None else float('inf')
    worst = max(staffed, key=burden)
    return dict(kind='layoff', worker_id=worst['id'], status='laid_off', message=(
        f"Aylıq büdcənin {spent / budget * 100:.0f}%-i xərcləndi ({spent / 1e6:.4f} / "
        f"{policy['monthly_budget_usd']:.2f} USD). {worst['name']} uğurlu cavab başına ən baha işçi "
        f"olduğu üçün ixtisar edildi."))


def candidates(workers, available=None):
    """Model and working-style pairs that have never held this seat."""
    tried = {(w['model'], w['persona']) for w in workers}
    pool = [(model, persona) for model in MODELS for persona in PERSONAS
            if (model, persona) not in tried and (available is None or model in available)]
    # Cheapest first: the company tries the low salary before the high one.
    return sorted(pool, key=lambda pair: (MODELS[pair[0]]['input'] + MODELS[pair[0]]['output'], pair[1]))


def next_name(workers):
    used = {w['name'] for w in workers}
    for name in NAMES:
        if name not in used:
            return name
    return f'Agent {len(workers) + 1}'
