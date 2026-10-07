"""Offline evidence-extraction evaluation over saved candidate trials.

Gold labels are human supplied. A match only means the same source passage was
selected; it does not prove that the candidate's claim is semantically true.
"""
import re


def normalized(value):
    return ' '.join(value.casefold().split())


def quote_in_source(quote, body):
    pattern = r'\s+'.join(re.escape(part) for part in quote.split())
    return bool(re.search(pattern, body, flags=re.IGNORECASE))


def matches(expected, finding):
    if expected['source_id'] != finding.get('source_id'):
        return False
    gold, actual = normalized(expected['quote']), normalized(finding.get('quote', ''))
    return bool(gold and actual and gold in actual)


def score_trial(cases, trial):
    findings = trial.get('output', {}).get('findings', []) if trial.get('output') else []
    used = set()
    matched = []
    for case in cases:
        index = next((i for i, finding in enumerate(findings)
                      if i not in used and matches(case, finding)), None)
        if index is not None:
            used.add(index)
            matched.append(case['id'])
    tp, predicted, expected = len(matched), len(findings), len(cases)
    precision = tp / predicted if predicted else 0.0
    recall = tp / expected if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    metrics = trial.get('metrics', {})
    return dict(tp=tp, predicted=predicted, expected=expected,
                precision=round(precision, 4), recall=round(recall, 4), f1=round(f1, 4),
                matched_case_ids=matched, missed_case_ids=[c['id'] for c in cases if c['id'] not in matched],
                unmatched_findings=[f.get('claim', '') for i, f in enumerate(findings) if i not in used],
                cost=metrics.get('cost', 0), duration_ms=metrics.get('duration_ms', 0),
                error=trial.get('error'))


def compare(project):
    cases = project['eval_cases']
    if not cases:
        raise ValueError('Əvvəl ən azı bir yoxlanmış test nümunəsi əlavə edin.')
    groups = {}
    for task in project['tasks']:
        selected = [c for c in cases if c['task_id'] == task['id']]
        if not selected:
            continue
        if len(task['trials']) < 2:
            raise ValueError('Test nümunəsi olan hər mərhələdə iki saxlanmış namizəd sınağı lazımdır.')
        for trial in task['trials'][:2]:
            name = trial['name']
            groups.setdefault(name, []).append(dict(task_id=task['id'], task=task['title'],
                                                      result=score_trial(selected, trial)))
    if len(groups) != 2:
        raise ValueError('Müqayisə üçün iki fərqli namizəd profili lazımdır.')
    variants = []
    for name, rows in groups.items():
        tp = sum(r['result']['tp'] for r in rows)
        predicted = sum(r['result']['predicted'] for r in rows)
        expected = sum(r['result']['expected'] for r in rows)
        precision = tp / predicted if predicted else 0.0
        recall = tp / expected if expected else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        variants.append(dict(name=name, tp=tp, predicted=predicted, expected=expected,
                             precision=round(precision, 4), recall=round(recall, 4), f1=round(f1, 4),
                             cost=sum(r['result']['cost'] for r in rows),
                             duration_ms=sum(r['result']['duration_ms'] for r in rows), tasks=rows))
    variants.sort(key=lambda v: v['name'])
    return dict(variants=variants, case_count=len(cases),
                comparison=[dict(task_id=a['task_id'], task=a['task'],
                                 first=a['result']['f1'], second=b['result']['f1'],
                                 difference=round(b['result']['f1'] - a['result']['f1'], 4))
                            for a, b in zip(variants[0]['tasks'], variants[1]['tasks'])])
