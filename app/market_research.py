"""Structured market brief, question plan and human verified evidence."""
from datetime import date


QUESTIONS = [
    ('demand', 'Tələb və bazar həcmi', 'Hədəf regionda bu məhsula tələb və ölçülə bilən bazar nə qədərdir?', 'market size demand statistics'),
    ('customer', 'Müştəri ehtiyacı', 'Hədəf müştəri hansı problemi necə həll edir və nə üçün pul ödəyir?', 'customer needs survey'),
    ('competitor', 'Rəqiblər və alternativlər', 'Birbaşa və dolayı rəqiblərin təklifləri və müştəri qrupları hansılardır?', 'competitors alternatives'),
    ('pricing', 'Qiymət və paketlər', 'Rəqiblər hansı qiymətə, hansı müddət və şərtlərlə xidmət göstərir?', 'pricing plans official'),
    ('channels', 'Satış kanalları', 'Bu müştərilərə hansı kanallarla çatmaq mümkündür?', 'sales channels market report'),
]


def brief_input(data):
    fields = {}
    for name in ('product', 'region', 'audience', 'decision'):
        value = data.get(name, '')
        if not isinstance(value, str) or not 3 <= len(value.strip()) <= 300:
            raise ValueError('Məhsul, region, hədəf müştəri və qərar 3–300 simvol olmalıdır.')
        fields[name] = value.strip()
    return fields


def plan(brief):
    base = brief['product'] + ' ' + brief['region']
    return [dict(id=key, title=title, question=question, query=base + ' ' + suffix,
                 status='queued', source_ids=[], error='')
            for key, title, question, suffix in QUESTIONS]


def evidence_input(data, sources, questions):
    question_id = data.get('question_id')
    if question_id not in {q['id'] for q in questions}:
        raise ValueError('Araşdırma sualını seçin.')
    source = next((s for s in sources if s['id'] == data.get('source_id')
                   and s.get('review', {}).get('status') == 'approved'), None)
    if source is None:
        raise ValueError('Təsdiqlənmiş mənbəni seçin.')
    fields = {}
    for name, maximum in (('claim', 1200), ('quote', 1000), ('region', 300), ('entity', 180)):
        value = data.get(name, '')
        if not isinstance(value, str) or len(value.strip()) > maximum:
            raise ValueError('Sübut mətninin ölçüsü uyğun deyil.')
        fields[name] = value.strip()
    if len(fields['claim']) < 8 or len(fields['quote']) < 12:
        raise ValueError('İddia ən azı 8, sitat ən azı 12 simvol olmalıdır.')
    from app.evaluation import quote_in_source
    if not quote_in_source(fields['quote'], source['body']):
        raise ValueError('Sitat seçilmiş mənbədə tapılmadı.')
    published = data.get('published_date', '')
    if published:
        try:
            day = date.fromisoformat(published)
            if day > date.today():
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('Məlumat tarixi düzgün olmalıdır və gələcək tarix ola bilməz.') from None
    else:
        day = None
    return dict(**fields, question_id=question_id, source_id=source['id'], published_date=published,
                date_unknown=not bool(day), stale=bool(day and (date.today() - day).days > 365),
                conflict_note='', status='verified')


def coverage(project):
    approved = {s['id'] for s in project['sources'] if s.get('review', {}).get('status') == 'approved'}
    evidence = [e for e in project.get('market_evidence', []) if e['source_id'] in approved]
    return [dict(id=q['id'], title=q['title'], count=sum(e['question_id'] == q['id'] for e in evidence),
                 conflicts=sum(e['question_id'] == q['id'] and bool(e['conflict_note']) for e in evidence))
            for q in project.get('research_plan', [])]
