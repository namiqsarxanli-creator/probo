"""Anonymous, locally stored customer observations; no population inference."""
from datetime import date
from app.operations import number


KINDS = {'interview': 'Müsahibə', 'survey': 'Sorğu', 'pilot': 'Pilot satış'}
METHODS = {'convenience': 'Əlçatan iştirakçılar', 'customer_list': 'Müştəri siyahısı',
           'random': 'Təsadüfi seçim', 'other': 'Digər seçim üsulu'}


def bounded_text(value, label, minimum=3, maximum=500):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ValueError(f'{label} {minimum}–{maximum} simvol olmalıdır.')
    return value.strip()


def count(value, label, low=0, high=100000):
    if isinstance(value, bool):
        raise ValueError(f'{label} tam ədəd olmalıdır.')
    result = number(value, label, low, high)
    if not result.is_integer():
        raise ValueError(f'{label} tam ədəd olmalıdır.')
    return int(result)


def study_input(data):
    kind, method = data.get('kind'), data.get('method')
    if kind not in KINDS or method not in METHODS:
        raise ValueError('Yoxlama növünü və iştirakçı seçimi üsulunu seçin.')
    sample_size = count(data.get('sample_size'), 'İştirakçı sayı', 1)
    if kind == 'interview' and sample_size != 1:
        raise ValueError('Hər müsahibə üçün bir anonim iştirakçı qeydi əlavə edin.')
    counts = {key: count(data.get(key), label, 0, sample_size) for key, label in (
        ('problem_count', 'Problemi bildirənlər'), ('intent_count', 'Alış niyyəti bildirənlər'),
        ('paid_count', 'Faktiki ödəniş edənlər'))}
    try:
        day = date.fromisoformat(data.get('observed_date', ''))
        if day > date.today():
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError('Yoxlama tarixi düzgün olmalıdır və gələcək tarix ola bilməz.') from None
    return dict(kind=kind, method=method, sample_size=sample_size, **counts,
                observed_date=day.isoformat(),
                sample_code=bounded_text(data.get('sample_code'), 'Anonim qeyd / qrup kodu', 3, 80),
                region=bounded_text(data.get('region'), 'Region', 3, 300),
                segment=bounded_text(data.get('segment'), 'Müştəri seqmenti', 3, 300),
                recruitment=bounded_text(data.get('recruitment'), 'İştirakçıların necə seçildiyi', 5, 500),
                summary=bounded_text(data.get('summary'), 'Nəticə qeydi', 10, 2000))


def study_summary(studies):
    # Different kinds and samples are never silently pooled. Reused people may exist.
    groups = {}
    for study in studies:
        key = (study['kind'], study['region'], study['segment'], study['method'])
        group = groups.setdefault(key, dict(kind=key[0], region=key[1], segment=key[2], method=key[3],
                                           records=0, sample_size=0, problem_count=0, intent_count=0, paid_count=0))
        group['records'] += 1
        for field in ('sample_size', 'problem_count', 'intent_count', 'paid_count'):
            group[field] += study[field]
    for group in groups.values():
        for field in ('problem', 'intent', 'paid'):
            group[field + '_percent'] = round(100 * group[field + '_count'] / group['sample_size'], 2)
    return list(groups.values())


def report_lines(studies):
    lines = ['## Müştəri yoxlamaları — yerli qeydlər', '']
    if not studies:
        return lines + ['Müsahibə, sorğu və pilot satış məlumatı əlavə edilməyib.', '']
    for study in studies:
        lines += [f"- {study['sample_code']} | {KINDS[study['kind']]} | {study['region']} | {study['segment']} | {study['observed_date']}",
                  f"  Seçim: {METHODS[study['method']]} — {study['recruitment']}",
                  f"  {study['sample_size']} iştirakçı: problem {study['problem_count']}, alış niyyəti {study['intent_count']}, faktiki ödəniş {study['paid_count']}.",
                  f"  Qeyd: {study['summary']}"]
    return lines + ['', 'Faizlər yalnız bu nümunələri təsvir edir; bütün bazara yayılmır. Alış niyyəti faktiki ödəniş sayılmır. '
                    'Fərqli qeydlərdə eyni şəxslər iştirak etmiş ola bilər; toplam say unikal müştəri sayı deyil.', '']
