"""Market parameters an LLM may extract but never invent.

Two independent guarantees stack here. The provider asks for constrained
decoding against `parameter_schema()`, so the evidence fields cannot be
omitted. This module then checks the evidence itself: the quote must appear
verbatim in the cited source, and for a `direct` reading the number must
actually occur inside that quote. A quote that does not contain the figure
does not support the figure.
"""
import json
import math
import re


# key -> (label, plausible range after normalisation, unit hint)
PARAMETERS = {
    'market_size': ('Ümumi bazar həcmi', (1.0, 1e13), 'USD və ya istifadəçi'),
    'arpu': ('İstifadəçi başına aylıq gəlir', (0.01, 100_000.0), 'USD/ay'),
    'cac': ('Müştəri cəlbetmə xərci', (0.01, 1_000_000.0), 'USD'),
    'churn_monthly': ('Aylıq itki nisbəti', (0.0001, 0.9), 'hissə (0–1)'),
    'cpm': ('Min göstərişə reklam qiyməti', (0.01, 10_000.0), 'USD/1000'),
    'sales_cycle_days': ('Satış dövrünün uzunluğu', (1.0, 1095.0), 'gün'),
}
CONFIDENCE = ('direct', 'derived', 'proxy')
GREEN, YELLOW = 'verified', 'derived'

MULTIPLIERS = {'k': 1e3, 'min': 1e3, 'minlik': 1e3, 'thousand': 1e3, 'thousands': 1e3,
               'm': 1e6, 'mln': 1e6, 'milyon': 1e6, 'million': 1e6, 'millions': 1e6,
               'bn': 1e9, 'milyard': 1e9, 'billion': 1e9, 'billions': 1e9,
               'trilyon': 1e12, 'trillion': 1e12}
PERCENT = {'%', 'percent', 'faiz'}
NUMBER = re.compile(r'(\d[\d\s .,]*\d|\d)\s*(%|[^\W\d_]{1,9})?', re.UNICODE)


def parameter_schema():
    """Strict-mode JSON schema: every field required, no extra properties."""
    return {
        'type': 'object', 'additionalProperties': False, 'required': ['parameters'],
        'properties': {'parameters': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['key', 'value', 'unit', 'source_id', 'quote', 'confidence', 'derivation'],
            'properties': {
                'key': {'type': 'string', 'enum': list(PARAMETERS)},
                'value': {'type': 'number'},
                'unit': {'type': 'string'},
                'source_id': {'type': 'string'},
                'quote': {'type': 'string'},
                'confidence': {'type': 'string', 'enum': list(CONFIDENCE)},
                'derivation': {'type': 'string'},
            }}}},
    }


def _float(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _readings(token):
    """Every defensible reading of one numeric token, separators being ambiguous."""
    compact = re.sub(r'[\s ]', '', token)
    if not re.fullmatch(r'\d[\d.,]*\d|\d', compact):
        return set()
    found = set()
    if ',' in compact and '.' in compact:
        if compact.rfind(',') > compact.rfind('.'):
            found.add(_float(compact.replace('.', '').replace(',', '.')))
        else:
            found.add(_float(compact.replace(',', '')))
    elif ',' in compact:
        found.add(_float(compact.replace(',', '.')))
        if re.fullmatch(r'\d{1,3}(,\d{3})+', compact):
            found.add(_float(compact.replace(',', '')))
    elif '.' in compact:
        found.add(_float(compact))
        if re.fullmatch(r'\d{1,3}(\.\d{3})+', compact):
            found.add(_float(compact.replace('.', '')))
    else:
        found.add(_float(compact))
    return {value for value in found if value is not None}


def quote_values(quote):
    """All numbers a reader could take from the quote, scale words included."""
    values = set()
    for token, suffix in NUMBER.findall(str(quote)):
        readings = _readings(token)
        values |= readings
        word = (suffix or '').casefold()
        if word in MULTIPLIERS:
            values |= {value * MULTIPLIERS[word] for value in readings}
        if word in PERCENT:
            values |= {value / 100 for value in readings}
    return values


def supports(value, quote, tolerance=0.005):
    """True when the quote states the figure, allowing for source rounding."""
    number = _float(value)
    if number is None:
        return False
    margin = max(abs(number) * tolerance, 1e-9)
    return any(abs(candidate - number) <= margin for candidate in quote_values(quote))


def normalise(key, value, unit):
    """Bring a stated figure onto the unit this simulator runs in."""
    unit = str(unit).casefold()
    if key == 'churn_monthly' and ('%' in unit or 'percent' in unit or 'faiz' in unit):
        return value / 100
    if key == 'sales_cycle_days':
        if 'month' in unit or 'ay' == unit.strip() or 'ay/' in unit:
            return value * 30
        if 'week' in unit or 'həftə' in unit:
            return value * 7
    return value


def _quoted_in(quote, body):
    return ' '.join(str(quote).split()).casefold() in ' '.join(str(body).split()).casefold()


def verify_parameters(raw, sources):
    """Split a model response into evidence that holds up and evidence that does not.

    Nothing is silently dropped: every rejection carries its reason, and the
    keys no source could supply are reported so the owner can enter them by
    hand and see them marked as unevidenced.
    """
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise ValueError('Cavab düzgün JSON deyil.') from None
    if not isinstance(result, dict) or not isinstance(result.get('parameters'), list):
        raise ValueError('Cavabda parameters siyahısı yoxdur.')
    entries = result['parameters']
    if not 1 <= len(entries) <= 24:
        raise ValueError('1–24 parametr gözlənilir.')

    by_id = {s['id']: s for s in sources}
    verified, rejected, taken = [], [], set()
    for entry in entries:
        reason = _reject(entry, by_id, taken)
        if reason:
            rejected.append(dict(entry=entry if isinstance(entry, dict) else {}, reason=reason))
            continue
        key, unit = entry['key'], entry['unit'].strip()
        stated = float(entry['value'])
        value = normalise(key, stated, unit)
        low, high = PARAMETERS[key][1]
        if not low <= value <= high:
            rejected.append(dict(entry=entry, reason=f'{key} üçün {value} məqbul aralıqdan ({low}–{high}) kənardır.'))
            continue
        taken.add(key)
        verified.append(dict(key=key, value=value, stated=stated, unit=unit,
                             source_id=entry['source_id'], quote=entry['quote'].strip(),
                             confidence=entry['confidence'], derivation=entry['derivation'].strip(),
                             grade=GREEN if entry['confidence'] == 'direct' else YELLOW))
    return dict(verified=verified, rejected=rejected,
                missing=[key for key in PARAMETERS if key not in taken],
                coverage=round(len(taken) / len(PARAMETERS), 3))


def _reject(entry, by_id, taken):
    """The reason this entry cannot be trusted, or '' when it can."""
    if not isinstance(entry, dict):
        return 'Parametr formatı uyğun deyil.'
    fields = ('key', 'value', 'unit', 'source_id', 'quote', 'confidence', 'derivation')
    if any(field not in entry for field in fields):
        return 'Məcburi sahələrdən biri yoxdur.'
    if entry['key'] not in PARAMETERS:
        return 'Naməlum parametr açarı.'
    if entry['key'] in taken:
        return 'Bu parametr artıq təsdiqlənib; təkrar qeyd nəzərə alınmadı.'
    if entry['confidence'] not in CONFIDENCE:
        return 'Etibarlılıq səviyyəsi uyğun deyil.'
    if isinstance(entry['value'], bool) or _float(entry['value']) is None:
        return 'Dəyər ədəd deyil.'
    for field in ('unit', 'source_id', 'quote', 'derivation'):
        if not isinstance(entry[field], str):
            return f'{field} mətn olmalıdır.'
    if not 1 <= len(entry['unit'].strip()) <= 40:
        return 'Ölçü vahidi göstərilməyib.'
    if not 12 <= len(entry['quote'].strip()) <= 1000:
        return 'Sitat 12–1000 simvol arasında olmalıdır.'
    source = by_id.get(entry['source_id'])
    if not source:
        return 'Naməlum mənbə istinadı.'
    if not _quoted_in(entry['quote'], source['body']):
        return 'Sitat göstərilən mənbədə tapılmadı.'
    if entry['confidence'] == 'direct' and not supports(entry['value'], entry['quote']):
        return 'Sitatda bu rəqəm yoxdur; birbaşa oxunuş kimi qəbul edilmir.'
    if entry['confidence'] == 'derived' and not 10 <= len(entry['derivation'].strip()) <= 600:
        return 'Törəmə dəyər üçün hesablama izahı tələb olunur.'
    return ''
