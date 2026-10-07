"""Transparent annual market-potential scenarios, with explicit input provenance."""
from app.operations import number
from app.customer_research import bounded_text, count


FIELDS = {
    'population': ('Regionda potensial müştəri sayı', 0, 1_000_000_000),
    'eligible_percent': ('Hədəf seqmentin payı', 0, 100),
    'reachable_percent': ('Hədəf seqmentdə xidmət göstərə biləcəyiniz pay', 0, 100),
    'annual_spend': ('Bir müştərinin illik xərci', 0, 1_000_000_000),
    'capture_low': ('Aşağı əldəetmə payı', 0, 100),
    'capture_base': ('Əsas əldəetmə payı', 0, 100),
    'capture_high': ('Yuxarı əldəetmə payı', 0, 100),
}


def sizing_input(data, project):
    inputs = data.get('inputs')
    if not isinstance(inputs, dict):
        raise ValueError('Bazar hesablamasının girişləri tələb olunur.')
    result = {}
    approved = {s['id'] for s in project['sources'] if s.get('review', {}).get('status') == 'approved'}
    evidence = {e['id']: e for e in project['market_evidence'] if e['source_id'] in approved}
    for key, (label, low, high) in FIELDS.items():
        entry = inputs.get(key)
        if not isinstance(entry, dict):
            raise ValueError(f'{label} üçün rəqəm və əsaslandırma tələb olunur.')
        value = number(entry.get('value'), label, low, high)
        if isinstance(entry.get('value'), bool):
            raise ValueError(f'{label} rəqəm olmalıdır.')
        basis = entry.get('basis')
        if basis not in ('assumption', 'evidence'):
            raise ValueError('Hər rəqəm üçün fərziyyə və ya mənbəli sübut seçin.')
        evidence_id = entry.get('evidence_id', '') if basis == 'evidence' else ''
        if not isinstance(evidence_id, str):
            raise ValueError('Sübut istinadı düzgün deyil.')
        if basis == 'evidence' and evidence_id not in evidence:
            raise ValueError(f'{label}: təsdiqlənmiş mənbəsi olan sübut seçin.')
        result[key] = dict(value=value, basis=basis, evidence_id=evidence_id,
                           note=bounded_text(entry.get('note'), label + ' əsaslandırması', 5, 500))
    if not result['capture_low']['value'] <= result['capture_base']['value'] <= result['capture_high']['value']:
        raise ValueError('Əldəetmə payları aşağı ≤ əsas ≤ yuxarı ardıcıllığında olmalıdır.')
    currency = data.get('currency')
    if currency not in ('AZN', 'USD', 'EUR'):
        raise ValueError('Valyuta AZN, USD və ya EUR olmalıdır.')
    return dict(inputs=result, currency=currency,
                horizon_months=count(data.get('horizon_months'), 'Əldəetmə müddəti', 1, 60))


def calculate(model, project):
    if model is None:
        return None
    values = {key: entry['value'] for key, entry in model['inputs'].items()}
    population = values['population']
    eligible = population * values['eligible_percent'] / 100
    serviceable = eligible * values['reachable_percent'] / 100
    annual = values['annual_spend']
    scenarios = [dict(name=name, capture_percent=values['capture_' + name],
                      customers=round(serviceable * values['capture_' + name] / 100, 2),
                      annual_potential=round(serviceable * values['capture_' + name] / 100 * annual, 2))
                 for name in ('low', 'base', 'high')]
    evidence = {e['id']: e for e in project['market_evidence']}
    approved = {s['id'] for s in project['sources'] if s.get('review', {}).get('status') == 'approved'}
    warnings, provenance = [], []
    for key, entry in model['inputs'].items():
        label = FIELDS[key][0]
        linked = evidence.get(entry['evidence_id'])
        valid = bool(linked and linked['source_id'] in approved)
        if entry['basis'] == 'assumption':
            status = 'assumption'
        elif not valid:
            status = 'unverified'
            warnings.append(label + ': istinadın mənbəsi artıq təsdiqlənmiş deyil və ya sübut çıxarılıb.')
        else:
            status = 'evidence'
            if linked['conflict_note']:
                warnings.append(label + ': əlaqəli sübutda ziddiyyət var.')
            if linked['stale'] or linked['date_unknown']:
                warnings.append(label + ': əlaqəli sübutun tarixi köhnədir və ya məlum deyil.')
            if linked['region'].strip().casefold() != project['research_brief']['region'].strip().casefold():
                warnings.append(label + ': sübutun regionunu araşdırma regionu ilə tutuşdurun.')
        provenance.append(dict(key=key, label=label, value=entry['value'], status=status,
                               evidence_id=entry['evidence_id'], note=entry['note']))
    return dict(currency=model['currency'], horizon_months=model['horizon_months'],
                tam_customers=population, tam_annual=round(population * annual, 2),
                eligible_customers=round(eligible, 2), sam_customers=round(serviceable, 2),
                sam_annual=round(serviceable * annual, 2), scenarios=scenarios,
                provenance=provenance, warnings=warnings,
                assumption_count=sum(p['status'] == 'assumption' for p in provenance),
                unverified_count=sum(p['status'] == 'unverified' for p in provenance))


def report_lines(model, project):
    if model is None:
        return ['## Bazar həcmi', '', 'Bazar həcmi hesablaması əlavə edilməyib.', '']
    result = calculate(model, project)
    currency = result['currency']
    lines = ['## Bazar həcmi — fərziyyələrə əsaslanan model', '',
             'TAM = regiondakı potensial müştəri sayı × bir müştərinin illik xərci.',
             'SAM = TAM × hədəf seqmentin payı × həmin seqmentdə xidmət göstərilə bilən pay.',
             'SOM = SAM × əldəetmə payı.', '',
             f"TAM: {result['tam_customers']:,.2f} müştəri; {result['tam_annual']:,.2f} {currency}/il.",
             f"SAM: {result['sam_customers']:,.2f} müştəri; {result['sam_annual']:,.2f} {currency}/il."]
    for row in result['scenarios']:
        lines.append(f"SOM ({row['name']}): {row['customers']:,.2f} müştəri; {row['annual_potential']:,.2f} {currency}/il.")
    lines += ['', f"Əldəetmə müddəti: {result['horizon_months']} ay. Məbləğ həmin miqyasa çatanda illik potensialdır; müddət ərzində yığılmış gəlir deyil.",
              'Bu ssenarilər satış proqnozu və statistik etibar intervalı deyil.', '', '### Rəqəmlərin əsası', '']
    for row in result['provenance']:
        label = {'assumption': 'Fərziyyə', 'evidence': 'Sübut istinadı — rəqəmin uyğunluğunu insan yoxlayır', 'unverified': 'İstinad etibarsızdır'}[row['status']]
        lines.append(f"- {row['label']}: {row['value']} — {label}. {row['note']}" +
                     (f" (Sübut: {row['evidence_id']})" if row['evidence_id'] else ''))
    lines += ['', *['- ' + warning for warning in result['warnings']], '']
    return lines
